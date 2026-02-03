from django.contrib import admin
from .models import ProviderOrganization, ProviderContract, FeeSchedule, PricingRule, PricingRuleCondition, PricingMethodology

class ConditionInline(admin.TabularInline):
    model = PricingRuleCondition
    extra = 1

@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    # CHANGED: Replaced 'rule_priority' with 'specificity_score'
    list_display = ('contract', 'methodology', 'rule_type', 'specificity_score', 'status')
    
    # NEW: Show the score but keep it read-only (since it's auto-calculated)
    readonly_fields = ('specificity_score',) 
    
    inlines = [ConditionInline]

@admin.register(ProviderContract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('contract_name', 'provider_org', 'status', 'effective_start_date')

admin.site.register(ProviderOrganization)
admin.site.register(FeeSchedule)
admin.site.register(PricingMethodology)