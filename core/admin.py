from django.contrib import admin, messages
from .models import (
    ProviderOrganization,
    PayerNetwork,
    ProviderContract,
    ContractScope,
    ContractProductScope,
    ContractProviderParticipation,
    ContractVersion,
    ContractVersionAudit,
    ContractTerm,
    PerDiemRate,
    ModifierAdjustment,
    ContractFlatRateOverride,
    FacilityBaseRate,
    CaseRateDefinition,
    MPPRDefinition,
    MPPRScope,
    CodeGroup,
    CodeGroupMember,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
    ContractBaseRate,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
    ContractOutlierRule,
    ContractStopLossRule,
    RefProcedureCode,
    RefModifier,
    ValidationResult,
)

@admin.register(ProviderOrganization)
class ProviderOrganizationAdmin(admin.ModelAdmin):
    list_display = ('organization_id', 'name', 'npi')
    search_fields = ('name', 'organization_id')


@admin.register(PayerNetwork)
class PayerNetworkAdmin(admin.ModelAdmin):
    list_display = ('network_id', 'network_name', 'payer_org')


@admin.register(ContractProductScope)
class ContractProductScopeAdmin(admin.ModelAdmin):
    list_display = ('contract', 'lob_code', 'product', 'effective_date')
    search_fields = ('lob_code',)

class ValidationResultInline(admin.TabularInline):
    """
    Step 10: Read-only inline showing open validation conflicts on a contract.
    Appears inside ProviderContractAdmin.
    """
    model = ValidationResult
    extra = 0
    can_delete = False
    show_change_link = False
    fields = ('validated_at', 'severity', 'conflict_type', 'message', 'suggested_action', 'resolved')
    readonly_fields = ('validated_at', 'severity', 'conflict_type', 'message', 'suggested_action')

    def get_queryset(self, request):
        return super().get_queryset(request).filter(resolved=False).order_by(
            'severity', 'conflict_type'
        )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProviderContract)
class ProviderContractAdmin(admin.ModelAdmin):
    list_display = ('contract_id', 'contract_name', 'provider_org', 'status', 'effective_start_date')
    list_filter = ('status', 'provider_org')
    inlines = [ValidationResultInline]
    actions = ['run_validation']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Run validation after save and surface warnings/errors as admin messages
        try:
            from core.services.validation_service import ValidationService
            conflicts = ValidationService.validate_contract(obj.pk)
            if conflicts:
                ValidationService.save_validation_results(obj, conflicts)
                errors = [c for c in conflicts if c.severity == "ERROR"]
                warnings = [c for c in conflicts if c.severity == "WARNING"]
                for c in errors:
                    self.message_user(
                        request,
                        f"[CONFLICT ERROR] {c.conflict_type}: {c.message}",
                        level=messages.ERROR,
                    )
                for c in warnings:
                    self.message_user(
                        request,
                        f"[CONFLICT WARNING] {c.conflict_type}: {c.message}",
                        level=messages.WARNING,
                    )
            else:
                self.message_user(
                    request,
                    "Contract validation passed — no conflicts detected.",
                    level=messages.SUCCESS,
                )
        except Exception as exc:
            self.message_user(
                request,
                f"Validation check failed: {exc}",
                level=messages.WARNING,
            )

    @admin.action(description="Run contract conflict validation")
    def run_validation(self, request, queryset):
        from core.services.validation_service import ValidationService
        for contract in queryset:
            conflicts = ValidationService.validate_contract(contract.pk)
            ValidationService.save_validation_results(contract, conflicts)
            error_count = sum(1 for c in conflicts if c.severity == "ERROR")
            warning_count = sum(1 for c in conflicts if c.severity == "WARNING")
            self.message_user(
                request,
                f"Contract {contract.pk} ({contract.contract_name}): "
                f"{error_count} error(s), {warning_count} warning(s).",
                level=messages.ERROR if error_count else (
                    messages.WARNING if warning_count else messages.SUCCESS
                ),
            )


@admin.register(ContractScope)
class ContractScopeAdmin(admin.ModelAdmin):
    list_display = ('id', 'contract', 'priority', 'line_of_business', 'specialty_code', 'site_of_service', 'geo')
    raw_id_fields = ('contract', 'geo', 'specialty_code')


@admin.register(ContractProviderParticipation)
class ContractProviderParticipationAdmin(admin.ModelAdmin):
    list_display = ('id', 'contract', 'organization', 'npi', 'effective_start_date', 'effective_end_date', 'created_at')
    raw_id_fields = ('contract', 'organization')


class ContractVersionAuditInline(admin.TabularInline):
    """Read-only audit trail shown inside ContractVersionAdmin."""
    model = ContractVersionAudit
    extra = 0
    can_delete = False
    show_change_link = False
    fields = ('timestamp', 'change_type', 'previous_status', 'new_status', 'changed_by', 'metadata')
    readonly_fields = fields
    ordering = ('-timestamp',)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    list_display = (
        'version_id', 'contract', 'version_number',
        'effective_start_date', 'effective_end_date',
        'claim_level_drg_enabled', 'status_badge', 'created_at',
    )
    list_filter = ('status',)
    raw_id_fields = ('contract',)
    readonly_fields = ('status', 'created_at')
    inlines = [ContractVersionAuditInline]
    actions = ['activate_versions', 'archive_versions']

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'DRAFT': '#888',
            'ACTIVE': '#22863a',
            'SUPERSEDED': '#b08800',
            'ARCHIVED': '#cb2431',
        }
        colour = colours.get(obj.status, '#888')
        return (
            f'<span style="color:{colour};font-weight:600">{obj.status}</span>'
        )
    status_badge.allow_tags = True

    def get_readonly_fields(self, request, obj=None):
        """Prevent editing ACTIVE or SUPERSEDED versions. Use only concrete DB fields to avoid RelatedManager 500."""
        if obj and obj.status in ('ACTIVE', 'SUPERSEDED'):
            return [f.name for f in obj._meta.concrete_fields]
        return self.readonly_fields

    @admin.action(description="Activate selected versions (DRAFT → ACTIVE)")
    def activate_versions(self, request, queryset):
        from core.services.rule_lifecycle_service import RuleLifecycleService
        from django.core.exceptions import ValidationError as DjangoValidationError

        for version in queryset:
            try:
                RuleLifecycleService.activate_version(
                    version.version_id,
                    user=request.user,
                )
                self.message_user(
                    request,
                    f"Version {version.version_id} activated successfully.",
                    level=messages.SUCCESS,
                )
            except DjangoValidationError as exc:
                self.message_user(request, f"Version {version.version_id}: {exc.message}", level=messages.ERROR)

    @admin.action(description="Archive selected versions (DRAFT/SUPERSEDED → ARCHIVED)")
    def archive_versions(self, request, queryset):
        from core.services.rule_lifecycle_service import RuleLifecycleService
        from django.core.exceptions import ValidationError as DjangoValidationError

        for version in queryset:
            try:
                RuleLifecycleService.archive_version(
                    version.version_id,
                    user=request.user,
                )
                self.message_user(
                    request,
                    f"Version {version.version_id} archived.",
                    level=messages.SUCCESS,
                )
            except DjangoValidationError as exc:
                self.message_user(request, f"Version {version.version_id}: {exc.message}", level=messages.ERROR)


@admin.register(ContractVersionAudit)
class ContractVersionAuditAdmin(admin.ModelAdmin):
    list_display = ('id', 'version', 'change_type', 'previous_status', 'new_status', 'changed_by', 'timestamp')
    list_filter = ('change_type', 'new_status')
    readonly_fields = ('version', 'change_type', 'previous_status', 'new_status', 'changed_by', 'timestamp', 'metadata')
    raw_id_fields = ('version',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContractTerm)
class ContractTermAdmin(admin.ModelAdmin):
    """Phase B: Contract/version-scoped multiplier reference. When a rule has contract_term_id set, loader uses this multiplier."""
    list_display = ('id', 'name', 'contract', 'version', 'multiplier', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract',)
    raw_id_fields = ('contract', 'version')
    search_fields = ('name',)


@admin.register(PerDiemRate)
class PerDiemRateAdmin(admin.ModelAdmin):
    """Phase D: Contract/version per diem rate. When a rule has per_diem_rate_id set, loader uses this for PER_DIEM."""
    list_display = ('id', 'contract', 'version', 'rate_amount', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract',)
    raw_id_fields = ('contract', 'version')


@admin.register(ModifierAdjustment)
class ModifierAdjustmentAdmin(admin.ModelAdmin):
    """Phase D: Contract/version modifier percentage override. Overrides RefModifier when same modifier_code."""
    list_display = ('id', 'contract', 'version', 'modifier_code', 'adjustment_type', 'adjustment_value', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract', 'modifier_code')
    raw_id_fields = ('contract', 'version')


@admin.register(ContractFlatRateOverride)
class ContractFlatRateOverrideAdmin(admin.ModelAdmin):
    """Phase D: Contract/version flat rate. When a rule has flat_rate_override_id set, loader uses this instead of rule.flat_rate."""
    list_display = ('id', 'contract', 'version', 'procedure_code', 'rate_amount', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract',)
    raw_id_fields = ('contract', 'version')


@admin.register(FacilityBaseRate)
class FacilityBaseRateAdmin(admin.ModelAdmin):
    """Phase E: Claim-level DRG/APC base rate. Used when claim_level_drg_enabled; payment = base_rate × RefDrg.relative_weight."""
    list_display = ('id', 'contract', 'version', 'facility_id', 'rate_type', 'base_rate', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract', 'rate_type')
    raw_id_fields = ('contract', 'version')


@admin.register(CaseRateDefinition)
class CaseRateDefinitionAdmin(admin.ModelAdmin):
    """Phase E: Claim-level case rate (lump sum per case_rate_code)."""
    list_display = ('id', 'contract', 'version', 'case_rate_code', 'lump_sum_amount', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract',)
    raw_id_fields = ('contract', 'version')


class MPPRScopeInline(admin.TabularInline):
    model = MPPRScope
    extra = 0
    raw_id_fields = ('code_group',)


@admin.register(MPPRDefinition)
class MPPRDefinitionAdmin(admin.ModelAdmin):
    """Phase F: Cross-line MPPR. Lines in scope ranked by rank_by; primary/secondary/tertiary pct applied."""
    list_display = ('id', 'name', 'contract', 'version', 'rank_by', 'primary_pct', 'secondary_pct', 'tertiary_pct', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract', 'rank_by')
    raw_id_fields = ('contract', 'version')
    inlines = [MPPRScopeInline]


@admin.register(MPPRScope)
class MPPRScopeAdmin(admin.ModelAdmin):
    """Phase F: Scope for MPPR (code_group or procedure_code)."""
    list_display = ('id', 'mppr_definition', 'code_group', 'procedure_code')
    raw_id_fields = ('mppr_definition', 'code_group')


class CodeGroupMemberInline(admin.TabularInline):
    model = CodeGroupMember
    extra = 1
    fk_name = 'code_group'


@admin.register(CodeGroup)
class CodeGroupAdmin(admin.ModelAdmin):
    """Phase C: Group of procedure codes for resolver condition attribute_name='code_group', attribute_value=code_group_id."""
    list_display = ('id', 'code_group_code', 'name', 'contract', 'version', 'effective_start_date', 'effective_end_date')
    list_filter = ('contract',)
    raw_id_fields = ('contract', 'version')
    search_fields = ('code_group_code', 'name')
    inlines = [CodeGroupMemberInline]


@admin.register(CodeGroupMember)
class CodeGroupMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'code_group', 'code_id', 'effective_start_date', 'effective_end_date')
    list_filter = ('code_group',)
    raw_id_fields = ('code_group',)
    search_fields = ('code_id',)


@admin.register(ContractBaseRate)
class ContractBaseRateAdmin(admin.ModelAdmin):
    list_display = ('base_rate_id', 'version', 'rate_type', 'base_rate')
    list_filter = ('rate_type',)
    raw_id_fields = ('version',)


@admin.register(FeeSchedule)
class FeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('fee_schedule_id', 'name', 'effective_date', 'version')


@admin.register(FeeScheduleRate)
class FeeScheduleRateAdmin(admin.ModelAdmin):
    list_display = ('rate_id', 'fee_schedule', 'code_id', 'rate_amount', 'effective_start_date', 'effective_end_date', 'year')
    list_filter = ('fee_schedule',)
    raw_id_fields = ('fee_schedule',)
    search_fields = ('code_id',)

@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ('rule_id', 'rule_name', 'contract', 'methodology_code', 'multiplier', 'contract_term', 'per_diem_rate', 'flat_rate_override', 'specificity_score')
    list_filter = ('methodology_code', 'rule_type')
    raw_id_fields = ('contract_term', 'per_diem_rate', 'flat_rate_override')

@admin.register(PricingRuleCondition)
class PricingRuleConditionAdmin(admin.ModelAdmin):
    list_display = ('condition_id', 'pricing_rule', 'attribute_name', 'operator', 'attribute_value')


@admin.register(ContractOutlierRule)
class ContractOutlierRuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'contract', 'threshold_amount', 'threshold_scope', 'priority', 'effective_start_date', 'effective_end_date')
    list_filter = ('threshold_scope',)
    raw_id_fields = ('contract',)


@admin.register(ContractStopLossRule)
class ContractStopLossRuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'contract', 'cost_threshold', 'reimbursement_percentage', 'priority', 'effective_start_date', 'effective_end_date')
    raw_id_fields = ('contract',)


@admin.register(RefProcedureCode)
class RefProcedureCodeAdmin(admin.ModelAdmin):
    list_display = ('code_id', 'code_type', 'description', 'work_rvu')
    search_fields = ('code_id', 'description')
    list_filter = ('code_type',)

@admin.register(ContractCarveout)
class ContractCarveoutAdmin(admin.ModelAdmin):
    list_display = ('carveout_id', 'version', 'code_type', 'code_value',
                    'carveout_methodology', 'carveout_percentage', 'carveout_rate')
    list_filter = ('carveout_methodology', 'code_type')
    raw_id_fields = ('version',)
    search_fields = ('code_value',)


@admin.register(ContractCapFloor)
class ContractCapFloorAdmin(admin.ModelAdmin):
    list_display = ('cap_floor_id', 'version', 'scope', 'cap_type', 'value',
                    'percentage', 'code_value', 'priority', 'effective_start_date', 'effective_end_date')
    list_filter = ('scope', 'cap_type')
    raw_id_fields = ('version',)


@admin.register(RefModifier)
class RefModifierAdmin(admin.ModelAdmin):
    list_display = ('modifier_code', 'description', 'percentage_adjustment')


@admin.register(ContractBlendingRule)
class ContractBlendingRuleAdmin(admin.ModelAdmin):
    list_display = (
        'blending_rule_id', 'version', 'blend_type', 'scope',
        'primary_methodology', 'secondary_methodology', 'blend_percentage',
        'priority', 'effective_start_date', 'effective_end_date',
    )
    list_filter = ('blend_type', 'scope', 'primary_methodology')
    raw_id_fields = ('version',)
    search_fields = ('primary_methodology', 'secondary_methodology')


@admin.register(ValidationResult)
class ValidationResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'contract', 'severity', 'conflict_type', 'message',
        'validated_at', 'resolved',
    )
    list_filter = ('severity', 'conflict_type', 'resolved')
    readonly_fields = (
        'contract', 'validated_at', 'conflict_type', 'severity',
        'message', 'affected_objects', 'suggested_action',
    )
    raw_id_fields = ('contract',)
    search_fields = ('conflict_type', 'message')
