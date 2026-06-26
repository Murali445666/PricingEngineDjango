from django.contrib import admin

from providers.models import (
    Facility,
    FacilityNetworkParticipation,
    Provider,
    ProviderAffiliation,
    ProviderNetworkParticipation,
)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ('npi', 'first_name', 'last_name', 'primary_specialty', 'status')
    search_fields = ('npi', 'last_name')
    list_filter = ('status',)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ('npi', 'name', 'facility_type', 'status')
    search_fields = ('npi', 'name', 'ccn')
    list_filter = ('facility_type', 'status')


@admin.register(ProviderAffiliation)
class ProviderAffiliationAdmin(admin.ModelAdmin):
    list_display = ('provider', 'organization', 'role', 'effective_date', 'termination_date')
    list_filter = ('role',)


@admin.register(ProviderNetworkParticipation)
class ProviderNetworkParticipationAdmin(admin.ModelAdmin):
    list_display = (
        'organization',
        'provider',
        'network',
        'status',
        'effective_date',
        'termination_date',
    )
    list_filter = ('status',)


@admin.register(FacilityNetworkParticipation)
class FacilityNetworkParticipationAdmin(admin.ModelAdmin):
    list_display = ('facility', 'network', 'status', 'effective_date')
    list_filter = ('status',)
