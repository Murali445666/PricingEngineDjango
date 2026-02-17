from django.contrib import admin
from .models import (
    ProviderOrganization, 
    PayerNetwork, 
    ProviderContract, 
    FeeSchedule, 
    FeeScheduleRate, 
    PricingRule, 
    PricingRuleCondition,
    RefProcedureCode,
    RefModifier
)

@admin.register(ProviderOrganization)
class ProviderOrganizationAdmin(admin.ModelAdmin):
    list_display = ('organization_id', 'name', 'npi')
    search_fields = ('name', 'organization_id')

@admin.register(PayerNetwork)
class PayerNetworkAdmin(admin.ModelAdmin):
    list_display = ('network_id', 'network_name', 'payer_org')

@admin.register(ProviderContract)
class ProviderContractAdmin(admin.ModelAdmin):
    # Updated to use 'provider_org' instead of old 'organization'
    list_display = ('contract_id', 'contract_name', 'provider_org', 'status', 'effective_start_date')
    list_filter = ('status', 'provider_org')

@admin.register(FeeSchedule)
class FeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('fee_schedule_id', 'name', 'effective_date', 'version')

@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    # Updated to use 'methodology_code' instead of relationship
    list_display = ('rule_id', 'rule_name', 'contract', 'methodology_code', 'multiplier', 'specificity_score')
    list_filter = ('methodology_code', 'rule_type')

@admin.register(PricingRuleCondition)
class PricingRuleConditionAdmin(admin.ModelAdmin):
    list_display = ('condition_id', 'pricing_rule', 'attribute_name', 'operator', 'attribute_value')

@admin.register(RefProcedureCode)
class RefProcedureCodeAdmin(admin.ModelAdmin):
    list_display = ('code_id', 'code_type', 'description', 'work_rvu')
    search_fields = ('code_id', 'description')
    list_filter = ('code_type',)

@admin.register(RefModifier)
class RefModifierAdmin(admin.ModelAdmin):
    list_display = ('modifier_code', 'description', 'percentage_adjustment')