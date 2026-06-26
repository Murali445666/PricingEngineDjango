"""Attach a single policy configuration to DEMO_POLICY for isolated tests."""
from __future__ import annotations

from decimal import Decimal

from core.models import (
    ContractBlendingRule,
    ContractCapFloor,
    ContractCarveout,
    ContractOutlierRule,
    ContractStopLossRule,
    ContractVersion,
    MPPRDefinition,
    MPPRScope,
)

from core.demo.scenarios import DEMO_SERVICE_DATE

_EFFECTIVE_START = DEMO_SERVICE_DATE.replace(day=1, month=1)
_EFFECTIVE_END = DEMO_SERVICE_DATE.replace(day=31, month=12)


def clear_policy_rows(version: ContractVersion) -> None:
    """Remove all policy rows from DEMO_POLICY version (rules unchanged)."""
    ContractCarveout.objects.filter(version=version).delete()
    ContractStopLossRule.objects.filter(version=version).delete()
    ContractOutlierRule.objects.filter(version=version).delete()
    ContractBlendingRule.objects.filter(version=version).delete()
    ContractCapFloor.objects.filter(version=version).delete()
    MPPRScope.objects.filter(mppr_definition__version=version).delete()
    MPPRDefinition.objects.filter(version=version).delete()


def attach_carveout_exclude(version: ContractVersion) -> None:
    ContractCarveout.objects.create(
        version=version,
        code_type="CPT",
        code_value="99100",
        carveout_methodology="EXCLUDE",
    )


def attach_stop_loss(contract, version: ContractVersion) -> None:
    ContractStopLossRule.objects.create(
        contract=contract,
        version=version,
        cost_threshold=Decimal("1000.00"),
        reimbursement_percentage=Decimal("50.00"),
        priority=0,
        effective_start_date=_EFFECTIVE_START,
        effective_end_date=_EFFECTIVE_END,
    )


def attach_outlier(contract, version: ContractVersion) -> None:
    ContractOutlierRule.objects.create(
        contract=contract,
        version=version,
        threshold_amount=Decimal("1000.00"),
        threshold_scope="PER_CLAIM",
        reimbursement_percentage=Decimal("80.00"),
        priority=0,
        effective_start_date=_EFFECTIVE_START,
        effective_end_date=_EFFECTIVE_END,
    )


def attach_blending_add(version: ContractVersion) -> None:
    ContractBlendingRule.objects.create(
        version=version,
        blend_type="ADD",
        scope="CLAIM",
        primary_methodology="",
        secondary_methodology="PERCENT_BILLED",
        blend_percentage=Decimal("10.00"),
        priority=0,
        effective_start_date=_EFFECTIVE_START,
        effective_end_date=_EFFECTIVE_END,
    )


def attach_claim_cap(version: ContractVersion, cap_value: str = "250.00") -> None:
    ContractCapFloor.objects.create(
        version=version,
        scope="CLAIM",
        cap_type="CAP",
        value=Decimal(cap_value),
        priority=0,
        effective_start_date=_EFFECTIVE_START,
        effective_end_date=_EFFECTIVE_END,
    )


def attach_claim_floor(version: ContractVersion, floor_value: str = "100.00") -> None:
    ContractCapFloor.objects.create(
        version=version,
        scope="CLAIM",
        cap_type="FLOOR",
        value=Decimal(floor_value),
        priority=0,
        effective_start_date=_EFFECTIVE_START,
        effective_end_date=_EFFECTIVE_END,
    )


def attach_mppr(contract, version: ContractVersion) -> None:
    mppr = MPPRDefinition.objects.create(
        contract=contract,
        version=version,
        name="MPPR 99213",
        rank_by=MPPRDefinition.RANK_BY_ALLOWED,
        primary_pct=Decimal("100.00"),
        secondary_pct=Decimal("50.00"),
        tertiary_pct=Decimal("25.00"),
        effective_start_date=_EFFECTIVE_START,
        effective_end_date=_EFFECTIVE_END,
    )
    MPPRScope.objects.create(mppr_definition=mppr, procedure_code="99213")
