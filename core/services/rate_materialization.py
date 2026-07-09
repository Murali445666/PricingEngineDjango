"""
Gap A/B (§16): Materialize ContractRateBasis (+ optional ContractEscalator) → concrete rates.

Rules WITHOUT a ContractRateBasis are never touched.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.db.models import Q

from core.models import (
    ContractBaseRate,
    ContractEscalator,
    ContractRateBasis,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    PublishedFeeSchedule,
    PublishedFeeScheduleRate,
    RefApc,
    RefDrg,
    RefMpfsRvu,
    RefProcedureCode,
)

# Documented fallbacks when PublishedFeeSchedule.base_rate is unset.
DEFAULT_MPFS_CONVERSION_FACTOR = Decimal('32.7442')  # 2025 Medicare physician CF (national)
DEFAULT_DRG_BASE_RATE = Decimal('6000.00')
DEFAULT_APC_CONVERSION_FACTOR = Decimal('84.00')

_MONEY = Decimal('0.01')


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def default_target_year(schedule: PublishedFeeSchedule, explicit: Optional[int] = None) -> int:
    """Default materialization year: explicit flag, else max(today, schedule year)."""
    if explicit is not None:
        return explicit
    return max(date.today().year, schedule.year)


def compose_rate_basis_label(
    basis: ContractRateBasis,
    escalator: Optional[ContractEscalator] = None,
) -> str:
    label = basis.readable_basis()
    if escalator is not None:
        label = f'{label}, {escalator.readable_suffix()}'
    return label


def find_applicable_escalator(
    contract: ProviderContract,
    version_id: Optional[int],
    target_year: int,
) -> Optional[ContractEscalator]:
    """Return contract/version escalator effective during target_year."""
    as_of = date(target_year, 6, 15)
    qs = ContractEscalator.objects.filter(
        contract=contract,
        effective_start_date__lte=as_of,
    ).filter(
        Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=as_of)
    )
    if version_id is not None:
        match = qs.filter(version_id=version_id).first()
        if match is not None:
            return match
    return qs.filter(version__isnull=True).first()


def apply_escalator(
    base: Decimal,
    escalator: Optional[ContractEscalator],
    target_year: int,
) -> tuple[Decimal, Decimal]:
    """
    Apply compounding escalator to a Gap-A base rate.
    Returns (effective_amount, factor). factor=1 when no escalator or target_year <= base_year.
    """
    if escalator is None:
        return base, Decimal('1')

    years = target_year - escalator.base_year
    if years <= 0:
        return base, Decimal('1')

    annual = escalator.annual_percentage / Decimal('100')
    factor = (Decimal('1') + annual) ** years

    if escalator.cap_percentage is not None:
        max_factor = Decimal('1') + escalator.cap_percentage / Decimal('100')
        if factor > max_factor:
            factor = max_factor

    return _quantize_money(base * factor), factor


def _rule_procedure_codes(rule: PricingRule) -> list[str]:
    return list(
        PricingRuleCondition.objects.filter(
            pricing_rule=rule,
            attribute_name='procedure_code',
        )
        .exclude(attribute_value__isnull=True)
        .exclude(attribute_value='')
        .order_by('condition_id')
        .values_list('attribute_value', flat=True)
    )


def resolve_schedule_amount(
    schedule: PublishedFeeSchedule,
    code: str,
    year: Optional[int] = None,
) -> Optional[Decimal]:
    """
    Look up the schedule dollar amount for a code before percentage is applied.

    MPFS  -> RefMpfsRvu total RVU × schedule.base_rate (or DEFAULT_MPFS_CONVERSION_FACTOR).
             Falls back to RefProcedureCode RVU sum × CF when MPFS row missing.
    MSDRG -> RefDrg.relative_weight × (schedule.base_rate or DEFAULT_DRG_BASE_RATE).
    APC   -> RefApc.payment_rate when set, else relative_weight × base CF.
    CUSTOM-> PublishedFeeScheduleRate.amount for (schedule, code).
    """
    lookup_year = year if year is not None else schedule.year
    code = (code or '').strip()
    if not code:
        return None

    basis = schedule.basis_type

    if basis == PublishedFeeSchedule.BasisType.CUSTOM:
        row = PublishedFeeScheduleRate.objects.filter(schedule=schedule, code=code).first()
        return row.amount if row else None

    if basis == PublishedFeeSchedule.BasisType.MPFS:
        cf = schedule.base_rate or DEFAULT_MPFS_CONVERSION_FACTOR
        rvu = RefMpfsRvu.objects.filter(code=code, year=lookup_year).first()
        if rvu is not None:
            total = rvu.total_rvu
            if total is None:
                total = (rvu.work_rvu or Decimal('0')) + (rvu.pe_rvu or Decimal('0')) + (rvu.mp_rvu or Decimal('0'))
            return _quantize_money(total * cf)
        try:
            ref = RefProcedureCode.objects.get(code_id=code)
        except RefProcedureCode.DoesNotExist:
            return None
        ref_cf = ref.conversion_factor or cf
        total = (ref.work_rvu or Decimal('0')) + (ref.pe_rvu or Decimal('0')) + (ref.mp_rvu or Decimal('0'))
        if total <= 0:
            return None
        return _quantize_money(total * ref_cf)

    if basis == PublishedFeeSchedule.BasisType.MSDRG:
        base = schedule.base_rate or DEFAULT_DRG_BASE_RATE
        drg = (
            RefDrg.objects.filter(drg_code=code, year=lookup_year).first()
            or RefDrg.objects.filter(drg_code=code).first()
        )
        if drg is None:
            return None
        return _quantize_money(drg.relative_weight * base)

    if basis == PublishedFeeSchedule.BasisType.APC:
        apc = (
            RefApc.objects.filter(apc_code=code, year=lookup_year).first()
            or RefApc.objects.filter(apc_code=code).first()
        )
        if apc is None:
            return None
        if apc.payment_rate is not None and apc.relative_weight and apc.relative_weight != 0:
            return _quantize_money(apc.payment_rate)
        cf = schedule.base_rate or DEFAULT_APC_CONVERSION_FACTOR
        weight = apc.relative_weight or Decimal('0')
        if weight <= 0:
            return None
        return _quantize_money(weight * cf)

    return None


def _materialized_amount(schedule_amount: Decimal, percentage: Decimal) -> Decimal:
    return _quantize_money(schedule_amount * percentage / Decimal('100'))


def _write_drg_apc_base_rate(rule: PricingRule, amount: Decimal, rate_type: str) -> tuple[str, Optional[Decimal], Decimal]:
    """Write materialized amount to ContractBaseRate; returns (field, old, new)."""
    version = rule.version
    if version is None:
        raise ValueError(f'Rule {rule.rule_id} has no version; cannot materialize DRG/APC base rate')
    row, _ = ContractBaseRate.objects.get_or_create(
        version=version,
        rate_type=rate_type,
        defaults={'base_rate': amount},
    )
    old = row.base_rate
    if old != amount:
        row.base_rate = amount
        row.save(update_fields=['base_rate'])
    return ('ContractBaseRate.base_rate', old, amount)


def _result_payload(
    rule: PricingRule,
    code: str,
    field: str,
    old: Optional[Decimal],
    new: Decimal,
    basis_label: str,
    schedule_amount: Decimal,
    base_amount: Decimal,
    escalator_factor: Decimal,
    target_year: int,
) -> dict:
    return {
        'rule_id': rule.rule_id,
        'rule_name': rule.rule_name,
        'code': code,
        'field': field,
        'old': old,
        'new': new,
        'basis': basis_label,
        'schedule_amount': schedule_amount,
        'base_amount': base_amount,
        'escalator_factor': escalator_factor,
        'target_year': target_year,
    }


def materialize_rule(rule: PricingRule, target_year: Optional[int] = None) -> Optional[dict]:
    """
    Materialize a single rule that has ContractRateBasis.
    Derives from schedule × percentage × escalator (never compounds on existing flat_rate).
    """
    try:
        basis = rule.rate_basis
    except ContractRateBasis.DoesNotExist:
        return None

    codes = _rule_procedure_codes(rule)
    if not codes:
        return {
            'rule_id': rule.rule_id,
            'rule_name': rule.rule_name,
            'skipped': True,
            'reason': 'no procedure_code condition',
        }
    code = codes[0]
    schedule = basis.schedule
    year = default_target_year(schedule, target_year)
    schedule_amount = resolve_schedule_amount(schedule, code, schedule.year)
    if schedule_amount is None:
        return {
            'rule_id': rule.rule_id,
            'rule_name': rule.rule_name,
            'skipped': True,
            'reason': f'no schedule amount for code={code!r} schedule={schedule.name!r}',
        }

    base_amount = _materialized_amount(schedule_amount, basis.percentage)
    escalator = find_applicable_escalator(rule.contract, rule.version_id, year)
    amount, escalator_factor = apply_escalator(base_amount, escalator, year)
    basis_label = compose_rate_basis_label(basis, escalator)
    methodology = (rule.methodology_code or 'FLAT_RATE').upper()

    if methodology in ('FLAT_RATE', 'PER_DIEM'):
        old = rule.flat_rate
        if old != amount:
            rule.flat_rate = amount
            rule.save(update_fields=['flat_rate'])
        return _result_payload(
            rule, code, 'flat_rate', old, amount, basis_label,
            schedule_amount, base_amount, escalator_factor, year,
        )

    if methodology == 'DRG':
        field, old, new = _write_drg_apc_base_rate(rule, amount, 'DRG')
        return _result_payload(
            rule, code, field, old, new, basis_label,
            schedule_amount, base_amount, escalator_factor, year,
        )

    if methodology in ('APC', 'OPPS'):
        field, old, new = _write_drg_apc_base_rate(rule, amount, 'APC')
        return _result_payload(
            rule, code, field, old, new, basis_label,
            schedule_amount, base_amount, escalator_factor, year,
        )

    if methodology in ('RBRVS', 'ANESTHESIA'):
        old = rule.flat_rate
        if old != amount:
            rule.flat_rate = amount
            rule.save(update_fields=['flat_rate'])
        return _result_payload(
            rule, code, 'flat_rate (RBRVS fallback)', old, amount, basis_label,
            schedule_amount, base_amount, escalator_factor, year,
        )

    return {
        'rule_id': rule.rule_id,
        'rule_name': rule.rule_name,
        'skipped': True,
        'reason': f'unsupported methodology {methodology}',
    }


def materialize_contract(contract_id: int, target_year: Optional[int] = None) -> list[dict]:
    """Materialize all rules under contract that have ContractRateBasis."""
    rule_ids = ContractRateBasis.objects.filter(
        pricing_rule__contract_id=contract_id,
    ).values_list('pricing_rule_id', flat=True)
    rules = PricingRule.objects.filter(rule_id__in=rule_ids).select_related(
        'rate_basis__schedule', 'version', 'contract',
    )
    results: list[dict] = []
    with transaction.atomic():
        for rule in rules:
            result = materialize_rule(rule, target_year=target_year)
            if result is not None:
                results.append(result)
    return results


def materialize_all(target_year: Optional[int] = None) -> list[dict]:
    """Materialize every rule that has ContractRateBasis."""
    rule_ids = ContractRateBasis.objects.values_list('pricing_rule_id', flat=True)
    rules = PricingRule.objects.filter(rule_id__in=rule_ids).select_related(
        'rate_basis__schedule', 'version', 'contract',
    )
    results: list[dict] = []
    with transaction.atomic():
        for rule in rules:
            result = materialize_rule(rule, target_year=target_year)
            if result is not None:
                results.append(result)
    return results
