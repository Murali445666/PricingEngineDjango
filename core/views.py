"""
Step 14: Functional Simulation Workflow UI.

ContractVersionWorkflowView: version detail page with simulation form and lifecycle buttons.
Uses existing APIs and ClaimPricingService; no pricing engine changes.
"""
import json
from datetime import date
from decimal import Decimal

from django.shortcuts import render, get_object_or_404
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required

from core.models import ProviderContract, ContractVersion
from core.engine.service import ClaimPricingService
from core.engine.config import ClaimPricingInput, ClaimLineInput
from core.engine.loader import resolve_active_contract_version, resolve_contract_version


def pricing_sandbox(request):
    """Simple internal test UI: input code and contract ID, see JSON pricing response."""
    return render(request, "pricing_sandbox.html")


SAMPLE_CLAIM_JSON = """{
  "lines": [
    {"procedure_code": "99213", "billed_amount": "500.00", "units": 1, "modifiers": []}
  ],
  "service_date": "2025-06-01"
}"""


def _build_claim_input(contract, claim_data, contract_id):
    """Build ClaimPricingInput from parsed claim dict. Raises ValueError on invalid data."""
    lines_data = claim_data.get("lines") or []
    if not lines_data:
        raise ValueError("Claim must have at least one line.")
    lines = []
    for line in lines_data:
        line = dict(line)
        pc = line.get("procedure_code") or ""
        billed = line.get("billed_amount")
        if billed is None:
            raise ValueError("Each line must have procedure_code and billed_amount.")
        try:
            billed = Decimal(str(billed))
        except Exception:
            raise ValueError("billed_amount must be numeric.")
        units = int(line.get("units") or 1)
        modifiers = list(line.get("modifiers") or [])
        cost = line.get("cost_amount")
        if cost is not None:
            cost = Decimal(str(cost))
        lines.append(
            ClaimLineInput(
                procedure_code=pc.strip(),
                billed_amount=billed,
                units=units,
                modifiers=modifiers,
                cost_amount=cost,
            )
        )
    svc_date = claim_data.get("service_date")
    if svc_date:
        if isinstance(svc_date, str):
            svc_date = date.fromisoformat(svc_date)
    else:
        svc_date = date.today()
    pricing_date = claim_data.get("pricing_date") or svc_date
    if isinstance(pricing_date, str):
        pricing_date = date.fromisoformat(pricing_date)
    return ClaimPricingInput(
        contract_id=contract_id,
        contract=contract,
        service_date=svc_date,
        pricing_date=pricing_date,
        lines=lines,
    )


@method_decorator(staff_member_required, name="dispatch")
class ContractVersionWorkflowView(View):
    """
    Step 14: GET /contracts/<contract_id>/versions/<version_id>/ui/
    Version detail page: structured version info, simulation form, lifecycle buttons.
    POST (same URL): run simulation (and optionally compare to ACTIVE).
    """

    def get(self, request, contract_id: int, version_id: int):
        contract = get_object_or_404(ProviderContract, pk=contract_id)
        try:
            version = resolve_contract_version(contract_id, version_id)
        except ValueError:
            return render(request, "contract_version_workflow.html", {"error": "Version not found or does not belong to this contract."}, status=404)

        if version.status == ContractVersion.VersionStatus.ARCHIVED:
            return render(request, "contract_version_workflow.html", {"error": "Cannot run simulation on an ARCHIVED version."}, status=400)

        context = self._base_context(contract, version, request)
        context["simulation_result"] = None
        context["active_result"] = None
        context["simulation_error"] = None
        context["claim_json"] = SAMPLE_CLAIM_JSON
        context["compare_checked"] = False
        msg = request.GET.get("msg")
        if msg == "activated":
            context["messages"].append("Version activated successfully.")
        elif msg == "archived":
            context["messages"].append("Version archived successfully.")
        return render(request, "contract_version_workflow.html", context)

    def post(self, request, contract_id: int, version_id: int):
        contract = get_object_or_404(ProviderContract, pk=contract_id)
        try:
            version = resolve_contract_version(contract_id, version_id)
        except ValueError:
            return render(request, "contract_version_workflow.html", {"error": "Version not found or does not belong to this contract."}, status=404)
        if version.status == ContractVersion.VersionStatus.ARCHIVED:
            return render(request, "contract_version_workflow.html", {"error": "Cannot run simulation on an ARCHIVED version."}, status=400)

        context = self._base_context(contract, version, request)
        claim_json_str = (request.POST.get("claim_json") or "").strip()
        # Strip one level of surrounding single/double quotes (e.g. form sends '{"claim":...}')
        if len(claim_json_str) >= 2 and (
            (claim_json_str[0] == "'" and claim_json_str[-1] == "'")
            or (claim_json_str[0] == '"' and claim_json_str[-1] == '"')
        ):
            claim_json_str = claim_json_str[1:-1]
        compare_checked = request.POST.get("compare_to_active") == "on"
        context["claim_json"] = claim_json_str or SAMPLE_CLAIM_JSON
        context["compare_checked"] = compare_checked

        if not claim_json_str:
            context["simulation_error"] = "Please provide claim JSON."
            context["simulation_result"] = None
            context["active_result"] = None
            return render(request, "contract_version_workflow.html", context)

        try:
            parsed = json.loads(claim_json_str)
        except json.JSONDecodeError as e:
            context["simulation_error"] = f"Invalid JSON: {e}"
            context["simulation_result"] = None
            context["active_result"] = None
            return render(request, "contract_version_workflow.html", context)

        # Accept either full API shape { contract_id, version_id, claim } or just { lines, service_date }
        if isinstance(parsed, dict) and "claim" in parsed and isinstance(parsed.get("claim"), dict):
            claim_data = parsed["claim"]
        else:
            claim_data = parsed if isinstance(parsed, dict) else {}

        try:
            claim_input = _build_claim_input(contract, claim_data, contract_id)
        except ValueError as e:
            context["simulation_error"] = str(e)
            context["simulation_result"] = None
            context["active_result"] = None
            return render(request, "contract_version_workflow.html", context)

        service = ClaimPricingService()
        try:
            sim_result = service.price_claim_with_version(contract_id, version_id, claim_input)
        except ValueError as e:
            context["simulation_error"] = str(e)
            context["simulation_result"] = None
            context["active_result"] = None
            return render(request, "contract_version_workflow.html", context)
        except Exception as e:
            context["simulation_error"] = f"Simulation failed: {e!s}"
            context["simulation_result"] = None
            context["active_result"] = None
            return render(request, "contract_version_workflow.html", context)

        total_billed = sum(line.billed_amount * line.units for line in claim_input.lines)
        context["simulation_result"] = sim_result
        context["simulation_total_billed"] = total_billed
        context["simulation_lines"] = [
            {"procedure_code": inp.procedure_code, "result": res}
            for inp, res in zip(claim_input.lines, sim_result.lines)
        ]
        context["active_result"] = None
        context["active_version_id"] = None
        context["simulation_error"] = None

        if compare_checked and context.get("can_compare"):
            active_version = resolve_active_contract_version(contract, claim_input.service_date)
            if active_version and active_version.pk != version.pk:
                claim_input_active = ClaimPricingInput(
                    contract_id=contract_id,
                    contract=contract,
                    service_date=claim_input.service_date,
                    pricing_date=claim_input.pricing_date,
                    lines=claim_input.lines,
                )
                active_result = service.price_claim(claim_input_active)
                context["active_result"] = active_result
                context["active_version_id"] = active_version.version_id
                context["diff_allowed"] = sim_result.total_allowed - active_result.total_allowed

        return render(request, "contract_version_workflow.html", context)

    def _base_context(self, contract, version, request):
        """Build context with contract, version, counts, and lifecycle flags."""
        count_methodologies = contract.methodologies.count() if hasattr(contract, "methodologies") else 0
        count_carveouts = contract.carveouts.count() if hasattr(contract, "carveouts") else 0
        count_cap_floors = contract.cap_floors.count() if hasattr(contract, "cap_floors") else 0
        count_blending = contract.blending_rules.count() if hasattr(contract, "blending_rules") else 0

        show_activate = version.status == ContractVersion.VersionStatus.DRAFT
        show_archive = version.status in (
            ContractVersion.VersionStatus.DRAFT,
            ContractVersion.VersionStatus.SUPERSEDED,
        )

        service_date = version.effective_start_date or date.today()
        active_version = resolve_active_contract_version(contract, service_date)
        can_compare = active_version is not None and active_version.pk != version.pk

        return {
            "contract": contract,
            "version": version,
            "version_status": version.status,
            "effective_start": version.effective_start_date,
            "effective_end": version.effective_end_date,
            "count_methodologies": count_methodologies,
            "count_carveouts": count_carveouts,
            "count_cap_floors": count_cap_floors,
            "count_blending_rules": count_blending,
            "show_activate": show_activate,
            "show_archive": show_archive,
            "can_compare": can_compare,
            "active_version_id": getattr(active_version, "version_id", None),
            "messages": [],  # success messages from query string
        }
