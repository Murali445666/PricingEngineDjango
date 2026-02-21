import time
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from core.models import ProviderContract, PricingRule, RuleHistory, FeeSchedule, RefProcedureCode, RefModifier
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingInput, PricingStatus
from core.engine.simulation import run_line_simulation
from core.services.rule_conflict import get_conflicts_for_rule, get_conflicts_for_rule_payload
from core.api.serializers import (
    ContractSerializer,
    ContractDetailSerializer,
    PricingRequestSerializer,
    PricingResponseSerializer,
    PricingClaimRequest,
    RuleListSerializer,
    RuleDetailSerializer,
    RuleHistorySerializer,
    RuleCreateSerializer,
    RuleUpdateSerializer,
    FeeScheduleSerializer,
    ProcedureCodeSerializer,
    ModifierSerializer,
)

def _get_contract(contract_id_value):
    """Resolve contract by legacy_contract_number or PK (integer)."""
    try:
        if isinstance(contract_id_value, int) or (isinstance(contract_id_value, str) and contract_id_value.isdigit()):
            return ProviderContract.objects.get(pk=int(contract_id_value))
        return ProviderContract.objects.get(legacy_contract_number=contract_id_value)
    except ProviderContract.DoesNotExist:
        return None


class ContractListView(APIView):
    def get(self, request):
        contracts = ProviderContract.objects.filter(status='ACTIVE')
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
        contract = get_object_or_404(ProviderContract, pk=pk)
        serializer = ContractDetailSerializer(contract)
        return Response(serializer.data)


class ContractRuleListView(APIView):
    def get(self, request, pk):
        get_object_or_404(ProviderContract, pk=pk)
        qs = PricingRule.objects.filter(contract_id=pk).prefetch_related('conditions')
        serializer = RuleListSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        """Create a new rule (DRAFT) for this contract."""
        contract = get_object_or_404(ProviderContract, pk=pk)
        serializer = RuleCreateSerializer(data=request.data, context={'contract': contract})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        rule = serializer.save()
        response_serializer = RuleDetailSerializer(
            PricingRule.objects.prefetch_related('conditions').get(pk=rule.pk)
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


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
    """POST /api/rules/check-conflicts/ — body: contract_id, conditions (advisory)."""

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
        conflicts = get_conflicts_for_rule_payload(contract.pk, conditions)
        return Response({"conflicts": conflicts}, status=status.HTTP_200_OK)


class FeeScheduleListView(APIView):
    """GET /api/fee-schedules/ — list fee schedules for dropdowns."""

    def get(self, request):
        qs = FeeSchedule.objects.all().order_by('name')
        serializer = FeeScheduleSerializer(qs, many=True)
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

        engine = PricingEngine()
        pricing_input = PricingInput(
            procedure_code=data['procedure_code'],
            billed_amount=data['billed_amount'],
            units=data['units'],
            modifiers=data['modifiers'],
        )
        result = engine.calculate_line(contract, pricing_input)
        response_serializer = PricingResponseSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


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
        })
        if not line_serializer.is_valid():
            return Response(line_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated = line_serializer.validated_data
        pricing_input = PricingInput(
            procedure_code=validated['procedure_code'],
            billed_amount=validated['billed_amount'],
            units=validated['units'],
            modifiers=validated['modifiers'],
        )
        draft_rule = data.get('draft_rule')
        result = run_line_simulation(contract, pricing_input, draft_rule=draft_rule)
        response_data = PricingResponseSerializer(result).data
        response_data['trace_logs'] = getattr(result.trace, 'logs', [])
        return Response(response_data, status=status.HTTP_200_OK)


class PriceClaimView(APIView):
    """Batch pricing: multiple claim lines in one request."""

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
        engine = PricingEngine()
        line_results = []
        total_allowed = Decimal("0.00")

        for line in data['lines']:
            inp = PricingInput(
                procedure_code=line['procedure_code'],
                billed_amount=line['billed_amount'],
                units=line.get('units', 1),
                modifiers=line.get('modifiers', []),
            )
            result = engine.calculate_line(contract, inp)
            line_results.append(result)
            if result.status == PricingStatus.SUCCESS:
                total_allowed += result.allowed_amount

        request_time_ms = (time.perf_counter() - start) * 1000
        response_data = {
            "contract_id": str(contract.pk),
            "total_allowed": float(total_allowed),
            "lines": [PricingResponseSerializer(r).data for r in line_results],
            "line_count": len(line_results),
            "request_time_ms": round(request_time_ms, 2),
        }
        return Response(response_data, status=status.HTTP_200_OK)
