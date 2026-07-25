from rest_framework import serializers
from core.models import (
    ProviderContract,
    PricingRule,
    PricingRuleCondition,
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
    ClaimLine,
    ValidationResult,
    ContractVersion,
    ContractVersionAudit,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
    ContractCoveredEntity,
    ProviderOrganization,
    ContractScopeUnified,
    ContractAmendment,
)
from core.engine.condition_schema import (
    ALLOWED_ATTRIBUTE_NAMES,
    ALLOWED_OPERATORS,
    validate_attribute_name,
    validate_operator,
)


class ValidationResultSerializer(serializers.ModelSerializer):
    """Step 12a: Read/resolve contract conflict records."""
    resolved = serializers.BooleanField()

    class Meta:
        model = ValidationResult
        fields = [
            'id',
            'conflict_type',
            'severity',
            'message',
            'affected_objects',
            'suggested_action',
            'validated_at',
            'resolved',
        ]
        read_only_fields = [
            'id', 'conflict_type', 'severity', 'message',
            'affected_objects', 'suggested_action', 'validated_at',
        ]


class ContractSerializer(serializers.ModelSerializer):
    open_error_count = serializers.SerializerMethodField()
    open_warning_count = serializers.SerializerMethodField()

    class Meta:
        model = ProviderContract
        fields = [
            'contract_id', 'contract_name', 'status', 'legacy_contract_number',
            'open_error_count', 'open_warning_count',
        ]

    def get_open_error_count(self, obj) -> int:
        return obj.validation_results.filter(
            resolved=False, severity=ValidationResult.SEVERITY_ERROR
        ).count()

    def get_open_warning_count(self, obj) -> int:
        return obj.validation_results.filter(
            resolved=False, severity=ValidationResult.SEVERITY_WARNING
        ).count()


class ContractCreateSerializer(serializers.ModelSerializer):
    """POST /api/contracts/ — always creates DRAFT contract + initial DRAFT version 1."""

    class Meta:
        model = ProviderContract
        fields = [
            'contract_name', 'legacy_contract_number', 'payer_org', 'provider_org',
            'network', 'line_of_business', 'effective_start_date', 'effective_end_date',
            'contract_origin_type', 'resolution_priority',
        ]

    def validate_legacy_contract_number(self, value):
        text = (value or '').strip()
        if not text:
            raise serializers.ValidationError('This field is required.')
        if ProviderContract.objects.filter(legacy_contract_number=text).exists():
            raise serializers.ValidationError('A contract with this legacy number already exists.')
        return text

    def create(self, validated_data):
        validated_data['status'] = 'DRAFT'
        contract = ProviderContract.objects.create(**validated_data)
        ContractVersion.objects.create(
            contract=contract,
            version_number=1,
            effective_start_date=contract.effective_start_date,
            effective_end_date=contract.effective_end_date,
            status=ContractVersion.VersionStatus.DRAFT,
        )
        return contract


class ProcedureCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefProcedureCode
        fields = ['code_id', 'code_type', 'description', 'work_rvu', 'pe_rvu', 'mp_rvu']


class RefCptHcpcsCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefCptHcpcsCode
        fields = ['code', 'code_type', 'description', 'status_indicator', 'effective_year']


class RefMpfsRvuSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefMpfsRvu
        fields = ['id', 'code', 'year', 'work_rvu', 'pe_rvu', 'mp_rvu', 'total_rvu', 'status_indicator']


class RefDrgSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefDrg
        fields = [
            'drg_code', 'description', 'relative_weight',
            'geometric_mean_los', 'arithmetic_mean_los', 'mdc', 'year',
        ]


class RefApcSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefApc
        fields = [
            'apc_code', 'description', 'relative_weight',
            'status_indicator', 'payment_rate', 'year',
        ]


# Phase 3: ICD-10 and ASP
class RefIcd10CmSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefIcd10Cm
        fields = ['diagnosis_code', 'description', 'billable_flag', 'effective_year']


class RefIcd10PcsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefIcd10Pcs
        fields = ['procedure_code', 'description', 'section', 'body_system', 'year']


class RefAspPricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefAspPricing
        fields = ['id', 'hcpcs_code', 'quarter', 'asp', 'payment_limit']


# Phase 4: Revenue codes and specialties
class RefRevenueCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefRevenueCode
        fields = ['revenue_code', 'description', 'category']


class RefSpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = RefSpecialty
        fields = ['specialty_code', 'description']


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
        default=list,
    )
    # Phase 2B / Phase 5: claim context for resolver and loader
    service_date = serializers.DateField(required=False, allow_null=True)
    claim_type = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    pricing_date = serializers.DateField(required=False, allow_null=True)
    contract_effective_date = serializers.DateField(required=False, allow_null=True)

class PricingResponseSerializer(serializers.Serializer):
    status = serializers.SerializerMethodField()
    allowed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    methodology = serializers.CharField()
    details = serializers.CharField()
    contract_id = serializers.CharField()
    rule_id = serializers.IntegerField()
    trace_id = serializers.CharField(source='trace.trace_id')
    execution_time_ms = serializers.FloatField()
    # Step 7: carve-out audit fields
    carveout_applied = serializers.BooleanField(default=False)
    carveout_id = serializers.IntegerField(allow_null=True, default=None)
    base_allowed_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, default=None
    )
    # Step 9: blending audit fields
    blended_allowed_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, default=None
    )
    blending_rule_id = serializers.IntegerField(allow_null=True, default=None)

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
    cost_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=None)
    # Phase 5: optional per-line claim context (else use claim-level)
    service_date = serializers.DateField(required=False, allow_null=True)
    pricing_date = serializers.DateField(required=False, allow_null=True)
    contract_effective_date = serializers.DateField(required=False, allow_null=True)
    # Phase C: optional revenue code for resolver condition revenue_code
    revenue_code = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)


class PricingClaimRequest(serializers.Serializer):
    contract_id = serializers.CharField(max_length=100)
    lines = serializers.ListField(child=PricingClaimLineRequest())
    # Phase 5: optional claim-level dates (applied to lines that don't specify)
    service_date = serializers.DateField(required=False, allow_null=True)
    pricing_date = serializers.DateField(required=False, allow_null=True)
    contract_effective_date = serializers.DateField(required=False, allow_null=True)
    claim_type = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    # Phase E: claim-level DRG (when claim_level_drg_enabled)
    drg_code = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    facility_id = serializers.IntegerField(required=False, allow_null=True)
    provider_id = serializers.IntegerField(required=False, allow_null=True)
    # Step 14a: optional tier context (ignored unless FEATURE_TIERED_RESOLUTION)
    product_id = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    network_id = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)

    def to_internal_value(self, data):
        # Allow contract_id as integer (e.g. from API clients sending PK)
        if isinstance(data.get('contract_id'), int):
            data = {**data, 'contract_id': str(data['contract_id'])}
        return super().to_internal_value(data)


class PriceClaimSimulateRequest(serializers.Serializer):
    """
    Step 13: Request body for POST /api/price-claim-simulate/.

    Accepts two shapes (normalized to the same internal form):
    - Original: { contract_id, version_id, claim: { lines: [...], service_date?, pricing_date? } }
    - Analyst UI: { contract_id, version_id, claim_lines: [...], service_date?, external_claim_id?, claim_input? }
    """
    contract_id = serializers.IntegerField()
    version_id = serializers.IntegerField()
    claim = serializers.DictField(required=False)
    # Analyst UI / alternate format (normalized into claim in to_internal_value)
    claim_lines = serializers.ListField(required=False, allow_empty=True)
    service_date = serializers.DateField(required=False, allow_null=True)
    external_claim_id = serializers.CharField(required=False, allow_blank=True)
    claim_input = serializers.DictField(required=False)
    member_id = serializers.CharField(required=False, allow_blank=True)
    billing_npi = serializers.CharField(required=False, allow_blank=True, max_length=15)
    rendering_npi = serializers.CharField(required=False, allow_blank=True, max_length=15)

    def to_internal_value(self, data):
        data = dict(data)
        # If client sent top-level claim_lines (analyst UI format), build claim from it
        if "claim_lines" in data:
            lines = data.pop("claim_lines", [])
            if "claim" not in data or not (data.get("claim") or {}).get("lines"):
                data["claim"] = dict(data.get("claim") or {})
                data["claim"]["lines"] = lines
                data["claim"].setdefault("service_date", data.get("service_date"))
                data["claim"].setdefault("pricing_date", data.get("pricing_date"))
        if "claim" not in data:
            data["claim"] = {"lines": [], "contract_id": data.get("contract_id")}
        return super().to_internal_value(data)

    def validate_claim(self, value):
        """Validate nested claim shape (lines, service_date, etc.) without requiring contract_id.
        Returns validated claim (including revenue_code and other line fields from PricingClaimLineRequest).
        """
        if not value or not value.get("lines"):
            raise serializers.ValidationError("Claim must have at least one line.")
        inner = PricingClaimRequest(data={**value, "contract_id": "0"})
        if not inner.is_valid():
            raise serializers.ValidationError(inner.errors)
        # Return validated claim so claim_data['lines'][i] has all fields (e.g. revenue_code) from PricingClaimLineRequest
        return inner.validated_data


class ClaimResponseSerializer(serializers.Serializer):
    lines = serializers.ListField(child=PricingResponseSerializer())
    claim_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    line_count = serializers.IntegerField()
    request_time_ms = serializers.FloatField(required=False)


# --- Phase 5B: Stored claims ---
class ClaimLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimLine
        fields = ['line_id', 'procedure_code', 'modifiers', 'billed_amount', 'cost_amount', 'units', 'sequence']


class ClaimHeaderSerializer(serializers.ModelSerializer):
    lines = ClaimLineSerializer(many=True, read_only=True)

    class Meta:
        model = ClaimHeader
        fields = [
            'claim_id', 'contract_id', 'member_id', 'service_date', 'claim_type',
            'drg_code', 'line_of_business', 'pricing_date', 'lines',
        ]


class ClaimLineCreateSerializer(serializers.Serializer):
    procedure_code = serializers.CharField(max_length=20)
    modifiers = serializers.ListField(child=serializers.CharField(max_length=5), required=False, default=list)
    billed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    cost_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=0)
    units = serializers.IntegerField(default=1, min_value=1)
    sequence = serializers.IntegerField(default=0, required=False)


class ClaimCreateSerializer(serializers.Serializer):
    contract_id = serializers.IntegerField()
    member_id = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)
    service_date = serializers.DateField()
    claim_type = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    drg_code = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    line_of_business = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    pricing_date = serializers.DateField(required=False, allow_null=True)
    lines = serializers.ListField(child=ClaimLineCreateSerializer())

    def validate_contract_id(self, value):
        from core.models import ProviderContract
        if not ProviderContract.objects.filter(pk=value).exists():
            raise serializers.ValidationError('Contract not found.')
        return value

    def create(self, validated_data):
        from core.models import ClaimHeader, ClaimLine, ProviderContract
        contract = ProviderContract.objects.get(pk=validated_data['contract_id'])
        lines_data = validated_data.pop('lines')
        header = ClaimHeader.objects.create(
            contract=contract,
            member_id=validated_data.get('member_id') or None,
            service_date=validated_data['service_date'],
            claim_type=validated_data.get('claim_type') or None,
            drg_code=validated_data.get('drg_code') or None,
            line_of_business=validated_data.get('line_of_business') or None,
            pricing_date=validated_data.get('pricing_date'),
        )
        for seq, line_data in enumerate(lines_data):
            ClaimLine.objects.create(
                claim=header,
                procedure_code=line_data['procedure_code'],
                modifiers=line_data.get('modifiers', []),
                billed_amount=line_data['billed_amount'],
                cost_amount=line_data.get('cost_amount'),
                units=line_data.get('units', 1),
                sequence=line_data.get('sequence', seq),
            )
        return header


class ClaimPricingResultSerializer(serializers.Serializer):
    claim_id = serializers.IntegerField()
    contract_id = serializers.CharField()
    total_allowed = serializers.DecimalField(max_digits=14, decimal_places=2)
    line_count = serializers.IntegerField()
    lines = serializers.ListField(child=PricingResponseSerializer())
    status = serializers.SerializerMethodField()
    claim_trace = serializers.SerializerMethodField()
    original_total_allowed = serializers.SerializerMethodField()
    final_total_allowed = serializers.SerializerMethodField()
    applied_outlier_rule_id = serializers.SerializerMethodField()
    applied_stop_loss_rule_id = serializers.SerializerMethodField()

    def get_status(self, obj):
        s = getattr(obj, 'status', None)
        return s.value if s is not None and hasattr(s, 'value') else 'SUCCESS'

    def get_claim_trace(self, obj):
        return getattr(obj, 'claim_trace', [])

    def get_original_total_allowed(self, obj):
        return getattr(obj, 'original_total_allowed', None) or getattr(obj, 'total_allowed', None)

    def get_final_total_allowed(self, obj):
        return getattr(obj, 'final_total_allowed', None) or getattr(obj, 'total_allowed', None)

    def get_applied_outlier_rule_id(self, obj):
        return getattr(obj, 'applied_outlier_rule_id', None)

    def get_applied_stop_loss_rule_id(self, obj):
        return getattr(obj, 'applied_stop_loss_rule_id', None)

    # Step 8: cap/floor audit fields
    pre_cap_total_allowed = serializers.SerializerMethodField()
    applied_cap_floor_id = serializers.SerializerMethodField()

    def get_pre_cap_total_allowed(self, obj):
        return getattr(obj, 'pre_cap_total_allowed', None)

    def get_applied_cap_floor_id(self, obj):
        return getattr(obj, 'applied_cap_floor_id', None)

    # Step 9: blending audit fields
    blended_total_allowed = serializers.SerializerMethodField()
    applied_blending_rule_ids = serializers.SerializerMethodField()

    def get_blended_total_allowed(self, obj):
        return getattr(obj, 'blended_total_allowed', None)

    def get_applied_blending_rule_ids(self, obj):
        return getattr(obj, 'applied_blending_rule_ids', [])

    # Phase A: unified execution trace
    execution_trace = serializers.SerializerMethodField()

    def get_execution_trace(self, obj):
        return getattr(obj, 'execution_trace', [])


# --- Phase 3: Rules read-only ---
class RuleListSerializer(serializers.ModelSerializer):
    contract_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PricingRule
        fields = [
            'rule_id', 'rule_name', 'methodology_code', 'rule_type',
            'contract_id', 'status', 'specificity_score', 'effective_start_date', 'effective_end_date',
            'claim_type', 'site_of_service',
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
        # claim_type, site_of_service already in RuleListSerializer.fields


class ContractMethodologySerializer(serializers.ModelSerializer):
    fee_schedule_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ContractMethodology
        fields = [
            'id', 'methodology_type', 'base_percentage', 'conversion_factor',
            'fee_schedule_id', 'effective_date', 'termination_date', 'priority',
            'claim_type', 'site_of_service', 'conditions',
        ]
        read_only_fields = ['id']

    def validate_conditions(self, value):
        from core.services.condition_validation_service import validate_condition_schema
        validate_condition_schema(value)
        return value


class ContractMethodologyCreateSerializer(serializers.Serializer):
    methodology_type = serializers.CharField(max_length=50)
    base_percentage = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    conversion_factor = serializers.DecimalField(max_digits=10, decimal_places=4, required=False, allow_null=True)
    fee_schedule_id = serializers.IntegerField(required=False, allow_null=True)
    effective_date = serializers.DateField()
    termination_date = serializers.DateField(required=False, allow_null=True)
    priority = serializers.IntegerField(default=0)
    claim_type = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    site_of_service = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    conditions = serializers.JSONField(required=False, allow_null=True)

    def validate_conditions(self, value):
        from core.services.condition_validation_service import validate_condition_schema
        validate_condition_schema(value)
        return value

    def create(self, validated_data):
        contract = self.context['contract']
        return ContractMethodology.objects.create(contract=contract, **validated_data)


class ContractOutlierRuleSerializer(serializers.ModelSerializer):
    """Phase 6: Outlier/stop-loss rule read."""

    class Meta:
        model = ContractOutlierRule
        fields = [
            'id', 'contract', 'threshold_amount', 'threshold_scope',
            'reimbursement_percentage', 'cost_to_charge_ratio',
            'priority', 'effective_start_date', 'effective_end_date',
        ]
        read_only_fields = ['id']


PER_CLAIM = "PER_CLAIM"
PER_LINE = "PER_LINE"


class ContractOutlierRuleCreateSerializer(serializers.Serializer):
    """Phase 6: Create outlier rule (contract from URL). PER_LINE not yet supported."""
    threshold_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    threshold_scope = serializers.ChoiceField(
        choices=[(PER_CLAIM, "Per Claim"), (PER_LINE, "Per Line")],
        default=PER_CLAIM,
    )
    reimbursement_percentage = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    cost_to_charge_ratio = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, allow_null=True)
    priority = serializers.IntegerField(default=0)
    effective_start_date = serializers.DateField(required=False)
    effective_end_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, data):
        if data.get('reimbursement_percentage') is None and data.get('cost_to_charge_ratio') is None:
            raise serializers.ValidationError(
                'At least one of reimbursement_percentage or cost_to_charge_ratio must be set.'
            )
        if data.get('threshold_scope') == PER_LINE:
            raise serializers.ValidationError("PER_LINE outlier not yet supported")
        return data

    def create(self, validated_data):
        from datetime import date
        contract = self.context['contract']
        if 'effective_start_date' not in validated_data:
            validated_data['effective_start_date'] = date(1900, 1, 1)
        return ContractOutlierRule.objects.create(contract=contract, **validated_data)


class ContractStopLossRuleSerializer(serializers.ModelSerializer):
    """Phase 7: Stop-loss rule read."""

    class Meta:
        model = ContractStopLossRule
        fields = [
            'id', 'contract', 'cost_threshold', 'reimbursement_percentage',
            'priority', 'effective_start_date', 'effective_end_date',
        ]
        read_only_fields = ['id']


class ContractStopLossRuleCreateSerializer(serializers.Serializer):
    """Phase 7: Create stop-loss rule (contract from URL)."""
    cost_threshold = serializers.DecimalField(max_digits=12, decimal_places=2)
    reimbursement_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Percentage of cost paid above threshold (0 < x <= 100)",
    )
    priority = serializers.IntegerField(default=0)
    effective_start_date = serializers.DateField()
    effective_end_date = serializers.DateField(required=False, allow_null=True)

    def validate_reimbursement_percentage(self, value):
        if value is None:
            raise serializers.ValidationError("reimbursement_percentage is required.")
        if value <= 0 or value > 100:
            raise serializers.ValidationError(
                "reimbursement_percentage must be greater than 0 and less than or equal to 100."
            )
        return value

    def create(self, validated_data):
        contract = self.context['contract']
        return ContractStopLossRule.objects.create(contract=contract, **validated_data)


class ContractDetailSerializer(serializers.ModelSerializer):
    methodologies = ContractMethodologySerializer(many=True, read_only=True)
    outlier_rules = ContractOutlierRuleSerializer(many=True, read_only=True)
    stop_loss_rules = ContractStopLossRuleSerializer(many=True, read_only=True)
    primary_specialty_id = serializers.SerializerMethodField()
    primary_specialty = serializers.SerializerMethodField()

    class Meta:
        model = ProviderContract
        fields = [
            'contract_id', 'contract_name', 'status', 'legacy_contract_number',
            'effective_start_date', 'effective_end_date',
            'line_of_business', 'methodologies', 'outlier_rules', 'stop_loss_rules',
            'primary_specialty_id', 'primary_specialty',
        ]

    def get_primary_specialty_id(self, obj):
        org = getattr(obj, 'provider_org', None)
        if org and getattr(org, 'primary_specialty_id', None):
            return org.primary_specialty_id
        return None

    def get_primary_specialty(self, obj):
        org = getattr(obj, 'provider_org', None)
        if org and getattr(org, 'primary_specialty', None):
            s = org.primary_specialty
            return {'specialty_code': s.specialty_code, 'description': s.description}
        return None


class ContractCoveredEntitySerializer(serializers.ModelSerializer):
    """Read representation for GET /api/contracts/<id>/covered-entities/."""

    name = serializers.SerializerMethodField()
    identifier = serializers.SerializerMethodField()

    class Meta:
        model = ContractCoveredEntity
        fields = [
            'id', 'entity_type', 'name', 'identifier',
            'organization_id', 'provider_id', 'facility_id',
            'is_primary', 'effective_start_date', 'effective_end_date',
        ]
        read_only_fields = fields

    def get_name(self, obj) -> str:
        if obj.entity_type == ContractCoveredEntity.EntityType.ORG and obj.organization_id:
            return obj.organization.name
        if obj.entity_type == ContractCoveredEntity.EntityType.FACILITY and obj.facility_id:
            return obj.facility.name
        if obj.entity_type == ContractCoveredEntity.EntityType.PROVIDER and obj.provider_id:
            prov = obj.provider
            return f'Dr. {prov.first_name} {prov.last_name}'.strip()
        return obj.entity_type

    def get_identifier(self, obj) -> str:
        if obj.entity_type == ContractCoveredEntity.EntityType.ORG and obj.organization_id:
            org = obj.organization
            return org.npi or org.organization_id
        if obj.entity_type == ContractCoveredEntity.EntityType.FACILITY and obj.facility_id:
            return obj.facility.npi or str(obj.facility_id)
        if obj.entity_type == ContractCoveredEntity.EntityType.PROVIDER and obj.provider_id:
            return obj.provider.npi or str(obj.provider_id)
        return ''


class ContractCoveredEntityCreateSerializer(serializers.Serializer):
    """POST body for adding one covered entity to a DRAFT contract roster."""

    entity_type = serializers.ChoiceField(
        choices=[c.value for c in ContractCoveredEntity.EntityType],
    )
    organization = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider = serializers.IntegerField(required=False, allow_null=True)
    facility = serializers.IntegerField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(default=False)
    effective_start_date = serializers.DateField(required=False, allow_null=True)
    effective_end_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        from providers.models import Facility, Provider

        entity_type = attrs['entity_type']
        org_key = (attrs.get('organization') or '').strip() or None
        provider_id = attrs.get('provider')
        facility_id = attrs.get('facility')

        refs = sum([
            org_key is not None,
            provider_id is not None,
            facility_id is not None,
        ])
        if refs != 1:
            raise serializers.ValidationError(
                'Exactly one of organization, provider, or facility must be provided.',
            )

        if entity_type == ContractCoveredEntity.EntityType.ORG:
            if org_key is None:
                raise serializers.ValidationError(
                    {'organization': 'Required when entity_type is ORG.'},
                )
            if provider_id is not None or facility_id is not None:
                raise serializers.ValidationError(
                    'Only organization may be set when entity_type is ORG.',
                )
            org = ProviderOrganization.objects.filter(organization_id=org_key).first()
            if org is None:
                raise serializers.ValidationError(
                    {'organization': f'ProviderOrganization {org_key!r} not found.'},
                )
            attrs['_organization'] = org

        elif entity_type == ContractCoveredEntity.EntityType.PROVIDER:
            if provider_id is None:
                raise serializers.ValidationError(
                    {'provider': 'Required when entity_type is PROVIDER.'},
                )
            if org_key is not None or facility_id is not None:
                raise serializers.ValidationError(
                    'Only provider may be set when entity_type is PROVIDER.',
                )
            try:
                attrs['_provider'] = Provider.objects.get(pk=provider_id)
            except Provider.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {'provider': f'Provider {provider_id} not found.'},
                ) from exc

        elif entity_type == ContractCoveredEntity.EntityType.FACILITY:
            if facility_id is None:
                raise serializers.ValidationError(
                    {'facility': 'Required when entity_type is FACILITY.'},
                )
            if org_key is not None or provider_id is not None:
                raise serializers.ValidationError(
                    'Only facility may be set when entity_type is FACILITY.',
                )
            try:
                attrs['_facility'] = Facility.objects.get(pk=facility_id)
            except Facility.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {'facility': f'Facility {facility_id} not found.'},
                ) from exc

        return attrs

    def create(self, validated_data):
        contract = self.context['contract']
        entity = ContractCoveredEntity.objects.create(
            contract=contract,
            entity_type=validated_data['entity_type'],
            organization=validated_data.get('_organization'),
            provider=validated_data.get('_provider'),
            facility=validated_data.get('_facility'),
            is_primary=validated_data.get('is_primary', False),
            effective_start_date=validated_data.get('effective_start_date'),
            effective_end_date=validated_data.get('effective_end_date'),
        )
        return entity


class ContractScopeUnifiedSerializer(serializers.ModelSerializer):
    """Read representation for GET /api/contracts/<id>/scope/ (Exhibit B)."""

    product_name = serializers.SerializerMethodField()
    product_code = serializers.SerializerMethodField()
    network_id = serializers.SerializerMethodField()

    class Meta:
        model = ContractScopeUnified
        fields = [
            'id', 'product_id', 'product_name', 'product_code',
            'lob_code', 'network_id',
            'effective_date', 'termination_date', 'priority',
        ]
        read_only_fields = fields

    def get_product_name(self, obj) -> str | None:
        if obj.product_id and obj.product:
            return obj.product.name
        return None

    def get_product_code(self, obj) -> str | None:
        if obj.product_id and obj.product:
            return obj.product.product_code
        return None

    def get_network_id(self, obj) -> str | None:
        contract = obj.contract
        if contract and contract.network_id:
            return contract.network_id
        return None


class ContractScopeUnifiedCreateSerializer(serializers.Serializer):
    """POST body for adding product scope to a DRAFT contract."""

    product_id = serializers.IntegerField(min_value=1)
    lob_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    effective_date = serializers.DateField(required=False, allow_null=True)
    termination_date = serializers.DateField(required=False, allow_null=True)

    def validate_product_id(self, value: int) -> int:
        from products.models import Product

        if not Product.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'Product {value} not found.')
        return value

    def create(self, validated_data):
        from core.services.scope_unified_sync import upsert_unified_product_scope

        contract = self.context['contract']
        product_id = validated_data['product_id']
        lob_raw = validated_data.get('lob_code')
        lob_code = (lob_raw or '').strip() if lob_raw is not None else ''
        if not lob_code:
            lob_code = (contract.line_of_business or '').strip() or None
        if not lob_code:
            from products.models import Product
            product = Product.objects.select_related('lob').get(pk=product_id)
            lob_code = product.lob.code if product.lob else None
        if not lob_code:
            raise serializers.ValidationError(
                {'lob_code': 'LOB is required when contract and product have no LOB.'},
            )

        effective_date = validated_data.get('effective_date') or contract.effective_start_date
        row, _created = upsert_unified_product_scope(
            contract_id=contract.contract_id,
            product_id=product_id,
            lob_code=lob_code,
            effective_date=effective_date,
            termination_date=validated_data.get('termination_date'),
        )
        return row


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
    # Phase 2B: blank = inherit from contract methodology
    methodology_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    multiplier = serializers.DecimalField(
        max_digits=6, decimal_places=4, required=False, default=1
    )
    flat_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    base_fee_schedule_id = serializers.IntegerField(required=False, allow_null=True)
    effective_start_date = serializers.DateField(required=True)
    effective_end_date = serializers.DateField(required=False, allow_null=True)
    claim_type = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    site_of_service = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    conditions = serializers.ListField(
        child=ConditionCreateSerializer(),
        required=False,
        default=list,
    )

    def create(self, validated_data):
        contract = self.context['contract']
        conditions_data = validated_data.pop('conditions', [])
        claim_type = validated_data.pop('claim_type', None) or ''
        site_of_service = validated_data.pop('site_of_service', None) or ''
        rule = PricingRule.objects.create(
            contract=contract,
            status=PricingRule.RuleStatus.DRAFT,
            rule_name=validated_data.get('rule_name') or '',
            rule_type=validated_data.get('rule_type', 'BASE'),
            methodology_code=validated_data.get('methodology_code') or '',
            multiplier=validated_data.get('multiplier', 1),
            flat_rate=validated_data.get('flat_rate'),
            base_fee_schedule_id=validated_data.get('base_fee_schedule_id'),
            effective_start_date=validated_data['effective_start_date'],
            effective_end_date=validated_data.get('effective_end_date'),
            claim_type=claim_type or None,
            site_of_service=site_of_service or None,
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
    methodology_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    multiplier = serializers.DecimalField(
        max_digits=6, decimal_places=4, required=False, allow_null=True
    )
    flat_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    base_fee_schedule_id = serializers.IntegerField(required=False, allow_null=True)
    effective_start_date = serializers.DateField(required=False)
    effective_end_date = serializers.DateField(required=False, allow_null=True)
    claim_type = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    site_of_service = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
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
    locality_code = serializers.SerializerMethodField()
    geo_id = serializers.SerializerMethodField()

    class Meta:
        model = FeeSchedule
        fields = [
            'fee_schedule_id', 'name', 'effective_date', 'version',
            'effective_year', 'effective_start_date', 'effective_end_date',
            'schedule_type', 'source', 'geo_id', 'locality_code',
        ]

    def get_geo_id(self, obj):
        return getattr(obj, 'geo_id', None)

    def get_locality_code(self, obj):
        return obj.geo.locality_code if getattr(obj, 'geo', None) else None


# --- Step 11 Milestone C: Bulk claim pricing ---

class BulkPricingClaimItem(serializers.Serializer):
    """Single claim entry inside a bulk pricing request. Same shape as PricingClaimRequest."""
    contract_id = serializers.CharField(max_length=100)
    lines = serializers.ListField(child=PricingClaimLineRequest())
    service_date = serializers.DateField(required=False, allow_null=True)
    pricing_date = serializers.DateField(required=False, allow_null=True)
    claim_type = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, default=None)
    product_id = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    network_id = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)

    def to_internal_value(self, data):
        if isinstance(data.get('contract_id'), int):
            data = {**data, 'contract_id': str(data['contract_id'])}
        return super().to_internal_value(data)


class BulkPricingClaimRequest(serializers.Serializer):
    """
    Request body for POST /api/price-claims-bulk/.
    Accepts a list of claim payloads; each may reference a different contract.
    """
    claims = serializers.ListField(
        child=BulkPricingClaimItem(),
        min_length=1,
        max_length=500,
    )


class BulkPricingResultSerializer(serializers.Serializer):
    """
    Response for POST /api/price-claims-bulk/.
    Returns all claim results plus aggregate metadata.
    """
    total_claims = serializers.IntegerField()
    priced_claims = serializers.IntegerField()
    results = serializers.ListField(child=ClaimPricingResultSerializer())
    request_time_ms = serializers.FloatField(required=False)


# --- Step 10: Contract validation serializers ---

class ConflictErrorSerializer(serializers.Serializer):
    """
    Serializer for a single ConflictError returned by ValidationService.
    Read-only: used for API output only.
    """
    conflict_type = serializers.CharField()
    severity = serializers.CharField()
    message = serializers.CharField()
    affected_objects = serializers.ListField(child=serializers.DictField())
    suggested_action = serializers.CharField(allow_blank=True, default="")


class ContractValidationResponseSerializer(serializers.Serializer):
    """
    Response for POST /api/validate-contract/<id>/.
    """
    contract_id = serializers.IntegerField()
    error_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    conflicts = ConflictErrorSerializer(many=True)


class BulkValidationRequestSerializer(serializers.Serializer):
    """Body for POST /api/validate-contracts/bulk/."""
    contract_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_contract_ids(self, ids):
        from core.services.validation_service import BULK_VALIDATE_MAX_CONTRACT_IDS
        if len(ids) > BULK_VALIDATE_MAX_CONTRACT_IDS:
            raise serializers.ValidationError(
                f'At most {BULK_VALIDATE_MAX_CONTRACT_IDS} contract_ids per request.',
            )
        return ids


class BulkContractValidationRowSerializer(serializers.Serializer):
    """One row in the bulk validation response."""
    contract_id = serializers.IntegerField()
    error_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    conflicts = ConflictErrorSerializer(many=True)
    errors = serializers.CharField(required=False, allow_blank=True)


# --- Step 12b: Version lifecycle serializers ---

class ContractVersionAuditSerializer(serializers.ModelSerializer):
    """Read-only audit record for a ContractVersion lifecycle transition."""
    changed_by_username = serializers.SerializerMethodField()

    class Meta:
        model = ContractVersionAudit
        fields = [
            'id', 'version', 'change_type',
            'previous_status', 'new_status',
            'timestamp', 'changed_by_username', 'metadata',
        ]
        read_only_fields = fields

    def get_changed_by_username(self, obj) -> str:
        return obj.changed_by.username if obj.changed_by else ''


class ContractVersionSerializer(serializers.ModelSerializer):
    """Full read representation of a ContractVersion including audit trail."""
    audit_records = ContractVersionAuditSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ContractVersion
        fields = [
            'version_id', 'contract', 'version_number',
            'effective_start_date', 'effective_end_date',
            'status', 'status_display', 'notes', 'created_at',
            'audit_records',
        ]
        read_only_fields = ['version_id', 'created_at', 'status', 'audit_records']


class VersionLifecycleResponseSerializer(serializers.Serializer):
    """
    Thin response for POST .../activate/ and .../archive/ endpoints.
    Returns the new status plus the version_id so callers can update their cache.
    """
    version_id = serializers.IntegerField()
    previous_status = serializers.CharField()
    new_status = serializers.CharField()


class ContractAmendmentSerializer(serializers.ModelSerializer):
    version_id = serializers.IntegerField(source='version.version_id', read_only=True, allow_null=True)
    version_number = serializers.IntegerField(source='version.version_number', read_only=True, allow_null=True)
    version_status = serializers.CharField(source='version.status', read_only=True, allow_null=True)

    class Meta:
        model = ContractAmendment
        fields = [
            'id', 'contract', 'version_id', 'version_number', 'version_status',
            'amendment_number', 'effective_date', 'description', 'what_changed',
            'status', 'created_at',
        ]
        read_only_fields = fields


class ContractAmendmentCreateSerializer(serializers.Serializer):
    amendment_number = serializers.CharField(max_length=50)
    effective_date = serializers.DateField()
    description = serializers.CharField()


# --- Step 12e: Contract Explorer (read-only nested tree) --------------------

class ExplorerMethodologySerializer(serializers.ModelSerializer):
    """Read-only methodology for explorer; includes version_id."""
    version_id = serializers.IntegerField(read_only=True, allow_null=True)
    fee_schedule_id = serializers.IntegerField(read_only=True, allow_null=True)
    contract_term_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ContractMethodology
        fields = [
            'id', 'methodology_type', 'version_id', 'effective_date', 'termination_date',
            'priority', 'claim_type', 'site_of_service', 'base_percentage', 'conversion_factor',
            'contract_term_id', 'fee_schedule_id', 'conditions',
        ]
        read_only_fields = ['id']


class ExplorerPricingRuleSerializer(serializers.ModelSerializer):
    """Read-only pricing rule with conditions for explorer."""
    contract_id = serializers.IntegerField(read_only=True)
    version_id = serializers.IntegerField(read_only=True, allow_null=True)
    base_fee_schedule_id = serializers.IntegerField(read_only=True, allow_null=True)
    conditions = RuleConditionSerializer(many=True, read_only=True)

    class Meta:
        model = PricingRule
        fields = [
            'rule_id', 'rule_name', 'methodology_code', 'rule_type', 'contract_id', 'status',
            'version_id', 'specificity_score', 'effective_start_date', 'effective_end_date',
            'multiplier', 'flat_rate', 'base_fee_schedule_id', 'conditions',
        ]
        read_only_fields = ['rule_id']


class ExplorerCarveoutSerializer(serializers.ModelSerializer):
    """Read-only carve-out for explorer."""
    version_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContractCarveout
        fields = [
            'carveout_id', 'version_id', 'code_type', 'code_value', 'carveout_methodology',
            'carveout_percentage', 'carveout_rate', 'status', 'conditions',
        ]
        read_only_fields = ['carveout_id']


class ExplorerCapFloorSerializer(serializers.ModelSerializer):
    """Read-only cap/floor for explorer."""
    version_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContractCapFloor
        fields = [
            'cap_floor_id', 'version_id', 'scope', 'cap_type', 'value', 'percentage',
            'code_value', 'priority', 'effective_start_date', 'effective_end_date', 'status', 'conditions',
        ]
        read_only_fields = ['cap_floor_id']


class ExplorerBlendingRuleSerializer(serializers.ModelSerializer):
    """Read-only blending rule for explorer."""
    version_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContractBlendingRule
        fields = [
            'blending_rule_id', 'version_id', 'blend_type', 'scope', 'primary_methodology',
            'secondary_methodology', 'blend_percentage', 'priority',
            'effective_start_date', 'effective_end_date', 'status', 'conditions',
        ]
        read_only_fields = ['blending_rule_id']


class ExplorerStopLossRuleSerializer(serializers.ModelSerializer):
    """Read-only stop-loss rule for explorer; includes version_id."""
    contract_id = serializers.IntegerField(read_only=True)
    version_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ContractStopLossRule
        fields = [
            'id', 'contract_id', 'version_id', 'cost_threshold', 'reimbursement_percentage',
            'priority', 'effective_start_date', 'effective_end_date',
        ]
        read_only_fields = ['id']


class ExplorerOutlierRuleSerializer(serializers.ModelSerializer):
    """Read-only outlier rule for explorer; includes version_id."""
    contract_id = serializers.IntegerField(read_only=True)
    version_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ContractOutlierRule
        fields = [
            'id', 'contract_id', 'version_id', 'threshold_amount', 'threshold_scope',
            'reimbursement_percentage', 'cost_to_charge_ratio',
            'priority', 'effective_start_date', 'effective_end_date',
        ]
        read_only_fields = ['id']


class ExplorerVersionSerializer(serializers.ModelSerializer):
    """One version with all nested explorer data."""
    methodologies = ExplorerMethodologySerializer(many=True, read_only=True)
    rules = ExplorerPricingRuleSerializer(many=True, source='pricing_rules', read_only=True)
    carveouts = ExplorerCarveoutSerializer(many=True, read_only=True)
    cap_floors = ExplorerCapFloorSerializer(many=True, read_only=True)
    blending_rules = ExplorerBlendingRuleSerializer(many=True, read_only=True)
    stop_loss_rules = ExplorerStopLossRuleSerializer(many=True, read_only=True)
    outlier_rules = ExplorerOutlierRuleSerializer(many=True, read_only=True)

    class Meta:
        model = ContractVersion
        fields = [
            'version_id', 'version_number', 'status', 'effective_start_date', 'effective_end_date',
            'notes', 'pricing_engine_mode', 'claim_level_drg_enabled',
            'methodologies', 'rules', 'carveouts', 'cap_floors',
            'blending_rules', 'stop_loss_rules', 'outlier_rules',
        ]
        read_only_fields = ['version_id']


class ContractExplorerSerializer(serializers.ModelSerializer):
    """
    Step 12e: Full contract tree for GET /api/contracts/<id>/explorer/.
    Serialized output (to_representation): contract {id, legacy_contract_number, contract_name},
    open_conflict_counts {errors, warnings}, versions[] (each with rules[], not pricing_rules).
    """
    open_error_count = serializers.SerializerMethodField()
    open_warning_count = serializers.SerializerMethodField()
    versions = ExplorerVersionSerializer(many=True, read_only=True)

    class Meta:
        model = ProviderContract
        fields = [
            'contract_id', 'contract_name', 'status', 'legacy_contract_number',
            'effective_start_date', 'effective_end_date',
            'open_error_count', 'open_warning_count',
            'versions',
        ]
        read_only_fields = ['contract_id']

    def get_open_error_count(self, obj) -> int:
        return obj.validation_results.filter(
            resolved=False,
            severity=ValidationResult.SEVERITY_ERROR,
        ).count()

    def get_open_warning_count(self, obj) -> int:
        return obj.validation_results.filter(
            resolved=False,
            severity=ValidationResult.SEVERITY_WARNING,
        ).count()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            'contract': {
                'id': data['contract_id'],
                'legacy_contract_number': data.get('legacy_contract_number'),
                'contract_name': data['contract_name'],
            },
            'open_conflict_counts': {
                'errors': data['open_error_count'],
                'warnings': data['open_warning_count'],
            },
            'versions': data['versions'],
        }


# --- Stage 5: Context-driven pricing APIs ---


class ClaimLineInputSerializer(serializers.Serializer):
    procedure_code = serializers.CharField(max_length=10)
    units = serializers.DecimalField(max_digits=8, decimal_places=2, default=1)
    modifier_1 = serializers.CharField(max_length=2, allow_blank=True, default='')
    modifier_2 = serializers.CharField(max_length=2, allow_blank=True, default='')
    modifier_3 = serializers.CharField(max_length=2, allow_blank=True, default='')
    modifier_4 = serializers.CharField(max_length=2, allow_blank=True, default='')
    billed_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    revenue_code = serializers.CharField(max_length=4, allow_blank=True, default='')
    place_of_service = serializers.CharField(max_length=2, allow_blank=True, default='')
    diagnosis_codes = serializers.ListField(
        child=serializers.CharField(max_length=8),
        required=False,
        default=list,
    )


class RepriceClaimRequestSerializer(serializers.Serializer):
    """POST /api/reprice-claim/ — full context resolution path."""
    billing_npi = serializers.CharField(max_length=15)
    rendering_npi = serializers.CharField(max_length=15, required=False, allow_blank=True)
    facility_npi = serializers.CharField(max_length=15, required=False, allow_blank=True)
    member_id = serializers.CharField(max_length=64)
    service_date = serializers.DateField()
    claim_type = serializers.ChoiceField(
        choices=['professional', 'institutional'],
        default='professional',
    )
    lines = ClaimLineInputSerializer(many=True, min_length=1)


class RepriceClaimBatchRequestSerializer(serializers.Serializer):
    """POST /api/reprice-claim-batch/ — up to 50 claims, each context-resolved."""
    claims = RepriceClaimRequestSerializer(many=True, min_length=1, max_length=50)
