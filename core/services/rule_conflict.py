"""
Phase 4: Rule conflict detection.
Finds other rules on the same contract with overlapping conditions (same attribute_name + attribute_value).
"""
from typing import List, Dict, Any, Optional

from core.models import PricingRule, PricingRuleCondition


def get_conflicts_for_rule(rule: PricingRule) -> List[Dict[str, str]]:
    """
    Return list of conflict messages for an existing rule.
    A conflict is another rule (ACTIVE or DRAFT) on the same contract with at least one
    condition matching (attribute_name, attribute_value).
    """
    if not rule.pk or not rule.contract_id:
        return []
    return _conflicts_for_conditions(
        contract_id=rule.contract_id,
        conditions=list(rule.conditions.values_list('attribute_name', 'attribute_value', flat=False)),
            exclude_rule_id=rule.pk,
        )


def get_conflicts_for_rule_payload(
    contract_id: int,
    conditions: List[Dict[str, Any]],
    exclude_rule_id: Optional[int] = None,
) -> List[Dict[str, str]]:
    """
    Return list of conflict messages for a payload (e.g. new rule not yet saved).
    conditions: list of {"attribute_name": "...", "attribute_value": "..."}.
    exclude_rule_id: when set, skip this rule (e.g. current rule on detail page).
    """
    cond_tuples = [
        (c.get('attribute_name'), c.get('attribute_value'))
        for c in conditions
        if c.get('attribute_name') and c.get('attribute_value') is not None
    ]
    return _conflicts_for_conditions(
        contract_id=contract_id, conditions=cond_tuples, exclude_rule_id=exclude_rule_id
    )


def _conflicts_for_conditions(
    contract_id: int,
    conditions: List[tuple],
    exclude_rule_id: Optional[int],
) -> List[Dict[str, str]]:
    if not conditions:
        return []
    conflicts = []
    qs = PricingRule.objects.filter(contract_id=contract_id).prefetch_related('conditions')
    if exclude_rule_id is not None:
        qs = qs.exclude(pk=exclude_rule_id)
    for other in qs:
        if other.status not in (PricingRule.RuleStatus.ACTIVE, PricingRule.RuleStatus.DRAFT):
            continue
        for attr_name, attr_val in conditions:
            if PricingRuleCondition.objects.filter(
                pricing_rule=other,
                attribute_name=attr_name,
                attribute_value=attr_val,
            ).exists():
                conflicts.append({
                    "message": f"Overlaps with Rule {other.rule_id} ({other.rule_name or 'Unnamed'}): same condition {attr_name}={attr_val}.",
                    "rule_id": other.rule_id,
                    "rule_name": other.rule_name or "",
                    "attribute_name": attr_name,
                    "attribute_value": attr_val,
                })
                break
    return conflicts
