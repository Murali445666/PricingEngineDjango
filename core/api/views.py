import time
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.models import ProviderContract
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingInput, PricingStatus
from core.api.serializers import (
    ContractSerializer,
    PricingRequestSerializer,
    PricingResponseSerializer,
    PricingClaimRequest,
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
