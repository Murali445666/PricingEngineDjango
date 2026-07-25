"""
§18 T1.4 — Immutable ContractVersion config snapshots and diff summaries.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from django.db import transaction

from core.models import (
    ContractAmendment,
    ContractBlendingRule,
    ContractCapFloor,
    ContractCarveout,
    ContractCoveredEntity,
    ContractDocument,
    ContractMethodology,
    ContractOutlierRule,
    ContractRateBasis,
    ContractScopeUnified,
    ContractStopLossRule,
    ContractVersion,
    ContractVersionSnapshot,
    PricingRule,
    ProviderContract,
)
from core.services.fee_schedule_import import (
    CHEN_ENTITY_LABEL,
    _entity_from_rule_name,
    _natural_key_from_rule,
)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


def _to_json_safe(value: Any) -> Any:
    """Recursively convert snapshot payload to JSONField-safe primitives."""
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, default=_json_default, separators=(',', ':'))


def _checksum(data: dict) -> str:
    return hashlib.sha256(_canonical_json(data).encode('utf-8')).hexdigest()


def _serialize_covered_entities(contract: ProviderContract) -> list[dict]:
    rows = []
    for ce in ContractCoveredEntity.objects.filter(contract=contract).order_by('id'):
        rows.append({
            'entity_type': ce.entity_type,
            'organization_id': ce.organization_id,
            'facility_id': ce.facility_id,
            'provider_id': ce.provider_id,
            'is_primary': ce.is_primary,
            'effective_start_date': ce.effective_start_date,
            'effective_end_date': ce.effective_end_date,
        })
    return rows


def _serialize_scope(contract: ProviderContract) -> list[dict]:
    rows = []
    for row in ContractScopeUnified.objects.filter(contract=contract).order_by('id'):
        rows.append({
            'lob_code': row.lob_code,
            'product_id': row.product_id,
            'specialty_code_id': row.specialty_code_id,
            'site_of_service': row.site_of_service,
            'geo': row.geo,
            'priority': row.priority,
            'effective_date': row.effective_date,
            'termination_date': row.termination_date,
        })
    return rows


def _serialize_rules(version: ContractVersion) -> list[dict]:
    rules = []
    qs = (
        PricingRule.objects.filter(contract=version.contract, version=version)
        .prefetch_related('conditions')
        .order_by('rule_id')
    )
    for rule in qs:
        conditions = [
            {
                'attribute_name': c.attribute_name,
                'operator': c.operator,
                'attribute_value': c.attribute_value,
            }
            for c in rule.conditions.all().order_by('condition_id')
        ]
        basis = ContractRateBasis.objects.filter(pricing_rule=rule).first()
        natural_key = _natural_key_from_rule(rule)
        procedure_code = natural_key[0] if natural_key else ''
        covered_entity = natural_key[1] if natural_key else ''
        rules.append({
            'procedure_code': procedure_code,
            'covered_entity': covered_entity,
            'natural_key': list(natural_key) if natural_key else None,
            'rule_name': rule.rule_name,
            'rule_type': rule.rule_type,
            'methodology_code': rule.methodology_code,
            'multiplier': rule.multiplier,
            'flat_rate': rule.flat_rate,
            'base_fee_schedule_id': rule.base_fee_schedule_id,
            'claim_type': rule.claim_type,
            'site_of_service': rule.site_of_service,
            'specificity_score': rule.specificity_score,
            'effective_start_date': rule.effective_start_date,
            'effective_end_date': rule.effective_end_date,
            'conditions': conditions,
            'rate_basis': (
                {
                    'schedule_id': basis.schedule_id,
                    'percentage': basis.percentage,
                }
                if basis is not None
                else None
            ),
        })
    return rules


def _serialize_methodologies(version: ContractVersion) -> list[dict]:
    return list(
        ContractMethodology.objects.filter(contract=version.contract, version=version)
        .order_by('id')
        .values(
            'methodology_type', 'base_percentage', 'conversion_factor',
            'contract_term_id', 'fee_schedule_id', 'effective_date', 'termination_date',
            'priority', 'claim_type', 'site_of_service', 'conditions',
        )
    )


def _serialize_carveouts(version: ContractVersion) -> list[dict]:
    return list(
        ContractCarveout.objects.filter(version=version)
        .order_by('carveout_id')
        .values(
            'code_type', 'code_value', 'carveout_methodology',
            'carveout_percentage', 'carveout_rate', 'status', 'conditions',
        )
    )


def _serialize_cap_floors(version: ContractVersion) -> list[dict]:
    return list(
        ContractCapFloor.objects.filter(version=version)
        .order_by('-priority', 'cap_floor_id')
        .values(
            'scope', 'cap_type', 'value', 'percentage', 'code_value',
            'priority', 'effective_start_date', 'effective_end_date', 'status', 'conditions',
        )
    )


def _serialize_blending(version: ContractVersion) -> list[dict]:
    return list(
        ContractBlendingRule.objects.filter(version=version)
        .order_by('-priority', 'blending_rule_id')
        .values(
            'blend_type', 'scope', 'primary_methodology', 'secondary_methodology',
            'blend_percentage', 'priority', 'effective_start_date', 'effective_end_date',
            'status', 'conditions',
        )
    )


def _serialize_outliers(version: ContractVersion) -> list[dict]:
    return list(
        ContractOutlierRule.objects.filter(contract=version.contract, version=version)
        .order_by('-priority', 'id')
        .values(
            'threshold_amount', 'threshold_scope', 'reimbursement_percentage',
            'cost_to_charge_ratio', 'priority', 'effective_start_date', 'effective_end_date',
        )
    )


def _serialize_stop_loss(version: ContractVersion) -> list[dict]:
    return list(
        ContractStopLossRule.objects.filter(contract=version.contract, version=version)
        .order_by('-priority', 'id')
        .values(
            'cost_threshold', 'reimbursement_percentage', 'priority',
            'effective_start_date', 'effective_end_date',
        )
    )


def _serialize_documents(contract: ProviderContract) -> list[dict]:
    return list(
        ContractDocument.objects.filter(contract=contract)
        .order_by('id')
        .values('doc_type', 'title', 'reference', 'uploaded_at')
    )


def _serialize_amendment(version: ContractVersion) -> Optional[dict]:
    amendment = ContractAmendment.objects.filter(version=version).first()
    if amendment is None:
        return None
    return {
        'id': amendment.id,
        'amendment_number': amendment.amendment_number,
        'effective_date': amendment.effective_date,
        'description': amendment.description,
        'status': amendment.status,
    }


def build_version_snapshot(version: ContractVersion) -> dict:
    """Serialize complete version config for immutable storage and diffing."""
    contract = version.contract
    return {
        'contract': {
            'contract_id': contract.contract_id,
            'contract_name': contract.contract_name,
            'legacy_contract_number': contract.legacy_contract_number,
            'line_of_business': contract.line_of_business,
            'status': contract.status,
            'effective_start_date': contract.effective_start_date,
            'effective_end_date': contract.effective_end_date,
            'resolution_priority': contract.resolution_priority,
        },
        'version': {
            'version_id': version.version_id,
            'version_number': version.version_number,
            'status': version.status,
            'effective_start_date': version.effective_start_date,
            'effective_end_date': version.effective_end_date,
            'pricing_engine_mode': version.pricing_engine_mode,
            'claim_level_drg_enabled': version.claim_level_drg_enabled,
            'product_id': version.product_id,
            'tier_priority': version.tier_priority,
        },
        'roster': _serialize_covered_entities(contract),
        'scope': _serialize_scope(contract),
        'rules': _serialize_rules(version),
        'methodologies': _serialize_methodologies(version),
        'carveouts': _serialize_carveouts(version),
        'cap_floors': _serialize_cap_floors(version),
        'blending_rules': _serialize_blending(version),
        'outlier_rules': _serialize_outliers(version),
        'stop_loss_rules': _serialize_stop_loss(version),
        'documents': _serialize_documents(contract),
        'amendment': _serialize_amendment(version),
    }


@transaction.atomic
def save_version_snapshot(version: ContractVersion) -> ContractVersionSnapshot:
    """Write immutable snapshot; raises if one already exists."""
    if hasattr(version, 'config_snapshot') and version.config_snapshot is not None:
        return version.config_snapshot
    existing = ContractVersionSnapshot.objects.filter(version=version).first()
    if existing is not None:
        return existing

    payload = _to_json_safe(build_version_snapshot(version))
    return ContractVersionSnapshot.objects.create(
        version=version,
        snapshot=payload,
        checksum=_checksum(payload),
    )


def _entity_key(row: dict) -> tuple:
    return (
        row.get('entity_type'),
        row.get('organization_id'),
        row.get('facility_id'),
        row.get('provider_id'),
    )


def _scope_key(row: dict) -> tuple:
    return (
        row.get('lob_code'),
        row.get('product_id'),
        row.get('specialty_code_id'),
        row.get('site_of_service'),
        row.get('geo'),
    )


# Version lifecycle metadata — expected to differ on amendment drafts; not substantive.
_VERSION_HEADER_SKIP = frozenset({
    'version_id', 'version_number', 'status',
    'effective_start_date', 'effective_end_date',
    'pricing_engine_mode', 'claim_level_drg_enabled', 'product_id', 'tier_priority',
})
_CONTRACT_HEADER_SKIP = frozenset({'contract_id', 'status'})


def _rule_key(rule: dict) -> str:
    """Legacy fallback when procedure_code is unavailable."""
    return (rule.get('rule_name') or '').strip()


def _rule_content_hash(row: dict) -> str:
    return hashlib.sha256(_canonical_json(row).encode('utf-8')).hexdigest()


def _rule_code(rule: dict) -> str:
    code = (rule.get('procedure_code') or '').strip()
    if code:
        return code
    for cond in rule.get('conditions', []):
        if cond.get('attribute_name') in ('procedure_code', 'code'):
            val = cond.get('attribute_value')
            if val:
                return str(val)
    return _rule_key(rule)


def _natural_rule_key(rule: dict) -> tuple[str, str] | None:
    """Business identity: (procedure_code, covered_entity) — stable across version clones."""
    stored = rule.get('natural_key')
    if stored and len(stored) >= 2:
        return (str(stored[0]).strip(), str(stored[1]).strip())
    code = _rule_code(rule)
    if not code:
        return None
    entity = (rule.get('covered_entity') or '').strip()
    if not entity:
        has_provider = any(
            c.get('attribute_name') == 'provider_id'
            for c in rule.get('conditions', [])
        )
        if has_provider:
            entity = CHEN_ENTITY_LABEL
        else:
            entity = _entity_from_rule_name(rule.get('rule_name'), code)
    return (code, entity)


def _rules_by_natural_key(snap: dict) -> dict[tuple[str, str], dict]:
    indexed: dict[tuple[str, str], dict] = {}
    for rule in snap.get('rules', []):
        key = _natural_rule_key(rule)
        if key is not None:
            indexed[key] = rule
    return indexed


def _rule_rate_fingerprint(rule: dict) -> str:
    basis = rule.get('rate_basis') or {}
    payload = {
        'flat_rate': rule.get('flat_rate'),
        'multiplier': rule.get('multiplier'),
        'rate_basis_percentage': basis.get('percentage'),
        'rate_basis_schedule_id': basis.get('schedule_id'),
    }
    return _canonical_json(payload)


def diff_snapshots(old_snap: dict, new_snap: dict) -> dict:
    """
    Compute what_changed summary: rule/entity/scope change counts for semantic-diff UI.
    """
    summary = _diff_summary_counts(old_snap, new_snap)
    summary['prior_version_id'] = old_snap.get('version', {}).get('version_id')
    summary['new_version_id'] = new_snap.get('version', {}).get('version_id')
    return summary


def _diff_summary_counts(old_snap: dict, new_snap: dict) -> dict:
    old_rules = _rules_by_natural_key(old_snap)
    new_rules = _rules_by_natural_key(new_snap)

    old_rule_keys = set(old_rules)
    new_rule_keys = set(new_rules)
    rules_added = len(new_rule_keys - old_rule_keys)
    rules_removed = len(old_rule_keys - new_rule_keys)
    rules_changed = sum(
        1 for key in old_rule_keys & new_rule_keys
        if _rule_rate_fingerprint(old_rules[key]) != _rule_rate_fingerprint(new_rules[key])
    )

    old_entities = {_entity_key(r) for r in old_snap.get('roster', [])}
    new_entities = {_entity_key(r) for r in new_snap.get('roster', [])}
    entities_added = len(new_entities - old_entities)
    entities_removed = len(old_entities - new_entities)

    old_scope = {_scope_key(r) for r in old_snap.get('scope', [])}
    new_scope = {_scope_key(r) for r in new_snap.get('scope', [])}
    scope_added = len(new_scope - old_scope)
    scope_removed = len(old_scope - new_scope)
    scope_changed = 0
    for key in old_scope & new_scope:
        old_row = next(r for r in old_snap['scope'] if _scope_key(r) == key)
        new_row = next(r for r in new_snap['scope'] if _scope_key(r) == key)
        if _rule_content_hash(old_row) != _rule_content_hash(new_row):
            scope_changed += 1

    cap_changed = len(_diff_config_rows(
        old_snap.get('cap_floors', []),
        new_snap.get('cap_floors', []),
        _cap_floor_key,
        ignore_status=True,
    )['changed'])
    outlier_changed = len(_diff_config_rows(
        old_snap.get('outlier_rules', []),
        new_snap.get('outlier_rules', []),
        _outlier_key,
    )['changed'])
    stop_loss_changed = len(_diff_config_rows(
        old_snap.get('stop_loss_rules', []),
        new_snap.get('stop_loss_rules', []),
        _stop_loss_key,
    )['changed'])
    header_changed = len(_diff_contract_header(old_snap, new_snap))

    return {
        'rules': {
            'added': rules_added,
            'changed': rules_changed,
            'removed': rules_removed,
        },
        'entities': {
            'added': entities_added,
            'removed': entities_removed,
        },
        'scope': {
            'added': scope_added,
            'changed': scope_changed,
            'removed': scope_removed,
        },
        'cap_floors': {'changed': cap_changed},
        'outlier_rules': {'changed': outlier_changed},
        'stop_loss_rules': {'changed': stop_loss_changed},
        'contract_header': {'changed': header_changed},
    }


def _rule_rate_display(rule: dict) -> Optional[str]:
    flat = rule.get('flat_rate')
    if flat is not None and str(flat).strip() != '':
        try:
            return f'{Decimal(str(flat)):.2f}'
        except InvalidOperation:
            return str(flat)
    basis = rule.get('rate_basis') or {}
    pct = basis.get('percentage')
    if pct is not None and str(pct).strip() != '':
        return f'{Decimal(str(pct)):.2f}%'
    mult = rule.get('multiplier')
    if mult is not None:
        return str(mult)
    return None


def _rule_rate_decimal(rule: dict) -> Optional[Decimal]:
    flat = rule.get('flat_rate')
    if flat is not None and str(flat).strip() != '':
        try:
            return Decimal(str(flat))
        except InvalidOperation:
            return None
    return None


def _pct_change(old_rate: Optional[Decimal], new_rate: Optional[Decimal]) -> Optional[float]:
    if old_rate is None or new_rate is None or old_rate == 0:
        return None
    return float((new_rate - old_rate) / old_rate * 100)


def _entity_label(row: dict) -> str:
    et = row.get('entity_type')
    if et == 'ORG':
        return f"ORG {row.get('organization_id')}"
    if et == 'FACILITY':
        return f"FACILITY {row.get('facility_id')}"
    if et == 'PROVIDER':
        return f"PROVIDER {row.get('provider_id')}"
    return str(_entity_key(row))


def _scope_label(row: dict) -> str:
    parts = [row.get('lob_code'), row.get('product_id')]
    return ' / '.join(str(p) for p in parts if p) or str(_scope_key(row))


def _cap_floor_key(row: dict) -> tuple:
    return (
        row.get('scope'),
        row.get('cap_type'),
        row.get('code_value'),
        row.get('priority'),
    )


def _outlier_key(row: dict) -> tuple:
    return (
        row.get('threshold_scope'),
        str(row.get('threshold_amount')),
        row.get('priority'),
    )


def _stop_loss_key(row: dict) -> tuple:
    return (str(row.get('cost_threshold')), row.get('priority'))


def _row_compare_hash(row: dict, *, ignore_status: bool = False) -> str:
    payload = row
    if ignore_status:
        payload = {k: v for k, v in row.items() if k != 'status'}
    return _rule_content_hash(payload)


def _diff_config_rows(
    old_rows: list[dict],
    new_rows: list[dict],
    key_fn,
    *,
    ignore_status: bool = False,
) -> dict[str, list]:
    old_map = {key_fn(r): r for r in old_rows}
    new_map = {key_fn(r): r for r in new_rows}
    old_keys, new_keys = set(old_map), set(new_map)
    added = [new_map[k] for k in sorted(new_keys - old_keys, key=str)]
    removed = [old_map[k] for k in sorted(old_keys - new_keys, key=str)]
    changed = []
    for key in old_keys & new_keys:
        old_row, new_row = old_map[key], new_map[key]
        if _row_compare_hash(old_row, ignore_status=ignore_status) != _row_compare_hash(
            new_row, ignore_status=ignore_status,
        ):
            changed.append({
                'key': key,
                'old': old_row,
                'new': new_row,
            })
    return {'added': added, 'removed': removed, 'changed': changed}


def _diff_contract_header(old_snap: dict, new_snap: dict) -> list[dict]:
    changes: list[dict] = []
    skip_by_section = {
        'contract': _CONTRACT_HEADER_SKIP,
        'version': _VERSION_HEADER_SKIP,
    }
    for section in ('contract', 'version'):
        old_sec = old_snap.get(section, {}) or {}
        new_sec = new_snap.get(section, {}) or {}
        skip = skip_by_section[section]
        for field in sorted(set(old_sec) | set(new_sec)):
            if field in skip:
                continue
            old_val = old_sec.get(field)
            new_val = new_sec.get(field)
            if old_val != new_val:
                changes.append({
                    'field': f'{section}.{field}',
                    'old': old_val,
                    'new': new_val,
                })
    return changes


def _rate_change_row(old_rule: dict, new_rule: dict) -> dict:
    key = _natural_rule_key(new_rule) or _natural_rule_key(old_rule)
    code = key[0] if key else _rule_code(new_rule)
    entity = key[1] if key else (new_rule.get('covered_entity') or '')
    old_dec = _rule_rate_decimal(old_rule)
    new_dec = _rule_rate_decimal(new_rule)
    return {
        'code': code,
        'covered_entity': entity,
        'rule_name': new_rule.get('rule_name'),
        'old_rate': _rule_rate_display(old_rule),
        'new_rate': _rule_rate_display(new_rule),
        'pct_change': _pct_change(old_dec, new_dec),
    }


def _diff_rates_detail(old_snap: dict, new_snap: dict) -> dict:
    old_rules = _rules_by_natural_key(old_snap)
    new_rules = _rules_by_natural_key(new_snap)
    old_keys, new_keys = set(old_rules), set(new_rules)

    added = []
    for key in sorted(new_keys - old_keys, key=str):
        rule = new_rules[key]
        added.append({
            'code': key[0],
            'covered_entity': key[1],
            'rule_name': rule.get('rule_name'),
            'new_rate': _rule_rate_display(rule),
        })

    removed = []
    for key in sorted(old_keys - new_keys, key=str):
        rule = old_rules[key]
        removed.append({
            'code': key[0],
            'covered_entity': key[1],
            'rule_name': rule.get('rule_name'),
            'old_rate': _rule_rate_display(rule),
        })

    changed = []
    for key in sorted(old_keys & new_keys, key=str):
        old_rule, new_rule = old_rules[key], new_rules[key]
        if _rule_rate_fingerprint(old_rule) == _rule_rate_fingerprint(new_rule):
            continue
        changed.append(_rate_change_row(old_rule, new_rule))

    return {'added': added, 'changed': changed, 'removed': removed}


def load_snapshot_for_diff(
    version: ContractVersion,
    *,
    require_stored: bool = False,
) -> Optional[dict]:
    """
    Load comparable config for semantic diff.

    Pre-publish review always builds from current DB (rules, roster, scope) so
    draft-vs-live works without persisted ContractVersionSnapshot rows.
    Stored snapshots are used only when require_stored=True (audit/historical).
    """
    if require_stored:
        row = ContractVersionSnapshot.objects.filter(version=version).first()
        return row.snapshot if row is not None else None
    return _to_json_safe(build_version_snapshot(version))


def semantic_diff_snapshots(old_snap: dict, new_snap: dict) -> dict:
    """Full semantic diff grouped by category with counts and detail rows."""
    summary = _diff_summary_counts(old_snap, new_snap)
    rates = _diff_rates_detail(old_snap, new_snap)
    old_roster = {_entity_key(r): r for r in old_snap.get('roster', [])}
    new_roster = {_entity_key(r): r for r in new_snap.get('roster', [])}
    old_scope = {_scope_key(r): r for r in old_snap.get('scope', [])}
    new_scope = {_scope_key(r): r for r in new_snap.get('scope', [])}

    entities_added = [
        {'label': _entity_label(new_roster[k]), **new_roster[k]}
        for k in sorted(new_roster.keys() - old_roster.keys(), key=str)
    ]
    entities_removed = [
        {'label': _entity_label(old_roster[k]), **old_roster[k]}
        for k in sorted(old_roster.keys() - new_roster.keys(), key=str)
    ]

    scope_added = [
        {'label': _scope_label(new_scope[k]), **new_scope[k]}
        for k in sorted(new_scope.keys() - old_scope.keys(), key=str)
    ]
    scope_removed = [
        {'label': _scope_label(old_scope[k]), **old_scope[k]}
        for k in sorted(old_scope.keys() - new_scope.keys(), key=str)
    ]
    scope_changed = []
    for key in old_scope.keys() & new_scope.keys():
        old_row, new_row = old_scope[key], new_scope[key]
        if _rule_content_hash(old_row) != _rule_content_hash(new_row):
            scope_changed.append({
                'label': _scope_label(new_row),
                'old': old_row,
                'new': new_row,
            })

    cap_floors = _diff_config_rows(
        old_snap.get('cap_floors', []),
        new_snap.get('cap_floors', []),
        _cap_floor_key,
        ignore_status=True,
    )
    outlier_rules = _diff_config_rows(
        old_snap.get('outlier_rules', []),
        new_snap.get('outlier_rules', []),
        _outlier_key,
    )
    stop_loss_rules = _diff_config_rows(
        old_snap.get('stop_loss_rules', []),
        new_snap.get('stop_loss_rules', []),
        _stop_loss_key,
    )
    contract_header = _diff_contract_header(old_snap, new_snap)

    return {
        'version_id': new_snap.get('version', {}).get('version_id'),
        'against_version_id': old_snap.get('version', {}).get('version_id'),
        'summary': summary,
        'headline': _format_headline(summary),
        'rates': rates,
        'covered_entities': {
            'added': entities_added,
            'removed': entities_removed,
        },
        'product_scope': {
            'added': scope_added,
            'removed': scope_removed,
            'changed': scope_changed,
        },
        'cap_floors': cap_floors,
        'outlier_rules': outlier_rules,
        'stop_loss_rules': stop_loss_rules,
        'contract_header': contract_header,
    }


def _format_headline(summary: dict) -> str:
    parts = []
    rules = summary.get('rules', {})
    if rules.get('changed'):
        parts.append(f"{rules['changed']} rate{'s' if rules['changed'] != 1 else ''} changed")
    if rules.get('added'):
        parts.append(f"{rules['added']} rate{'s' if rules['added'] != 1 else ''} added")
    if rules.get('removed'):
        parts.append(f"{rules['removed']} rate{'s' if rules['removed'] != 1 else ''} removed")
    entities = summary.get('entities', {})
    if entities.get('added'):
        parts.append(f"{entities['added']} entit{'ies' if entities['added'] != 1 else 'y'} added")
    if entities.get('removed'):
        parts.append(f"{entities['removed']} entit{'ies' if entities['removed'] != 1 else 'y'} removed")
    scope = summary.get('scope', {})
    if scope.get('added'):
        parts.append(f"{scope['added']} product scope row{'s' if scope['added'] != 1 else ''} added")
    if scope.get('removed'):
        parts.append(f"{scope['removed']} product scope row{'s' if scope['removed'] != 1 else ''} removed")
    if scope.get('changed'):
        parts.append(f"{scope['changed']} product scope row{'s' if scope['changed'] != 1 else ''} changed")
    for label, key in (
        ('cap/floor', 'cap_floors'),
        ('outlier rule', 'outlier_rules'),
        ('stop-loss rule', 'stop_loss_rules'),
    ):
        n = summary.get(key, {}).get('changed', 0)
        if n:
            parts.append(f"{n} {label}{'' if n == 1 else 's'} changed")
    header_n = summary.get('contract_header', {}).get('changed', 0)
    if header_n:
        parts.append(f"{header_n} header field{'s' if header_n != 1 else ''} changed")
    return ', '.join(parts) if parts else 'No changes detected'
