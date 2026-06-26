"""
Step 12c-2: Server-side validation for structured condition JSON.

Used at rule save time (model clean(), serializers). Not used in pricing execution.
Validates schema only; does not perform DB queries.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Allowlists (source of truth for rule authoring)
# ---------------------------------------------------------------------------

ALLOWED_CONDITION_FIELDS = {
    "procedure_code": str,
    "billed_amount": Decimal,
    "units": int,
    "claim_type": str,
    "modifiers_count": int,
    # Claim-level context (for cap/floor, blending rules)
    "total_billed": Decimal,
    "current_total": Decimal,
}

ALLOWED_OPERATORS = frozenset({
    "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in",
})

LOGICAL_OPERATORS = frozenset({"AND", "OR"})

# For "in" / "not_in" the value must be a list
LIST_OPS = frozenset({"in", "not_in"})


def validate_condition_schema(condition_json: dict | None) -> None:
    """
    Validate structured condition JSON against the allowed schema.
    Raises ValidationError on failure. Does not perform DB queries.

    Rules:
    - None → valid (backward compatible)
    - Must contain keys: operator, conditions
    - operator must be AND or OR
    - conditions must be non-empty list
    - Each condition must contain field, op, value
    - field in ALLOWED_CONDITION_FIELDS
    - op in ALLOWED_OPERATORS
    - value type must match allowed field type (or be coercible)
    - No nested logical groups (no nested operator/conditions)
    """
    if condition_json is None:
        return

    if not isinstance(condition_json, dict):
        raise ValidationError(
            {"conditions": "Condition payload must be a JSON object or null."}
        )

    if "operator" not in condition_json:
        raise ValidationError(
            {"conditions": "Missing required key 'operator'. Allowed: AND, OR."}
        )
    if "conditions" not in condition_json:
        raise ValidationError(
            {"conditions": "Missing required key 'conditions' (array of condition objects)."}
        )

    op = condition_json.get("operator")
    if op is None:
        raise ValidationError({"conditions": "Key 'operator' cannot be null."})
    op_str = str(op).strip().upper()
    if op_str not in LOGICAL_OPERATORS:
        raise ValidationError(
            {"conditions": f"Invalid operator '{op}'. Allowed: AND, OR."}
        )

    raw_conditions = condition_json.get("conditions")
    if not isinstance(raw_conditions, list):
        raise ValidationError(
            {"conditions": "'conditions' must be a non-empty array."}
        )
    if len(raw_conditions) == 0:
        raise ValidationError(
            {"conditions": "At least one condition is required when conditions object is present."}
        )

    for i, cond in enumerate(raw_conditions):
        if not isinstance(cond, dict):
            raise ValidationError(
                {"conditions": f"Condition at index {i} must be an object with field, op, value."}
            )
        if "field" not in cond or "op" not in cond or "value" not in cond:
            raise ValidationError(
                {"conditions": f"Condition at index {i} must contain 'field', 'op', and 'value'."}
            )

        field_name = cond.get("field")
        if field_name not in ALLOWED_CONDITION_FIELDS:
            raise ValidationError(
                {"conditions": f"Unknown field '{field_name}'. Allowed: {sorted(ALLOWED_CONDITION_FIELDS)}."}
            )

        op_val = cond.get("op")
        op_lower = str(op_val).strip().lower() if op_val is not None else ""
        if op_lower not in ALLOWED_OPERATORS:
            raise ValidationError(
                {"conditions": f"Unknown operator '{op_val}'. Allowed: {sorted(ALLOWED_OPERATORS)}."}
            )

        value = cond.get("value")
        expected_type = ALLOWED_CONDITION_FIELDS[field_name]
        if op_lower in LIST_OPS:
            if not isinstance(value, (list, tuple)):
                raise ValidationError(
                    {"conditions": f"Operator '{op_lower}' requires a list value for field '{field_name}'."}
                )
            for j, v in enumerate(value):
                _check_value_type(v, field_name, expected_type, f"conditions[{i}].value[{j}]")
        else:
            _check_value_type(value, field_name, expected_type, f"conditions[{i}].value")


def _check_value_type(
    value: Any,
    field_name: str,
    expected_type: type,
    path: str,
) -> None:
    """Raise ValidationError if value cannot be used for the given field type."""
    if expected_type == str:
        if value is not None and not isinstance(value, str):
            # Allow numbers that can be stringified for eq/neq
            try:
                str(value)
            except Exception:
                raise ValidationError(
                    {"conditions": f"Field '{field_name}' expects a string value at {path}."}
                )
        return

    if expected_type == int:
        if value is None:
            raise ValidationError(
                {"conditions": f"Field '{field_name}' requires an integer value at {path}."}
            )
        if isinstance(value, int):
            return
        if isinstance(value, str):
            try:
                int(value)
                return
            except (ValueError, TypeError):
                pass
        raise ValidationError(
            {"conditions": f"Field '{field_name}' expects an integer at {path} (got {type(value).__name__})."}
        )

    if expected_type == Decimal:
        if value is None:
            raise ValidationError(
                {"conditions": f"Field '{field_name}' requires a numeric value at {path}."}
            )
        if isinstance(value, (Decimal, int, float)):
            return
        if isinstance(value, str):
            try:
                Decimal(str(value))
                return
            except (InvalidOperation, ValueError, TypeError):
                pass
        raise ValidationError(
            {"conditions": f"Field '{field_name}' expects a number at {path} (got {type(value).__name__})."}
        )
