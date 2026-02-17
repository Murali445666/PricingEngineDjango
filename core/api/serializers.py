from rest_framework import serializers
from core.models import ProviderContract

class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderContract
        fields = ['contract_id', 'contract_name', 'status', 'legacy_contract_number']

class PricingRequestSerializer(serializers.Serializer):
    contract_id = serializers.CharField(max_length=100)
    procedure_code = serializers.CharField(max_length=20)
    billed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    units = serializers.IntegerField(default=1, min_value=1)
    modifiers = serializers.ListField(
        child=serializers.CharField(max_length=5),
        required=False,
        default=list
    )

class PricingResponseSerializer(serializers.Serializer):
    status = serializers.SerializerMethodField()
    allowed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    methodology = serializers.CharField()
    details = serializers.CharField()
    contract_id = serializers.CharField()
    rule_id = serializers.IntegerField()
    trace_id = serializers.CharField(source='trace.trace_id')
    execution_time_ms = serializers.FloatField()

    def get_status(self, obj):
        return obj.status.value if hasattr(obj.status, 'value') else str(obj.status)


# --- Multi-line (Claim) ---
class PricingClaimLineRequest(serializers.Serializer):
    line_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    procedure_code = serializers.CharField(max_length=20)
    billed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    units = serializers.IntegerField(default=1, min_value=1)
    modifiers = serializers.ListField(
        child=serializers.CharField(max_length=5),
        required=False,
        default=list,
    )


class PricingClaimRequest(serializers.Serializer):
    contract_id = serializers.CharField(max_length=100)
    lines = serializers.ListField(child=PricingClaimLineRequest())

    def to_internal_value(self, data):
        # Allow contract_id as integer (e.g. from API clients sending PK)
        if isinstance(data.get('contract_id'), int):
            data = {**data, 'contract_id': str(data['contract_id'])}
        return super().to_internal_value(data)


class ClaimResponseSerializer(serializers.Serializer):
    lines = serializers.ListField(child=PricingResponseSerializer())
    claim_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    line_count = serializers.IntegerField()
    request_time_ms = serializers.FloatField(required=False)
