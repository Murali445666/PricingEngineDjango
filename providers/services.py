from datetime import date

from django.db.models import Q

from core.models import ProviderOrganization
from providers.models import Facility, Provider, ProviderAffiliation, ProviderNetworkParticipation


class OrgHierarchyDepthError(Exception):
    """Raised when parent_org traversal exceeds the maximum allowed depth."""


class ProviderLookupService:
    """Read-only lookups for provider, facility, affiliation, and network participation."""

    def resolve_org_by_billing_npi(self, npi: str) -> ProviderOrganization | None:
        """Look up ProviderOrganization by npi field. Returns None if not found."""
        if not npi:
            return None
        return ProviderOrganization.objects.filter(npi=npi).first()

    def list_orgs_by_billing_npi(self, npi: str) -> list[ProviderOrganization]:
        """All organizations sharing a billing NPI (for ambiguity detection)."""
        if not npi:
            return []
        return list(ProviderOrganization.objects.filter(npi=npi))

    def _org_ancestor_ids(
        self, org: ProviderOrganization, max_depth: int = 5
    ) -> set[str]:
        """organization_id set including org and parent_org chain upward."""
        seen: set[str] = set()
        current: ProviderOrganization | None = org
        depth = 0
        while current is not None:
            if current.organization_id in seen:
                break
            seen.add(current.organization_id)
            depth += 1
            if depth > max_depth:
                break
            parent_id = current.parent_org_id
            if not parent_id:
                break
            current = ProviderOrganization.objects.filter(
                organization_id=parent_id
            ).first()
        return seen

    def are_orgs_in_same_hierarchy_chain(
        self, org_a: ProviderOrganization, org_b: ProviderOrganization
    ) -> bool:
        """True when org_a and org_b lie on one parent/child chain (R5 hierarchy)."""
        chain_a = self._org_ancestor_ids(org_a)
        chain_b = self._org_ancestor_ids(org_b)
        return (
            org_b.organization_id in chain_a
            or org_a.organization_id in chain_b
        )

    def billing_org_ambiguity(self, npi: str) -> tuple[bool, list[str]]:
        """
        True when billing NPI maps to multiple orgs not on one parent/child chain.
        Returns (is_ambiguous, candidate organization_ids).
        """
        orgs = self.list_orgs_by_billing_npi(npi)
        if len(orgs) <= 1:
            return False, [o.organization_id for o in orgs]
        for i, org_a in enumerate(orgs):
            for org_b in orgs[i + 1 :]:
                if not self.are_orgs_in_same_hierarchy_chain(org_a, org_b):
                    return True, [o.organization_id for o in orgs]
        return False, [o.organization_id for o in orgs]

    def resolve_org_hierarchy(
        self, npi: str, service_date: date, max_depth: int = 5
    ) -> list[ProviderOrganization]:
        """
        Walk parent_org upward from the org matching billing NPI.
        Returns ordered list [leaf, group, idn, ...] (most specific first).
        """
        leaf = self.resolve_org_by_billing_npi(npi)
        if leaf is None:
            return []

        hierarchy: list[ProviderOrganization] = []
        seen_ids: set[str] = set()
        current = leaf
        depth = 0

        while current is not None:
            if current.organization_id in seen_ids:
                raise OrgHierarchyDepthError(
                    f'Cycle detected in parent_org chain at {current.organization_id}'
                )
            seen_ids.add(current.organization_id)
            hierarchy.append(current)
            depth += 1
            if depth > max_depth:
                raise OrgHierarchyDepthError(
                    f'parent_org chain exceeds max depth {max_depth} starting at {leaf.organization_id}'
                )
            parent_id = current.parent_org_id
            if not parent_id:
                break
            current = ProviderOrganization.objects.filter(
                organization_id=parent_id
            ).first()

        return hierarchy

    def resolve_provider_by_rendering_npi(self, npi: str) -> Provider | None:
        """Look up Provider by npi field. Returns None if not found."""
        if not npi:
            return None
        return Provider.objects.filter(npi=npi).first()

    def list_providers_by_rendering_npi(self, npi: str) -> list[Provider]:
        """All Provider rows for a rendering NPI (for ambiguity detection)."""
        if not npi:
            return []
        return list(Provider.objects.filter(npi=npi))

    def rendering_provider_ambiguity(self, npi: str) -> tuple[bool, list[int]]:
        """True when rendering NPI maps to more than one distinct Provider row."""
        providers = self.list_providers_by_rendering_npi(npi)
        if len(providers) <= 1:
            return False, [p.id for p in providers]
        return True, [p.id for p in providers]

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
