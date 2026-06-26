"""Shared helpers for deterministic demo pricing tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from core.engine.config import ClaimLineInput, ClaimPricingInput
from core.engine.service import ClaimPricingService
from core.engine.types import PricingStatus
from core.models import ProviderContract


def claim_dict_to_input(claim: dict[str, Any]) -> ClaimPricingInput:
    lines = []
    for ln in claim.get("lines", []):
        cost = ln.get("cost_amount")
        lines.append(
            ClaimLineInput(
                procedure_code=ln["procedure_code"],
                billed_amount=Decimal(str(ln["billed_amount"])),
                units=int(ln.get("units", 1)),
                modifiers=list(ln.get("modifiers") or []),
                cost_amount=Decimal(str(cost)) if cost is not None else None,
            )
        )
    svc = claim.get("service_date")
    service_date = date.fromisoformat(svc) if isinstance(svc, str) else svc
    return ClaimPricingInput(
        service_date=service_date,
        claim_type=claim.get("claim_type"),
        drg_code=claim.get("drg_code"),
        lines=lines,
    )


def simulate_claim(
    registry: dict[str, dict[str, Any]],
    contract_key: str,
    claim: dict[str, Any],
):
    """Run price_claim_with_version for a seeded DEMO contract."""
    meta = registry[contract_key]
    claim_input = claim_dict_to_input(claim)
    contract = ProviderContract.objects.get(pk=meta["contract_id"])
    claim_input.contract = contract
    claim_input.contract_id = meta["contract_id"]
    service = ClaimPricingService()
    return service.price_claim_with_version(
        meta["contract_id"],
        meta["version_id"],
        claim_input,
    )


def status_value(status) -> str:
    if isinstance(status, PricingStatus):
        return status.value
    return str(status)
