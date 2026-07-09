"""Persist failed contract resolution attempts for analyst review (Phase D3)."""
from __future__ import annotations

import logging
import uuid
from datetime import date

from core.models import ContractResolutionException
from core.services.contract_resolution_service import (
    ContractResolutionResult,
    STATUS_RESOLVED,
)

logger = logging.getLogger(__name__)


def persist_resolution_exception(
    result: ContractResolutionResult,
    *,
    trace_id: uuid.UUID | None = None,
) -> ContractResolutionException | None:
    """Write a review-queue row for non-RESOLVED outcomes. Never raises."""
    if result.status == STATUS_RESOLVED:
        return None
    try:
        service_date = None
        raw_date = (result.gathered or {}).get('service_date')
        if raw_date:
            service_date = date.fromisoformat(raw_date)
        return ContractResolutionException.objects.create(
            trace_id=trace_id,
            status=result.status,
            reason=result.reason,
            candidates=list(result.candidates or []),
            gathered_inputs=dict(result.gathered or {}),
            service_date=service_date,
        )
    except Exception:
        logger.exception('Failed to persist ContractResolutionException')
        return None


def resolution_failure_payload(result: ContractResolutionResult) -> dict:
    """Standard HTTP 200 JSON body for a failed Stage-1 resolution."""
    return {
        'status': result.status,
        'message': result.reason,
        'contract_id': result.contract_id if result.status == 'NO_ACTIVE_VERSION' else None,
        'candidates': list(result.candidates or []),
        'lines': [],
    }
