from datetime import date

from django.db.models import Q

from core.models import ProviderOrganization
from providers.models import Facility, Provider, ProviderAffiliation, ProviderNetworkParticipation


class ProviderLookupService:
    """Read-only lookups for provider, facility, affiliation, and network participation."""

    def resolve_org_by_billing_npi(self, npi: str) -> ProviderOrganization | None:
        """Look up ProviderOrganization by npi field. Returns None if not found."""
        if not npi:
            return None
        return ProviderOrganization.objects.filter(npi=npi).first()

    def resolve_provider_by_rendering_npi(self, npi: str) -> Provider | None:
        """Look up Provider by npi field. Returns None if not found."""
        if not npi:
            return None
        return Provider.objects.filter(npi=npi).first()

    def resolve_facility_by_npi(self, npi: str) -> Facility | None:
        """Look up Facility by npi field. Returns None if not found."""
        if not npi:
            return None
        return Facility.objects.filter(npi=npi).first()

    def check_affiliation(
        self, provider_id: int, org_id: str, service_date: date
    ) -> bool:
        """
        Return True if ProviderAffiliation exists for (provider, org) where
        effective_date <= service_date and (termination_date is null OR
        termination_date >= service_date).
        """
        return ProviderAffiliation.objects.filter(
            provider_id=provider_id,
            organization_id=org_id,
            effective_date__lte=service_date,
        ).filter(
            Q(termination_date__isnull=True)
            | Q(termination_date__gte=service_date)
        ).exists()

    def check_org_network_participation(
        self, org_id: str, network_id: str, service_date: date
    ) -> str | None:
        """
        Return the participation status ('IN_NETWORK', 'OUT_OF_NETWORK', 'TIER_1', 'TIER_2')
        for (organization, network) on service_date, or None if no record found.
        Uses effective_date / termination_date scoping.
        """
        participation = ProviderNetworkParticipation.objects.filter(
            organization_id=org_id,
            network_id=network_id,
            effective_date__lte=service_date,
        ).filter(
            Q(termination_date__isnull=True)
            | Q(termination_date__gte=service_date)
        ).first()
        if participation is None:
            return None
        return participation.status
