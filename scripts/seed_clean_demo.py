#!/usr/bin/env python3
"""
Reset contract/pricing rows and seed four minimal demo contracts for clean API/engine tests.

Deletes (child → parent where needed): claims, contracts (CASCADE to versions, rules,
methodologies, validation, etc.), then all fee_schedule_rates and fee_schedules.
Does NOT delete ref_* tables, provider_organizations, or payer_networks (rows are
preserved; this script uses get_or_create for ORG_DEMO / NET_DEMO / payer).

Usage (from repository root: PricingEngineDjango/):
  python scripts/seed_clean_demo.py

Ref helper: ensures RefDrg drg_code=470 exists (relative_weight=1.0, year=2026) if missing.

After seeding, smoke-test ideas:
  python manage.py test
  curl -X POST .../api/price-line/ with contract_id, procedure_code 99213 / 470 / 00100
"""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

# Django setup when run as a standalone script
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from core.models import (  # noqa: E402
    ClaimHeader,
    ClaimLine,
    ContractBaseRate,
    ContractVersion,
    FeeSchedule,
    FeeScheduleRate,
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    RefDrg,
)

EFFECTIVE_START = date(2026, 1, 1)
EFFECTIVE_END = date(2026, 12, 31)


def _d(x) -> Decimal:
    return Decimal(str(x))


def wipe_pricing_data() -> None:
    """Remove all contracts (and cascaded dependents), then fee schedules."""
    with transaction.atomic():
        ClaimLine.objects.all().delete()
        ClaimHeader.objects.all().delete()
        ProviderContract.objects.all().delete()
        FeeScheduleRate.objects.all().delete()
        FeeSchedule.objects.all().delete()


def ensure_ref_drg_470() -> RefDrg:
    obj, created = RefDrg.objects.update_or_create(
        drg_code='470',
        defaults={
            'description': 'seed_clean_demo placeholder DRG',
            'relative_weight': _d('1.0'),
            'geometric_mean_los': None,
            'arithmetic_mean_los': None,
            'mdc': None,
            'year': 2026,
        },
    )
    if created:
        print('[seed_clean_demo] Created RefDrg 470 (relative_weight=1.0, year=2026).')
    return obj


def ensure_demo_orgs() -> tuple[ProviderOrganization, PayerNetwork]:
    payer, _ = ProviderOrganization.objects.get_or_create(
        organization_id='PAYER_DEMO',
        defaults={'name': 'Demo payer (seed_clean_demo)'},
    )
    prov, _ = ProviderOrganization.objects.get_or_create(
        organization_id='ORG_DEMO',
        defaults={'name': 'Demo provider (seed_clean_demo)'},
    )
    net, _ = PayerNetwork.objects.get_or_create(
        network_id='NET_DEMO',
        defaults={
            'network_name': 'Demo network (seed_clean_demo)',
            'payer_org': payer,
        },
    )
    return prov, net


def _add_condition(rule: PricingRule, procedure_code: str) -> None:
    PricingRuleCondition.objects.create(
        pricing_rule=rule,
        attribute_name='procedure_code',
        operator='EQ',
        attribute_value=str(procedure_code),
    )


def _version(contract: ProviderContract) -> ContractVersion:
    return ContractVersion.objects.create(
        contract=contract,
        version_number=1,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        status=ContractVersion.VersionStatus.ACTIVE,
        pricing_engine_mode=ContractVersion.PricingEngineMode.LEGACY,
        claim_level_drg_enabled=False,
    )


def seed_demo_contracts() -> list[dict]:
    prov, net = ensure_demo_orgs()
    ensure_ref_drg_470()

    fs = FeeSchedule.objects.create(
        name='FS_DEMO',
        effective_date=EFFECTIVE_START,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        schedule_type='PROFESSIONAL',
        source='seed_clean_demo',
    )
    FeeScheduleRate.objects.create(
        fee_schedule=fs,
        code_id='99213',
        rate_amount=_d('100.00'),
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        year=2026,
    )

    summary: list[dict] = []

    # --- A: RBRVS ---
    ca = ProviderContract.objects.create(
        contract_name='DEMO_RBRVS',
        legacy_contract_number='DEMO_RBRVS',
        status='ACTIVE',
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        provider_org=prov,
        network=net,
    )
    va = _version(ca)
    ra = PricingRule.objects.create(
        contract=ca,
        version=va,
        rule_name='R1',
        rule_type='BASE',
        methodology_code='RBRVS',
        multiplier=_d('1.5'),
        base_fee_schedule=fs,
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(ra, '99213')
    summary.append({'key': 'A_RBRVS', 'contract_id': ca.pk, 'version_id': va.pk, 'rule_id': ra.pk})

    # --- B: DRG ---
    cb = ProviderContract.objects.create(
        contract_name='DEMO_DRG',
        legacy_contract_number='DEMO_DRG',
        status='ACTIVE',
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        provider_org=prov,
        network=net,
    )
    vb = _version(cb)
    ContractBaseRate.objects.create(
        version=vb,
        rate_type='DRG',
        base_rate=_d('6000.00'),
    )
    rb = PricingRule.objects.create(
        contract=cb,
        version=vb,
        rule_name='R1',
        rule_type='BASE',
        methodology_code='DRG',
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(rb, '470')
    summary.append({'key': 'B_DRG', 'contract_id': cb.pk, 'version_id': vb.pk, 'rule_id': rb.pk})

    # --- C: FLAT ---
    cc = ProviderContract.objects.create(
        contract_name='DEMO_FLAT',
        legacy_contract_number='DEMO_FLAT',
        status='ACTIVE',
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        provider_org=prov,
        network=net,
    )
    vc = _version(cc)
    rc = PricingRule.objects.create(
        contract=cc,
        version=vc,
        rule_name='R1',
        rule_type='BASE',
        methodology_code='FLAT_RATE',
        flat_rate=_d('250.00'),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(rc, '00100')
    summary.append({'key': 'C_FLAT', 'contract_id': cc.pk, 'version_id': vc.pk, 'rule_id': rc.pk})

    # --- D: PCT_BILLED ---
    cd = ProviderContract.objects.create(
        contract_name='DEMO_PCT_BILLED',
        legacy_contract_number='DEMO_PCT_BILLED',
        status='ACTIVE',
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        provider_org=prov,
        network=net,
    )
    vd = _version(cd)
    rd = PricingRule.objects.create(
        contract=cd,
        version=vd,
        rule_name='R1',
        rule_type='BASE',
        methodology_code='PCT_BILLED',
        multiplier=_d('0.8'),
        status=PricingRule.RuleStatus.ACTIVE,
        effective_start_date=EFFECTIVE_START,
        effective_end_date=EFFECTIVE_END,
        specificity_score=10,
    )
    _add_condition(rd, '99213')
    summary.append({'key': 'D_PCT_BILLED', 'contract_id': cd.pk, 'version_id': vd.pk, 'rule_id': rd.pk})

    return summary


def main() -> None:
    print('[seed_clean_demo] Wiping pricing data...')
    wipe_pricing_data()
    print('[seed_clean_demo] Seeding demo orgs, fee schedule, contracts...')
    with transaction.atomic():
        rows = seed_demo_contracts()

    print('')
    print('seed_clean_demo - created rows (document for tests / Claim Simulation):')
    print('(Expected: RBRVS 99213 ~ 150.00; DRG 470 ~ 6000 * RefDrg.relative_weight(470);')
    print(' FLAT 00100 = 250.00; PCT_BILLED 99213 = 80% of billed.)')
    print('')
    for r in rows:
        print(
            f"  {r['key']}: contract_id={r['contract_id']}  "
            f"version_id={r['version_id']}  rule_id={r['rule_id']}"
        )
    print('')
    print(f"  Fee schedule: FS_DEMO fee_schedule_id={FeeSchedule.objects.get(name='FS_DEMO').pk}")
    print('Done.')


if __name__ == '__main__':
    main()
