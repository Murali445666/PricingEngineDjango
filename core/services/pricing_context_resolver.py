from datetime import date

from core.engine.types import (
    ClaimPricingContext,
    MemberPricingContext,
    ProviderPricingContext,
    RawClaimInput,
)
from core.services.contract_resolver import ContractResolutionError, ContractResolver
from members.services import MemberLookupService
from products.services import NetworkLookupService
from providers.services import ProviderLookupService

__all__ = ['PricingContextResolver', 'ContractResolutionError']


class PricingContextResolver:
    """
    Transforms a RawClaimInput into a fully-resolved ClaimPricingContext.
    Orchestrates ProviderLookupService, MemberLookupService, NetworkLookupService,
    and ContractResolver. The pricing engine never calls this directly.
    """

    def __init__(self):
        self._provider_svc = ProviderLookupService()
        self._member_svc = MemberLookupService()
        self._network_svc = NetworkLookupService()
        self._contract_resolver = ContractResolver()

    def resolve(self, raw: RawClaimInput) -> ClaimPricingContext:
        """
        Full resolution: member + provider + network + contract.
        Use when caller provides member_id and billing_npi.
        """
        service_date = raw.service_date or date.today()
        pricing_date = raw.pricing_date or service_date

        if raw.override_contract_id is not None:
            return self._build_direct(raw, service_date, pricing_date)

        org = None
        if raw.billing_npi:
            org = self._provider_svc.resolve_org_by_billing_npi(raw.billing_npi)

        rendering = None
        if raw.rendering_npi:
            rendering = self._provider_svc.resolve_provider_by_rendering_npi(
                raw.rendering_npi
            )

        enrollment = None
        product = None
        lob = None
        network_id = None
        locality_zip = None
        enrollment_id = None

        if raw.member_id:
            enrollment = self._member_svc.resolve_enrollment(raw.member_id, service_date)
            if enrollment:
                product = enrollment.product
                lob = enrollment.product.lob.code if enrollment.product else None
                locality_zip = self._member_svc.get_locality_zip(raw.member_id)
                enrollment_id = enrollment.id
                network = self._network_svc.resolve_network(
                    product.id, raw.claim_type, service_date
                )
                if network:
                    network_id = network.id

        network_status = 'UNKNOWN'
        network_tier = None
        if org and network_id:
            status = self._network_svc.check_org_participation(
                org.organization_id, network_id, service_date
            )
            if status:
                network_status = status
                if status in ('TIER_1', 'TIER_2'):
                    network_tier = status
                    network_status = 'IN_NETWORK'
            else:
                network_status = 'OUT_OF_NETWORK'

        affiliation_verified = False
        if rendering and org:
            affiliation_verified = self._provider_svc.check_affiliation(
                rendering.id, org.organization_id, service_date
            )

        resolution_mode = 'RESOLVED'
        try:
            contract_id = self._contract_resolver.resolve(
                org_id=org.organization_id if org else None,
                network_id=network_id,
                lob=lob,
                service_date=service_date,
                product_id=product.id if product else None,
            )
        except ContractResolutionError as e:
            if e.is_oon:
                resolution_mode = 'OON'
            else:
                resolution_mode = 'NO_CONTRACT'
            return self._build_no_contract(
                raw,
                service_date,
                pricing_date,
                org,
                rendering,
                network_status,
                network_tier,
                network_id,
                lob,
                enrollment,
                locality_zip,
                resolution_mode,
                affiliation_verified,
            )

        provider_ctx = ProviderPricingContext(
            billing_org_id=org.organization_id if org else None,
            billing_org_tax_id=org.tax_id if org else None,
            rendering_provider_id=rendering.id if rendering else None,
            rendering_provider_specialty=(
                rendering.primary_specialty.specialty_code
                if rendering and rendering.primary_specialty
                else None
            ),
            facility_id=None,
            facility_type=None,
            place_of_service=None,
            network_status=network_status,
            network_tier=network_tier,
            affiliation_verified=affiliation_verified,
        )

        member_ctx = MemberPricingContext(
            member_id=raw.member_id,
            product_id=product.id if product else None,
            lob=lob,
            network_id=network_id,
            locality_zip=locality_zip,
            enrollment_id=enrollment_id,
        )

        return ClaimPricingContext(
            resolution_mode=resolution_mode,
            contract_id=contract_id,
            version_id=None,
            provider=provider_ctx,
            member=member_ctx,
            service_date=service_date,
            pricing_date=pricing_date,
            claim_type=raw.claim_type,
            lines=raw.lines,
        )

    def resolve_provider_only(self, raw: RawClaimInput) -> ClaimPricingContext:
        """
        Provider-side resolution without member context.
        Resolves org → contract (no LOB or product scoping).
        """
        service_date = raw.service_date or date.today()
        pricing_date = raw.pricing_date or service_date

        org = None
        if raw.billing_npi:
            org = self._provider_svc.resolve_org_by_billing_npi(raw.billing_npi)

        rendering = None
        if raw.rendering_npi:
            rendering = self._provider_svc.resolve_provider_by_rendering_npi(
                raw.rendering_npi
            )

        contract_id = None
        resolution_mode = 'RESOLVED'
        try:
            contract_id = self._contract_resolver.resolve(
                org_id=org.organization_id if org else None,
                network_id=None,
                lob=None,
                service_date=service_date,
            )
        except ContractResolutionError as e:
            resolution_mode = 'OON' if e.is_oon else 'NO_CONTRACT'

        provider_ctx = ProviderPricingContext(
            billing_org_id=org.organization_id if org else None,
            billing_org_tax_id=org.tax_id if org else None,
            rendering_provider_id=rendering.id if rendering else None,
            rendering_provider_specialty=None,
            facility_id=None,
            facility_type=None,
            place_of_service=None,
            network_status='UNKNOWN',
            network_tier=None,
            affiliation_verified=False,
        )

        member_ctx = MemberPricingContext(
            member_id=None,
            product_id=None,
            lob=None,
            network_id=None,
            locality_zip=None,
            enrollment_id=None,
        )

        return ClaimPricingContext(
            resolution_mode=resolution_mode,
            contract_id=contract_id,
            version_id=None,
            provider=provider_ctx,
            member=member_ctx,
            service_date=service_date,
            pricing_date=pricing_date,
            claim_type=raw.claim_type,
            lines=raw.lines,
        )

    def _build_direct(self, raw, service_date, pricing_date) -> ClaimPricingContext:
        """Bypass all resolution — caller gave override_contract_id."""
        empty_provider = ProviderPricingContext(
            billing_org_id=None,
            billing_org_tax_id=None,
            rendering_provider_id=None,
            rendering_provider_specialty=None,
            facility_id=None,
            facility_type=None,
            place_of_service=None,
            network_status='UNKNOWN',
            network_tier=None,
            affiliation_verified=False,
        )
        empty_member = MemberPricingContext(
            member_id=raw.member_id,
            product_id=None,
            lob=None,
            network_id=None,
            locality_zip=None,
            enrollment_id=None,
        )
        return ClaimPricingContext(
            resolution_mode='DIRECT',
            contract_id=raw.override_contract_id,
            version_id=None,
            provider=empty_provider,
            member=empty_member,
            service_date=service_date,
            pricing_date=pricing_date,
            claim_type=raw.claim_type,
            lines=raw.lines,
        )

    def _build_no_contract(
        self,
        raw,
        service_date,
        pricing_date,
        org,
        rendering,
        network_status,
        network_tier,
        network_id,
        lob,
        enrollment,
        locality_zip,
        resolution_mode,
        affiliation_verified,
    ) -> ClaimPricingContext:
        """Build context when no contract was resolved (OON or NO_CONTRACT)."""
        raise ContractResolutionError(
            f'Resolution mode={resolution_mode}: no contract resolved',
            is_oon=(resolution_mode == 'OON'),
        )
