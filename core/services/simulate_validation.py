"""
Advisory member/provider validation for POST /api/price-claim-simulate/.

Never raises to callers — all failures become warnings inside the validation block.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.engine.types import RawClaimInput
from core.services.contract_resolver import ContractResolutionAmbiguityError
from core.services.pricing_context_resolver import (
    ContractResolutionError,
    PricingContextResolver,
)
from members.models import Member
from members.services import MemberLookupService
from providers.services import OrgHierarchyDepthError, ProviderLookupService

_EMPTY_PROVIDER = {
    'billing_org_id': None,
    'network_status': 'UNKNOWN',
    'network_tier': None,
    'affiliation_verified': False,
}
_EMPTY_MEMBER = {
    'enrolled': False,
    'lob': None,
    'product_id': None,
}


def build_simulate_validation(
    *,
    selected_contract_id: int,
    member_id: str | None,
    billing_npi: str | None,
    rendering_npi: str | None,
    claim_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Run optional advisory validation. Returns {"ran": false} when neither
    member_id nor billing_npi was supplied.
    """
    member_id = (member_id or '').strip() or None
    billing_npi = (billing_npi or '').strip() or None
    rendering_npi = (rendering_npi or '').strip() or None

    if not member_id and not billing_npi:
        return {'ran': False}

    try:
        return _run_validation(
            selected_contract_id=selected_contract_id,
            member_id=member_id,
            billing_npi=billing_npi,
            rendering_npi=rendering_npi,
            claim_data=claim_data,
        )
    except Exception:
        return {
            'ran': True,
            'resolution_mode': None,
            'resolved_contract_id': None,
            'selected_contract_id': selected_contract_id,
            'matches_selected_contract': None,
            'provider': dict(_EMPTY_PROVIDER),
            'member': dict(_EMPTY_MEMBER),
            'warnings': ['Validation check could not be completed.'],
        }


def _run_validation(
    *,
    selected_contract_id: int,
    member_id: str | None,
    billing_npi: str | None,
    rendering_npi: str | None,
    claim_data: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    provider_svc = ProviderLookupService()
    member_svc = MemberLookupService()

    service_date = claim_data.get('service_date') or date.today()
    if isinstance(service_date, str):
        service_date = date.fromisoformat(service_date)
    claim_type = (claim_data.get('claim_type') or 'professional').lower()

    provider_info = dict(_EMPTY_PROVIDER)
    member_info = dict(_EMPTY_MEMBER)

    if billing_npi:
        try:
            hierarchy = provider_svc.resolve_org_hierarchy(billing_npi, service_date)
            if hierarchy:
                provider_info['billing_org_id'] = hierarchy[0].organization_id
            else:
                warnings.append(f'Billing NPI {billing_npi} not found')
        except OrgHierarchyDepthError as exc:
            warnings.append(str(exc))

    if member_id:
        member = Member.objects.filter(member_id=member_id).first()
        if member is None:
            warnings.append(f'Member {member_id} not found')
        else:
            enrollment = member_svc.resolve_enrollment(member_id, service_date)
            if enrollment is None:
                warnings.append(
                    f'Member {member_id} is not enrolled on {service_date}'
                )
            else:
                member_info['enrolled'] = True
                member_info['product_id'] = enrollment.product_id
                if enrollment.product and enrollment.product.lob:
                    member_info['lob'] = enrollment.product.lob.code

    resolution_mode: str | None = None
    resolved_contract_id: int | None = None
    matches_selected: bool | None = None

    raw = RawClaimInput(
        billing_npi=billing_npi,
        rendering_npi=rendering_npi,
        member_id=member_id,
        service_date=service_date,
        claim_type=claim_type,
        lines=[dict(line) for line in (claim_data.get('lines') or [])],
    )

    try:
        ctx = PricingContextResolver().resolve(raw)
        resolution_mode = 'RESOLVED'
        resolved_contract_id = ctx.contract_id
        provider_info = {
            'billing_org_id': ctx.provider.billing_org_id,
            'network_status': ctx.provider.network_status,
            'network_tier': ctx.provider.network_tier,
            'affiliation_verified': ctx.provider.affiliation_verified,
        }
        if ctx.member.member_id:
            member_info['enrolled'] = ctx.member.enrollment_id is not None
            member_info['lob'] = ctx.member.lob
            member_info['product_id'] = ctx.member.product_id

        if ctx.provider.network_status == 'OUT_OF_NETWORK':
            warnings.append(
                "Provider is out-of-network for this member's network"
            )
        if resolved_contract_id != selected_contract_id:
            warnings.append(
                f'Selected contract {selected_contract_id} differs from the '
                f'contract that would resolve for this member/provider: '
                f'{resolved_contract_id} (mode={resolution_mode})'
            )
        if rendering_npi and not ctx.provider.affiliation_verified:
            warnings.append(
                'Rendering provider affiliation could not be verified for '
                'billing organization on service date'
            )
        matches_selected = resolved_contract_id == selected_contract_id

    except ContractResolutionAmbiguityError as exc:
        resolution_mode = 'AMBIGUOUS'
        ids = exc.contract_ids
        warnings.append(
            'Contract resolution is ambiguous among contract IDs: '
            + ', '.join(str(i) for i in ids)
        )
        matches_selected = None

    except ContractResolutionError as exc:
        resolution_mode = 'OON' if exc.is_oon else 'NO_CONTRACT'
        warnings.append(str(exc))
        matches_selected = False

    except OrgHierarchyDepthError as exc:
        resolution_mode = 'NO_CONTRACT'
        warnings.append(str(exc))
        matches_selected = False

    return {
        'ran': True,
        'resolution_mode': resolution_mode,
        'resolved_contract_id': resolved_contract_id,
        'selected_contract_id': selected_contract_id,
        'matches_selected_contract': matches_selected,
        'provider': provider_info,
        'member': member_info,
        'warnings': warnings,
    }
