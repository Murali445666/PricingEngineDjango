from __future__ import annotations

import uuid
from typing import Any

from core.engine.types import ClaimPricingContext
from core.models import ClaimHeader, ClaimResolutionLog


def build_resolver_inputs(ctx: ClaimPricingContext) -> dict[str, Any]:
    return {
        'billing_org_id': ctx.provider.billing_org_id,
        'rendering_provider_id': ctx.provider.rendering_provider_id,
        'member_id': ctx.member.member_id,
        'product_id': ctx.member.product_id,
        'lob': ctx.member.lob,
        'network_id': ctx.member.network_id,
        'network_status': ctx.provider.network_status,
        'resolution_mode': ctx.resolution_mode,
    }


def write_claim_resolution_log(
    ctx: ClaimPricingContext,
    resolution_path: str,
    *,
    claim_header: ClaimHeader | None = None,
    is_repricing: bool = False,
    resolver_inputs: dict[str, Any] | None = None,
    trace_id: uuid.UUID | str | None = None,
) -> ClaimResolutionLog:
    """
    Persist an append-only ClaimResolutionLog row for audit (Phase R4).
    resolved_version must be non-null (requires R2 version_id propagation).
    """
    if ctx.contract_id is None:
        raise ValueError('Cannot write resolution log without contract_id on context')
    if ctx.version_id is None:
        raise ValueError(
            'Cannot write resolution log without version_id on context '
            '(no ACTIVE ContractVersion for service_date?)'
        )

    trace_uuid = None
    if trace_id is not None:
        trace_uuid = trace_id if isinstance(trace_id, uuid.UUID) else uuid.UUID(str(trace_id))
    elif ctx.trace_id:
        trace_uuid = uuid.UUID(str(ctx.trace_id))

    inputs = resolver_inputs if resolver_inputs is not None else build_resolver_inputs(ctx)

    return ClaimResolutionLog.objects.create(
        claim_header=claim_header,
        trace_id=trace_uuid,
        resolved_contract_id=ctx.contract_id,
        resolved_version_id=ctx.version_id,
        resolution_path=resolution_path,
        service_date=ctx.service_date,
        resolver_inputs=inputs,
        is_repricing=is_repricing,
    )
