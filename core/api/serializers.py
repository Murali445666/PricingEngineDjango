from rest_framework import serializers
from core.models import (
    ProviderContract,
    PricingRule,
    PricingRuleCondition,
    RuleHistory,
    FeeSchedule,
    RefProcedureCode,
    RefModifier,
)
from core.engine.condition_schema import (
    ALLOWED_ATTRIBUTE_NAMES,
    ALLOWED_OPERATORS,
    validate_attribute_name,
    validate_operator,
)


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderContract
        fields = ['contract_id', 'contract_name', 'status', 'legacy_contract_number']


class ProcedureCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefProcedureCode
        fields = ['code_id', 'code_type', 'description', 'work_rvu', 'pe_rvu', 'mp_rvu']


class ModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefModifier
        fields = ['modifier_code', 'description', 'percentage_adjustment']

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


# --- Phase 3: Rules read-only ---
class RuleListSerializer(serializers.ModelSerializer):
    contract_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PricingRule
        fields = [
            'rule_id', 'rule_name', 'methodology_code', 'rule_type',
            'contract_id', 'status', 'specificity_score', 'effective_start_date', 'effective_end_date',
        ]


class RuleConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingRuleCondition
        fields = ['condition_id', 'attribute_name', 'operator', 'attribute_value']


class RuleDetailSerializer(RuleListSerializer):
    contract_id = serializers.IntegerField(read_only=True)
    base_fee_schedule_id = serializers.IntegerField(read_only=True, allow_null=True)
    conditions = RuleConditionSerializer(many=True, read_only=True)

    class Meta(RuleListSerializer.Meta):
        fields = RuleListSerializer.Meta.fields + [
            'multiplier', 'flat_rate', 'base_fee_schedule_id', 'conditions',
        ]


class ContractDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderContract
        fields = [
            'contract_id', 'contract_name', 'status', 'legacy_contract_number',
            'effective_start_date', 'effective_end_date',
        ]


class RuleHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleHistory
        fields = ['id', 'change_date', 'previous_status', 'new_status', 'change_reason']


# --- Phase 4: Rule authoring (write APIs) ---

class ConditionCreateSerializer(serializers.Serializer):
    """Validates condition payload against allowed attribute names and operators."""
    attribute_name = serializers.CharField(max_length=50)
    operator = serializers.CharField(max_length=10, default='EQ')
    attribute_value = serializers.CharField(max_length=255)

    def validate_attribute_name(self, value):
        if not validate_attribute_name(value):
            raise serializers.ValidationError(
                f"Invalid attribute_name. Allowed: {sorted(ALLOWED_ATTRIBUTE_NAMES)}"
            )
        return value

    def validate_operator(self, value):
        if not validate_operator(value):
            raise serializers.ValidationError(
                f"Invalid operator. Allowed: {sorted(ALLOWED_OPERATORS)}"
            )
        return value


class RuleCreateSerializer(serializers.Serializer):
    rule_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    rule_type = serializers.CharField(max_length=10, default='BASE')
    methodology_code = serializers.CharField(max_length=50)
    multiplier = serializers.DecimalField(
        max_digits=6, decimal_places=4, required=False, default=1
    )
    flat_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    base_fee_schedule_id = serializers.IntegerField(required=False, allow_null=True)
    effective_start_date = serializers.DateField(required=True)
    effective_end_date = serializers.DateField(required=False, allow_null=True)
    conditions = serializers.ListField(
        child=ConditionCreateSerializer(),
        required=False,
        default=list,
    )

    def create(self, validated_data):
        contract = self.context['contract']
        conditions_data = validated_data.pop('conditions', [])
        rule = PricingRule.objects.create(
            contract=contract,
            status=PricingRule.RuleStatus.DRAFT,
            rule_name=validated_data.get('rule_name') or '',
            rule_type=validated_data.get('rule_type', 'BASE'),
            methodology_code=validated_data['methodology_code'],
            multiplier=validated_data.get('multiplier', 1),
            flat_rate=validated_data.get('flat_rate'),
            base_fee_schedule_id=validated_data.get('base_fee_schedule_id'),
            effective_start_date=validated_data['effective_start_date'],
            effective_end_date=validated_data.get('effective_end_date'),
        )
        for cond in conditions_data:
            PricingRuleCondition.objects.create(
                pricing_rule=rule,
                attribute_name=cond['attribute_name'],
                operator=cond.get('operator', 'EQ'),
                attribute_value=cond['attribute_value'],
            )
        rule.calculate_score()
        return rule


class RuleUpdateSerializer(serializers.Serializer):
    rule_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    rule_type = serializers.CharField(max_length=10, required=False)
    methodology_code = serializers.CharField(max_length=50, required=False)
    multiplier = serializers.DecimalField(
        max_digits=6, decimal_places=4, required=False, allow_null=True
    )
    flat_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    base_fee_schedule_id = serializers.IntegerField(required=False, allow_null=True)
    effective_start_date = serializers.DateField(required=False)
    effective_end_date = serializers.DateField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=[c[0] for c in PricingRule.RuleStatus.choices],
        required=False,
    )
    conditions = serializers.ListField(
        child=ConditionCreateSerializer(),
        required=False,
    )

    def update(self, instance, validated_data):
        conditions_data = validated_data.pop('conditions', None)
        for attr, value in validated_data.items():
            if attr != 'conditions' and value is not None:
                setattr(instance, attr, value)
        instance.save()
        if conditions_data is not None:
            instance.conditions.all().delete()
            for cond in conditions_data:
                PricingRuleCondition.objects.create(
                    pricing_rule=instance,
                    attribute_name=cond['attribute_name'],
                    operator=cond.get('operator', 'EQ'),
                    attribute_value=cond['attribute_value'],
                )
            instance.calculate_score()
        return instance


class FeeScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeSchedule
        fields = ['fee_schedule_id', 'name', 'effective_date', 'version']
