"""
KEYSTONE-* multi-entity seed — resolution scenario catalog (R2/R3/R4/R5/F7/E2/E3).

All natural keys use the KEYSTONE- prefix. Idempotent get_or_create; --wipe deletes
only KEYSTONE-* rows (guarded). See docs/CONTRACT_RESOLUTION_SCENARIOS.md.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from core.models import (
    ContractArrangement,
    ContractCoveredEntity,
    ContractProductScope,
    ContractResolutionException,
    ContractVersion,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
    RefProcedureCode,
    RefSpecialty,
)
from members.models import Enrollment, Member
from products.models import LineOfBusiness, Network, PayerOrganization, Product, ProductNetworkConfig
from providers.models import (
    Facility,
    FacilityNetworkParticipation,
    Provider,
    ProviderAffiliation,
    ProviderNetworkParticipation,
)

logger = logging.getLogger(__name__)

PREFIX = "KEYSTONE-"

EFFECTIVE_START = date(2025, 1, 1)
EFFECTIVE_END = date(2025, 12, 31)
SERVICE_DATE = date(2025, 6, 15)

# Natural keys (all KEYSTONE- prefixed)
KEYS = {
    "payer_id": f"{PREFIX}PAYER",
    "payer_core_org": f"{PREFIX}PAYER-CORE",
    "prod_code": f"{PREFIX}PROD-PPO",
    "net_code": f"{PREFIX}NET-PPO",
    "org_idn": f"{PREFIX}IDN",
    "org_card": f"{PREFIX}CARD",
    "npi_idn": f"{PREFIX}NPI01",
    "npi_card": f"{PREFIX}NPI02",
    "npi_f1": f"{PREFIX}NPI03",
    "npi_f2": f"{PREFIX}NPI04",
    "npi_chen": f"{PREFIX}NPI05",
    "fac_ccn_f1": f"{PREFIX}F1",
    "fac_ccn_f2": f"{PREFIX}F2",
    "member_id": f"{PREFIX}MEM-1",
    "spec_cardio": f"{PREFIX}CARDIO",
    "contract_idn": f"{PREFIX}C-IDN",
    "contract_card": f"{PREFIX}C-CARD",
    "contract_f1": f"{PREFIX}C-F1",
    "contract_card_old": f"{PREFIX}C-CARD-OLD",
}

CONTRACT_SPECS = [
    {
        "legacy": KEYS["contract_idn"],
        "name": "Keystone IDN Professional",
        "org_key": "org_idn",
        "rate": "130.00",
        "covered": [{"type": "ORG", "org_key": "org_idn", "primary": True}],
    },
    {
        "legacy": KEYS["contract_card"],
        "name": "Keystone Cardiology Group",
        "org_key": "org_card",
        "rate": "150.00",
        "covered": [
            {"type": "ORG", "org_key": "org_card", "primary": True},
            {"type": "PROVIDER", "provider_key": "npi_chen", "primary": False},
        ],
    },
    {
        "legacy": KEYS["contract_f1"],
        "name": "Keystone General Hospital Facility",
        "org_key": "org_idn",
        "rate": "200.00",
        "arrangement_claim_type": "INSTITUTIONAL",
        "covered": [{"type": "FACILITY", "facility_key": "npi_f1", "primary": True}],
    },
    {
        "legacy": KEYS["contract_card_old"],
        "name": "Keystone Cardiology Group (Legacy Unterminated)",
        "org_key": "org_card",
        "rate": "999.00",
        "covered": [{"type": "ORG", "org_key": "org_card", "primary": True}],
    },
]

_stats: dict[str, int] = {}


def _d(v) -> Decimal:
    return Decimal(str(v))


def _bump(key: str, n: int = 1) -> None:
    _stats[key] = _stats.get(key, 0) + n


def _assert_keystone_prefix(value: str, label: str) -> None:
    if not value or not str(value).startswith(PREFIX):
        raise ValueError(f"Refusing {label}={value!r}: must start with {PREFIX!r}")


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


class KeystoneContext:
    """Shared KEYSTONE cast built once per seed run."""

    def __init__(self) -> None:
        self.payer_core: ProviderOrganization | None = None
        self.payer_products: PayerOrganization | None = None
        self.lob: LineOfBusiness | None = None
        self.product: Product | None = None
        self.legacy_network: PayerNetwork | None = None
        self.network: Network | None = None
        self.orgs: dict[str, ProviderOrganization] = {}
        self.facilities: dict[str, Facility] = {}
        self.providers: dict[str, Provider] = {}
        self.member: Member | None = None
        self.registry: dict[str, dict[str, Any]] = {}


def _ensure_ref_data() -> None:
    _, created = RefProcedureCode.objects.get_or_create(
        code_id="99213",
        defaults={"description": "Office Visit Level 3"},
    )
    if created:
        _bump("RefProcedureCode")


def build_cast(ctx: KeystoneContext) -> None:
    """Payer, product, provider hierarchy, member enrollment."""
    _ensure_ref_data()

    ctx.payer_core, pc_created = ProviderOrganization.objects.get_or_create(
        organization_id=KEYS["payer_core_org"],
        defaults={"name": "Horizon Health Plan (Core)", "tax_id": "99-0000001"},
    )
    if pc_created:
        _bump("ProviderOrganization")

    ctx.payer_products, pp_created = PayerOrganization.objects.get_or_create(
        payer_id=KEYS["payer_id"],
        defaults={
            "name": "Horizon Health Plan",
            "payer_type": PayerOrganization.PayerType.COMMERCIAL,
            "legacy_provider_org": ctx.payer_core,
        },
    )
    if pp_created:
        _bump("PayerOrganization")

    ctx.lob, lob_created = LineOfBusiness.objects.get_or_create(
        code="COMMERCIAL",
        defaults={"name": "Commercial"},
    )
    if lob_created:
        _bump("LineOfBusiness")

    ctx.legacy_network, ln_created = PayerNetwork.objects.get_or_create(
        network_id=KEYS["net_code"],
        defaults={
            "network_name": "Horizon PPO Net",
            "payer_org": ctx.payer_core,
            "line_of_business": "COMMERCIAL",
            "network_type": "PPO",
        },
    )
    if ln_created:
        _bump("PayerNetwork")

    ctx.network, n_created = Network.objects.get_or_create(
        network_code=KEYS["net_code"],
        defaults={
            "payer": ctx.payer_products,
            "name": "Horizon PPO Net",
            "network_type": Network.NetworkType.PPO,
            "legacy_payer_network": ctx.legacy_network,
        },
    )
    if n_created:
        _bump("Network")

    ctx.product, prod_created = Product.objects.get_or_create(
        product_code=KEYS["prod_code"],
        defaults={
            "payer": ctx.payer_products,
            "lob": ctx.lob,
            "name": "Horizon PPO",
            "effective_date": EFFECTIVE_START,
        },
    )
    if prod_created:
        _bump("Product")

    for claim_type in ("PROFESSIONAL", "INSTITUTIONAL", "ALL"):
        _, pnc_created = ProductNetworkConfig.objects.get_or_create(
            product=ctx.product,
            network=ctx.network,
            claim_type=claim_type,
            effective_date=EFFECTIVE_START,
            defaults={},
        )
        if pnc_created:
            _bump("ProductNetworkConfig")

    ctx.orgs["org_idn"], idn_created = ProviderOrganization.objects.get_or_create(
        organization_id=KEYS["org_idn"],
        defaults={
            "name": "Keystone Health",
            "npi": KEYS["npi_idn"],
            "org_type": "HEALTH_SYSTEM",
            "tax_id": "11-1111111",
        },
    )
    if idn_created:
        _bump("ProviderOrganization")

    ctx.orgs["org_card"], card_created = ProviderOrganization.objects.get_or_create(
        organization_id=KEYS["org_card"],
        defaults={
            "name": "Keystone Cardiology Grp",
            "npi": KEYS["npi_card"],
            "org_type": "GROUP",
            "parent_org": ctx.orgs["org_idn"],
            "tax_id": "11-2222222",
        },
    )
    if card_created:
        _bump("ProviderOrganization")

    ctx.facilities["npi_f1"], f1_created = Facility.objects.get_or_create(
        npi=KEYS["npi_f1"],
        defaults={
            "ccn": KEYS["fac_ccn_f1"],
            "name": "Keystone General Hospital",
            "facility_type": Facility.FacilityType.HOSPITAL_OUTPATIENT,
            "status": "ACTIVE",
        },
    )
    if f1_created:
        _bump("Facility")

    ctx.facilities["npi_f2"], f2_created = Facility.objects.get_or_create(
        npi=KEYS["npi_f2"],
        defaults={
            "ccn": KEYS["fac_ccn_f2"],
            "name": "Keystone Suburban Hospital",
            "facility_type": Facility.FacilityType.HOSPITAL_OUTPATIENT,
            "status": "ACTIVE",
        },
    )
    if f2_created:
        _bump("Facility")

    specialty, sp_created = RefSpecialty.objects.get_or_create(
        specialty_code=KEYS["spec_cardio"],
        defaults={"description": "KEYSTONE Cardiology"},
    )
    if sp_created:
        _bump("RefSpecialty")

    ctx.providers["npi_chen"], prov_created = Provider.objects.get_or_create(
        npi=KEYS["npi_chen"],
        defaults={
            "first_name": "Sarah",
            "last_name": "Chen",
            "credential": "MD",
            "primary_specialty": specialty,
            "status": "ACTIVE",
        },
    )
    if prov_created:
        _bump("Provider")

    _, aff_created = ProviderAffiliation.objects.get_or_create(
        provider=ctx.providers["npi_chen"],
        organization=ctx.orgs["org_card"],
        effective_date=EFFECTIVE_START,
        defaults={"role": ProviderAffiliation.Role.EMPLOYEE},
    )
    if aff_created:
        _bump("ProviderAffiliation")

    for org_key in ("org_idn", "org_card"):
        org = ctx.orgs[org_key]
        _, pn_created = ProviderNetworkParticipation.objects.get_or_create(
            organization=org,
            network=ctx.legacy_network,
            effective_date=EFFECTIVE_START,
            defaults={
                "status": ProviderNetworkParticipation.Status.IN_NETWORK,
                "network_new": ctx.network,
            },
        )
        if pn_created:
            _bump("ProviderNetworkParticipation")

    for fac_key in ("npi_f1", "npi_f2"):
        fac = ctx.facilities[fac_key]
        _, fn_created = FacilityNetworkParticipation.objects.get_or_create(
            facility=fac,
            network=ctx.legacy_network,
            effective_date=EFFECTIVE_START,
            defaults={"status": "IN_NETWORK"},
        )
        if fn_created:
            _bump("FacilityNetworkParticipation")

    ctx.member, mem_created = Member.objects.get_or_create(
        member_id=KEYS["member_id"],
        defaults={
            "first_name": "Alex",
            "last_name": "Patient",
            "zip_code": "19104",
        },
    )
    if mem_created:
        _bump("Member")

    _, enr_created = Enrollment.objects.get_or_create(
        member=ctx.member,
        product=ctx.product,
        effective_date=EFFECTIVE_START,
        defaults={"termination_date": None},
    )
    if enr_created:
        _bump("Enrollment")


def _resolve_covered_entity(
    ctx: KeystoneContext,
    spec: dict,
) -> dict[str, Any]:
    entity_type = spec["type"]
    defaults = {
        "is_primary": spec.get("primary", False),
        "effective_start_date": EFFECTIVE_START,
        "effective_end_date": EFFECTIVE_END,
    }
    lookup: dict[str, Any] = {"entity_type": entity_type}
    if entity_type == "ORG":
        org = ctx.orgs[spec["org_key"]]
        lookup["organization"] = org
    elif entity_type == "FACILITY":
        fac = ctx.facilities[spec["facility_key"]]
        lookup["facility"] = fac
    elif entity_type == "PROVIDER":
        prov = ctx.providers[spec["provider_key"]]
        lookup["provider"] = prov
    else:
        raise ValueError(f"Unknown covered entity type: {entity_type}")
    return lookup, defaults


def _contract_exists(legacy: str) -> bool:
    return ProviderContract.objects.filter(legacy_contract_number=legacy).exists()


def build_contracts(ctx: KeystoneContext) -> None:
    """Four KEYSTONE contracts with versions, rules, covered entities, arrangements."""
    assert ctx.product and ctx.legacy_network and ctx.payer_products

    for spec in CONTRACT_SPECS:
        legacy = spec["legacy"]
        _assert_keystone_prefix(legacy, "contract")

        if _contract_exists(legacy):
            contract = ProviderContract.objects.get(legacy_contract_number=legacy)
            version = (
                ContractVersion.objects.filter(contract=contract)
                .order_by("-version_number")
                .first()
            )
            desired_claim_type = spec.get("arrangement_claim_type")
            if desired_claim_type is not None:
                ContractArrangement.objects.filter(
                    contract=contract,
                    name=f"{legacy} Fee Schedule",
                ).update(claim_type=desired_claim_type)
            if version:
                _register_contract(ctx, spec, contract, version)
            continue

        org = ctx.orgs[spec["org_key"]]
        contract, c_created = ProviderContract.objects.get_or_create(
            legacy_contract_number=legacy,
            defaults={
                "contract_name": spec["name"],
                "status": "ACTIVE",
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
                "provider_org": org,
                "network": ctx.legacy_network,
                "line_of_business": "COMMERCIAL",
                "contract_origin_type": ProviderContract.ContractOriginType.DIRECT,
                "resolution_priority": 10,
                "payer_org": ctx.payer_products,
            },
        )
        if c_created:
            _bump("ProviderContract")

        version, v_created = ContractVersion.objects.get_or_create(
            contract=contract,
            version_number=1,
            defaults={
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
                "status": ContractVersion.VersionStatus.ACTIVE,
            },
        )
        if v_created:
            _bump("ContractVersion")

        _, ps_created = ContractProductScope.objects.get_or_create(
            contract=contract,
            product=ctx.product,
            defaults={
                "lob_code": "COMMERCIAL",
                "effective_date": EFFECTIVE_START,
            },
        )
        if ps_created:
            _bump("ContractProductScope")

        arrangement, arr_created = ContractArrangement.objects.get_or_create(
            contract=contract,
            name=f"{legacy} Fee Schedule",
            defaults={
                "arrangement_type": ContractArrangement.ArrangementType.FEE_SCHEDULE,
                "claim_type": spec.get("arrangement_claim_type"),
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
                "status": ContractVersion.VersionStatus.ACTIVE,
            },
        )
        desired_claim_type = spec.get("arrangement_claim_type")
        if not arr_created and arrangement.claim_type != desired_claim_type:
            arrangement.claim_type = desired_claim_type
            arrangement.save(update_fields=["claim_type"])
        if arr_created:
            _bump("ContractArrangement")

        rule_name = f"{legacy} FLAT 99213"
        rule, r_created = PricingRule.objects.get_or_create(
            contract=contract,
            version=version,
            rule_name=rule_name,
            defaults={
                "rule_type": "BASE",
                "methodology_code": "FLAT_RATE",
                "status": PricingRule.RuleStatus.ACTIVE,
                "effective_start_date": EFFECTIVE_START,
                "effective_end_date": EFFECTIVE_END,
                "specificity_score": 10,
                "claim_type": None,
                "flat_rate": _d(spec["rate"]),
                "arrangement": arrangement,
            },
        )
        if r_created:
            _bump("PricingRule")
            _add_condition(rule, "procedure_code", "99213")

        for cov_spec in spec["covered"]:
            lookup, defaults = _resolve_covered_entity(ctx, cov_spec)
            _, ce_created = ContractCoveredEntity.objects.get_or_create(
                contract=contract,
                **lookup,
                defaults=defaults,
            )
            if ce_created:
                _bump("ContractCoveredEntity")

        _register_contract(ctx, spec, contract, version)


def _register_contract(
    ctx: KeystoneContext,
    spec: dict,
    contract: ProviderContract,
    version: ContractVersion,
) -> None:
    covered_rows = []
    for ce in contract.covered_entities.select_related(
        "organization", "facility", "provider"
    ).all():
        if ce.entity_type == ContractCoveredEntity.EntityType.ORG and ce.organization:
            label = f"ORG={ce.organization.organization_id}"
        elif ce.entity_type == ContractCoveredEntity.EntityType.FACILITY and ce.facility:
            label = f"FACILITY={ce.facility.npi}"
        elif ce.entity_type == ContractCoveredEntity.EntityType.PROVIDER and ce.provider:
            label = f"PROVIDER={ce.provider.npi}"
        else:
            label = ce.entity_type
        covered_rows.append(
            f"{label}{' (primary)' if ce.is_primary else ''}"
        )

    rule = (
        PricingRule.objects.filter(contract=contract, version=version)
        .order_by("rule_id")
        .first()
    )
    rate = str(rule.flat_rate) if rule and rule.flat_rate is not None else spec["rate"]

    ctx.registry[spec["legacy"]] = {
        "legacy": spec["legacy"],
        "name": spec["name"],
        "contract_id": contract.contract_id,
        "version_id": version.version_id,
        "rate_99213": rate,
        "covered_entities": covered_rows,
    }


def _count_keystone_rows() -> dict[str, int]:
    return {
        "ProviderContract": ProviderContract.objects.filter(
            legacy_contract_number__startswith=PREFIX
        ).count(),
        "ContractCoveredEntity": ContractCoveredEntity.objects.filter(
            contract__legacy_contract_number__startswith=PREFIX
        ).count(),
        "Member": Member.objects.filter(member_id__startswith=PREFIX).count(),
        "Provider": Provider.objects.filter(npi__startswith=PREFIX).count(),
        "Facility": Facility.objects.filter(npi__startswith=PREFIX).count(),
        "ProviderOrganization": ProviderOrganization.objects.filter(
            organization_id__startswith=PREFIX
        ).count(),
        "PayerOrganization": PayerOrganization.objects.filter(
            payer_id__startswith=PREFIX
        ).count(),
        "Product": Product.objects.filter(product_code__startswith=PREFIX).count(),
        "Enrollment": Enrollment.objects.filter(
            member__member_id__startswith=PREFIX
        ).count(),
    }


def wipe_keystone(stdout=None) -> dict[str, int]:
    """Delete ONLY KEYSTONE-* rows and dependents. Guarded — raises on prefix mismatch."""
    def out(msg: str) -> None:
        if stdout:
            stdout.write(msg)
        else:
            logger.info(msg)

    contracts = list(
        ProviderContract.objects.filter(legacy_contract_number__startswith=PREFIX)
    )
    for c in contracts:
        _assert_keystone_prefix(c.legacy_contract_number or "", "contract")

    members = list(Member.objects.filter(member_id__startswith=PREFIX))
    for m in members:
        _assert_keystone_prefix(m.member_id, "member")

    providers = list(Provider.objects.filter(npi__startswith=PREFIX))
    for p in providers:
        _assert_keystone_prefix(p.npi, "provider")

    facilities = list(Facility.objects.filter(npi__startswith=PREFIX))
    for f in facilities:
        _assert_keystone_prefix(f.npi, "facility")

    orgs = list(ProviderOrganization.objects.filter(organization_id__startswith=PREFIX))
    for o in orgs:
        _assert_keystone_prefix(o.organization_id, "org")

    payers = list(PayerOrganization.objects.filter(payer_id__startswith=PREFIX))
    for p in payers:
        _assert_keystone_prefix(p.payer_id, "payer")

    products = list(Product.objects.filter(product_code__startswith=PREFIX))
    for p in products:
        _assert_keystone_prefix(p.product_code or "", "product")

    networks = list(PayerNetwork.objects.filter(network_id__startswith=PREFIX))
    for n in networks:
        _assert_keystone_prefix(n.network_id, "network")

    counts = {
        "contracts": len(contracts),
        "members": len(members),
        "providers": len(providers),
        "facilities": len(facilities),
        "orgs": len(orgs),
        "payers": len(payers),
        "products": len(products),
        "networks": len(networks),
    }
    out(f"--wipe will delete KEYSTONE- rows: {counts}")

    with transaction.atomic():
        from core.models import ClaimResolutionLog

        deleted_logs = ClaimResolutionLog.objects.filter(
            resolved_contract__legacy_contract_number__startswith=PREFIX
        ).delete()[0]
        if deleted_logs:
            out(f"Deleted {deleted_logs} ClaimResolutionLog row(s) for KEYSTONE contracts")

        deleted_exc = ContractResolutionException.objects.filter(
            gathered_inputs__member_id__startswith=PREFIX
        ).delete()[0]
        if deleted_exc:
            out(f"Deleted {deleted_exc} ContractResolutionException row(s) for KEYSTONE")

        for c in contracts:
            c.delete()
        for m in members:
            m.delete()
        for p in providers:
            p.delete()
        for f in facilities:
            f.delete()
        Network.objects.filter(network_code__startswith=PREFIX).delete()
        for pr in products:
            pr.delete()
        for n in networks:
            n.delete()
        # Child orgs before parents
        for org_id in (KEYS["org_card"], KEYS["org_idn"], KEYS["payer_core_org"]):
            ProviderOrganization.objects.filter(organization_id=org_id).delete()
        for p in payers:
            p.delete()
        RefSpecialty.objects.filter(specialty_code__startswith=PREFIX).delete()

    return counts


def _print_summary(ctx: KeystoneContext, stdout) -> None:
    stdout.write("\n=== KEYSTONE contract summary ===")
    for legacy in (
        KEYS["contract_idn"],
        KEYS["contract_card"],
        KEYS["contract_f1"],
        KEYS["contract_card_old"],
    ):
        meta = ctx.registry.get(legacy, {})
        if not meta:
            stdout.write(f"  {legacy}: (not seeded)")
            continue
        covered = "; ".join(meta.get("covered_entities") or [])
        stdout.write(
            f"  {meta['name']} [{legacy}]\n"
            f"    contract_id={meta['contract_id']}  version_id={meta['version_id']}\n"
            f"    99213 flat rate=${meta['rate_99213']}\n"
            f"    covered entities: {covered or '—'}"
        )

    stdout.write("\n=== Natural keys for reprice payloads ===")
    stdout.write(f"  member_id:        {KEYS['member_id']}")
    stdout.write(f"  service_date:     {SERVICE_DATE.isoformat()}")
    stdout.write(f"  product:          {KEYS['prod_code']} (Horizon PPO)")
    stdout.write(f"  billing NPI IDN:  {KEYS['npi_idn']}  (org {KEYS['org_idn']})")
    stdout.write(f"  billing NPI CARD: {KEYS['npi_card']}  (org {KEYS['org_card']})")
    stdout.write(f"  rendering NPI:    {KEYS['npi_chen']}  (Dr. Sarah Chen)")
    stdout.write(f"  facility F1 NPI:  {KEYS['npi_f1']}  ({KEYS['fac_ccn_f1']} Keystone General)")
    stdout.write(f"  facility F2 NPI:  {KEYS['npi_f2']}  ({KEYS['fac_ccn_f2']} Keystone Suburban)")
    stdout.write(f"  claim_type:       professional (office) | institutional (facility)")

    stdout.write("\n=== Scenario catalog hints (docs/CONTRACT_RESOLUTION_SCENARIOS.md) ===")
    hints = [
        ("R2", "Group beats IDN", f"billing={KEYS['npi_card']}", f"→ {KEYS['contract_card']} $150"),
        ("R3", "IDN hierarchy fallback", f"billing={KEYS['npi_idn']}", f"→ {KEYS['contract_idn']} $130"),
        ("R4", "Facility-specific", f"facility={KEYS['npi_f1']}", f"→ {KEYS['contract_f1']} $200"),
        ("R5", "Provider at facility", f"rendering={KEYS['npi_chen']} + facility", "→ provider-at-facility (D5)"),
        ("F7", "Unterminated overlap", f"billing={KEYS['npi_card']}", "→ AMBIGUOUS (CARD + CARD-OLD)"),
        ("E2", "Office vs facility", f"CARD office vs F1", "→ CARD $150 vs F1 $200"),
        ("E3", "F1 vs F2", f"facility F1 vs F2", "→ F1 $200 vs IDN fallback $130"),
    ]
    for sid, title, facts, expected in hints:
        stdout.write(f"  {sid} {title}: {facts}  {expected}")


@transaction.atomic
def seed_keystone_atomic(*, wipe: bool = False, stdout=None) -> dict[str, Any]:
    global _stats
    _stats = {}

    if wipe:
        wipe_keystone(stdout=stdout)

    ctx = KeystoneContext()
    build_cast(ctx)
    build_contracts(ctx)

    if stdout:
        _print_summary(ctx, stdout)

    return {
        "created_stats": dict(_stats),
        "keystone_row_counts": _count_keystone_rows(),
        "registry": ctx.registry,
        "keys": KEYS,
    }
