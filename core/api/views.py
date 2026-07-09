import csv
import io
import time
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from core.models import (
    ProviderContract,
    PricingRule,
    RuleHistory,
    FeeSchedule,
    RefProcedureCode,
    RefModifier,
    RefCptHcpcsCode,
    RefMpfsRvu,
    RefDrg,
    RefApc,
    RefIcd10Cm,
    RefIcd10Pcs,
    RefAspPricing,
    RefRevenueCode,
    RefSpecialty,
    ContractMethodology,
    ContractOutlierRule,
    ContractStopLossRule,
    ClaimHeader,
    ClaimResolutionLog,
    ValidationResult,
    ContractVersion,
    ContractVersionAudit,
)
from core.engine.service import ClaimPricingService
from core.engine.types import PricingInput, PricingStatus, ClaimPricingResult
from core.engine.config import ClaimPricingInput, ClaimLineInput
from core.engine.simulation import run_line_simulation
from core.services.rule_conflict import get_conflicts_for_rule, get_conflicts_for_rule_payload
from core.api.serializers import (
    ContractSerializer,
    ContractDetailSerializer,
    PricingRequestSerializer,
    PricingResponseSerializer,
    PricingClaimRequest,
    PriceClaimSimulateRequest,
    RuleListSerializer,
    RuleDetailSerializer,
    RuleHistorySerializer,
    RuleCreateSerializer,
    RuleUpdateSerializer,
    FeeScheduleSerializer,
    ProcedureCodeSerializer,
    ModifierSerializer,
    RefCptHcpcsCodeSerializer,
    RefMpfsRvuSerializer,
    RefDrgSerializer,
    RefApcSerializer,
    RefIcd10CmSerializer,
    RefIcd10PcsSerializer,
    RefAspPricingSerializer,
    RefRevenueCodeSerializer,
    RefSpecialtySerializer,
    ContractMethodologySerializer,
    ContractMethodologyCreateSerializer,
    ContractOutlierRuleSerializer,
    ContractOutlierRuleCreateSerializer,
    ContractStopLossRuleSerializer,
    ContractStopLossRuleCreateSerializer,
    ClaimHeaderSerializer,
    ClaimCreateSerializer,
    ClaimPricingResultSerializer,
    BulkPricingClaimRequest,
    BulkPricingResultSerializer,
    ValidationResultSerializer,
    ContractVersionSerializer,
    ContractVersionAuditSerializer,
    VersionLifecycleResponseSerializer,
    ContractExplorerSerializer,
)

def _get_contract(contract_id_value):
    """Resolve contract by legacy_contract_number or PK (integer)."""
    try:
        if isinstance(contract_id_value, int) or (isinstance(contract_id_value, str) and contract_id_value.isdigit()):
            return ProviderContract.objects.get(pk=int(contract_id_value))
        return ProviderContract.objects.get(legacy_contract_number=contract_id_value)
    except ProviderContract.DoesNotExist:
        return None


def _optional_str_field(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


class ContractListView(APIView):
    def get(self, request):
        contracts = ProviderContract.objects.filter(
            status='ACTIVE'
        ).prefetch_related('validation_results')
        serializer = ContractSerializer(contracts, many=True)
        return Response(serializer.data)


class RuleListView(APIView):
    def get(self, request):
        qs = PricingRule.objects.all().select_related('contract')
        contract_id = request.query_params.get('contract_id')
        if contract_id is not None:
            qs = qs.filter(contract_id=int(contract_id))
        status_param = request.query_params.get('status')
        if status_param and status_param.upper() in ('DRAFT', 'ACTIVE', 'RETIRED'):
            qs = qs.filter(status=status_param.upper())
        serializer = RuleListSerializer(qs, many=True)
        return Response(serializer.data)


class ContractDetailView(APIView):
    def get(self, request, pk):
        contract = get_object_or_404(
            ProviderContract.objects.select_related('provider_org', 'provider_org__primary_specialty').prefetch_related('methodologies', 'outlier_rules', 'stop_loss_rules'),
            pk=pk,
        )
        serializer = ContractDetailSerializer(contract)
        return Response(serializer.data)


class ContractSummaryView(APIView):
    """GET /api/contracts/<pk>/summary/ — read-only layered contract summary (§15)."""

    def get(self, request, pk):
        from django.core.exceptions import ObjectDoesNotExist

        from core.services.contract_summary import ContractSummaryService

        try:
            payload = ContractSummaryService.build(pk)
        except ObjectDoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)


class ContractMethodologyListCreateView(APIView):
    """GET/POST /api/contracts/<id>/methodologies/ — Phase 2B."""

    def get(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        qs = ContractMethodology.objects.filter(contract=contract).order_by('-effective_date')
        serializer = ContractMethodologySerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        serializer = ContractMethodologyCreateSerializer(
            data=request.data,
            context={'contract': contract},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        return Response(
            ContractMethodologySerializer(obj).data,
            status=status.HTTP_201_CREATED,
        )


class ContractRuleListView(APIView):
    def get(self, request, pk):
        get_object_or_404(ProviderContract, pk=pk)
        qs = PricingRule.objects.filter(contract_id=pk).prefetch_related('conditions')
        serializer = RuleListSerializer(qs, many=True)
        return Response(serializer.data)


class ContractSnapshotView(APIView):
    """Phase 5C: GET /api/contracts/<id>/snapshot/ — materialized contract runtime config (cached)."""

    def get(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        from core.services.contract_snapshot import get_or_build_snapshot
        snapshot = get_or_build_snapshot(contract)
        return Response(snapshot)


class ContractOutlierRuleListCreateView(APIView):
    """Phase 6: GET/POST /api/contracts/<id>/outlier-rules/ — list and create outlier/stop-loss rules."""

    def get(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        qs = ContractOutlierRule.objects.filter(contract=contract).order_by('-priority', 'effective_start_date')
        serializer = ContractOutlierRuleSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        serializer = ContractOutlierRuleCreateSerializer(
            data=request.data,
            context={'contract': contract},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        return Response(
            ContractOutlierRuleSerializer(obj).data,
            status=status.HTTP_201_CREATED,
        )


class ContractStopLossRuleListCreateView(APIView):
    """Phase 7: GET/POST /api/contracts/<id>/stop-loss-rules/."""

    def get(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        qs = ContractStopLossRule.objects.filter(contract=contract).order_by('-priority', 'effective_start_date')
        serializer = ContractStopLossRuleSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        contract = get_object_or_404(ProviderContract, pk=pk)
        serializer = ContractStopLossRuleCreateSerializer(
            data=request.data,
            context={'contract': contract},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        return Response(
            ContractStopLossRuleSerializer(obj).data,
            status=status.HTTP_201_CREATED,
        )


class RuleDetailView(APIView):
    def get(self, request, pk):
        rule = get_object_or_404(
            PricingRule.objects.prefetch_related('conditions'),
            pk=pk,
        )
        serializer = RuleDetailSerializer(rule)
        return Response(serializer.data)

    def patch(self, request, pk):
        """Partial update; send 'conditions' to full-replace conditions."""
        rule = get_object_or_404(PricingRule.objects.prefetch_related('conditions'), pk=pk)
        serializer = RuleUpdateSerializer(rule, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        response_serializer = RuleDetailSerializer(
            PricingRule.objects.prefetch_related('conditions').get(pk=rule.pk)
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class RuleHistoryView(APIView):
    def get(self, request, rule_id):
        get_object_or_404(PricingRule, pk=rule_id)
        qs = RuleHistory.objects.filter(pricing_rule_id=rule_id).order_by('-change_date')
        serializer = RuleHistorySerializer(qs, many=True)
        return Response(serializer.data)


class RuleConflictsView(APIView):
    """GET /api/rules/<pk>/conflicts/ — conflicts for an existing rule (advisory)."""

    def get(self, request, pk):
        rule = get_object_or_404(PricingRule.objects.prefetch_related('conditions'), pk=pk)
        conflicts = get_conflicts_for_rule(rule)
        return Response({"conflicts": conflicts}, status=status.HTTP_200_OK)


class RuleCheckConflictsView(APIView):
    """POST /api/rules/check-conflicts/ — body: contract_id, conditions; optional exclude_rule_id (advisory)."""

    def post(self, request):
        contract_id = request.data.get('contract_id')
        conditions = request.data.get('conditions') or []
        if contract_id is None:
            return Response(
                {"error": "contract_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            contract = ProviderContract.objects.get(pk=int(contract_id))
        except (ValueError, ProviderContract.DoesNotExist):
            return Response(
                {"error": f"Contract {contract_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        raw_exclude = request.data.get('exclude_rule_id')
        exclude_rule_id = None
        if raw_exclude is not None and raw_exclude != '':
            try:
                exclude_rule_id = int(raw_exclude)
            except (TypeError, ValueError):
                exclude_rule_id = None
        conflicts = get_conflicts_for_rule_payload(
            contract.pk, conditions, exclude_rule_id=exclude_rule_id
        )
        return Response({"conflicts": conflicts}, status=status.HTTP_200_OK)


class FeeScheduleListView(APIView):
    """GET /api/fee-schedules/ — list fee schedules for dropdowns."""

    def get(self, request):
        qs = FeeSchedule.objects.all().select_related('geo').order_by('name')
        serializer = FeeScheduleSerializer(qs, many=True)
        return Response(serializer.data)


class CptHcpcsCodeListView(APIView):
    """GET /api/cpt-hcpcs-codes/ — list CPT/HCPCS codes (Phase 1)."""

    def get(self, request):
        qs = RefCptHcpcsCode.objects.all().order_by('code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(code__icontains=q) | Q(description__icontains=q)
            )
        code_type = request.query_params.get('code_type', '').strip()
        if code_type:
            qs = qs.filter(code_type=code_type)
        year = request.query_params.get('year')
        if year is not None:
            try:
                qs = qs.filter(effective_year=int(year))
            except ValueError:
                pass
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefCptHcpcsCodeSerializer(qs, many=True)
        return Response(serializer.data)


class MpfsRvuListView(APIView):
    """GET /api/mpfs-rvu/ — list MPFS RVUs by code/year (Phase 1)."""

    def get(self, request):
        qs = RefMpfsRvu.objects.all().order_by('code', 'year')
        code = request.query_params.get('code', '').strip()
        if code:
            qs = qs.filter(code=code)
        year = request.query_params.get('year')
        if year is not None:
            try:
                qs = qs.filter(year=int(year))
            except ValueError:
                pass
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefMpfsRvuSerializer(qs, many=True)
        return Response(serializer.data)


class DrgListView(APIView):
    """GET /api/drg/ — list DRG reference (Phase 2). Read-only."""

    def get(self, request):
        qs = RefDrg.objects.all().order_by('drg_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(drg_code__icontains=q) | Q(description__icontains=q)
            )
        year = request.query_params.get('year')
        if year is not None:
            try:
                qs = qs.filter(year=int(year))
            except ValueError:
                pass
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefDrgSerializer(qs, many=True)
        return Response(serializer.data)


class ApcListView(APIView):
    """GET /api/apc/ — list APC reference (Phase 2). Read-only."""

    def get(self, request):
        qs = RefApc.objects.all().order_by('apc_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(apc_code__icontains=q) | Q(description__icontains=q)
            )
        year = request.query_params.get('year')
        if year is not None:
            try:
                qs = qs.filter(year=int(year))
            except ValueError:
                pass
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefApcSerializer(qs, many=True)
        return Response(serializer.data)


class Icd10CmListView(APIView):
    """GET /api/icd10-cm/ — list ICD-10-CM diagnosis codes (Phase 3)."""

    def get(self, request):
        from django.db.models import Q
        qs = RefIcd10Cm.objects.all().order_by('diagnosis_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            qs = qs.filter(
                Q(diagnosis_code__icontains=q) | Q(description__icontains=q)
            )
        year = request.query_params.get('effective_year')
        if year is not None:
            try:
                qs = qs.filter(effective_year=int(year))
            except ValueError:
                pass
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefIcd10CmSerializer(qs, many=True)
        return Response(serializer.data)


class Icd10PcsListView(APIView):
    """GET /api/icd10-pcs/ — list ICD-10-PCS procedure codes (Phase 3)."""

    def get(self, request):
        from django.db.models import Q
        qs = RefIcd10Pcs.objects.all().order_by('procedure_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            qs = qs.filter(
                Q(procedure_code__icontains=q) | Q(description__icontains=q)
            )
        year = request.query_params.get('year')
        if year is not None:
            try:
                qs = qs.filter(year=int(year))
            except ValueError:
                pass
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefIcd10PcsSerializer(qs, many=True)
        return Response(serializer.data)


class AspPricingListView(APIView):
    """GET /api/asp-pricing/ — list ASP pricing (Phase 3)."""

    def get(self, request):
        qs = RefAspPricing.objects.all().order_by('hcpcs_code', 'quarter')
        hcpcs = request.query_params.get('hcpcs_code', '').strip()
        if hcpcs:
            qs = qs.filter(hcpcs_code=hcpcs)
        quarter = request.query_params.get('quarter', '').strip()
        if quarter:
            qs = qs.filter(quarter=quarter)
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefAspPricingSerializer(qs, many=True)
        return Response(serializer.data)


class RevenueCodeListView(APIView):
    """GET /api/revenue-codes/ — list revenue codes (Phase 4)."""

    def get(self, request):
        from django.db.models import Q
        qs = RefRevenueCode.objects.all().order_by('revenue_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            qs = qs.filter(
                Q(revenue_code__icontains=q) | Q(description__icontains=q)
            )
        category = request.query_params.get('category', '').strip()
        if category:
            qs = qs.filter(category=category)
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefRevenueCodeSerializer(qs, many=True)
        return Response(serializer.data)


class SpecialtyListView(APIView):
    """GET /api/specialties/ — list provider specialties (Phase 4)."""

    def get(self, request):
        from django.db.models import Q
        qs = RefSpecialty.objects.all().order_by('specialty_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            qs = qs.filter(
                Q(specialty_code__icontains=q) | Q(description__icontains=q)
            )
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = RefSpecialtySerializer(qs, many=True)
        return Response(serializer.data)


class ProcedureCodeListView(APIView):
    """GET /api/procedure-codes/ — list procedure codes for search/autocomplete (optional ?q= or ?search=)."""

    def get(self, request):
        qs = RefProcedureCode.objects.all().order_by('code_id')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(code_id__icontains=q) | Q(description__icontains=q)
            )
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = ProcedureCodeSerializer(qs, many=True)
        return Response(serializer.data)


class ModifierListView(APIView):
    """GET /api/modifiers/ — list modifiers for search/autocomplete (optional ?q=)."""

    def get(self, request):
        qs = RefModifier.objects.all().order_by('modifier_code')
        q = request.query_params.get('q') or request.query_params.get('search', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(modifier_code__icontains=q) | Q(description__icontains=q)
            )
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = ModifierSerializer(qs, many=True)
        return Response(serializer.data)


class PriceLineView(APIView):
    def post(self, request):
        serializer = PricingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        contract = _get_contract(data['contract_id'])
        if not contract:
            return Response(
                {"error": f"Contract {data['contract_id']} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        service = ClaimPricingService()
        pricing_input = PricingInput(
            procedure_code=data['procedure_code'],
            billed_amount=data['billed_amount'],
            units=data['units'],
            modifiers=data.get('modifiers', []),
            service_date=data.get('service_date'),
            claim_type=data.get('claim_type') or None,
            pricing_date=data.get('pricing_date'),
            contract_effective_date=data.get('contract_effective_date'),
        )
        result = service.price_line(contract, pricing_input)
        response_data = PricingResponseSerializer(result).data
        response_data['trace_logs'] = getattr(result.trace, 'logs', [])
        return Response(response_data, status=status.HTTP_200_OK)


class SimulateLineView(APIView):
    """POST /api/simulate-line/ — single-line simulation, optional draft_rule."""

    def post(self, request):
        data = request.data
        contract_id = data.get('contract_id')
        if not contract_id:
            return Response(
                {"error": "contract_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        contract = _get_contract(contract_id)
        if not contract:
            return Response(
                {"error": f"Contract {contract_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        line = data.get('line') or data
        line_serializer = PricingRequestSerializer(data={
            'contract_id': contract_id,
            'procedure_code': line.get('procedure_code'),
            'billed_amount': line.get('billed_amount'),
            'units': line.get('units', 1),
            'modifiers': line.get('modifiers', []),
            'service_date': line.get('service_date'),
            'claim_type': line.get('claim_type'),
            'pricing_date': line.get('pricing_date'),
            'contract_effective_date': line.get('contract_effective_date'),
        })
        if not line_serializer.is_valid():
            return Response(line_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated = line_serializer.validated_data
        pricing_input = PricingInput(
            procedure_code=validated['procedure_code'],
            billed_amount=validated['billed_amount'],
            units=validated['units'],
            modifiers=validated.get('modifiers', []),
            service_date=validated.get('service_date'),
            claim_type=validated.get('claim_type') or None,
            pricing_date=validated.get('pricing_date'),
            contract_effective_date=validated.get('contract_effective_date'),
        )
        draft_rule = data.get('draft_rule')
        if isinstance(draft_rule, dict) and draft_rule.get('contract_id') in (None, ''):
            draft_rule = {**draft_rule, 'contract_id': contract.pk}
        result = run_line_simulation(contract, pricing_input, draft_rule=draft_rule)
        response_data = PricingResponseSerializer(result).data
        response_data['trace_logs'] = getattr(result.trace, 'logs', [])
        return Response(response_data, status=status.HTTP_200_OK)


class PriceClaimView(APIView):
    """Batch pricing: multiple claim lines in one request. Uses same ClaimPricingService path as stored-claim pricing."""

    def post(self, request):
        serializer = PricingClaimRequest(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        contract = _get_contract(data['contract_id'])
        if not contract:
            return Response(
                {"error": f"Contract {data['contract_id']} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        start = time.perf_counter()
        claim_service = data.get('service_date')
        claim_pricing = data.get('pricing_date')
        claim_contract_eff = data.get('contract_effective_date')
        lines = []
        for line in data['lines']:
            from decimal import Decimal
            cost = line.get('cost_amount')
            if cost is not None:
                cost = Decimal(str(cost))
            lines.append(ClaimLineInput(
                procedure_code=line['procedure_code'],
                billed_amount=line['billed_amount'],
                units=line.get('units', 1),
                modifiers=line.get('modifiers', []),
                cost_amount=cost,
                revenue_code=line.get('revenue_code'),
            ))
        from datetime import date
        claim_input = ClaimPricingInput(
            contract_id=contract.pk,
            contract=contract,
            service_date=claim_service or date.today(),
            claim_type=data.get('claim_type') or None,
            pricing_date=claim_pricing or claim_service,
            claim_id=None,
            lines=lines,
            drg_code=data.get('drg_code'),
            facility_id=data.get('facility_id'),
            provider_id=data.get('provider_id'),
            product_id=_optional_str_field(data.get('product_id')),
            network_id=_optional_str_field(data.get('network_id')),
        )
        service = ClaimPricingService()
        result = service.price_claim(claim_input)
        request_time_ms = (time.perf_counter() - start) * 1000
        response_data = ClaimPricingResultSerializer(result).data
        response_data['request_time_ms'] = round(request_time_ms, 2)
        return Response(response_data, status=status.HTTP_200_OK)


class PriceClaimSimulateView(APIView):
    """Step 13: POST /api/price-claim-simulate/ — price a claim against a specific contract version (DRAFT/ACTIVE/SUPERSEDED)."""

    def post(self, request):
        # Debug: raw request lines (revenue_code flow)
        _raw_lines = (request.data.get("claim") or {}).get("lines") or (request.data.get("claim_lines") or [])
        for i, L in enumerate(_raw_lines):
            print(f"[SIMULATE] parsed request line[{i}] revenue_code={L.get('revenue_code')!r} (keys={list(L.keys())})")

        serializer = PriceClaimSimulateRequest(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        contract_id = data['contract_id']
        version_id = data['version_id']
        claim_data = data['claim']

        from decimal import Decimal
        from datetime import date
        lines = []
        for idx, line in enumerate(claim_data['lines']):
            cost = line.get('cost_amount')
            if cost is not None:
                cost = Decimal(str(cost))
            rev = line.get('revenue_code')
            print(f"[SIMULATE] claim line DTO line[{idx}] revenue_code={rev!r} (from validated_data)")
            lines.append(ClaimLineInput(
                procedure_code=line['procedure_code'],
                billed_amount=line['billed_amount'],
                units=line.get('units', 1),
                modifiers=line.get('modifiers', []),
                cost_amount=cost,
                revenue_code=rev,
            ))
        claim_service = claim_data.get('service_date')
        claim_pricing = claim_data.get('pricing_date')
        claim_type = claim_data.get('claim_type') or None
        claim_input = ClaimPricingInput(
            contract_id=contract_id,
            contract=None,
            service_date=claim_service or date.today(),
            claim_type=claim_type,
            pricing_date=claim_pricing or claim_service,
            claim_id=None,
            lines=lines,
            drg_code=claim_data.get('drg_code'),
            facility_id=claim_data.get('facility_id'),
            provider_id=claim_data.get('provider_id'),
            product_id=_optional_str_field(claim_data.get('product_id')),
            network_id=_optional_str_field(claim_data.get('network_id')),
        )
        service = ClaimPricingService()
        try:
            result = service.price_claim_with_version(contract_id, version_id, claim_input)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"error": f"Simulation failed: {e!s}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        response_data = {
            "version_id": version_id,
            "simulation": True,
            "result": ClaimPricingResultSerializer(result).data,
            "validation": self._build_validation_block(data, contract_id, claim_data),
        }
        return Response(response_data, status=status.HTTP_200_OK)

    @staticmethod
    def _build_validation_block(data, contract_id, claim_data):
        from core.services.simulate_validation import build_simulate_validation

        return build_simulate_validation(
            selected_contract_id=contract_id,
            member_id=data.get('member_id'),
            billing_npi=data.get('billing_npi'),
            rendering_npi=data.get('rendering_npi'),
            claim_data=claim_data,
        )


class ClaimListCreateView(APIView):
    """Phase 5B: GET /api/claims/ — list claims (optional ?contract_id=). POST — create header + lines."""

    def get(self, request):
        qs = ClaimHeader.objects.all().select_related('contract').prefetch_related('lines').order_by('-service_date')
        contract_id = request.query_params.get('contract_id')
        if contract_id is not None:
            try:
                qs = qs.filter(contract_id=int(contract_id))
            except ValueError:
                pass
        serializer = ClaimHeaderSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ClaimCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        header = serializer.save()
        if header.member_id and header.member_fk_id is None:
            from members.models import Member
            try:
                member = Member.objects.get(member_id=header.member_id)
                header.member_fk = member
                header.save(update_fields=['member_fk'])
            except Member.DoesNotExist:
                pass
        response_serializer = ClaimHeaderSerializer(
            ClaimHeader.objects.prefetch_related('lines').get(pk=header.pk)
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ClaimDetailView(APIView):
    """GET /api/claims/<id>/ — single claim with lines."""

    def get(self, request, pk):
        claim = get_object_or_404(
            ClaimHeader.objects.select_related('contract').prefetch_related('lines'),
            pk=pk,
        )
        serializer = ClaimHeaderSerializer(claim)
        return Response(serializer.data)


class ClaimPriceView(APIView):
    """GET or POST /api/claims/<id>/price/ — context-resolved pricing (Path C)."""

    def get(self, request, pk):
        return self._price_claim(pk)

    def post(self, request, pk):
        return self._price_claim(pk)

    def _price_claim(self, pk):
        import logging

        from core.services.contract_resolution_service import (
            ContractResolutionService,
            RESOLUTION_PROCEEDS_TO_PRICING,
        )
        from core.services.pricing_context_resolver import PricingContextResolver
        from core.services.resolution_exception import (
            persist_resolution_exception,
            resolution_failure_payload,
        )

        logger = logging.getLogger(__name__)
        logger.warning(
            'ClaimPriceView uses PricingContextResolver (Path C); '
            'legacy resolve_contract_for_claim() in loader.py is deprecated and unused.'
        )

        claim = get_object_or_404(
            ClaimHeader.objects.select_related(
                'contract', 'provider_org', 'rendering_provider'
            ).prefetch_related('lines'),
            pk=pk,
        )

        raw = _build_raw_from_claim(claim)
        member_context = bool(raw.member_id)
        resolution = ContractResolutionService().resolve(raw, member_context=member_context)

        if resolution.status not in RESOLUTION_PROCEEDS_TO_PRICING:
            persist_resolution_exception(resolution)
            payload = resolution_failure_payload(resolution)
            return Response(payload, status=status.HTTP_200_OK)

        ctx = PricingContextResolver().context_from_resolution(raw, resolution)

        try:
            result, resolution_log = _price_with_resolved_context(
                ctx,
                claim_header=claim,
                resolution_path=ClaimResolutionLog.ResolutionPath.CONTEXT_RESOLVER,
                is_repricing=False,
            )
        except Exception as e:
            return Response(
                {'status': 'ENGINE_ERROR', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = ClaimPricingResultSerializer(result).data
        response_data['trace_id'] = ctx.trace_id
        response_data['resolution_log_id'] = resolution_log.id if resolution_log else None
        return Response(response_data, status=status.HTTP_200_OK)


class BulkPriceClaimsView(APIView):
    """
    POST /api/price-claims-bulk/ — Step 11 Milestone C: snapshot-backed bulk claim pricing.

    Accepts a list of claim payloads (each may target a different contract).
    Builds ContractPricingConfig once per unique (contract_id, version_id, service_date) and
    reuses it across all claims that share that key, eliminating repeated config DB queries.

    Request body:
        {
            "claims": [
                {"contract_id": 1, "lines": [...], "service_date": "2025-01-15"},
                {"contract_id": 1, "lines": [...], "service_date": "2025-01-15"},
                ...
            ]
        }

    Response:
        {
            "total_claims": 3,
            "priced_claims": 3,
            "results": [<ClaimPricingResult>, ...],
            "request_time_ms": 42.1
        }
    """

    def post(self, request):
        serializer = BulkPricingClaimRequest(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        start = time.perf_counter()

        # Resolve all unique contracts up front (batch-friendly; service handles the actual batching).
        from datetime import date
        claim_inputs = []
        for claim_data in data['claims']:
            contract = _get_contract(claim_data['contract_id'])
            if not contract:
                return Response(
                    {"error": f"Contract {claim_data['contract_id']} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            svc_date = claim_data.get('service_date') or date.today()
            lines = []
            for line in claim_data['lines']:
                from decimal import Decimal as _Decimal
                cost = line.get('cost_amount')
                if cost is not None:
                    cost = _Decimal(str(cost))
                lines.append(ClaimLineInput(
                    procedure_code=line['procedure_code'],
                    billed_amount=line['billed_amount'],
                    units=line.get('units', 1),
                    modifiers=line.get('modifiers', []),
                    cost_amount=cost,
                    revenue_code=line.get('revenue_code'),
                ))
            claim_inputs.append(ClaimPricingInput(
                contract_id=contract.pk,
                contract=contract,
                service_date=svc_date,
                claim_type=claim_data.get('claim_type') or None,
                pricing_date=claim_data.get('pricing_date') or svc_date,
                claim_id=None,
                lines=lines,
                drg_code=claim_data.get('drg_code'),
                facility_id=claim_data.get('facility_id'),
                provider_id=claim_data.get('provider_id'),
                product_id=_optional_str_field(claim_data.get('product_id')),
                network_id=_optional_str_field(claim_data.get('network_id')),
            ))

        svc = ClaimPricingService()
        results = svc.price_claims_bulk(claim_inputs)

        request_time_ms = (time.perf_counter() - start) * 1000
        response_data = BulkPricingResultSerializer({
            'total_claims': len(claim_inputs),
            'priced_claims': len(results),
            'results': results,
            'request_time_ms': round(request_time_ms, 2),
        }).data
        return Response(response_data, status=status.HTTP_200_OK)


class ValidateContractView(APIView):
    """
    Step 10: POST /api/validate-contract/<id>/

    Runs all contract conflict checks (scope overlap, participation overlap,
    methodology collision, carve-out overlap, blending cycle) and returns
    a structured JSON report.

    This endpoint is validation-only and does NOT affect pricing.
    Optionally saves results to ValidationResult if ?save=1 query parameter is present.
    """

    def post(self, request, pk: int):
        from core.services.validation_service import ValidationService
        from core.api.serializers import ContractValidationResponseSerializer

        conflicts = ValidationService.validate_contract(pk)

        # Optionally persist results for audit
        if request.query_params.get("save") == "1":
            from core.models import ProviderContract
            try:
                contract = ProviderContract.objects.get(pk=pk)
                ValidationService.save_validation_results(contract, conflicts)
            except ProviderContract.DoesNotExist:
                pass

        error_count = sum(1 for c in conflicts if c.severity == "ERROR")
        warning_count = sum(1 for c in conflicts if c.severity == "WARNING")

        response_data = ContractValidationResponseSerializer({
            "contract_id": pk,
            "error_count": error_count,
            "warning_count": warning_count,
            "conflicts": [c.to_dict() for c in conflicts],
        }).data

        http_status = status.HTTP_200_OK if error_count == 0 else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(response_data, status=http_status)


class ValidateContractsBulkView(APIView):
    """
    Step 12d: POST /api/validate-contracts/bulk/

    Body: {"contract_ids": [int, ...]} (max 100). Optional ?save=1 persists ValidationResult
    per contract (same as single validate-contract). Each contract is validated independently;
    exceptions are returned in an ``errors`` field on that row. Response is always 200 for a
    valid payload; batch too large returns 400.
    """

    def post(self, request):
        from core.services.validation_service import ValidationService
        from core.api.serializers import (
            BulkValidationRequestSerializer,
            BulkContractValidationRowSerializer,
        )

        serializer = BulkValidationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        raw_ids = serializer.validated_data['contract_ids']
        seen: set = set()
        contract_ids = []
        for cid in raw_ids:
            if cid not in seen:
                seen.add(cid)
                contract_ids.append(cid)

        persist = request.query_params.get('save') == '1'
        rows = ValidationService.bulk_validate(contract_ids, persist=persist)
        out = BulkContractValidationRowSerializer(rows, many=True).data
        return Response(out, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Step 12a – Conflict Warnings Panel
# ---------------------------------------------------------------------------

class ContractConflictsView(APIView):
    """
    Step 12a: GET /api/contracts/<pk>/conflicts/

    Returns all unresolved ValidationResult records for the contract.
    Resolved conflicts are excluded; pass ?all=1 to include them.
    """

    def get(self, request, pk: int):
        contract = get_object_or_404(ProviderContract, pk=pk)
        include_all = request.query_params.get('all') == '1'
        qs = ValidationResult.objects.filter(contract=contract)
        if not include_all:
            qs = qs.filter(resolved=False)
        serializer = ValidationResultSerializer(qs, many=True)
        return Response(serializer.data)


class ContractConflictResolveView(APIView):
    """
    Step 12a: PATCH /api/contracts/<pk>/conflicts/<result_id>/resolve/

    Marks a single ValidationResult as resolved=True.
    Accepts an optional JSON body {"resolved": false} to un-resolve.
    """

    def patch(self, request, pk: int, result_id: int):
        get_object_or_404(ProviderContract, pk=pk)
        result = get_object_or_404(ValidationResult, pk=result_id, contract_id=pk)
        serializer = ValidationResultSerializer(result, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Step 12e – Contract Explorer
# ---------------------------------------------------------------------------

class ContractExplorerView(APIView):
    """
    Step 12e: GET /api/contracts/<id>/explorer/
    Returns full contract tree (metadata, versions, methodologies, rules, carve-outs,
    caps/floors, blending rules, stop-loss, outlier, open conflict counts).
    Read-only; 404 if contract not found.
    Query: ?export=csv — flat rows (contract + version + rule).
    Note: avoid ?format= — DRF reserves it for renderer negotiation.
    """

    def get(self, request, pk: int):
        from core.services.contract_explorer_service import get_full_contract
        contract = get_full_contract(pk)
        fmt = (request.query_params.get('export') or '').strip().lower()
        if fmt == 'csv':
            return _contract_explorer_csv_response(contract)
        return Response(ContractExplorerSerializer(contract).data)


def _contract_explorer_csv_response(contract) -> HttpResponse:
    """One row per pricing rule (plus a placeholder row when a version has no rules)."""
    data = ContractExplorerSerializer(contract).data
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        'contract_id',
        'contract_name',
        'legacy_contract_number',
        'version_id',
        'version_number',
        'version_status',
        'rule_id',
        'rule_name',
        'methodology_code',
        'rule_type',
        'rule_status',
        'rule_effective_start',
        'rule_effective_end',
        'conditions',
    ])
    c = data['contract']
    cid = c['id']
    writer_contract_name = c['contract_name'] or ''
    writer_legacy = c.get('legacy_contract_number') or ''

    for ver in data.get('versions') or []:
        vid = ver['version_id']
        vnum = ver['version_number']
        vst = ver.get('status') or ''
        rules = ver.get('rules') or []
        if not rules:
            writer.writerow([
                cid,
                writer_contract_name,
                writer_legacy,
                vid,
                vnum,
                vst,
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
            ])
            continue
        for r in rules:
            conds = r.get('conditions') or []
            cond_str = '; '.join(
                f"{x.get('attribute_name', '')} {x.get('operator', '')} {x.get('attribute_value', '')}".strip()
                for x in conds
            )
            writer.writerow([
                cid,
                writer_contract_name,
                writer_legacy,
                vid,
                vnum,
                vst,
                r.get('rule_id', ''),
                r.get('rule_name', ''),
                r.get('methodology_code', ''),
                r.get('rule_type', ''),
                r.get('status', ''),
                r.get('effective_start_date') or '',
                r.get('effective_end_date') or '',
                cond_str,
            ])

    response = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="contract_{cid}_explorer.csv"'
    return response


# Step 12b – Version Lifecycle Endpoints
# ---------------------------------------------------------------------------

class ContractVersionDetailView(APIView):
    """
    Step 12b: GET /api/contract-versions/<id>/
    Returns full version data including audit trail.
    """

    def get(self, request, pk: int):
        version = get_object_or_404(
            ContractVersion.objects.prefetch_related('audit_records'), pk=pk
        )
        return Response(ContractVersionSerializer(version).data)


class ContractVersionAuditView(APIView):
    """
    Step 12b: GET /api/contracts/<pk>/version-audit/
    Returns all ContractVersionAudit records for every version of a contract,
    most-recent first.
    """

    def get(self, request, pk: int):
        get_object_or_404(ProviderContract, pk=pk)
        records = (
            ContractVersionAudit.objects
            .filter(version__contract_id=pk)
            .select_related('changed_by', 'version')
            .order_by('-timestamp')
        )
        return Response(ContractVersionAuditSerializer(records, many=True).data)


class ContractVersionActivateView(APIView):
    """
    Step 12b: POST /api/contract-versions/<id>/activate/
    Transitions a DRAFT ContractVersion to ACTIVE.
    Automatically supersedes any overlapping ACTIVE version.
    Returns 400 on invalid transition.
    """

    def post(self, request, pk: int):
        from core.services.rule_lifecycle_service import RuleLifecycleService
        from django.core.exceptions import ValidationError as DjangoValidationError

        get_object_or_404(ContractVersion, pk=pk)
        try:
            version = RuleLifecycleService.activate_version(
                pk, user=request.user if request.user.is_authenticated else None
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            VersionLifecycleResponseSerializer({
                'version_id': version.version_id,
                'previous_status': 'DRAFT',
                'new_status': version.status,
            }).data
        )


class ContractVersionArchiveView(APIView):
    """
    Step 12b: POST /api/contract-versions/<id>/archive/
    Transitions a DRAFT or SUPERSEDED ContractVersion to ARCHIVED.
    Returns 400 if version is ACTIVE.
    """

    def post(self, request, pk: int):
        from core.services.rule_lifecycle_service import RuleLifecycleService
        from django.core.exceptions import ValidationError as DjangoValidationError

        version = get_object_or_404(ContractVersion, pk=pk)
        prev = version.status
        try:
            version = RuleLifecycleService.archive_version(
                pk, user=request.user if request.user.is_authenticated else None
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            VersionLifecycleResponseSerializer({
                'version_id': version.version_id,
                'previous_status': prev,
                'new_status': version.status,
            }).data
        )


class ResolveContextView(APIView):
    """
    Debug/dev endpoint: resolves claim context without executing pricing.
    Returns the ClaimPricingContext as JSON for inspection.
    """

    def get(self, request):
        from datetime import date as date_cls

        from core.engine.types import RawClaimInput
        from core.services.contract_resolution_service import (
            ContractResolutionService,
            RESOLUTION_PROCEEDS_TO_PRICING,
        )
        from core.services.pricing_context_resolver import PricingContextResolver
        from core.services.resolution_exception import (
            persist_resolution_exception,
        )

        billing_npi = request.query_params.get('billing_npi')
        rendering_npi = request.query_params.get('rendering_npi')
        member_id = request.query_params.get('member_id')
        service_date_str = request.query_params.get('service_date')
        claim_type = request.query_params.get('claim_type', 'professional')

        service_date = date_cls.today()
        if service_date_str:
            try:
                service_date = date_cls.fromisoformat(service_date_str)
            except ValueError:
                return Response(
                    {'error': 'Invalid service_date format. Use YYYY-MM-DD.'},
                    status=400,
                )

        raw = RawClaimInput(
            billing_npi=billing_npi,
            rendering_npi=rendering_npi,
            member_id=member_id,
            service_date=service_date,
            claim_type=claim_type,
            lines=[],
        )

        resolution_svc = ContractResolutionService()
        member_context = bool(member_id)
        resolution = resolution_svc.resolve(raw, member_context=member_context)

        if resolution.status not in RESOLUTION_PROCEEDS_TO_PRICING:
            persist_resolution_exception(resolution)
            return Response({
                'resolution_mode': resolution.status,
                'message': resolution.reason,
                'contract_id': resolution.contract_id,
                'version_id': resolution.version_id,
                'candidates': list(resolution.candidates or []),
            })

        ctx = PricingContextResolver().context_from_resolution(raw, resolution)
        return Response({
            'resolution_mode': ctx.resolution_mode,
            'contract_id': ctx.contract_id,
            'version_id': ctx.version_id,
            'claim_type': ctx.claim_type,
            'service_date': str(ctx.service_date),
            'provider': {
                'billing_org_id': ctx.provider.billing_org_id,
                'rendering_provider_id': ctx.provider.rendering_provider_id,
                'rendering_provider_specialty': ctx.provider.rendering_provider_specialty,
                'network_status': ctx.provider.network_status,
                'network_tier': ctx.provider.network_tier,
                'affiliation_verified': ctx.provider.affiliation_verified,
            },
            'member': {
                'member_id': ctx.member.member_id,
                'product_id': ctx.member.product_id,
                'lob': ctx.member.lob,
                'network_id': ctx.member.network_id,
                'locality_zip': ctx.member.locality_zip,
                'enrollment_id': ctx.member.enrollment_id,
            },
        })


# --- Stage 5: Context-driven pricing APIs ---

from core.engine.types import RawClaimInput
from core.services.contract_resolution_service import (
    ContractResolutionService,
    RESOLUTION_PROCEEDS_TO_PRICING,
)
from core.services.pricing_context_resolver import PricingContextResolver
from core.services.resolution_exception import (
    persist_resolution_exception,
    resolution_failure_payload,
)
from core.api.serializers import (
    RepriceClaimRequestSerializer,
    RepriceClaimBatchRequestSerializer,
)


class RepriceClaimView(APIView):
    """
    POST /api/reprice-claim/
    Caller supplies member identity + billing NPI only.
    System resolves enrollment → product → network → contract automatically.
    Distinct from POST /api/price-claim/ which requires the caller to know contract_id.
    """

    def post(self, request):
        serializer = RepriceClaimRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=400)

        data = serializer.validated_data
        raw = RawClaimInput(
            billing_npi=data['billing_npi'],
            rendering_npi=data.get('rendering_npi') or None,
            facility_npi=data.get('facility_npi') or None,
            member_id=data['member_id'],
            service_date=data['service_date'],
            claim_type=data['claim_type'],
            lines=[dict(line) for line in data['lines']],
        )

        resolution = ContractResolutionService().resolve(raw, member_context=True)
        if resolution.status not in RESOLUTION_PROCEEDS_TO_PRICING:
            persist_resolution_exception(resolution)
            return Response(resolution_failure_payload(resolution), status=200)

        ctx = PricingContextResolver().context_from_resolution(raw, resolution)

        try:
            result, resolution_log = _price_with_resolved_context(
                ctx,
                resolution_path=ClaimResolutionLog.ResolutionPath.CONTEXT_RESOLVER,
                is_repricing=True,
            )
        except Exception as e:
            return Response({'status': 'ENGINE_ERROR', 'message': str(e)}, status=500)

        line_status = result.status
        if hasattr(line_status, 'value'):
            line_status = line_status.value

        return Response({
            'status': line_status,
            'contract_id': ctx.contract_id,
            'resolution_mode': ctx.resolution_mode,
            'provider': {
                'billing_org_id': ctx.provider.billing_org_id,
                'network_status': ctx.provider.network_status,
                'network_tier': ctx.provider.network_tier,
                'affiliation_verified': ctx.provider.affiliation_verified,
            },
            'member': {
                'member_id': ctx.member.member_id,
                'lob': ctx.member.lob,
                'product_id': ctx.member.product_id,
                'enrollment_id': ctx.member.enrollment_id,
            },
            'lines': _serialize_result_lines(result),
            'trace_id': ctx.trace_id,
            'resolution_log_id': resolution_log.id if resolution_log else None,
        })


class RepriceClaimBatchView(APIView):
    """
    POST /api/reprice-claim-batch/
    Prices up to 50 claims, each fully context-resolved (member + provider → contract).
    Distinct from POST /api/price-claims-bulk/ which requires contract_id per claim.
    Per-claim failures are isolated — batch never fails wholesale.
    """

    def post(self, request):
        serializer = RepriceClaimBatchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=400)

        claims_data = serializer.validated_data['claims']
        resolution_svc = ContractResolutionService()
        context_resolver = PricingContextResolver()
        results = []

        for i, claim_data in enumerate(claims_data):
            raw = RawClaimInput(
                billing_npi=claim_data['billing_npi'],
                rendering_npi=claim_data.get('rendering_npi') or None,
                facility_npi=claim_data.get('facility_npi') or None,
                member_id=claim_data['member_id'],
                service_date=claim_data['service_date'],
                claim_type=claim_data['claim_type'],
                lines=[dict(line) for line in claim_data['lines']],
            )
            try:
                resolution = resolution_svc.resolve(raw, member_context=True)
                if resolution.status not in RESOLUTION_PROCEEDS_TO_PRICING:
                    persist_resolution_exception(resolution)
                    row = resolution_failure_payload(resolution)
                    row['index'] = i
                    row['member_id'] = claim_data['member_id']
                    results.append(row)
                    continue

                ctx = context_resolver.context_from_resolution(raw, resolution)
                result, resolution_log = _price_with_resolved_context(
                    ctx,
                    resolution_path=ClaimResolutionLog.ResolutionPath.CONTEXT_RESOLVER,
                    is_repricing=True,
                )
                line_status = result.status
                if hasattr(line_status, 'value'):
                    line_status = line_status.value
                results.append({
                    'index': i,
                    'status': line_status,
                    'resolution_mode': ctx.resolution_mode,
                    'contract_id': ctx.contract_id,
                    'member_id': claim_data['member_id'],
                    'lines': _serialize_result_lines(result),
                    'trace_id': ctx.trace_id,
                    'resolution_log_id': resolution_log.id if resolution_log else None,
                })
            except Exception as e:
                results.append({
                    'index': i,
                    'status': 'ENGINE_ERROR',
                    'member_id': claim_data['member_id'],
                    'message': str(e),
                    'lines': [],
                })

        return Response({'count': len(results), 'results': results})


class ProviderListView(APIView):
    """
    GET /api/providers/?npi=&name=&specialty=&status=&page=&page_size=
    Provider directory. No equivalent exists in the current API.
    """

    def get(self, request):
        from django.db import models as dj_models
        from providers.models import Provider

        qs = Provider.objects.select_related('primary_specialty').all()

        npi = request.query_params.get('npi')
        name = request.query_params.get('name')
        specialty = request.query_params.get('specialty')
        prov_status = request.query_params.get('status')

        if npi:
            qs = qs.filter(npi=npi)
        if name:
            qs = qs.filter(
                dj_models.Q(first_name__icontains=name)
                | dj_models.Q(last_name__icontains=name)
            )
        if specialty:
            qs = qs.filter(primary_specialty__specialty_code=specialty)
        if prov_status:
            qs = qs.filter(status=prov_status)

        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(int(request.query_params.get('page_size', 25)), 100)
        offset = (page - 1) * page_size
        total = qs.count()

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'id': p.id,
                    'npi': p.npi,
                    'first_name': p.first_name,
                    'last_name': p.last_name,
                    'credential': p.credential,
                    'primary_specialty': (
                        p.primary_specialty.specialty_code
                        if p.primary_specialty else None
                    ),
                    'status': p.status,
                }
                for p in qs[offset: offset + page_size]
            ],
        })


class ProviderNetworkStatusView(APIView):
    """
    GET /api/providers/<provider_id>/network-status/?network_id=&service_date=
    Real-time in/out-of-network check for a provider against a products.Network.
    No equivalent exists in the current API.
    """

    def get(self, request, provider_id):
        from datetime import date as date_cls
        from providers.models import Provider
        from providers.services import ProviderLookupService
        from products.services import NetworkLookupService

        service_date_str = request.query_params.get('service_date')
        network_id_str = request.query_params.get('network_id')

        service_date = date_cls.today()
        if service_date_str:
            try:
                service_date = date_cls.fromisoformat(service_date_str)
            except ValueError:
                return Response(
                    {'error': 'Invalid service_date. Use YYYY-MM-DD.'}, status=400
                )

        try:
            provider = Provider.objects.get(pk=provider_id)
        except Provider.DoesNotExist:
            return Response({'error': 'Provider not found.'}, status=404)

        network_status = 'UNKNOWN'
        network_tier = None

        if network_id_str:
            try:
                network_id = int(network_id_str)
            except ValueError:
                return Response({'error': 'network_id must be an integer.'}, status=400)

            provider_svc = ProviderLookupService()
            network_svc = NetworkLookupService()
            org = provider_svc.resolve_org_by_billing_npi(provider.npi)
            if org:
                status_val = network_svc.check_org_participation(
                    org.organization_id, network_id, service_date
                )
                if status_val:
                    if status_val in ('TIER_1', 'TIER_2'):
                        network_tier = status_val
                        network_status = 'IN_NETWORK'
                    else:
                        network_status = status_val
                else:
                    network_status = 'OUT_OF_NETWORK'

        return Response({
            'provider_id': provider.id,
            'npi': provider.npi,
            'network_status': network_status,
            'network_tier': network_tier,
            'as_of_date': service_date,
        })


class MemberEnrollmentView(APIView):
    """
    GET /api/members/<member_id>/enrollment/?service_date=
    Active coverage lookup — product, LOB, network — for a member on a date.
    No equivalent exists in the current API.
    """

    def get(self, request, member_id):
        from datetime import date as date_cls
        from members.services import MemberLookupService
        from products.services import NetworkLookupService

        service_date_str = request.query_params.get('service_date')
        service_date = date_cls.today()
        if service_date_str:
            try:
                service_date = date_cls.fromisoformat(service_date_str)
            except ValueError:
                return Response(
                    {'error': 'Invalid service_date. Use YYYY-MM-DD.'}, status=400
                )

        svc = MemberLookupService()
        enrollment = svc.resolve_enrollment(member_id, service_date)

        if enrollment is None:
            return Response({
                'member_id': member_id,
                'enrolled': False,
                'enrollment_id': None,
                'product_id': None,
                'product_name': None,
                'lob': None,
                'network_id': None,
                'effective_date': None,
                'termination_date': None,
                'as_of_date': service_date,
            })

        network_id = None
        net = NetworkLookupService().resolve_network(
            enrollment.product_id, 'ALL', service_date
        )
        if net:
            network_id = net.id

        return Response({
            'member_id': member_id,
            'enrolled': True,
            'enrollment_id': enrollment.id,
            'product_id': enrollment.product_id,
            'product_name': enrollment.product.name if enrollment.product else None,
            'lob': enrollment.product.lob.code if enrollment.product else None,
            'network_id': network_id,
            'effective_date': enrollment.effective_date,
            'termination_date': enrollment.termination_date,
            'as_of_date': service_date,
        })


class ProductListView(APIView):
    """
    GET /api/products/?payer_id=&lob=&effective_date=&page=&page_size=
    Payer product catalog. No equivalent exists in the current API.
    """

    def get(self, request):
        from django.db import models as dj_models
        from products.models import Product

        qs = Product.objects.select_related('payer', 'lob').all()

        payer_id = request.query_params.get('payer_id')
        lob = request.query_params.get('lob')
        effective_date_str = request.query_params.get('effective_date')

        if payer_id:
            qs = qs.filter(payer__payer_id=payer_id)
        if lob:
            qs = qs.filter(lob__code=lob)
        if effective_date_str:
            from datetime import date as date_cls
            try:
                ed = date_cls.fromisoformat(effective_date_str)
                qs = qs.filter(effective_date__lte=ed).filter(
                    dj_models.Q(termination_date__isnull=True)
                    | dj_models.Q(termination_date__gte=ed)
                )
            except ValueError:
                return Response(
                    {'error': 'Invalid effective_date. Use YYYY-MM-DD.'}, status=400
                )

        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(int(request.query_params.get('page_size', 25)), 100)
        offset = (page - 1) * page_size
        total = qs.count()

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'id': p.id,
                    'name': p.name,
                    'product_code': p.product_code,
                    'payer_id': p.payer.payer_id,
                    'payer_name': p.payer.name,
                    'lob': p.lob.code if p.lob else None,
                    'effective_date': p.effective_date,
                    'termination_date': p.termination_date,
                }
                for p in qs[offset: offset + page_size]
            ],
        })


def _build_raw_from_claim(claim: ClaimHeader) -> RawClaimInput:
    """Build RawClaimInput from a stored ClaimHeader for context resolution."""
    from decimal import Decimal

    from core.engine.config import ClaimLineInput

    billing_npi = claim.billing_npi or claim.npi
    if not billing_npi and claim.provider_org_id:
        billing_npi = getattr(claim.provider_org, 'npi', None)

    rendering_npi = None
    if claim.rendering_provider_id:
        rendering_npi = claim.rendering_provider.npi

    lines = []
    for line in claim.lines.all().order_by('sequence', 'line_id'):
        modifiers = line.modifiers if isinstance(line.modifiers, list) else []
        cost = getattr(line, 'cost_amount', None)
        lines.append(
            {
                'procedure_code': line.procedure_code,
                'billed_amount': line.billed_amount,
                'units': line.units,
                'modifiers': modifiers,
                'cost_amount': Decimal(str(cost)) if cost is not None else None,
            }
        )

    return RawClaimInput(
        billing_npi=billing_npi,
        rendering_npi=rendering_npi,
        member_id=claim.member_id,
        service_date=claim.service_date,
        pricing_date=claim.pricing_date or claim.service_date,
        claim_type=(claim.claim_type or 'professional').lower(),
        lines=lines,
    )


def _price_with_resolved_context(
    ctx,
    *,
    resolution_path: str,
    claim_header: ClaimHeader | None = None,
    is_repricing: bool = False,
):
    from core.services.resolution_log import write_claim_resolution_log

    svc = ClaimPricingService()
    result = svc.price_claim_from_context(ctx)
    resolution_log = None
    if ctx.version_id is not None:
        resolution_log = write_claim_resolution_log(
            ctx,
            resolution_path,
            claim_header=claim_header,
            is_repricing=is_repricing,
        )
    return result, resolution_log


class ResolutionLogView(APIView):
    """GET /api/resolution-log/<trace_id>/ — fetch persisted resolution audit row(s)."""

    def get(self, request, trace_id):
        logs = ClaimResolutionLog.objects.filter(
            trace_id=trace_id
        ).select_related(
            'resolved_contract', 'resolved_version', 'claim_header'
        ).order_by('resolved_at')

        if not logs.exists():
            return Response({'error': 'No resolution log found for trace_id.'}, status=404)

        payload = []
        for log in logs:
            payload.append({
                'id': log.id,
                'trace_id': str(log.trace_id) if log.trace_id else None,
                'claim_header_id': log.claim_header_id,
                'resolved_contract_id': log.resolved_contract_id,
                'resolved_version_id': log.resolved_version_id,
                'resolution_path': log.resolution_path,
                'service_date': str(log.service_date),
                'resolver_inputs': log.resolver_inputs,
                'is_repricing': log.is_repricing,
                'resolved_at': log.resolved_at.isoformat(),
            })
        return Response({'count': len(payload), 'results': payload})


class ResolutionExceptionListView(APIView):
    """GET /api/resolution-exceptions/ — analyst review queue for failed resolutions."""

    def get(self, request):
        from core.models import ContractResolutionException

        qs = ContractResolutionException.objects.all().order_by('-created_at')
        status_filter = request.query_params.get('status')
        reviewed = request.query_params.get('is_reviewed')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if reviewed is not None:
            qs = qs.filter(is_reviewed=reviewed.lower() in ('true', '1', 'yes'))

        page_size = min(int(request.query_params.get('page_size', 25)), 100)
        page = max(int(request.query_params.get('page', 1)), 1)
        start = (page - 1) * page_size
        end = start + page_size
        total = qs.count()
        rows = []
        for exc in qs[start:end]:
            rows.append({
                'id': exc.id,
                'trace_id': str(exc.trace_id) if exc.trace_id else None,
                'status': exc.status,
                'reason': exc.reason,
                'candidates': exc.candidates,
                'gathered_inputs': exc.gathered_inputs,
                'service_date': exc.service_date.isoformat() if exc.service_date else None,
                'is_reviewed': exc.is_reviewed,
                'review_notes': exc.review_notes,
                'created_at': exc.created_at.isoformat(),
            })
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': rows,
        })


class ResolutionExceptionDetailView(APIView):
    """PATCH /api/resolution-exceptions/<id>/ — mark exception reviewed."""

    def patch(self, request, pk):
        from core.models import ContractResolutionException

        exc = get_object_or_404(ContractResolutionException, pk=pk)
        if 'is_reviewed' in request.data:
            exc.is_reviewed = bool(request.data['is_reviewed'])
        if 'review_notes' in request.data:
            exc.review_notes = request.data['review_notes']
        exc.save(update_fields=['is_reviewed', 'review_notes'])
        return Response({
            'id': exc.id,
            'status': exc.status,
            'is_reviewed': exc.is_reviewed,
            'review_notes': exc.review_notes,
        })


def _serialize_result_lines(result) -> list:
    """
    Serialize ClaimPricingResult lines using exact attribute names from
    core/engine/types.py. Read that file before implementing — do not guess.
    """
    lines = []
    for line in getattr(result, 'lines', []):
        line_status = getattr(line, 'status', '')
        if hasattr(line_status, 'value'):
            line_status = line_status.value
        lines.append({
            'procedure_code': getattr(line, 'procedure_code', None),
            'units': str(getattr(line, 'units', '')),
            'billed_amount': str(getattr(line, 'billed_amount', '')),
            'allowed_amount': str(getattr(line, 'allowed_amount', '')),
            'payment_rate': str(getattr(line, 'payment_rate', '')),
            'modifier_1': getattr(line, 'modifier_1', ''),
            'status': line_status,
            'notes': getattr(line, 'notes', '') or getattr(line, 'details', ''),
        })
    return lines
