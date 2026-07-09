from datetime import date

from core.engine.types import (
    ClaimPricingContext,
    MemberPricingContext,
    ProviderPricingContext,
    RawClaimInput,
)
from core.services.contract_resolution_service import (
    ContractResolutionService,
    STATUS_AMBIGUOUS,
    STATUS_NO_ACTIVE_VERSION,
    STATUS_NO_CONTRACT,
    STATUS_OON,
    STATUS_UNRESOLVED_ENTITY,
)
from core.services.contract_resolver import (
    ContractResolutionAmbiguityError,
    ContractResolutionError,
)

__all__ = ['PricingContextResolver', 'ContractResolutionError']


class PricingContextResolver:
    """
    Transforms a RawClaimInput into a fully-resolved ClaimPricingContext.
    Stage-1 gather + contract pick delegates to ContractResolutionService.
    Affiliation and context assembly remain here (Stage-2 prep).
    """

    def __init__(self):
        from providers.services import ProviderLookupService

        self._provider_svc = ProviderLookupService()
        self._resolution_service = ContractResolutionService()

    def resolve(self, raw: RawClaimInput) -> ClaimPricingContext:
        """Full resolution: member + provider + network + contract."""
        resolution = self._resolution_service.resolve(raw, member_context=True)
        return self._context_from_resolution(raw, resolution)

    def resolve_provider_only(self, raw: RawClaimInput) -> ClaimPricingContext:
        """Provider-side resolution without member context."""
        resolution = self._resolution_service.resolve(raw, member_context=False)
        return self._context_from_resolution(raw, resolution, provider_only=True)

    def context_from_resolution(self, raw: RawClaimInput, resolution) -> ClaimPricingContext:
        """Build ClaimPricingContext from an existing ContractResolutionResult."""
        member_context = bool(raw.member_id)
        return self._context_from_resolution(
            raw,
            resolution,
            provider_only=not member_context,
        )

    def _context_from_resolution(
        self,
        raw: RawClaimInput,
        resolution,
        *,
        provider_only: bool = False,
    ) -> ClaimPricingContext:
        if resolution.status == STATUS_AMBIGUOUS:
            raise ContractResolutionAmbiguityError(
                resolution.reason,
                specificity_level=resolution.resolution_basis or 'unknown',
                contract_ids=resolution.candidates,
            )
        if resolution.status == STATUS_UNRESOLVED_ENTITY:
            raise ContractResolutionError(
                resolution.reason,
                is_oon=False,
            )
        if resolution.status == STATUS_NO_ACTIVE_VERSION:
            raise ContractResolutionError(
                resolution.reason,
                is_oon=False,
            )
        if resolution.status in (STATUS_OON, STATUS_NO_CONTRACT):
            raise ContractResolutionError(
                resolution.reason,
                is_oon=(resolution.status == STATUS_OON),
            )

        # RESOLVED (including legacy version_id=None) proceeds to context assembly.
        gathered = resolution.gather
        if gathered is None:
            service_date = raw.service_date or date.today()
            pricing_date = raw.pricing_date or service_date
            gathered = type('G', (), {
                'service_date': service_date,
                'pricing_date': pricing_date,
                'org': None,
                'rendering': None,
                'network_status': 'UNKNOWN',
                'network_tier': None,
                'lob': None,
                'network_id': None,
                'locality_zip': None,
                'enrollment_id': None,
                'product': None,
                'enrollment': None,
            })()

        affiliation_verified = False
        if gathered.rendering and gathered.org:
            affiliation_verified = self._provider_svc.check_affiliation(
                gathered.rendering.id,
                gathered.org.organization_id,
                gathered.service_date,
            )

        if raw.override_contract_id is not None:
            resolution_mode = 'DIRECT'
        else:
            resolution_mode = 'RESOLVED'

        provider_ctx = ProviderPricingContext(
            billing_org_id=gathered.org.organization_id if gathered.org else None,
            billing_org_tax_id=gathered.org.tax_id if gathered.org else None,
            rendering_provider_id=gathered.rendering.id if gathered.rendering else None,
            rendering_provider_specialty=(
                gathered.rendering.primary_specialty.specialty_code
                if gathered.rendering and gathered.rendering.primary_specialty
                else None
            ),
            facility_id=gathered.facility.id if gathered.facility else None,
            facility_type=(
                gathered.facility.facility_type if gathered.facility else None
            ),
            place_of_service=None,
            network_status=gathered.network_status if not provider_only else 'UNKNOWN',
            network_tier=gathered.network_tier if not provider_only else None,
            affiliation_verified=affiliation_verified,
        )

        member_ctx = MemberPricingContext(
            member_id=raw.member_id if not provider_only else None,
            product_id=gathered.product.id if gathered.product and not provider_only else None,
            lob=gathered.lob if not provider_only else None,
            network_id=gathered.network_id if not provider_only else None,
            locality_zip=gathered.locality_zip if not provider_only else None,
            enrollment_id=gathered.enrollment_id if not provider_only else None,
        )

        return ClaimPricingContext(
            resolution_mode=resolution_mode,
            contract_id=resolution.contract_id,
            version_id=resolution.version_id,
            provider=provider_ctx,
            member=member_ctx,
            service_date=gathered.service_date,
            pricing_date=gathered.pricing_date,
            claim_type=raw.claim_type,
            lines=raw.lines,
        )
