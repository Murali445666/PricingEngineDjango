"""
Phase E: Claim-level methodology plugins (DRG, case rate).

Run after line pricing, before stop-loss/outlier. Each plugin receives ExecutionContext
and optional ContractPricingConfig; may mutate context.claim_total, context.drg_applied, etc.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ExecutionContext
    from .config import ContractPricingConfig


class BaseClaimPlugin:
    """Base for claim-level methodology plugins. run() mutates context."""

    def run(
        self,
        context: "ExecutionContext",
        config: Optional["ContractPricingConfig"] = None,
    ) -> None:
        raise NotImplementedError


class DRGClaimPlugin(BaseClaimPlugin):
    """
    Phase E: Claim-level DRG. One payment per claim = FacilityBaseRate × RefDrg.relative_weight.
    DRG code from context.drg_code or first line procedure_code. Sets context.claim_total and context.drg_applied.
    """

    def run(
        self,
        context: "ExecutionContext",
        config: Optional["ContractPricingConfig"] = None,
    ) -> None:
        from django.db.models import Q
        from core.models import FacilityBaseRate, RefDrg

        drg_code = getattr(context, "drg_code", None) or ""
        drg_code = (drg_code or "").strip()
        if not drg_code and context.line_states:
            first_input = context.line_states[0].input
            drg_code = (getattr(first_input, "procedure_code", None) or "").strip()
        if not drg_code:
            print("[CLAIM_DRG] skip: no drg_code on context or first line")
            return
        service_date = context.service_date
        if not service_date:
            print("[CLAIM_DRG] skip: no service_date on context")
            return
        year = service_date.year
        facility_id = getattr(context, "facility_id", None)

        # Resolve FacilityBaseRate: contract, version, facility_id (or null), rate_type=DRG, effective for service_date
        contract = context.contract
        version = context.version
        if not contract or not version:
            print(f"[CLAIM_DRG] skip: contract={contract!r} version={version!r}")
            return
        qs = FacilityBaseRate.objects.filter(
            contract=contract,
            version=version,
            rate_type="DRG",
            effective_start_date__lte=service_date,
        ).filter(
            Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
        )
        # Prefer facility-specific rate, then facility_id null
        base_row = qs.filter(facility_id=facility_id).first()
        if base_row is None and facility_id is not None:
            base_row = qs.filter(facility_id__isnull=True).first()
        if base_row is None:
            base_row = qs.filter(facility_id__isnull=True).first()
        if base_row is None:
            print(
                f"[CLAIM_DRG] skip: no FacilityBaseRate for contract_id={getattr(contract, 'pk', None)} "
                f"version_id={getattr(version, 'version_id', getattr(version, 'pk', None))} rate_type=DRG service_date={service_date}"
            )
            return
        base_rate = base_row.base_rate

        # RefDrg by drg_code and year
        try:
            ref_drg = RefDrg.objects.get(drg_code=drg_code, year=year)
            weight = ref_drg.relative_weight
        except RefDrg.DoesNotExist:
            print(f"[CLAIM_DRG] skip: RefDrg.DoesNotExist for drg_code={drg_code!r} year={year}")
            return
        payment = base_rate * weight
        context.claim_total = payment
        context.claim_level_payment = payment
        context.drg_applied = True
        context.drg_code = drg_code
        print(f"[CLAIM_DRG] applied: drg_code={drg_code} base_rate={base_rate} weight={weight} claim_total={payment}")


class CaseRateClaimPlugin(BaseClaimPlugin):
    """
    Phase E: Claim-level case rate (lump sum per case_rate_code). Opt-in per version/config.
    When case_rate_code is present on claim and a CaseRateDefinition matches, sets context.claim_total to lump_sum_amount.
    """

    def run(
        self,
        context: "ExecutionContext",
        config: Optional["ContractPricingConfig"] = None,
    ) -> None:
        # Optional: read case_rate_code from claim input when added; lookup CaseRateDefinition; set context.claim_total.
        # Stub: no-op until claim payload and config expose case_rate_code.
        pass


# Registry: enabled by version/config (e.g. claim_level_drg_enabled → run DRG).
CLAIM_METHODOLOGY_REGISTRY = {
    "DRG": DRGClaimPlugin(),
    "CASE_RATE": CaseRateClaimPlugin(),
}
