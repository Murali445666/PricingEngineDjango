"""
Phase 4: Condition schema normalization.
Allowed attribute names and operators for PricingRuleCondition validation.
"""

ALLOWED_ATTRIBUTE_NAMES = frozenset({
    'procedure_code',
    'code',  # alias mapped to procedure_code in resolver
    'modifier',
    'plan_id',
    'group_id',
    'provider_id',
})

ALLOWED_OPERATORS = frozenset({
    'EQ',
})


def validate_attribute_name(value: str) -> bool:
    return value in ALLOWED_ATTRIBUTE_NAMES


def validate_operator(value: str) -> bool:
    return value in ALLOWED_OPERATORS
