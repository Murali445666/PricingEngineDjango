"""
Attach Gap A rate-basis demo to KEYSTONE-C-CARD (99213 = 120% of MPFS 2025).
"""
from __future__ import annotations

from decimal import Decimal

from core.demo.seed_keystone import EFFECTIVE_END, EFFECTIVE_START, KEYS, PREFIX
from core.models import (
    ContractEscalator,
    ContractRateBasis,
    PricingRule,
    ProviderContract,
    PublishedFeeSchedule,
)


def attach_keystone_card_rate_basis(stdout=None) -> dict:
    """Create MPFS 2025 schedule + ContractRateBasis on KEYSTONE-C-CARD 99213 rule."""
    out = stdout.write if stdout is not None else print

    contract = ProviderContract.objects.filter(
        legacy_contract_number=KEYS['contract_card'],
    ).first()
    if contract is None:
        raise RuntimeError('KEYSTONE-C-CARD not found — run seed_keystone first')

    schedule, sched_created = PublishedFeeSchedule.objects.get_or_create(
        name='MPFS 2025',
        basis_type=PublishedFeeSchedule.BasisType.MPFS,
        year=2025,
        defaults={
            'source': 'CMS MPFS',
            'effective_start_date': EFFECTIVE_START,
            'effective_end_date': EFFECTIVE_END,
            'base_rate': Decimal('32.7442'),
        },
    )

    rule = PricingRule.objects.filter(
        contract=contract,
        rule_name__icontains='99213',
    ).first()
    if rule is None:
        raise RuntimeError(f'99213 rule not found on {KEYS["contract_card"]}')

    basis, basis_created = ContractRateBasis.objects.get_or_create(
        pricing_rule=rule,
        defaults={
            'schedule': schedule,
            'percentage': Decimal('120.00'),
        },
    )
    if not basis_created and basis.schedule_id != schedule.pk:
        basis.schedule = schedule
        basis.percentage = Decimal('120.00')
        basis.save(update_fields=['schedule', 'percentage', 'updated_at'])

    out(
        f'KEYSTONE rate basis: rule {rule.rule_id} ({rule.rule_name}) '
        f'-> {basis.percentage}% of {schedule.name} '
        f'(schedule {"created" if sched_created else "exists"}, '
        f'basis {"created" if basis_created else "exists"})'
    )
    return {
        'contract_id': contract.contract_id,
        'rule_id': rule.rule_id,
        'schedule_id': schedule.id,
        'basis_id': basis.id,
        'prefix': PREFIX,
    }


def attach_keystone_card_escalator(stdout=None) -> dict:
    """Add 3%/yr escalator (base_year 2025) to KEYSTONE-C-CARD."""
    out = stdout.write if stdout is not None else print

    contract = ProviderContract.objects.filter(
        legacy_contract_number=KEYS['contract_card'],
    ).first()
    if contract is None:
        raise RuntimeError('KEYSTONE-C-CARD not found — run seed_keystone first')

    escalator, created = ContractEscalator.objects.get_or_create(
        contract=contract,
        version=None,
        base_year=2025,
        defaults={
            'annual_percentage': Decimal('3.00'),
            'cap_percentage': None,
            'effective_start_date': EFFECTIVE_START,
            'effective_end_date': None,
        },
    )
    if not created:
        escalator.annual_percentage = Decimal('3.00')
        escalator.base_year = 2025
        escalator.effective_start_date = EFFECTIVE_START
        escalator.effective_end_date = None
        escalator.save()

    out(
        f'KEYSTONE escalator: contract {contract.contract_id} '
        f'+{escalator.annual_percentage}%/yr from base_year {escalator.base_year} '
        f'({"created" if created else "updated"})'
    )
    return {
        'contract_id': contract.contract_id,
        'escalator_id': escalator.id,
    }
