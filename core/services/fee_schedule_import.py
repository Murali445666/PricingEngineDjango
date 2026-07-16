"""
Import Exhibit C fee schedule rows as PricingRule + PricingRuleCondition (CURSOR_SEED_BRIEF).
Upserts by natural key (version, procedure_code, covered_entity) so rule_ids survive reloads.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from core.models import (
    ContractArrangement,
    ContractRateBasis,
    ContractVersion,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
    PublishedFeeSchedule,
)
from providers.models import Provider

INSTITUTIONAL_SETTINGS = frozenset({
    'Inpatient',
    'Outpatient',
    'Facility per-diem',
})

ALL_SETTINGS = INSTITUTIONAL_SETTINGS | frozenset({'Professional', 'Ancillary'})

COVERED_ENTITY_ORG_KEYS = {
    'Keystone Cardiology (org)': 'KEYSTONE-CARD',
    'Keystone Imaging Center': 'KHS-IMG',
    'Keystone General (OP)': 'KHS-GEN',
    'Keystone General Hospital': 'KHS-GEN',
    'Keystone Behavioral Health': 'KHS-BH',
}

CHEN_PROVIDER_NPI = 'KEYSTONE-NPI05'
CHEN_ENTITY_LABEL = 'Robert Chen, MD'


@dataclass
class FeeScheduleImportResult:
    contract_id: int
    version_id: int
    year: int
    rules_created: int = 0
    rules_updated: int = 0
    rules_deleted: int = 0
    conditions_created: int = 0
    rate_bases_created: int = 0
    rate_bases_updated: int = 0
    rows_processed: int = 0
    skipped: list[dict[str, Any]] = field(default_factory=list)
    rate_basis_skipped: list[dict[str, Any]] = field(default_factory=list)


def _d(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(',', '').replace('$', '')
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f'Invalid decimal: {value!r}') from exc


def _has_numeric_percentage(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip().replace('%', '')
    if not text:
        return False
    try:
        Decimal(text)
        return True
    except InvalidOperation:
        return False


def _build_entity_context() -> dict[str, Any]:
    orgs = {
        org_id: org
        for org_id in set(COVERED_ENTITY_ORG_KEYS.values())
        for org in [ProviderOrganization.objects.filter(organization_id=org_id).first()]
        if org is not None
    }
    chen = Provider.objects.filter(npi=CHEN_PROVIDER_NPI).first()
    return {'orgs': orgs, 'chen': chen}


def _rule_name(row: dict[str, str]) -> str:
    code = row.get('procedure_code', '').strip()
    entity = row.get('covered_entity', '').strip()
    setting = row.get('setting', '').strip()
    name = f'{code} {entity} {setting}'.strip()
    return name[:150]


def _natural_key_from_row(row: dict[str, str]) -> tuple[str, str]:
    return (
        (row.get('procedure_code') or '').strip(),
        (row.get('covered_entity') or '').strip(),
    )


def _entity_from_rule_name(rule_name: str | None, code: str) -> str:
    if not rule_name:
        return ''
    name = rule_name.strip()
    parts = name.split(' ', 1)
    if len(parts) == 2:
        name = parts[1]
    prefix = f'{code} '
    if name.startswith(prefix):
        name = name[len(prefix):]
    for setting in sorted(ALL_SETTINGS, key=len, reverse=True):
        suffix = f' {setting}'
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name.strip()


def _natural_key_from_rule(rule: PricingRule) -> tuple[str, str] | None:
    code = None
    has_provider = False
    for cond in rule.conditions.all():
        attr = (cond.attribute_name or '').strip()
        op = (getattr(cond, 'operator', None) or 'EQ').strip().upper()
        if attr in ('procedure_code', 'code') and op == 'EQ':
            code = (cond.attribute_value or '').strip()
        elif attr == 'provider_id':
            has_provider = True
    if not code:
        return None
    entity = CHEN_ENTITY_LABEL if has_provider else _entity_from_rule_name(rule.rule_name, code)
    return (code, entity)


def _dedupe_csv_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Keep first row per (procedure_code, covered_entity); report duplicates."""
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    duplicates: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        key = _natural_key_from_row(row)
        if not key[0]:
            continue
        if key in seen:
            duplicates.append({
                'row': idx + 2,
                'procedure_code': key[0],
                'covered_entity': key[1],
                'reason': 'duplicate (procedure_code, covered_entity); kept first row',
            })
            continue
        seen.add(key)
        deduped.append(row)
    return deduped, duplicates


def _ensure_arrangement(contract: ProviderContract) -> ContractArrangement:
    existing = ContractArrangement.objects.filter(contract=contract).order_by('id').first()
    if existing is not None:
        return existing
    return ContractArrangement.objects.create(
        contract=contract,
        name=f'{contract.legacy_contract_number or contract.contract_id} Fee Schedule',
        arrangement_type=ContractArrangement.ArrangementType.FEE_SCHEDULE,
        status=ContractVersion.VersionStatus.ACTIVE,
        effective_start_date=contract.effective_start_date,
        effective_end_date=contract.effective_end_date,
    )


def _resolve_published_schedule(
    row: dict[str, str],
    contract: ProviderContract,
) -> PublishedFeeSchedule | None:
    """Map rate_basis + base_year to PublishedFeeSchedule; create if missing."""
    rate_basis = (row.get('rate_basis') or '').strip()
    base_year_raw = (row.get('base_year') or '').strip()
    if not rate_basis or not base_year_raw:
        return None

    try:
        year = int(base_year_raw)
    except ValueError:
        return None

    upper_basis = rate_basis.upper()
    if 'MPFS' in upper_basis:
        basis_type = PublishedFeeSchedule.BasisType.MPFS
        name = f'MPFS {year}'
        source = 'CMS MPFS'
        default_cf = _d(row.get('conversion_factor')) or Decimal('32.7442')
    elif 'MSDRG' in upper_basis or ('DRG' in upper_basis and 'MPFS' not in upper_basis):
        basis_type = PublishedFeeSchedule.BasisType.MSDRG
        name = f'MSDRG {year}'
        source = 'CMS MSDRG'
        default_cf = None
    elif 'APC' in upper_basis:
        basis_type = PublishedFeeSchedule.BasisType.APC
        name = f'APC {year}'
        source = 'CMS APC'
        default_cf = None
    else:
        return None

    schedule, _ = PublishedFeeSchedule.objects.get_or_create(
        name=name,
        basis_type=basis_type,
        year=year,
        defaults={
            'source': source,
            'effective_start_date': contract.effective_start_date,
            'effective_end_date': contract.effective_end_date,
            'base_rate': default_cf,
        },
    )
    if schedule.base_rate is None and default_cf is not None:
        schedule.base_rate = default_cf
        schedule.save(update_fields=['base_rate'])
    return schedule


def _sync_conditions(
    rule: PricingRule,
    *,
    procedure_code: str,
    is_chen: bool,
    chen: Provider | None,
) -> int:
    """Ensure procedure_code (+ optional provider_id) conditions match CSV row."""
    created = 0
    conditions = list(rule.conditions.all())
    code_conds = [
        c for c in conditions
        if (c.attribute_name or '').strip() in ('procedure_code', 'code')
    ]
    prov_conds = [
        c for c in conditions
        if (c.attribute_name or '').strip() == 'provider_id'
    ]

    if code_conds:
        primary = code_conds[0]
        if primary.attribute_name != 'procedure_code':
            primary.attribute_name = 'procedure_code'
        if primary.operator != 'EQ':
            primary.operator = 'EQ'
        if primary.attribute_value != procedure_code:
            primary.attribute_value = procedure_code
            primary.save(update_fields=['attribute_name', 'operator', 'attribute_value'])
        for extra in code_conds[1:]:
            extra.delete()
    else:
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name='procedure_code',
            operator='EQ',
            attribute_value=procedure_code,
        )
        created += 1

    if is_chen and chen is not None:
        provider_val = str(chen.id)
        if prov_conds:
            primary = prov_conds[0]
            if primary.attribute_value != provider_val:
                primary.attribute_value = provider_val
                primary.save(update_fields=['attribute_value'])
            for extra in prov_conds[1:]:
                extra.delete()
        else:
            PricingRuleCondition.objects.create(
                pricing_rule=rule,
                attribute_name='provider_id',
                operator='EQ',
                attribute_value=provider_val,
            )
            created += 1
    else:
        for cond in prov_conds:
            cond.delete()

    return created


def _upsert_rate_basis(
    rule: PricingRule,
    row: dict[str, str],
    contract: ProviderContract,
    *,
    row_number: int,
    result: FeeScheduleImportResult,
) -> None:
    pct_raw = row.get('percentage')
    if not _has_numeric_percentage(pct_raw):
        methodology = (row.get('methodology_code') or '').strip().upper()
        result.rate_basis_skipped.append({
            'row': row_number,
            'procedure_code': (row.get('procedure_code') or '').strip(),
            'covered_entity': (row.get('covered_entity') or '').strip(),
            'methodology_code': methodology,
            'rate_basis': (row.get('rate_basis') or '').strip(),
            'reason': 'no numeric percentage — basis is textual; ContractRateBasis not created',
        })
        return

    schedule = _resolve_published_schedule(row, contract)
    if schedule is None:
        result.rate_basis_skipped.append({
            'row': row_number,
            'procedure_code': (row.get('procedure_code') or '').strip(),
            'covered_entity': (row.get('covered_entity') or '').strip(),
            'rate_basis': (row.get('rate_basis') or '').strip(),
            'reason': 'rate_basis/base_year not mappable to PublishedFeeSchedule',
        })
        return

    percentage = Decimal(str(pct_raw).strip().replace('%', ''))
    basis, created = ContractRateBasis.objects.get_or_create(
        pricing_rule=rule,
        defaults={'schedule': schedule, 'percentage': percentage},
    )
    if created:
        result.rate_bases_created += 1
    else:
        changed = False
        if basis.schedule_id != schedule.pk:
            basis.schedule = schedule
            changed = True
        if basis.percentage != percentage:
            basis.percentage = percentage
            changed = True
        if changed:
            basis.save(update_fields=['schedule', 'percentage', 'updated_at'])
            result.rate_bases_updated += 1


def import_fee_schedule_from_csv(
    contract_id: int,
    version_id: int,
    csv_path: Path,
    *,
    year: int = 2025,
) -> FeeScheduleImportResult:
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

    allowed_column = 'allowed_2026' if year == 2026 else 'allowed_2025'
    if year not in (2025, 2026):
        raise ValueError('--year must be 2025 or 2026')

    with csv_path.open(encoding='utf-8', newline='') as handle:
        raw_rows = list(csv.DictReader(handle))

    if not raw_rows:
        raise ValueError(f'No rows in {csv_path}')

    rows, csv_duplicates = _dedupe_csv_rows(raw_rows)

    entity_ctx = _build_entity_context()
    chen = entity_ctx['chen']
    arrangement = _ensure_arrangement(contract)
    result = FeeScheduleImportResult(
        contract_id=contract_id,
        version_id=version_id,
        year=year,
    )
    result.skipped.extend(csv_duplicates)

    existing_rules = list(
        PricingRule.objects.filter(version_id=version_id).prefetch_related('conditions')
    )
    existing_by_key: dict[tuple[str, str], PricingRule] = {}
    for rule in existing_rules:
        key = _natural_key_from_rule(rule)
        if key is not None:
            existing_by_key[key] = rule

    csv_keys: set[tuple[str, str]] = set()
    touched_rules: list[PricingRule] = []

    with transaction.atomic():
        for idx, row in enumerate(rows):
            row_number = idx + 2
            code = (row.get('procedure_code') or '').strip()
            if not code:
                result.skipped.append({'row': row_number, 'reason': 'missing procedure_code'})
                continue

            allowed_raw = row.get(allowed_column)
            flat_rate = _d(allowed_raw)
            if flat_rate is None:
                result.skipped.append({
                    'row': row_number,
                    'reason': f'missing {allowed_column}',
                    'procedure_code': code,
                })
                continue

            natural_key = _natural_key_from_row(row)
            csv_keys.add(natural_key)

            setting = (row.get('setting') or '').strip()
            entity_label = (row.get('covered_entity') or '').strip()
            institutional = setting in INSTITUTIONAL_SETTINGS
            is_chen = entity_label == CHEN_ENTITY_LABEL
            source_methodology = (row.get('methodology_code') or 'FLAT_RATE').strip().upper()
            pricing_methodology = 'FLAT_RATE'
            claim_type = 'institutional' if institutional else None
            rule_name = f'{source_methodology} {_rule_name(row)}'[:150]

            rule = existing_by_key.get(natural_key)
            if rule is None:
                rule = PricingRule.objects.create(
                    contract=contract,
                    version=version,
                    rule_name=rule_name,
                    arrangement=arrangement,
                    rule_type='BASE',
                    methodology_code=pricing_methodology,
                    status=PricingRule.RuleStatus.ACTIVE,
                    claim_type=claim_type,
                    effective_start_date=contract.effective_start_date,
                    effective_end_date=contract.effective_end_date,
                    flat_rate=flat_rate,
                )
                existing_by_key[natural_key] = rule
                result.rules_created += 1
            else:
                changed_fields: list[str] = []
                updates = {
                    'rule_name': rule_name,
                    'methodology_code': pricing_methodology,
                    'status': PricingRule.RuleStatus.ACTIVE,
                    'claim_type': claim_type,
                    'effective_start_date': contract.effective_start_date,
                    'effective_end_date': contract.effective_end_date,
                    'flat_rate': flat_rate,
                }
                for field_name, new_val in updates.items():
                    if getattr(rule, field_name) != new_val:
                        setattr(rule, field_name, new_val)
                        changed_fields.append(field_name)
                if changed_fields:
                    rule.save(update_fields=changed_fields)
                    result.rules_updated += 1

            result.conditions_created += _sync_conditions(
                rule,
                procedure_code=code,
                is_chen=is_chen,
                chen=chen,
            )
            _upsert_rate_basis(rule, row, contract, row_number=row_number, result=result)
            touched_rules.append(rule)

        stale_qs = PricingRule.objects.filter(version_id=version_id).exclude(
            pk__in={r.pk for r in touched_rules}
        )
        if stale_qs.exists():
            _, delete_details = stale_qs.delete()
            result.rules_deleted = delete_details.get('core.PricingRule', 0)

        for rule in touched_rules:
            rule.calculate_score()

        result.rows_processed = len(csv_keys)

    return result
