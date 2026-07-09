"""
Stage 1: standalone contract resolution (gather + contract pick + version).

Returns a typed ContractResolutionResult — never raises for business outcomes.
PricingContextResolver and API views consume this as the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.engine.loader import resolve_active_contract_version
from core.engine.types import RawClaimInput
from core.models import ContractVersion, ProviderContract
from core.services.contract_resolver import (
    ContractResolutionAmbiguityError,
    ContractResolutionError,
    ContractResolver,
)
from members.services import MemberLookupService
from products.services import NetworkLookupService
from providers.services import ProviderLookupService

STATUS_RESOLVED = 'RESOLVED'
STATUS_OON = 'OON'
STATUS_NO_CONTRACT = 'NO_CONTRACT'
STATUS_AMBIGUOUS = 'AMBIGUOUS'
STATUS_NO_ACTIVE_VERSION = 'NO_ACTIVE_VERSION'
STATUS_UNRESOLVED_ENTITY = 'UNRESOLVED_ENTITY'

RESOLUTION_PROCEEDS_TO_PRICING = frozenset({STATUS_RESOLVED})


@dataclass
class GatheredClaimContext:
    """Non-serialized gather artifacts used to build ClaimPricingContext."""

    service_date: date
    pricing_date: date
    org: Any = None
    org_ids: list[str] = field(default_factory=list)
    rendering: Any = None
    enrollment: Any = None
    product: Any = None
    lob: str | None = None
    network_id: int | None = None
    network_status: str = 'UNKNOWN'
    network_tier: str | None = None
    locality_zip: str | None = None
    enrollment_id: int | None = None
    facility: Any = None


@dataclass
class ContractResolutionResult:
    status: str
    contract_id: int | None
    version_id: int | None
    resolution_basis: str | None
    candidates: list[int]
    reason: str
    gathered: dict[str, Any]
    gather: GatheredClaimContext | None = None


class ContractResolutionService:
    """Claim-level contract resolution: gather context, pick contract, resolve version."""

    def __init__(self):
        self._provider_svc = ProviderLookupService()
        self._member_svc = MemberLookupService()
        self._network_svc = NetworkLookupService()
        self._contract_resolver = ContractResolver()

    def resolve(
        self,
        raw: RawClaimInput,
        *,
        member_context: bool = True,
    ) -> ContractResolutionResult:
        service_date = raw.service_date or date.today()
        pricing_date = raw.pricing_date or service_date

        if raw.override_contract_id is not None:
            return self._resolve_direct(raw, service_date, pricing_date)

        entity_failure = self._check_gather_ambiguity(
            raw, service_date, member_context=member_context,
        )
        if entity_failure is not None:
            return entity_failure

        gathered = self._gather(raw, service_date, pricing_date, member_context=member_context)
        serializable = self._serialize_gathered(gathered, raw)

        if not gathered.org and raw.billing_npi:
            return ContractResolutionResult(
                status=STATUS_NO_CONTRACT,
                contract_id=None,
                version_id=None,
                resolution_basis=None,
                candidates=[],
                reason='Organization not found for billing NPI',
                gathered=serializable,
                gather=gathered,
            )

        try:
            contract_id = self._contract_resolver.resolve(
                org_id=gathered.org.organization_id if gathered.org else None,
                org_ids=gathered.org_ids or None,
                network_id=gathered.network_id,
                lob=gathered.lob,
                service_date=service_date,
                product_id=gathered.product.id if gathered.product else None,
                claim_type=raw.claim_type,
                facility_id=gathered.facility.id if gathered.facility else None,
                provider_id=gathered.rendering.id if gathered.rendering else None,
            )
        except ContractResolutionAmbiguityError as exc:
            return ContractResolutionResult(
                status=STATUS_AMBIGUOUS,
                contract_id=None,
                version_id=None,
                resolution_basis=exc.specificity_level,
                candidates=list(exc.contract_ids),
                reason=str(exc),
                gathered=serializable,
                gather=gathered,
            )
        except ContractResolutionError as exc:
            return ContractResolutionResult(
                status=STATUS_OON if exc.is_oon else STATUS_NO_CONTRACT,
                contract_id=None,
                version_id=None,
                resolution_basis=None,
                candidates=[],
                reason=str(exc),
                gathered=serializable,
                gather=gathered,
            )

        version_id, version_outcome = self._resolve_version_outcome(contract_id, service_date)
        if version_outcome == 'no_active_version':
            return ContractResolutionResult(
                status=STATUS_NO_ACTIVE_VERSION,
                contract_id=contract_id,
                version_id=None,
                resolution_basis=self._resolution_basis(gathered),
                candidates=[],
                reason=f'No active contract version for contract_id={contract_id} on {service_date}',
                gathered=serializable,
                gather=gathered,
            )

        return ContractResolutionResult(
            status=STATUS_RESOLVED,
            contract_id=contract_id,
            version_id=version_id,
            resolution_basis=self._resolution_basis(gathered),
            candidates=[],
            reason='Contract resolved',
            gathered=serializable,
            gather=gathered,
        )

    def _resolve_direct(
        self,
        raw: RawClaimInput,
        service_date: date,
        pricing_date: date,
    ) -> ContractResolutionResult:
        contract_id = raw.override_contract_id
        version_id, version_outcome = self._resolve_version_outcome(contract_id, service_date)
        gathered = GatheredClaimContext(service_date=service_date, pricing_date=pricing_date)
        serializable = self._serialize_gathered(gathered, raw)
        serializable['override_contract_id'] = contract_id

        if version_outcome == 'no_active_version':
            return ContractResolutionResult(
                status=STATUS_NO_ACTIVE_VERSION,
                contract_id=contract_id,
                version_id=None,
                resolution_basis='direct override',
                candidates=[],
                reason=f'No active contract version for override contract_id={contract_id}',
                gathered=serializable,
                gather=gathered,
            )

        return ContractResolutionResult(
            status=STATUS_RESOLVED,
            contract_id=contract_id,
            version_id=version_id,
            resolution_basis='direct override',
            candidates=[],
            reason='Direct contract override',
            gathered=serializable,
            gather=gathered,
        )

    def _check_gather_ambiguity(
        self,
        raw: RawClaimInput,
        service_date: date,
        *,
        member_context: bool,
    ) -> ContractResolutionResult | None:
        """Return UNRESOLVED_ENTITY when gather inputs are genuinely ambiguous."""
        gathered_stub = {
            'member_id': raw.member_id,
            'service_date': service_date.isoformat(),
            'billing_npi': raw.billing_npi,
            'rendering_npi': raw.rendering_npi,
            'claim_type': raw.claim_type,
        }

        if raw.facility_npi:
            gathered_stub['facility_npi'] = raw.facility_npi

        if raw.billing_npi:
            ambiguous, org_ids = self._provider_svc.billing_org_ambiguity(raw.billing_npi)
            if ambiguous:
                gathered_stub['ambiguous_entity'] = 'billing_org'
                gathered_stub['ambiguous_candidates'] = org_ids
                return ContractResolutionResult(
                    status=STATUS_UNRESOLVED_ENTITY,
                    contract_id=None,
                    version_id=None,
                    resolution_basis=None,
                    candidates=[],
                    reason=f'billing_org ambiguous: {org_ids}',
                    gathered=gathered_stub,
                    gather=None,
                )

        if member_context and raw.member_id:
            ambiguous, enrollment_ids = self._member_svc.enrollment_product_ambiguity(
                raw.member_id, service_date,
            )
            if ambiguous:
                gathered_stub['ambiguous_entity'] = 'member'
                gathered_stub['ambiguous_candidates'] = enrollment_ids
                return ContractResolutionResult(
                    status=STATUS_UNRESOLVED_ENTITY,
                    contract_id=None,
                    version_id=None,
                    resolution_basis=None,
                    candidates=enrollment_ids,
                    reason=f'member enrollment ambiguous: {enrollment_ids}',
                    gathered=gathered_stub,
                    gather=None,
                )

        if raw.rendering_npi:
            ambiguous, provider_ids = self._provider_svc.rendering_provider_ambiguity(
                raw.rendering_npi,
            )
            if ambiguous:
                gathered_stub['ambiguous_entity'] = 'rendering'
                gathered_stub['ambiguous_candidates'] = provider_ids
                return ContractResolutionResult(
                    status=STATUS_UNRESOLVED_ENTITY,
                    contract_id=None,
                    version_id=None,
                    resolution_basis=None,
                    candidates=provider_ids,
                    reason=f'rendering provider ambiguous: {provider_ids}',
                    gathered=gathered_stub,
                    gather=None,
                )

        return None

    def _gather(
        self,
        raw: RawClaimInput,
        service_date: date,
        pricing_date: date,
        *,
        member_context: bool,
    ) -> GatheredClaimContext:
        org = None
        org_ids: list[str] = []
        if raw.billing_npi:
            hierarchy = self._provider_svc.resolve_org_hierarchy(raw.billing_npi, service_date)
            org_ids = [o.organization_id for o in hierarchy]
            org = hierarchy[0] if hierarchy else None

        rendering = None
        if raw.rendering_npi:
            rendering = self._provider_svc.resolve_provider_by_rendering_npi(raw.rendering_npi)

        facility = None
        if raw.facility_npi:
            facility = self._provider_svc.resolve_facility_by_npi(raw.facility_npi)

        enrollment = None
        product = None
        lob = None
        network_id = None
        locality_zip = None
        enrollment_id = None

        if member_context and raw.member_id:
            enrollment = self._member_svc.resolve_enrollment(raw.member_id, service_date)
            if enrollment:
                product = enrollment.product
                lob = enrollment.product.lob.code if enrollment.product else None
                locality_zip = self._member_svc.get_locality_zip(raw.member_id)
                enrollment_id = enrollment.id
                network = self._network_svc.resolve_network(
                    product.id, raw.claim_type, service_date,
                )
                if network:
                    network_id = network.id

        network_status = 'UNKNOWN'
        network_tier = None
        if org and network_id:
            status = self._network_svc.check_org_participation(
                org.organization_id, network_id, service_date,
            )
            if status:
                network_status = status
                if status in ('TIER_1', 'TIER_2'):
                    network_tier = status
                    network_status = 'IN_NETWORK'
            else:
                network_status = 'OUT_OF_NETWORK'

        return GatheredClaimContext(
            service_date=service_date,
            pricing_date=pricing_date,
            org=org,
            org_ids=org_ids,
            rendering=rendering,
            enrollment=enrollment,
            product=product,
            lob=lob,
            network_id=network_id,
            network_status=network_status,
            network_tier=network_tier,
            locality_zip=locality_zip,
            enrollment_id=enrollment_id,
            facility=facility,
        )

    @staticmethod
    def _serialize_gathered(gathered: GatheredClaimContext, raw: RawClaimInput) -> dict[str, Any]:
        return {
            'org_id': gathered.org.organization_id if gathered.org else None,
            'org_ids': list(gathered.org_ids),
            'member_id': raw.member_id,
            'network_id': gathered.network_id,
            'lob': gathered.lob,
            'service_date': gathered.service_date.isoformat(),
            'billing_npi': raw.billing_npi,
            'rendering_npi': raw.rendering_npi,
            'facility_npi': raw.facility_npi,
            'claim_type': raw.claim_type,
        }

    @staticmethod
    def _resolution_basis(gathered: GatheredClaimContext) -> str:
        if gathered.product and gathered.lob and gathered.network_id:
            return 'org+network+lob @ product level'
        if gathered.lob and gathered.network_id:
            return 'org+network+lob'
        if gathered.network_id:
            return 'org+network'
        return 'org only'

    @staticmethod
    def _resolve_version_outcome(
        contract_id: int, service_date: date,
    ) -> tuple[int | None, str]:
        """
        Returns (version_id, outcome).
        outcome: 'resolved' | 'legacy_no_versions' | 'no_active_version'
        Legacy contracts with no ContractVersion rows proceed with version_id=None.
        """
        contract = ProviderContract.objects.get(pk=contract_id)
        has_versions = ContractVersion.objects.filter(contract=contract).exists()
        if not has_versions:
            return None, 'legacy_no_versions'
        version = resolve_active_contract_version(contract, service_date)
        if version is None:
            return None, 'no_active_version'
        return version.version_id, 'resolved'
