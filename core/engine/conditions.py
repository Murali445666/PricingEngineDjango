"""
Step 12c-1: Structured condition evaluation engine.

Pure Python — no Django model imports, no DB queries.
Called by ClaimOrchestrator / LineOrchestrator before applying any rule that
carries a non-null `conditions` JSON payload.

Supported schema
----------------
{
    "operator": "AND" | "OR",          # logical combinator; default AND
    "conditions": [
        {"field": "<name>", "op": "<op>", "value": <scalar_or_list>}
        ...
    ]
}

Supported comparison operators
-------------------------------
eq      equal (string-safe)
neq     not equal
gt      greater-than   (numeric)
gte     greater-than-or-equal
lt      less-than
lte     less-than-or-equal
in      context value is contained in value list
not_in  context value is NOT contained in value list

Behaviour
---------
- condition_json is None  →  True  (rule always applies)
- empty conditions list   →  True
- field referenced in condition but missing from context  →  raises ValidationError
- context may have extra keys (e.g. base_allowed_amount); only fields referenced in conditions are validated
- unknown operator          →  raises ValidationError
- type coercion errors      →  raises ValidationError

No nested groups (flat list only). Nesting support deferred to Step 12c-2.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_SUPPORTED_OPS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"})
_NUMERIC_OPS = frozenset({"gt", "gte", "lt", "lte"})


def evaluate_conditions(condition_json: dict | None, context: dict) -> bool:
    """
    Evaluate a structured condition blob against a runtime context dict.

    Parameters
    ----------
    condition_json:
        A dict following the schema above, or None.
    context:
        A flat dict of field names → values derived from already-available
        pricing input data.  No DB calls should have produced this dict.

    Returns
    -------
    True if the rule should be applied; False if it should be skipped.

    Raises
    ------
    ValidationError
        When condition_json references an unknown field or an unsupported op.
    """
    if condition_json is None:
        return True

    conditions = condition_json.get("conditions")
    if not conditions:
        return True

    logical_op = str(condition_json.get("operator", "AND")).upper()
    if logical_op not in ("AND", "OR"):
        raise ValidationError(
            f"Unsupported logical operator '{logical_op}'. Allowed: AND, OR."
        )

    results = [_eval_single(c, context) for c in conditions]

    if logical_op == "AND":
        return all(results)
    return any(results)  # OR


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _eval_single(condition: dict, context: dict) -> bool:
    """Evaluate one leaf condition against context."""
    field = condition.get("field")
    op = str(condition.get("op", "")).lower()
    value = condition.get("value")

    if op not in _SUPPORTED_OPS:
        raise ValidationError(
            f"Unsupported operator '{op}'. Allowed: {sorted(_SUPPORTED_OPS)}."
        )

    if field not in context:
        raise ValidationError(
            f"Unknown condition field '{field}'. "
            f"Available fields: {sorted(context.keys())}."
        )

    ctx_value = context[field]

    # ---- string-based ops -----------------------------------------------
    if op == "eq":
        return _str(ctx_value) == _str(value)

    if op == "neq":
        return _str(ctx_value) != _str(value)

    # ---- set-membership ops ---------------------------------------------
    if op == "in":
        if not isinstance(value, (list, tuple)):
            raise ValidationError(
                f"Operator 'in' expects a list value, got {type(value).__name__}."
            )
        return _str(ctx_value) in [_str(v) for v in value]

    if op == "not_in":
        if not isinstance(value, (list, tuple)):
            raise ValidationError(
                f"Operator 'not_in' expects a list value, got {type(value).__name__}."
            )
        return _str(ctx_value) not in [_str(v) for v in value]

    # ---- numeric ops ----------------------------------------------------
    try:
        ctx_dec = _to_decimal(ctx_value)
        val_dec = _to_decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(
            f"Operator '{op}' requires numeric values; "
            f"could not convert field='{field}' value='{ctx_value}' or "
            f"condition value='{value}': {exc}"
        ) from exc

    if op == "gt":
        return ctx_dec > val_dec
    if op == "gte":
        return ctx_dec >= val_dec
    if op == "lt":
        return ctx_dec < val_dec
    if op == "lte":
        return ctx_dec <= val_dec

    # Unreachable given the frozenset guard above, but keeps mypy happy.
    raise ValidationError(f"Operator '{op}' not handled.")  # pragma: no cover


def _str(v: Any) -> str:
    """Normalise a value to a stripped lowercase string for equality comparisons."""
    if v is None:
        return ""
    return str(v).strip().lower()


def _to_decimal(v: Any) -> Decimal:
    """Convert a value to Decimal; raises InvalidOperation on failure."""
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def build_line_context(inp, state=None) -> dict:
    """
    Build a flat condition-evaluation context from a PricingInput (or duck-typed object).
    Optionally merge runtime state (Phase 3) for ADJUSTMENT rules (e.g. base_allowed_amount).

    All values originate from the already-available line input (and state if provided); no DB queries.
    Fields exposed:
        procedure_code, billed_amount, units, claim_type, modifiers_count, revenue_code (Phase C)
        When state is provided: base_allowed_amount, current_allowed_amount (default 0 if None)
    """
    modifiers = getattr(inp, "modifiers", None) or []
    revenue_code = getattr(inp, "revenue_code", None)
    ctx = {
        "procedure_code": str(getattr(inp, "procedure_code", "") or ""),
        "billed_amount": _safe_decimal(getattr(inp, "billed_amount", 0)),
        "units": int(getattr(inp, "units", 1) or 1),
        "claim_type": str(getattr(inp, "claim_type", "") or "").upper(),
        "modifiers_count": len(modifiers),
        "revenue_code": str(revenue_code).strip() if revenue_code else "",
    }
    if state is not None:
        ctx["base_allowed_amount"] = _safe_decimal(
            getattr(state, "base_allowed_amount", None)
        )
        ctx["current_allowed_amount"] = _safe_decimal(
            getattr(state, "current_allowed_amount", None)
        )
    return ctx


def build_claim_context(total_billed: Decimal, current_total: Decimal, claim_type: str = "") -> dict:
    """
    Build a flat condition-evaluation context for claim-level rules
    (cap/floor, blending rules).

    Fields exposed: total_billed, current_total, claim_type
    """
    return {
        "total_billed": _safe_decimal(total_billed),
        "current_total": _safe_decimal(current_total),
        "claim_type": str(claim_type or "").upper(),
    }


def _safe_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v)) if v is not None else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")
