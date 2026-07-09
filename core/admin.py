from django.contrib import admin

from core.models import (
    ContractRateBasis,
    ContractEscalator,
    ContractScopeUnified,
    PublishedFeeSchedule,
    PublishedFeeScheduleRate,
)


class PublishedFeeScheduleRateInline(admin.TabularInline):
    model = PublishedFeeScheduleRate
    extra = 1
    fields = ('code', 'amount', 'unit')


@admin.register(PublishedFeeSchedule)
class PublishedFeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'basis_type', 'year', 'source', 'effective_start_date', 'effective_end_date', 'base_rate')
    list_filter = ('basis_type', 'year')
    search_fields = ('name', 'source')
    inlines = [PublishedFeeScheduleRateInline]


@admin.register(PublishedFeeScheduleRate)
class PublishedFeeScheduleRateAdmin(admin.ModelAdmin):
    list_display = ('schedule', 'code', 'amount', 'unit')
    list_filter = ('schedule__basis_type',)
    search_fields = ('code', 'schedule__name')


@admin.register(ContractRateBasis)
class ContractRateBasisAdmin(admin.ModelAdmin):
    list_display = ('pricing_rule', 'schedule', 'percentage', 'updated_at')
    list_filter = ('schedule__basis_type',)
    search_fields = ('pricing_rule__rule_name', 'schedule__name')
    raw_id_fields = ('pricing_rule',)


@admin.register(ContractEscalator)
class ContractEscalatorAdmin(admin.ModelAdmin):
    list_display = (
        'contract',
        'version',
        'annual_percentage',
        'cap_percentage',
        'base_year',
        'effective_start_date',
        'effective_end_date',
    )
    list_filter = ('base_year',)
    search_fields = ('contract__contract_name', 'contract__legacy_contract_number')
    raw_id_fields = ('contract', 'version')


@admin.register(ContractScopeUnified)
class ContractScopeUnifiedAdmin(admin.ModelAdmin):
    list_display = (
        'contract',
        'lob_code',
        'product',
        'specialty_code',
        'site_of_service',
        'priority',
        'migration_source',
        'effective_date',
        'termination_date',
    )
    list_filter = ('migration_source', 'lob_code')
    search_fields = ('contract__contract_name', 'lob_code')
    raw_id_fields = ('contract', 'product', 'specialty_code', 'geo')
