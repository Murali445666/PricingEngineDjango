from datetime import date

from django.db.models import Q

from products.models import Network, ProductNetworkConfig
from providers.models import ProviderNetworkParticipation


class NetworkLookupService:
    """Read-only lookups for product-network resolution and org participation."""

    def resolve_network(
        self, product_id: int, claim_type: str, service_date: date
    ) -> Network | None:
        """
        Return the Network for a product on service_date.
        Match on claim_type = given value OR claim_type = 'ALL'.
        Filter: effective_date <= service_date, termination_date is null
        OR termination_date >= service_date.
        If multiple match, prefer specific claim_type over ALL.
        Return None if not found.
        """
        claim_type = (claim_type or '').strip().upper()
        configs = ProductNetworkConfig.objects.filter(
            product_id=product_id,
            effective_date__lte=service_date,
        ).filter(
            Q(termination_date__isnull=True) | Q(termination_date__gte=service_date)
        ).filter(
            Q(claim_type=claim_type) | Q(claim_type='ALL')
        ).select_related('network')

        specific = configs.filter(claim_type=claim_type).first()
        if specific is not None:
            return specific.network

        fallback = configs.filter(claim_type='ALL').first()
        if fallback is not None:
            return fallback.network

        return None

    def check_org_participation(
        self, org_id: str, network_id: int, service_date: date
    ) -> str | None:
        """
        Check ProviderNetworkParticipation for an org against a products.Network id.
        First tries matching on network_new_id = network_id.
        Falls back to matching on legacy network FK where network.legacy_payer_network
        matches the participation's network field.
        Returns status string or None.
        """
        base_qs = ProviderNetworkParticipation.objects.filter(
            organization_id=org_id,
            effective_date__lte=service_date,
        ).filter(
            Q(termination_date__isnull=True) | Q(termination_date__gte=service_date)
        )

        participation = base_qs.filter(network_new_id=network_id).first()
        if participation is not None:
            return participation.status

        legacy_network = Network.objects.filter(pk=network_id).first()
        if legacy_network is None or legacy_network.legacy_payer_network_id is None:
            return None

        participation = base_qs.filter(
            network_id=legacy_network.legacy_payer_network_id,
        ).first()
        if participation is not None:
            return participation.status

        return None
