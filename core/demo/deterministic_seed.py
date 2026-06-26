"""
Deterministic DEMO_* contract seeding for UI demos and regression tests.

Idempotent: removes prior contracts whose legacy_contract_number starts with DEMO_
(or matches known DEMO contract names), then recreates reference rows and contracts
with fixed rates so expected amounts are reproducible.

Usage:
    python manage.py seed_demo

From tests:
    from core.demo.deterministic_seed import seed_deterministic_demos
    registry = seed_deterministic_demos()
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from core.models import (
    ContractBaseRate,
    ContractBlendingRule,
    ContractCapFloor,
    ContractCarveout,
    ContractMethodology,
    ContractOutlierRule,
    ContractStopLossRule,
    ContractVersion,
    FacilityBaseRate,
    FeeSchedule,
    FeeScheduleRate,
    MPPRDefinition,
    MPPRScope,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
    RefApc,
    RefAspPricing,
    RefCptHcpcsCode,
    RefDrg,
    RefModifier,
)

from .scenarios import DEMO_CONTRACT_KEYS, DEMO_SERVICE_DATE

logger = logging.getLogger(__name__)

DEMO_PREFIX = "DEMO_"
EFFECTIVE_START = date(2026, 1, 1)
EFFECTIVE_END = date(2026, 12, 31)
REF_YEAR = 2026


def _decimal(v) -> Decimal:
    return Decimal(str(v))


def _safe_delete_demo() -> None:
    """Remove prior DEMO contracts and orphan DEMO fee schedules."""
    names = list(DEMO_CONTRACT_KEYS)
    deleted = ProviderContract.objects.filter(legacy_contract_number__in=names)
    count = deleted.count()
    deleted.delete()
    if count:
        logger.info("Deleted %s prior DEMO contract(s).", count)
    for fs in FeeSchedule.objects.filter(name__startswith=DEMO_PREFIX):
        fs.delete()
    ProviderOrganization.objects.filter(organization_id__startswith=DEMO_PREFIX).delete()
    PayerNetwork.objects.filter(network_id__startswith=DEMO_PREFIX).delete()


def _seed_reference_data() -> None:
    """Minimal reference rows with fixed values (deterministic)."""
    codes = [
        ("99213", "CPT", "Office visit"),
        ("00100", "CPT", "Anesthesia head"),
        ("99100", "CPT", "Anesthesia add-on"),
        ("73030", "CPT", "X-ray"),
        ("0120", "CPT", "Per diem revenue"),
        ("J0129", "HCPCS", "Drug J0129"),
    ]
    for code, code_type, desc in codes:
        RefCptHcpcsCode.objects.update_or_create(
            code=code,
            defaults={
                "code_type": code_type,
                "description": desc,
                "effective_year": REF_YEAR,
            },
        )

    RefDrg.objects.update_or_create(
        drg_code="470",
        defaults={
            "description": "Demo DRG 470",
            "relative_weight": _decimal("2.000000"),
            "year": REF_YEAR,
        },
    )

    RefApc.objects.update_or_create(
        apc_code="5121",
        defaults={
            "description": "Demo APC 5121",
            "relative_weight": _decimal("1.50"),
            "status_indicator": "J",
            "payment_rate": _decimal("100.00"),
            "year": REF_YEAR,
        },
    )

    RefAspPricing.objects.update_or_create(
        hcpcs_code="J0129",
        quarter="2026-Q2",
        defaults={
            "asp": _decimal("10.50"),
            "payment_limit": _decimal("12.00"),
        },
    )

    RefModifier.objects.update_or_create(
        modifier_code="26",
        defaults={
            "description": "Professional component",
            "percentage_adjustment": _decimal("100.00"),
        },
    )


def _add_condition(rule, attribute_name: str, attribute_value: str) -> None:
    PricingRuleCondition.objects.create(
        pricing_rule=rule,
        attribute_name=attribute_name,
        operator="EQ",
        attribute_value=attribute_value,
    )


def _make_fee_schedule(name: str, rates: dict[str, str]) -> FeeSchedule:
    fs = FeeSchedule.objects.create(
        name=name,
        effective_date=EFFECTIVE_START,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        effective_year=REF_YEAR,
    )
    for code, amount in rates.items():
        FeeScheduleRate.objects.create(
            fee_schedule=fs,
            code_id=code,
            rate_amount=_decimal(amount),
            effective_start_date=EFFECTIVE_START,
            effective_end_date=EFFECTIVE_END,
            year=REF_YEAR,
        )
    return fs


def _create_demo_shell(contract_key: str) -> tuple[ProviderContract, ContractVersion]:
    payer, _ = ProviderOrganization.objects.get_or_create(
        organization_id=f"{DEMO_PREFIX}PAYER",
        defaults={"name": "Demo Payer", "tax_id": "00-0000000"},
    )
    prov_org = ProviderOrganization.objects.create(
        organization_id=f"{DEMO_PREFIX}ORG_{contract_key}",
        name=f"Demo Provider {contract_key}",
        tax_id="11-1111111",
    )
    network = PayerNetwork.objects.create(
        network_id=f"{DEMO_PREFIX}NET_{contract_key}",
        network_name=f"Demo Network {contract_key}",
        payer_org=payer,
    )
    contract = ProviderContract.objects.create(
        contract_name=contract_key,
        legacy_contract_number=contract_key,
        status="ACTIVE",
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        provider_org=prov_org,
        network=network,
    )
    version = ContractVersion.objects.create(
        contract=contract,
        version_number=1,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        status=ContractVersion.VersionStatus.ACTIVE,
    )
    return contract, version


def _build_demo_rbrvs() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_RBRVS")
    fs = _make_fee_schedule(f"{DEMO_PREFIX}FS_RBRVS", {"99213": "100.00"})
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="RBRVS 99213",
        rule_type="BASE",
        methodology_code="RBRVS",
        base_fee_schedule=fs,
        multiplier=_decimal("1.5"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="PROFESSIONAL",
    )
    _add_condition(rule, "procedure_code", "99213")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_drg() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_DRG")
    version.claim_level_drg_enabled = True
    version.save(update_fields=["claim_level_drg_enabled"])
    FacilityBaseRate.objects.create(
        contract=contract,
        version=version,
        facility_id=None,
        rate_type="DRG",
        base_rate=_decimal("6000.00"),
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="DRG 470",
        rule_type="BASE",
        methodology_code="DRG",
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=20,
        claim_type="INPATIENT",
    )
    _add_condition(rule, "procedure_code", "470")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_flat() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_FLAT")
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="FLAT 00100",
        rule_type="BASE",
        methodology_code="FLAT_RATE",
        flat_rate=_decimal("250.00"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="OUTPATIENT",
    )
    _add_condition(rule, "procedure_code", "00100")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_pct() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_PCT_BILLED")
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="PCT 99213",
        rule_type="BASE",
        methodology_code="PCT_BILLED",
        multiplier=_decimal("0.8"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="OUTPATIENT",
    )
    _add_condition(rule, "procedure_code", "99213")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_apc() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_APC")
    ContractBaseRate.objects.create(
        version=version,
        rate_type="APC",
        base_rate=_decimal("100.00"),
    )
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="APC 5121",
        rule_type="BASE",
        methodology_code="APC",
        multiplier=_decimal("1.0"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="OUTPATIENT",
    )
    _add_condition(rule, "procedure_code", "5121")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_asp() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_ASP")
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="ASP J0129",
        rule_type="BASE",
        methodology_code="ASP",
        multiplier=_decimal("1.0"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="PROFESSIONAL",
    )
    _add_condition(rule, "procedure_code", "J0129")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_per_diem() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_PER_DIEM")
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="PER_DIEM 0120",
        rule_type="BASE",
        methodology_code="PER_DIEM",
        flat_rate=_decimal("400.00"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="INPATIENT",
    )
    _add_condition(rule, "procedure_code", "0120")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_anesthesia() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_ANESTHESIA")
    fs = _make_fee_schedule(f"{DEMO_PREFIX}FS_ANES", {"00100": "5.00"})
    rule = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="ANESTHESIA 00100",
        rule_type="BASE",
        methodology_code="ANESTHESIA",
        base_fee_schedule=fs,
        multiplier=_decimal("45.00"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
        claim_type="PROFESSIONAL",
    )
    _add_condition(rule, "procedure_code", "00100")
    return {"contract": contract, "version": version, "rule": rule}


def _build_demo_policy() -> dict[str, Any]:
    contract, version = _create_demo_shell("DEMO_POLICY")
    fs = _make_fee_schedule(
        f"{DEMO_PREFIX}FS_POLICY",
        {"99213": "100.00", "99100": "80.00"},
    )
    r1 = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="RBRVS 99213",
        rule_type="BASE",
        methodology_code="RBRVS",
        base_fee_schedule=fs,
        multiplier=_decimal("1.5"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(r1, "procedure_code", "99213")

    r2 = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="RBRVS 99100",
        rule_type="BASE",
        methodology_code="RBRVS",
        base_fee_schedule=fs,
        multiplier=_decimal("1.25"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(r2, "procedure_code", "99100")

    r3 = PricingRule.objects.create(
        contract=contract,
        version=version,
        rule_name="FLAT 73030",
        rule_type="BASE",
        methodology_code="FLAT_RATE",
        flat_rate=_decimal("75.00"),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(r3, "procedure_code", "73030")

    ContractCarveout.objects.create(
        version=version,
        code_type="CPT",
        code_value="99100",
        carveout_methodology="EXCLUDE",
    )
    ContractStopLossRule.objects.create(
        contract=contract,
        version=version,
        cost_threshold=_decimal("1000.00"),
        reimbursement_percentage=_decimal("50.00"),
        priority=0,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    ContractOutlierRule.objects.create(
        contract=contract,
        version=version,
        threshold_amount=_decimal("1000.00"),
        threshold_scope="PER_CLAIM",
        reimbursement_percentage=_decimal("80.00"),
        priority=0,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    ContractBlendingRule.objects.create(
        version=version,
        blend_type="ADD",
        scope="CLAIM",
        primary_methodology="",
        secondary_methodology="PERCENT_BILLED",
        blend_percentage=_decimal("10.00"),
        priority=0,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    ContractCapFloor.objects.create(
        version=version,
        scope="CLAIM",
        cap_type="CAP",
        value=_decimal("250.00"),
        priority=0,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    ContractCapFloor.objects.create(
        version=version,
        scope="CLAIM",
        cap_type="FLOOR",
        value=_decimal("100.00"),
        priority=0,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    mppr = MPPRDefinition.objects.create(
        contract=contract,
        version=version,
        name="MPPR 99213",
        rank_by=MPPRDefinition.RANK_BY_ALLOWED,
        primary_pct=_decimal("100.00"),
        secondary_pct=_decimal("50.00"),
        tertiary_pct=_decimal("25.00"),
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
    )
    MPPRScope.objects.create(mppr_definition=mppr, procedure_code="99213")

    return {"contract": contract, "version": version, "rules": [r1, r2, r3]}


_BUILDERS = {
    "DEMO_RBRVS": _build_demo_rbrvs,
    "DEMO_DRG": _build_demo_drg,
    "DEMO_FLAT": _build_demo_flat,
    "DEMO_PCT_BILLED": _build_demo_pct,
    "DEMO_APC": _build_demo_apc,
    "DEMO_ASP": _build_demo_asp,
    "DEMO_PER_DIEM": _build_demo_per_diem,
    "DEMO_ANESTHESIA": _build_demo_anesthesia,
    "DEMO_POLICY": _build_demo_policy,
}


def _pack_registry_entry(key: str, built: dict[str, Any]) -> dict[str, Any]:
    contract = built["contract"]
    version = built["version"]
    entry = {
        "contract_key": key,
        "contract_id": contract.contract_id,
        "version_id": version.version_id,
        "contract_name": contract.contract_name,
        "legacy_contract_number": contract.legacy_contract_number,
    }
    if "rule" in built:
        entry["rule_id"] = built["rule"].rule_id
    return entry


def seed_deterministic_demos() -> dict[str, dict[str, Any]]:
    """
    Seed all DEMO_* contracts. Returns registry keyed by contract name with IDs.
    """
    _safe_delete_demo()
    _seed_reference_data()
    registry: dict[str, dict[str, Any]] = {}
    for key in DEMO_CONTRACT_KEYS:
        built = _BUILDERS[key]()
        registry[key] = _pack_registry_entry(key, built)
    return registry


@transaction.atomic
def seed_deterministic_demos_atomic() -> dict[str, dict[str, Any]]:
    """Wrapped in atomic transaction for management command."""
    return seed_deterministic_demos()


def resolve_demo_registry() -> dict[str, dict[str, Any]]:
    """Look up DEMO contract/version IDs from DB (after seed)."""
    registry = {}
    for key in DEMO_CONTRACT_KEYS:
        contract = ProviderContract.objects.filter(legacy_contract_number=key).first()
        if not contract:
            continue
        version = (
            ContractVersion.objects.filter(contract=contract)
            .order_by("-version_number")
            .first()
        )
        if not version:
            continue
        registry[key] = {
            "contract_key": key,
            "contract_id": contract.contract_id,
            "version_id": version.version_id,
            "contract_name": contract.contract_name,
            "legacy_contract_number": contract.legacy_contract_number,
        }
    return registry
