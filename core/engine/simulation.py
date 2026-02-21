"""
Phase 4: Single-line simulation, optionally with a draft rule (in-memory).
When draft_rule is provided, resolution runs in single-rule mode (only that rule).
"""
import time
from decimal import Decimal
from typing import Optional, List, Dict, Any

from core.models import ProviderContract, PricingRule, FeeSchedule
from .types import PricingInput, LineResult, PricingStatus, PricingTrace
from .loader import PricingDataLoader
from .resolver import StrictRuleResolver
from .strategies import get_methodology


class _ShadowCondition:
    def __init__(self, attribute_name: str, attribute_value: str):
        self.attribute_name = attribute_name
        self.attribute_value = attribute_value


class _ShadowRule:
    """Rule-like object for draft simulation. Loader and resolver use attribute access."""
    def __init__(self, contract: ProviderContract, payload: Dict[str, Any]):
        self.contract = contract
        self.rule_id = int(payload.get('rule_id') or 0)
        self.rule_name = str(payload.get('rule_name') or 'Draft')
        self.rule_type = str(payload.get('rule_type') or 'BASE')
        self.methodology_code = str(payload.get('methodology_code') or '')
        self.multiplier = payload.get('multiplier')
        if self.multiplier is not None:
            self.multiplier = Decimal(str(self.multiplier))
        self.flat_rate = payload.get('flat_rate')
        if self.flat_rate is not None:
            self.flat_rate = Decimal(str(self.flat_rate))
        fs_id = payload.get('base_fee_schedule_id')
        self.base_fee_schedule = None
        if fs_id:
            try:
                self.base_fee_schedule = FeeSchedule.objects.get(pk=int(fs_id))
            except (ValueError, FeeSchedule.DoesNotExist):
                pass
        conditions = payload.get('conditions') or []
        self._conditions = [
            _ShadowCondition(
                c.get('attribute_name', ''),
                str(c.get('attribute_value', '')),
            )
            for c in conditions
            if c.get('attribute_name')
        ]

    @property
    def conditions(self):
        class _Q:
            def all(_self):
                return self._conditions
        return _Q()


def _matches_draft(rule: _ShadowRule, request: PricingInput, trace: PricingTrace) -> bool:
    for condition in rule.conditions.all():
        request_attr = condition.attribute_name
        if request_attr == 'code':
            request_attr = 'procedure_code'
        request_value = getattr(request, request_attr, None)
        if request_value is None:
            return False
        if str(request_value) != str(condition.attribute_value):
            return False
    return True


def run_line_simulation(
    contract: ProviderContract,
    request: PricingInput,
    draft_rule: Optional[Dict[str, Any]] = None,
) -> LineResult:
    """
    Run pricing for one line. If draft_rule is provided, use only that rule (single-rule mode).
    Otherwise delegate to the normal engine (ACTIVE rules only).
    """
    start_time = time.perf_counter()
    trace = PricingTrace()
    trace.log("SIMULATION", f"Processing {request.procedure_code}")

    def build_result(status, amount=None, method="", details="", rule=None):
        duration = (time.perf_counter() - start_time) * 1000
        r_id = getattr(rule, 'rule_id', 0) if rule else 0
        c_id = str(contract.pk) if contract else "UNKNOWN"
        return LineResult(
            status=status,
            allowed_amount=amount if amount is not None else Decimal("0.00"),
            methodology=method,
            details=details,
            contract_id=c_id,
            rule_id=r_id,
            trace=trace,
            engine_version="1.0.1-Traceability",
            execution_time_ms=round(duration, 2),
        )

    if draft_rule:
        shadow = _ShadowRule(contract, draft_rule)
        if not _matches_draft(shadow, request, trace):
            return build_result(
                PricingStatus.DENIED_NO_RULE,
                details="Draft rule conditions do not match this line.",
            )
        trace.log("SIMULATION", f"Using draft rule: {shadow.rule_name}")
        loader = PricingDataLoader()
        try:
            context = loader.load_context(request, shadow)
        except Exception as e:
            return build_result(
                PricingStatus.DENIED_MISSING_DATA,
                method=PricingStatus.DENIED_MISSING_DATA.value,
                details=str(e),
                rule=shadow,
            )
        try:
            strategy = get_methodology(shadow.methodology_code)
            price = strategy.calculate(context)
            return build_result(
                PricingStatus.SUCCESS,
                amount=price,
                method=shadow.methodology_code,
                rule=shadow,
            )
        except Exception as e:
            return build_result(
                PricingStatus.DENIED_CALCULATION_ERROR,
                method=PricingStatus.DENIED_CALCULATION_ERROR.value,
                details=str(e),
                rule=shadow,
            )

    # No draft: use normal engine (ACTIVE rules only)
    from .orchestrator import PricingEngine
    return PricingEngine().calculate_line(contract, request)
