"""
Gap D (§16): Bulk-create rate-basis pricing rules for a list of procedure codes.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from io import StringIO
from typing import Iterable, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from core.models import (
    ContractArrangement,
    ContractRateBasis,
    ContractVersion,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    PublishedFeeSchedule,
)
from core.services.rate_materialization import materialize_rule


@dataclass
class CodeSpec:
    code: str
    methodology: str = 'FLAT_RATE'


@dataclass
class BulkRateResult:
    contract_id: int
    version_id: int
    schedule_id: int
    percentage: Decimal
    created_rules: list[dict] = field(default_factory=list)
    updated_bases: list[dict] = field(default_factory=list)
    materialized: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


def parse_codes_csv(text: str) -> list[CodeSpec]:
    """Parse CSV lines: code or code,methodology."""
    specs: list[CodeSpec] = []
    reader = csv.reader(StringIO(text))
    for row in reader:
        if not row or not row[0].strip():
            continue
        code = row[0].strip()
        methodology = row[1].strip().upper() if len(row) > 1 and row[1].strip() else 'FLAT_RATE'
        specs.append(CodeSpec(code=code, methodology=methodology))
    return specs


def parse_codes_list(codes: Iterable[str], default_methodology: str = 'FLAT_RATE') -> list[CodeSpec]:
    return [CodeSpec(code=c.strip(), methodology=default_methodology) for c in codes if c.strip()]


def _find_rule_for_code(contract_id: int, version_id: int, code: str) -> Optional[PricingRule]:
    return (
        PricingRule.objects.filter(
            contract_id=contract_id,
            version_id=version_id,
            conditions__attribute_name='procedure_code',
            conditions__operator='EQ',
            conditions__attribute_value=code,
        )
        .distinct()
        .first()
    )


def _ensure_arrangement(contract: ProviderContract) -> ContractArrangement:
    existing = ContractArrangement.objects.filter(contract=contract).order_by('id').first()
    if existing is not None:
        return existing
    return ContractArrangement.objects.create(
        contract=contract,
        name=f'{contract.contract_name or "Contract"} Fee Schedule',
        arrangement_type=ContractArrangement.ArrangementType.FEE_SCHEDULE,
        status=ContractVersion.VersionStatus.DRAFT,
    )


def bulk_add_rate_basis(
    contract_id: int,
    version_id: int,
    *,
    schedule_id: int,
    percentage: Decimal,
    codes: list[CodeSpec],
    claim_type: Optional[str] = None,
    target_year: Optional[int] = None,
) -> BulkRateResult:
    """
    For each code: get_or_create PricingRule + procedure_code condition + ContractRateBasis,
    then materialize concrete rates via Gap A/B materialization.
    """
    try:
        contract = ProviderContract.objects.get(pk=contract_id)
    except ProviderContract.DoesNotExist as exc:
        raise ObjectDoesNotExist(f'Contract {contract_id} not found') from exc

    try:
        version = ContractVersion.objects.get(pk=version_id, contract=contract)
    except ContractVersion.DoesNotExist as exc:
        raise ObjectDoesNotExist(
            f'Version {version_id} not found on contract {contract_id}'
        ) from exc

    try:
        schedule = PublishedFeeSchedule.objects.get(pk=schedule_id)
    except PublishedFeeSchedule.DoesNotExist as exc:
        raise ObjectDoesNotExist(f'PublishedFeeSchedule {schedule_id} not found') from exc

    result = BulkRateResult(
        contract_id=contract_id,
        version_id=version_id,
        schedule_id=schedule_id,
        percentage=percentage,
    )
    arrangement = _ensure_arrangement(contract)

    with transaction.atomic():
        for spec in codes:
            code = spec.code
            methodology = spec.methodology or 'FLAT_RATE'
            rule = _find_rule_for_code(contract_id, version_id, code)
            created = False
            if rule is None:
                rule = PricingRule.objects.create(
                    contract=contract,
                    version=version,
                    rule_name=f'BULK {code} {methodology}',
                    arrangement=arrangement,
                    rule_type='BASE',
                    methodology_code=methodology,
                    status=PricingRule.RuleStatus.DRAFT,
                    claim_type=claim_type,
                    specificity_score=10,
                    effective_start_date=contract.effective_start_date,
                    effective_end_date=contract.effective_end_date,
                )
                PricingRuleCondition.objects.create(
                    pricing_rule=rule,
                    attribute_name='procedure_code',
                    operator='EQ',
                    attribute_value=code,
                )
                created = True
                result.created_rules.append({
                    'rule_id': rule.rule_id,
                    'code': code,
                    'methodology': methodology,
                })
            else:
                result.skipped.append({
                    'rule_id': rule.rule_id,
                    'code': code,
                    'reason': 'rule already exists for code',
                })

            basis, basis_created = ContractRateBasis.objects.get_or_create(
                pricing_rule=rule,
                defaults={
                    'schedule': schedule,
                    'percentage': percentage,
                },
            )
            if not basis_created and (
                basis.schedule_id != schedule.pk or basis.percentage != percentage
            ):
                basis.schedule = schedule
                basis.percentage = percentage
                basis.save(update_fields=['schedule', 'percentage', 'updated_at'])
                result.updated_bases.append({
                    'rule_id': rule.rule_id,
                    'code': code,
                    'percentage': str(percentage),
                })
            elif basis_created:
                result.updated_bases.append({
                    'rule_id': rule.rule_id,
                    'code': code,
                    'percentage': str(percentage),
                    'created': True,
                })

            mat = materialize_rule(rule, target_year=target_year)
            if mat and not mat.get('skipped'):
                result.materialized.append({
                    'rule_id': rule.rule_id,
                    'code': code,
                    'created': created,
                    'flat_rate': str(mat.get('new')),
                    'basis': mat.get('basis'),
                    'target_year': mat.get('target_year'),
                })
            elif mat and mat.get('skipped'):
                result.skipped.append({
                    'rule_id': rule.rule_id,
                    'code': code,
                    'reason': mat.get('reason'),
                })

    return result
