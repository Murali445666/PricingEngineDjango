"""
DEMO-UC-* use-case seed — isolated transactional data for identity-first pricing demos.

All natural keys use the DEMO-UC- prefix. Create-only on normal run; --wipe deletes
only DEMO-UC- rows (guarded). See core/demo/use_cases.py for the registry.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from core.demo.use_cases import CAST, PREFIX, USE_CASES, USE_CASE_IDS
from core.models import (
    CodeGroup,
    CodeGroupMember,
    ContractBaseRate,
    ContractBlendingRule,
    ContractCapFloor,
    ContractCarveout,
    ContractOutlierRule,
    ContractProductScope,
    ContractScope,
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
    RefAspPricing,
    RefDrg,
    RefSpecialty,
)
from members.models import Enrollment, Member
from products.models import LineOfBusiness, Network, PayerOrganization, Product, ProductNetworkConfig
from providers.models import Provider, ProviderAffiliation, ProviderNetworkParticipation

logger = logging.getLogger(__name__)

EFFECTIVE_START = date(2025, 1, 1)
EFFECTIVE_END = date(2025, 12, 31)
SERVICE_DATE = date(2025, 6, 15)
REF_YEAR = 2025
ASP_QUARTER = "2025-Q2"

_stats: dict[str, int] = {}


def _d(v) -> Decimal:
    return Decimal(str(v))


def _bump(key: str, n: int = 1) -> None:
    _stats[key] = _stats.get(key, 0) + n


def _assert_demo_prefix(value: str, label: str) -> None:
    if not value or not str(value).startswith(PREFIX):
        raise ValueError(
            f"Refusing {label}={value!r}: must start with {PREFIX!r}"
        )


def _add_condition(rule: PricingRule, attribute_name: str, attribute_value: str) -> None:
    _, created = PricingRuleCondition.objects.get_or_create(
        pricing_rule=rule,
        attribute_name=attribute_name,
        operator="EQ",
        attribute_value=attribute_value,
        defaults={},
    )
    if created:
        _bump("PricingRuleCondition")


def _make_fee_schedule(name: str, rates: dict[str, str]) -> FeeSchedule:
    fs, created = FeeSchedule.objects.get_or_create(
        name=name,
        defaults={
            "effective_date": EFFECTIVE_START,
            "effective_start_date": EFFECTIVE_START,
            "effective_end_date": EFFECTIVE_END,
            "effective_year": REF_YEAR,
        },
    )
    if created:
        _bump("FeeSchedule")
    for code, amount in rates.items():
        _, fr_created = FeeScheduleRate.objects.get_or_create(
            fee_schedule=fs,
            code_id=code,
            defaults={
                "rate_amount": _d(amount),
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
                "year": REF_YEAR,
            },
        )
        if fr_created:
            _bump("FeeScheduleRate")
    return fs


def seed_drg_ref_topup() -> None:
    """
    Demo prerequisite for B5 claim-level DRG: DRGClaimPlugin looks up RefDrg by
    (drg_code, service_date.year). Ensure code 470 exists for REF_YEAR with a
    non-zero weight (mirrors core/demo/deterministic_seed.py).
    """
    _, created = RefDrg.objects.update_or_create(
        drg_code="470",
        defaults={
            "description": "Demo DRG 470",
            "relative_weight": _d("2.000000"),
            "year": REF_YEAR,
        },
    )
    if created:
        _bump("RefDrg")


def seed_asp_topup() -> None:
    """STEP 5: demo ASP rows only — get_or_create, never overwrite existing values."""
    rows = [
        ("J0129", _d("10.50"), _d("12.00")),
        ("J1885", _d("8.25"), _d("9.50")),   # ketorolac — demo prerequisite for B8
        ("J3490", _d("15.00"), _d("18.00")),
    ]
    for hcpcs, asp, limit in rows:
        _, created = RefAspPricing.objects.get_or_create(
            hcpcs_code=hcpcs,
            quarter=ASP_QUARTER,
            defaults={"asp": asp, "payment_limit": limit},
        )
        if created:
            _bump("RefAspPricing")


def _get_or_create_specialty(code: str, description: str) -> RefSpecialty:
    sp, created = RefSpecialty.objects.get_or_create(
        specialty_code=code,
        defaults={"description": description},
    )
    if created:
        _bump("RefSpecialty")
    return sp


class CastContext:
    """Shared DEMO-UC cast built once per seed run."""

    def __init__(self) -> None:
        self.payer_core: ProviderOrganization | None = None
        self.payer_products: PayerOrganization | None = None
        self.org_in: ProviderOrganization | None = None
        self.org_oon: ProviderOrganization | None = None
        self.lobs: dict[str, LineOfBusiness] = {}
        self.products: dict[str, Product] = {}
        self.legacy_networks: dict[str, PayerNetwork] = {}
        self.networks: dict[str, Network] = {}
        self.providers: dict[str, Provider] = {}
        self.members: dict[str, Member] = {}
        self.registry: dict[str, dict[str, Any]] = {}


def build_cast(ctx: CastContext) -> None:
    """STEP 2: shared payer/product/provider/member cast."""
    ctx.payer_core, created = ProviderOrganization.objects.get_or_create(
        organization_id=CAST["org_payer_core"],
        defaults={"name": "DEMO-UC Core Payer Org", "tax_id": "00-0000001"},
    )
    if created:
        _bump("ProviderOrganization")

    ctx.payer_products, created = PayerOrganization.objects.get_or_create(
        payer_id=CAST["payer_id"],
        defaults={
            "name": "Demo Health Plan",
            "payer_type": PayerOrganization.PayerType.COMMERCIAL,
        },
    )
    if created:
        _bump("PayerOrganization")

    for code, name in [
        ("COMMERCIAL", "Commercial"),
        ("MEDICARE_ADVANTAGE", "Medicare Advantage"),
        ("MEDICAID", "Medicaid"),
    ]:
        lob, created = LineOfBusiness.objects.get_or_create(
            code=code,
            defaults={"name": name},
        )
        ctx.lobs[code] = lob
        if created:
            _bump("LineOfBusiness")

    ctx.org_in, created = ProviderOrganization.objects.get_or_create(
        organization_id=CAST["org_in"],
        defaults={
            "name": "DEMO-UC In-Network Org",
            "tax_id": "11-1111111",
            "npi": CAST["billing_npi_in"],
        },
    )
    if created:
        _bump("ProviderOrganization")

    ctx.org_oon, created = ProviderOrganization.objects.get_or_create(
        organization_id=CAST["org_oon"],
        defaults={
            "name": "DEMO-UC Out-of-Network Org",
            "tax_id": "22-2222222",
            "npi": CAST["billing_npi_oon"],
        },
    )
    if created:
        _bump("ProviderOrganization")

    net_specs = [
        (CAST["net_ppo"], "DEMO-UC PPO Network", "PPO", "COMMERCIAL"),
        (CAST["net_hmo"], "DEMO-UC HMO Network", "HMO", "COMMERCIAL"),
        (CAST["net_tier"], "DEMO-UC Tiered Network", "TIERED", "COMMERCIAL"),
    ]
    for net_code, net_name, net_type, lob in net_specs:
        legacy, ln_created = PayerNetwork.objects.get_or_create(
            network_id=net_code,
            defaults={
                "network_name": net_name,
                "payer_org": ctx.payer_core,
                "line_of_business": lob,
            },
        )
        ctx.legacy_networks[net_code] = legacy
        if ln_created:
            _bump("PayerNetwork")

        net, n_created = Network.objects.get_or_create(
            network_code=net_code,
            defaults={
                "payer": ctx.payer_products,
                "name": net_name,
                "network_type": net_type,
                "legacy_payer_network": legacy,
            },
        )
        ctx.networks[net_code] = net
        if n_created:
            _bump("Network")

    prod_specs = [
        (CAST["prod_commercial"], "DEMO-UC Commercial PPO", "COMMERCIAL", CAST["net_ppo"]),
        (CAST["prod_ma"], "DEMO-UC Medicare Advantage", "MEDICARE_ADVANTAGE", CAST["net_ppo"]),
        (CAST["prod_medicaid"], "DEMO-UC Medicaid HMO", "MEDICAID", CAST["net_hmo"]),
    ]
    for pcode, pname, lob_code, net_code in prod_specs:
        prod, p_created = Product.objects.get_or_create(
            product_code=pcode,
            defaults={
                "payer": ctx.payer_products,
                "lob": ctx.lobs[lob_code],
                "name": pname,
                "effective_date": EFFECTIVE_START,
            },
        )
        ctx.products[pcode] = prod
        if p_created:
            _bump("Product")

        for claim_type in ("PROFESSIONAL", "ALL"):
            _, pnc_created = ProductNetworkConfig.objects.get_or_create(
                product=prod,
                network=ctx.networks[net_code],
                claim_type=claim_type,
                effective_date=EFFECTIVE_START,
                defaults={},
            )
            if pnc_created:
                _bump("ProductNetworkConfig")

    tier_prod, tp_created = Product.objects.get_or_create(
        product_code=f"{PREFIX}PROD-TIER",
        defaults={
            "payer": ctx.payer_products,
            "lob": ctx.lobs["COMMERCIAL"],
            "name": "DEMO-UC Tiered Product",
            "effective_date": EFFECTIVE_START,
        },
    )
    if tp_created:
        _bump("Product")
    ctx.products["TIER"] = tier_prod
    for claim_type in ("PROFESSIONAL", "ALL"):
        _, pnc_created = ProductNetworkConfig.objects.get_or_create(
            product=tier_prod,
            network=ctx.networks[CAST["net_tier"]],
            claim_type=claim_type,
            effective_date=EFFECTIVE_START,
            defaults={},
        )
        if pnc_created:
            _bump("ProductNetworkConfig")

    fam = _get_or_create_specialty(f"{PREFIX}FAM", "DEMO-UC Family Medicine")
    surg = _get_or_create_specialty(f"{PREFIX}SURG", "DEMO-UC Surgery")
    anes = _get_or_create_specialty(f"{PREFIX}ANES", "DEMO-UC Anesthesia")

    prov_specs = [
        (CAST["render_pcp"], "Pat", "Primary", fam),
        (CAST["render_surg"], "Sam", "Surgeon", surg),
        (CAST["render_anes"], "Ann", "Anesthesiologist", anes),
    ]
    for npi, first, last, spec in prov_specs:
        prov, pr_created = Provider.objects.get_or_create(
            npi=npi,
            defaults={
                "first_name": first,
                "last_name": last,
                "credential": "MD",
                "primary_specialty": spec,
                "status": "ACTIVE",
            },
        )
        ctx.providers[npi] = prov
        if pr_created:
            _bump("Provider")

    _, aff_created = ProviderAffiliation.objects.get_or_create(
        provider=ctx.providers[CAST["render_pcp"]],
        organization=ctx.org_in,
        effective_date=EFFECTIVE_START,
        defaults={"role": ProviderAffiliation.Role.EMPLOYEE},
    )
    if aff_created:
        _bump("ProviderAffiliation")
    # A9: surgeon NOT affiliated with billing org

    part_specs = [
        (ctx.org_in, CAST["net_ppo"], "IN_NETWORK"),
        (ctx.org_in, CAST["net_tier"], "TIER_2"),
        (ctx.org_oon, CAST["net_ppo"], "OUT_OF_NETWORK"),
    ]
    for org, net_code, status in part_specs:
        legacy = ctx.legacy_networks[net_code]
        net = ctx.networks[net_code]
        _, pn_created = ProviderNetworkParticipation.objects.get_or_create(
            organization=org,
            network=legacy,
            effective_date=EFFECTIVE_START,
            defaults={
                "status": status,
                "network_new": net,
            },
        )
        if pn_created:
            _bump("ProviderNetworkParticipation")

    member_specs = [
        ("DEMO-UC-MEM-A1", CAST["prod_commercial"]),
        ("DEMO-UC-MEM-A2", CAST["prod_commercial"]),
        ("DEMO-UC-MEM-NOENROLL", None),
        ("DEMO-UC-MEM-TERMED", CAST["prod_commercial"]),
        ("DEMO-UC-MEM-MA", CAST["prod_ma"]),
        ("DEMO-UC-MEM-HMO", CAST["prod_medicaid"]),
        ("DEMO-UC-MEM-TIER", f"{PREFIX}PROD-TIER"),
    ]
    for mid, prod_code in member_specs:
        member, m_created = Member.objects.get_or_create(
            member_id=mid,
            defaults={"first_name": "Demo", "last_name": mid[-3:], "zip_code": "60601"},
        )
        ctx.members[mid] = member
        if m_created:
            _bump("Member")

    for uc in USE_CASES:
        mid = uc["member_id"]
        if mid not in ctx.members and mid.startswith(PREFIX):
            member, m_created = Member.objects.get_or_create(
                member_id=mid,
                defaults={"first_name": "Demo", "last_name": uc["id"], "zip_code": "60601"},
            )
            ctx.members[mid] = member
            if m_created:
                _bump("Member")

    enroll_specs = [
        ("DEMO-UC-MEM-A1", CAST["prod_commercial"], EFFECTIVE_START, None),
        ("DEMO-UC-MEM-A2", CAST["prod_commercial"], EFFECTIVE_START, None),
        ("DEMO-UC-MEM-TERMED", CAST["prod_commercial"], EFFECTIVE_START, date(2025, 5, 1)),
        ("DEMO-UC-MEM-MA", CAST["prod_ma"], EFFECTIVE_START, None),
        ("DEMO-UC-MEM-HMO", CAST["prod_medicaid"], EFFECTIVE_START, None),
        ("DEMO-UC-MEM-TIER", f"{PREFIX}PROD-TIER", EFFECTIVE_START, None),
    ]
    for mid, prod_code, eff, term in enroll_specs:
        member = ctx.members[mid]
        product = ctx.products[prod_code] if prod_code != f"{PREFIX}PROD-TIER" else tier_prod
        _, e_created = Enrollment.objects.get_or_create(
            member=member,
            product=product,
            effective_date=eff,
            defaults={"termination_date": term},
        )
        if e_created:
            _bump("Enrollment")

    for uc in USE_CASES:
        mid = uc["member_id"]
        if mid == "DEMO-UC-MEM-NOENROLL" or mid in {e[0] for e in enroll_specs}:
            continue
        if not mid.startswith(PREFIX):
            continue
        member = ctx.members[mid]
        product = ctx.products[CAST["prod_commercial"]]
        _, e_created = Enrollment.objects.get_or_create(
            member=member,
            product=product,
            effective_date=EFFECTIVE_START,
            defaults={},
        )
        if e_created:
            _bump("Enrollment")


def _contract_legacy(uc_id: str) -> str:
    return f"{PREFIX}{uc_id}"


def _contract_exists(uc_id: str) -> bool:
    return ProviderContract.objects.filter(
        legacy_contract_number=_contract_legacy(uc_id)
    ).exists()


def _create_shell(
    ctx: CastContext,
    uc_id: str,
    *,
    org: ProviderOrganization | None = None,
    network_code: str | None = None,
    line_of_business: str | None = "COMMERCIAL",
    effective_start: date | None = None,
    effective_end: date | None = None,
) -> tuple[ProviderContract, ContractVersion]:
    legacy = _contract_legacy(uc_id)
    org = org or ctx.org_in
    network_code = network_code or CAST["net_ppo"]
    eff_start = effective_start or EFFECTIVE_START
    eff_end = effective_end or EFFECTIVE_END
    legacy_net = ctx.legacy_networks[network_code]

    contract, c_created = ProviderContract.objects.get_or_create(
        legacy_contract_number=legacy,
        defaults={
            "contract_name": legacy,
            "status": "ACTIVE",
            "effective_start_date": eff_start,
            "effective_end_date": eff_end,
            "provider_org": org,
            "network": legacy_net,
            "line_of_business": line_of_business,
        },
    )
    if c_created:
        _bump("ProviderContract")

    version, v_created = ContractVersion.objects.get_or_create(
        contract=contract,
        version_number=1,
        defaults={
            "effective_start_date": eff_start,
            "effective_end_date": eff_end,
            "status": ContractVersion.VersionStatus.ACTIVE,
        },
    )
    if v_created:
        _bump("ContractVersion")
    return contract, version


def _base_rule(
    contract: ProviderContract,
    version: ContractVersion,
    *,
    rule_name: str,
    methodology_code: str,
    procedure_code: str,
    claim_type: str | None = None,
    specificity_score: int = 10,
    **rule_kwargs,
) -> PricingRule:
    rule, created = PricingRule.objects.get_or_create(
        contract=contract,
        version=version,
        rule_name=rule_name,
        defaults={
            "rule_type": "BASE",
            "methodology_code": methodology_code,
            "status": PricingRule.RuleStatus.ACTIVE,
            "effective_start_date": contract.effective_start_date,
            "effective_end_date": contract.effective_end_date,
            "specificity_score": specificity_score,
            "claim_type": claim_type,
            **rule_kwargs,
        },
    )
    if created:
        _bump("PricingRule")
        _add_condition(rule, "procedure_code", procedure_code)
    return rule


def _register(ctx: CastContext, uc_id: str, contract: ProviderContract, version: ContractVersion) -> None:
    ctx.registry[uc_id] = {
        "contract_id": contract.contract_id,
        "version_id": version.version_id,
        "contract_name": contract.contract_name,
        "legacy_contract_number": contract.legacy_contract_number,
    }


def build_use_case_contracts(ctx: CastContext) -> None:
    """STEP 3: per use-case contracts (skip if already present)."""

    def go(uc_id: str, builder) -> None:
        if _contract_exists(uc_id):
            contract = ProviderContract.objects.get(legacy_contract_number=_contract_legacy(uc_id))
            version = ContractVersion.objects.filter(contract=contract).order_by("-version_number").first()
            if version:
                _register(ctx, uc_id, contract, version)
            return
        contract, version = builder()
        _register(ctx, uc_id, contract, version)

    # A1 / B1 style FLAT 99213
    def build_a1():
        c, v = _create_shell(ctx, "A1")
        _base_rule(c, v, rule_name="FLAT 99213", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, product=ctx.products[CAST["prod_commercial"]],
            defaults={"lob_code": "COMMERCIAL", "effective_date": EFFECTIVE_START},
        )
        return c, v

    go("A1", build_a1)

    def build_a5():
        c, v = _create_shell(ctx, "A5", line_of_business="MEDICARE_ADVANTAGE")
        _base_rule(c, v, rule_name="FLAT MA", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("120.00"))
        ContractScope.objects.get_or_create(
            contract=c, line_of_business="MEDICARE_ADVANTAGE",
            defaults={"priority": 10},
        )
        return c, v

    go("A5", build_a5)

    def build_a6():
        c, v = _create_shell(ctx, "A6")
        _base_rule(c, v, rule_name="FLAT 99214 product", methodology_code="FLAT_RATE",
                   procedure_code="99214", flat_rate=_d("175.00"), specificity_score=20)
        ContractProductScope.objects.get_or_create(
            contract=c, product=ctx.products[CAST["prod_commercial"]],
            defaults={"lob_code": "COMMERCIAL", "effective_date": EFFECTIVE_START},
        )
        return c, v

    go("A6", build_a6)

    def build_a6b():
        c, v = _create_shell(ctx, "A6B")
        _base_rule(c, v, rule_name="FLAT 99214 LOB", methodology_code="FLAT_RATE",
                   procedure_code="99214", flat_rate=_d("100.00"), specificity_score=5)
        ContractScope.objects.get_or_create(
            contract=c, line_of_business="COMMERCIAL", defaults={"priority": 50},
        )
        return c, v

    go("A6B", build_a6b)

    def build_a7():
        c, v = _create_shell(ctx, "A7", network_code=CAST["net_ppo"])
        _base_rule(c, v, rule_name="FLAT PPO only", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("90.00"))
        return c, v

    go("A7", build_a7)

    def build_a8():
        c, v = _create_shell(ctx, "A8", network_code=CAST["net_tier"])
        _base_rule(c, v, rule_name="FLAT tier", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("95.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, product=ctx.products["TIER"],
            defaults={"lob_code": "COMMERCIAL", "effective_date": EFFECTIVE_START},
        )
        return c, v

    go("A8", build_a8)

    def build_b1():
        c, v = _create_shell(ctx, "B1")
        _base_rule(c, v, rule_name="FLAT 99213", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, product=ctx.products[CAST["prod_commercial"]],
            defaults={"lob_code": "COMMERCIAL", "effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B1", build_b1)

    def build_b2():
        c, v = _create_shell(ctx, "B2")
        _base_rule(c, v, rule_name="PCT 99214", methodology_code="PCT_BILLED",
                   procedure_code="99214", multiplier=_d("0.80"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B2", build_b2)

    def build_b3():
        c, v = _create_shell(ctx, "B3")
        fs = _make_fee_schedule(f"{PREFIX}FS-B3", {"29881": "500.00"})
        _base_rule(c, v, rule_name="RBRVS 29881", methodology_code="RBRVS",
                   procedure_code="29881", base_fee_schedule=fs, multiplier=_d("1.5"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B3", build_b3)

    def build_b4():
        c, v = _create_shell(ctx, "B4")
        _base_rule(c, v, rule_name="PER_DIEM 0120", methodology_code="PER_DIEM",
                   procedure_code="0120", flat_rate=_d("400.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B4", build_b4)

    def build_b5():
        c, v = _create_shell(ctx, "B5", line_of_business="COMMERCIAL")
        version = v
        version.claim_level_drg_enabled = True
        version.save(update_fields=["claim_level_drg_enabled"])
        FacilityBaseRate.objects.get_or_create(
            contract=c, version=version, facility_id=None, rate_type="DRG",
            defaults={
                "base_rate": _d("6000.00"),
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
            },
        )
        ContractBaseRate.objects.get_or_create(
            version=version, rate_type="DRG",
            defaults={"base_rate": _d("6000.00")},
        )
        _base_rule(c, version, rule_name="DRG 470", methodology_code="DRG",
                   procedure_code="470", specificity_score=20)
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, version

    go("B5", build_b5)

    def build_b6():
        c, v = _create_shell(ctx, "B6")
        ContractBaseRate.objects.get_or_create(
            version=v, rate_type="APC", defaults={"base_rate": _d("100.00")},
        )
        _base_rule(c, v, rule_name="APC 5121", methodology_code="APC",
                   procedure_code="5121", multiplier=_d("1.0"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B6", build_b6)

    def build_b7():
        c, v = _create_shell(ctx, "B7")
        fs = _make_fee_schedule(f"{PREFIX}FS-B7", {"00100": "5.00"})
        _base_rule(c, v, rule_name="ANES 00100", methodology_code="ANESTHESIA",
                   procedure_code="00100", base_fee_schedule=fs, multiplier=_d("45.00"))
        _base_rule(c, v, rule_name="FLAT 99100", methodology_code="FLAT_RATE",
                   procedure_code="99100", flat_rate=_d("25.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B7", build_b7)

    def build_b8():
        c, v = _create_shell(ctx, "B8")
        _base_rule(c, v, rule_name="ASP J1885", methodology_code="ASP",
                   procedure_code="J1885", multiplier=_d("1.0"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("B8", build_b8)

    def build_c1():
        c, v = _create_shell(ctx, "C1")
        fs = _make_fee_schedule(f"{PREFIX}FS-C1", {"29881": "400.00"})
        _base_rule(c, v, rule_name="RBRVS 29881", methodology_code="RBRVS",
                   procedure_code="29881", base_fee_schedule=fs, multiplier=_d("1.0"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("C1", build_c1)

    def build_c2():
        c, v = _create_shell(ctx, "C2")
        _base_rule(c, v, rule_name="FLAT 99213", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"))
        _base_rule(c, v, rule_name="FLAT 73030", methodology_code="FLAT_RATE",
                   procedure_code="73030", flat_rate=_d("75.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("C2", build_c2)

    def build_c3():
        c, v = _create_shell(ctx, "C3")
        fs = _make_fee_schedule(f"{PREFIX}FS-C3", {"70450": "200.00"})
        _base_rule(c, v, rule_name="RBRVS 70450", methodology_code="RBRVS",
                   procedure_code="70450", base_fee_schedule=fs, multiplier=_d("1.0"))
        mppr, mp_created = MPPRDefinition.objects.get_or_create(
            contract=c, version=v, name=f"{PREFIX}MPPR-70450",
            defaults={
                "rank_by": MPPRDefinition.RANK_BY_ALLOWED,
                "primary_pct": _d("100.00"),
                "secondary_pct": _d("50.00"),
                "tertiary_pct": _d("25.00"),
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
            },
        )
        if mp_created:
            _bump("MPPRDefinition")
        MPPRScope.objects.get_or_create(mppr_definition=mppr, procedure_code="70450")
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("C3", build_c3)

    def build_policy(uc_id: str, *, carveout: bool = False, outlier: bool = False,
                     stop_loss: bool = False, blending: bool = False,
                     line_cap: bool = False, claim_cap: bool = False) -> tuple:
        c, v = _create_shell(ctx, uc_id)
        fs = _make_fee_schedule(f"{PREFIX}FS-{uc_id}", {"99213": "100.00", "99100": "80.00", "73030": "50.00"})
        _base_rule(c, v, rule_name="RBRVS 99213", methodology_code="RBRVS",
                   procedure_code="99213", base_fee_schedule=fs, multiplier=_d("1.5"))
        _base_rule(c, v, rule_name="RBRVS 99100", methodology_code="RBRVS",
                   procedure_code="99100", base_fee_schedule=fs, multiplier=_d("1.0"))
        if carveout:
            ContractCarveout.objects.get_or_create(
                version=v, code_type="CPT", code_value="99100",
                defaults={"carveout_methodology": "EXCLUDE"},
            )
        if stop_loss:
            _base_rule(c, v, rule_name="FLAT SL-TRIG", methodology_code="FLAT_RATE",
                       procedure_code="SL-TRIG", flat_rate=_d("100.00"))
            ContractStopLossRule.objects.get_or_create(
                contract=c, version=v,
                defaults={
                    "cost_threshold": _d("1000.00"),
                    "reimbursement_percentage": _d("50.00"),
                    "priority": 0,
                    "effective_start_date": EFFECTIVE_START,
                    "effective_end_date": EFFECTIVE_END,
                },
            )
        if outlier:
            ContractOutlierRule.objects.get_or_create(
                contract=c, version=v,
                defaults={
                    "threshold_amount": _d("1000.00"),
                    "threshold_scope": "PER_CLAIM",
                    "reimbursement_percentage": _d("80.00"),
                    "priority": 0,
                    "effective_start_date": EFFECTIVE_START,
                    "effective_end_date": EFFECTIVE_END,
                },
            )
        if blending:
            ContractBlendingRule.objects.get_or_create(
                version=v, blend_type="ADD", scope="CLAIM",
                defaults={
                    "primary_methodology": "",
                    "secondary_methodology": "PERCENT_BILLED",
                    "blend_percentage": _d("10.00"),
                    "priority": 0,
                    "effective_start_date": EFFECTIVE_START,
                    "effective_end_date": EFFECTIVE_END,
                },
            )
        if line_cap:
            ContractCapFloor.objects.get_or_create(
                version=v, scope="LINE", cap_type="PCT_BILLED_CAP", percentage=_d("60.00"),
                defaults={
                    "priority": 0,
                    "effective_start_date": EFFECTIVE_START,
                    "effective_end_date": EFFECTIVE_END,
                },
            )
        if claim_cap:
            ContractCapFloor.objects.get_or_create(
                version=v, scope="CLAIM", cap_type="CAP", value=_d("250.00"),
                defaults={
                    "priority": 0,
                    "effective_start_date": EFFECTIVE_START,
                    "effective_end_date": EFFECTIVE_END,
                },
            )
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("C4", lambda: build_policy("C4", carveout=True))
    go("C5", lambda: build_policy("C5", line_cap=True))
    go("C6", lambda: build_policy("C6", outlier=True))
    go("C7", lambda: build_policy("C7", stop_loss=True))
    go("C8", lambda: build_policy("C8", blending=True))

    def build_c9():
        c, v = _create_shell(ctx, "C9")
        cg, cg_created = CodeGroup.objects.get_or_create(
            contract=c, version=v, code_group_code=f"{PREFIX}LAB",
            defaults={
                "name": "DEMO-UC Lab Codes",
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
            },
        )
        if cg_created:
            _bump("CodeGroup")
        CodeGroupMember.objects.get_or_create(
            code_group=cg, code_id="36415",
            defaults={
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
            },
        )
        rule, created = PricingRule.objects.get_or_create(
            contract=c, version=v, rule_name="FLAT lab group",
            defaults={
                "rule_type": "BASE",
                "methodology_code": "FLAT_RATE",
                "flat_rate": _d("30.00"),
                "status": PricingRule.RuleStatus.ACTIVE,
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
                "specificity_score": 15,
                "claim_type": None,
            },
        )
        if created:
            _bump("PricingRule")
            _add_condition(rule, "code_group", str(cg.id))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("C9", build_c9)

    def build_c10():
        c, v = _create_shell(ctx, "C10")
        _base_rule(c, v, rule_name="Generic prof low", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"), specificity_score=5)
        _base_rule(c, v, rule_name="Specific 99214", methodology_code="FLAT_RATE",
                   procedure_code="99214", flat_rate=_d("175.00"), specificity_score=20)
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("C10", build_c10)

    def build_d1():
        c, v = _create_shell(ctx, "D1")
        _base_rule(c, v, rule_name="FLAT 99213 only", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("D1", build_d1)

    def build_d2():
        c, v = _create_shell(ctx, "D2")
        _base_rule(c, v, rule_name="FLAT 99213", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("D2", build_d2)

    def build_d3():
        c, v = _create_shell(ctx, "D3")
        _base_rule(c, v, rule_name="PCT 99214", methodology_code="PCT_BILLED",
                   procedure_code="99214", multiplier=_d("0.80"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("D3", build_d3)

    def build_d4():
        c, v = _create_shell(ctx, "D4")
        _base_rule(c, v, rule_name="FLAT 99213", methodology_code="FLAT_RATE",
                   procedure_code="99213", flat_rate=_d("100.00"))
        ContractProductScope.objects.get_or_create(
            contract=c, lob_code="COMMERCIAL", product=None,
            defaults={"effective_date": EFFECTIVE_START},
        )
        return c, v

    go("D4", build_d4)

    # Resolution-only cases without dedicated contracts reuse A1 registry
    for uc_id in ("A2", "A3", "A4", "A9", "A10"):
        if uc_id not in ctx.registry and "A1" in ctx.registry:
            ctx.registry[uc_id] = {**ctx.registry["A1"], "notes": f"resolves via {PREFIX}A1 or none"}


def _count_demo_rows() -> dict[str, int]:
    return {
        "ProviderContract": ProviderContract.objects.filter(
            legacy_contract_number__startswith=PREFIX
        ).count(),
        "Member": Member.objects.filter(member_id__startswith=PREFIX).count(),
        "Provider": Provider.objects.filter(npi__startswith=PREFIX).count(),
        "ProviderOrganization": ProviderOrganization.objects.filter(
            organization_id__startswith=PREFIX
        ).count(),
        "PayerOrganization": PayerOrganization.objects.filter(
            payer_id__startswith=PREFIX
        ).count(),
        "Product": Product.objects.filter(product_code__startswith=PREFIX).count(),
        "Enrollment": Enrollment.objects.filter(member__member_id__startswith=PREFIX).count(),
    }


def wipe_demo_uc(stdout=None) -> dict[str, int]:
    """Delete ONLY DEMO-UC- rows and dependents. Guarded — raises if prefix mismatch."""
    def out(msg: str) -> None:
        if stdout:
            stdout.write(msg)
        else:
            logger.info(msg)

    contracts = list(
        ProviderContract.objects.filter(legacy_contract_number__startswith=PREFIX)
    )
    for c in contracts:
        _assert_demo_prefix(c.legacy_contract_number or "", "contract")

    members = list(Member.objects.filter(member_id__startswith=PREFIX))
    for m in members:
        _assert_demo_prefix(m.member_id, "member")

    providers = list(Provider.objects.filter(npi__startswith=PREFIX))
    for p in providers:
        _assert_demo_prefix(p.npi, "provider")

    orgs = list(ProviderOrganization.objects.filter(organization_id__startswith=PREFIX))
    for o in orgs:
        _assert_demo_prefix(o.organization_id, "org")

    payers = list(PayerOrganization.objects.filter(payer_id__startswith=PREFIX))
    for p in payers:
        _assert_demo_prefix(p.payer_id, "payer")

    products = list(Product.objects.filter(product_code__startswith=PREFIX))
    for p in products:
        _assert_demo_prefix(p.product_code or "", "product")

    networks = list(PayerNetwork.objects.filter(network_id__startswith=PREFIX))
    for n in networks:
        _assert_demo_prefix(n.network_id, "network")

    fee_schedules = list(FeeSchedule.objects.filter(name__startswith=PREFIX))
    for fs in fee_schedules:
        _assert_demo_prefix(fs.name, "fee_schedule")

    counts = {
        "contracts": len(contracts),
        "members": len(members),
        "providers": len(providers),
        "orgs": len(orgs),
        "payers": len(payers),
        "products": len(products),
        "networks": len(networks),
        "fee_schedules": len(fee_schedules),
    }
    out(f"--wipe will delete DEMO-UC- rows: {counts}")

    with transaction.atomic():
        from core.models import ClaimResolutionLog

        deleted_logs = ClaimResolutionLog.objects.filter(
            resolved_contract__legacy_contract_number__startswith=PREFIX
        ).delete()[0]
        if deleted_logs:
            out(f"Deleted {deleted_logs} ClaimResolutionLog row(s) for DEMO-UC contracts")

        for c in contracts:
            c.delete()
        for fs in fee_schedules:
            fs.delete()
        for m in members:
            m.delete()
        for p in providers:
            p.delete()
        for pr in products:
            pr.delete()
        Network.objects.filter(network_code__startswith=PREFIX).delete()
        for n in networks:
            n.delete()
        for o in orgs:
            o.delete()
        for p in payers:
            p.delete()

    return counts


@transaction.atomic
def seed_use_cases_atomic(*, wipe: bool = False, stdout=None) -> dict[str, Any]:
    global _stats
    _stats = {}

    if wipe:
        wipe_demo_uc(stdout=stdout)

    seed_asp_topup()
    seed_drg_ref_topup()
    ctx = CastContext()
    build_cast(ctx)
    build_use_case_contracts(ctx)

    # Fill registry from USE_CASES for summary
    summary_cases = []
    for uc in USE_CASES:
        uc_id = uc["id"]
        meta = ctx.registry.get(uc_id, ctx.registry.get("A1", {}))
        summary_cases.append({
            "id": uc_id,
            "family": uc["family"],
            "member_id": uc["member_id"],
            "billing_npi": uc["billing_npi"],
            "contract_name": meta.get("contract_name") or _contract_legacy(uc_id),
            "contract_id": meta.get("contract_id"),
            "expected_status": uc["expected_status"],
        })

    demo_counts = _count_demo_rows()

    if stdout:
        stdout.write("\nDEMO-UC contract → version map (update test catalog after --wipe):")
        seen: set[tuple[int | None, int | None]] = set()
        for uc_id in sorted(
            ctx.registry.keys(),
            key=lambda x: (ctx.registry[x].get("contract_name") or "", x),
        ):
            meta = ctx.registry[uc_id]
            key = (meta.get("contract_id"), meta.get("version_id"))
            if key in seen:
                continue
            seen.add(key)
            stdout.write(
                f"  {meta.get('contract_name', _contract_legacy(uc_id))}: "
                f"contract_id={meta.get('contract_id')} "
                f"version_id={meta.get('version_id')}"
            )

    return {
        "created_stats": dict(_stats),
        "demo_row_counts": demo_counts,
        "use_cases": summary_cases,
        "registry": ctx.registry,
    }
