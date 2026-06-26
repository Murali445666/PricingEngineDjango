from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q, Case, When, Value, IntegerField
from django.conf import settings

from core.models import ProviderContract, PricingRule, CodeGroupMember
from .types import PricingInput, PricingTrace, LinePricingState
from .config import ContractPricingConfig
from .conditions import build_line_context
from typing import Optional, List

# Attribute names that should use Decimal comparison when operator is numeric (LT/GT/LTE/GTE or EQ).
_NUMERIC_CONDITION_FIELDS = frozenset({
    "billed_amount", "base_allowed_amount", "current_allowed_amount", "units", "modifiers_count",
})


def _tiered_resolution_enabled() -> bool:
    return bool(getattr(settings, 'FEATURE_TIERED_RESOLUTION', False))


def _rule_tier_priority(rule: PricingRule) -> int:
    if not getattr(rule, 'version_id', None):
        return 0
    v = getattr(rule, 'version', None)
    if v is None:
        return 0
    return int(getattr(v, 'tier_priority', 0) or 0)


def _rule_passes_tier_product_filter(rule: PricingRule, request: PricingInput) -> bool:
    """When tier resolution is on and request.product_id is set, drop rules on versions with another product_id."""
    if not _tiered_resolution_enabled():
        return True
    pid = getattr(request, 'product_id', None)
    if pid is None or str(pid).strip() == '':
        return True
    if not rule.version_id:
        return True
    v = getattr(rule, 'version', None)
    if v is None:
        return True
    vp = getattr(v, 'product_id', None)
    if vp is None or str(vp).strip() == '':
        return True
    return str(vp).strip() == str(pid).strip()


def _safe_date(v) -> date:
    """Return a date for comparison. Accepts date, datetime, or isoformat string (e.g. from JSON)."""
    if v is None:
        return date.today()
    if isinstance(v, date):
        return v if not isinstance(v, datetime) else v.date()
    if isinstance(v, datetime):
        return v.date()
    try:
        return date.fromisoformat(str(v).strip())
    except (TypeError, ValueError):
        return date.today()


def _safe_decimal_for_compare(v) -> Optional[Decimal]:
    """Cast to Decimal for comparison; return None if not convertible."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


class StrictRuleResolver:
    def __init__(self, contract: ProviderContract, version=None, config: Optional[ContractPricingConfig] = None):
        self.contract = contract
        self.version = version
        self.config = config
        # Phase C: cache (code_group_id, service_date) -> set of code_id for N+1 avoidance
        self._code_group_cache: dict = {}

    def resolve(self, request: PricingInput, trace: PricingTrace) -> Optional[PricingRule]:
        service_date = _safe_date(request.service_date)

        if self.config is not None and self.config.rules:
            # Use config: filter by service_date in memory; already contract/version-scoped
            rules = [
                r for r in self.config.rules
                if r.effective_start_date <= service_date
                and (r.effective_end_date is None or r.effective_end_date >= service_date)
            ]
            rules = [r for r in rules if _rule_passes_tier_product_filter(r, request)]
            if self.version is not None:
                if _tiered_resolution_enabled():
                    rules = sorted(
                        rules,
                        key=lambda r: (
                            0 if r.version_id == self.version.pk else 1,
                            -_rule_tier_priority(r),
                            -(r.specificity_score or 0),
                        ),
                    )
                else:
                    rules = sorted(
                        rules,
                        key=lambda r: (0 if r.version_id == self.version.pk else 1, -(r.specificity_score or 0)),
                    )
            else:
                rules = [r for r in rules if r.version_id is None]
                if _tiered_resolution_enabled():
                    rules = sorted(
                        rules,
                        key=lambda r: (-_rule_tier_priority(r), -(r.specificity_score or 0)),
                    )
                else:
                    rules = sorted(rules, key=lambda r: -(r.specificity_score or 0))
        else:
            # Live DB path
            rules_qs = (
                PricingRule.objects.filter(
                    contract=self.contract,
                    status=PricingRule.RuleStatus.ACTIVE,
                    effective_start_date__lte=service_date,
                )
                .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
                .select_related('contract', 'base_fee_schedule', 'version')
                .prefetch_related('conditions')
            )
            if self.version is not None:
                rules_qs = rules_qs.filter(Q(version=self.version) | Q(version__isnull=True))
                rules_qs = rules_qs.annotate(
                    _version_first=Case(
                        When(version_id=self.version.pk, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                ).order_by('_version_first', '-specificity_score')
            else:
                rules_qs = rules_qs.filter(version__isnull=True).order_by('-specificity_score')
            rules = list(rules_qs)
            rules = [r for r in rules if _rule_passes_tier_product_filter(r, request)]
            if _tiered_resolution_enabled():
                if self.version is not None:
                    rules.sort(
                        key=lambda r: (
                            0 if r.version_id == self.version.pk else 1,
                            -_rule_tier_priority(r),
                            -(r.specificity_score or 0),
                        ),
                    )
                else:
                    rules.sort(
                        key=lambda r: (-_rule_tier_priority(r), -(r.specificity_score or 0)),
                    )

        trace.log("RESOLVER", f"Evaluating {len(rules)} rules for Contract {self.contract.contract_name} (service_date={service_date})")

        for rule in rules:
            if request.claim_type:
                rule_ct = getattr(rule, 'claim_type', None) or ''
                if rule_ct and rule_ct != request.claim_type:
                    continue
            if self._matches(rule, request, trace):
                trace.log("RESOLVER", f"✅ MATCH: {rule.rule_name} (Score: {rule.specificity_score})")
                return rule

        trace.log("RESOLVER", "❌ NO MATCH found.")
        return None

    def resolve_for_stage(
        self,
        request: PricingInput,
        trace: PricingTrace,
        stage: str,
        state: Optional[LinePricingState] = None,
    ) -> List[PricingRule]:
        """
        Phase 1: Return all rules for the given stage that pass conditions.
        Conditions are evaluated inside this method (single place); orchestrator does not re-check.
        Treat null/blank rule_type as 'BASE'. Sorted by version precedence then -specificity_score.
        """
        service_date = _safe_date(request.service_date)
        stage_key = (stage or 'BASE').strip().upper() or 'BASE'

        if self.config is not None and self.config.rules:
            rules_for_stage = getattr(self.config, 'rules_by_stage', None) or {}
            rules_for_stage = rules_for_stage.get(stage_key)
            if rules_for_stage is None:
                rules_for_stage = [
                    r for r in self.config.rules
                    if ((getattr(r, 'rule_type', None) or 'BASE').strip() or 'BASE').upper() == stage_key
                ]
            rules_for_stage = list(rules_for_stage) if rules_for_stage else []
            rules_for_stage = [r for r in rules_for_stage if _rule_passes_tier_product_filter(r, request)]
            if self.version is not None:
                if _tiered_resolution_enabled():
                    rules_for_stage.sort(
                        key=lambda r: (
                            0 if r.version_id == self.version.pk else 1,
                            -_rule_tier_priority(r),
                            -(r.specificity_score or 0),
                        ),
                    )
                else:
                    rules_for_stage.sort(
                        key=lambda r: (0 if r.version_id == self.version.pk else 1, -(r.specificity_score or 0)),
                    )
            else:
                if _tiered_resolution_enabled():
                    rules_for_stage.sort(
                        key=lambda r: (-_rule_tier_priority(r), -(r.specificity_score or 0)),
                    )
                else:
                    rules_for_stage.sort(key=lambda r: -(r.specificity_score or 0))
        else:
            if stage_key == 'BASE':
                rule_type_filter = Q(rule_type='BASE') | Q(rule_type__isnull=True) | Q(rule_type='')
            else:
                rule_type_filter = Q(rule_type=stage_key)
            rules_qs = (
                PricingRule.objects.filter(
                    contract=self.contract,
                    status=PricingRule.RuleStatus.ACTIVE,
                    effective_start_date__lte=service_date,
                )
                .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
                .filter(rule_type_filter)
                .select_related('contract', 'base_fee_schedule', 'version')
                .prefetch_related('conditions')
            )
            if self.version is not None:
                rules_qs = rules_qs.filter(Q(version=self.version) | Q(version__isnull=True))
                rules_qs = rules_qs.annotate(
                    _version_first=Case(
                        When(version_id=self.version.pk, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                ).order_by('_version_first', '-specificity_score')
            else:
                rules_qs = rules_qs.filter(version__isnull=True).order_by('-specificity_score')
            rules_for_stage = list(rules_qs)
            rules_for_stage = [r for r in rules_for_stage if _rule_passes_tier_product_filter(r, request)]
            if _tiered_resolution_enabled():
                if self.version is not None:
                    rules_for_stage.sort(
                        key=lambda r: (
                            0 if r.version_id == self.version.pk else 1,
                            -_rule_tier_priority(r),
                            -(r.specificity_score or 0),
                        ),
                    )
                else:
                    rules_for_stage.sort(
                        key=lambda r: (-_rule_tier_priority(r), -(r.specificity_score or 0)),
                    )

        trace.log("RESOLVER", f"resolve_for_stage({stage_key}): {len(rules_for_stage)} candidate rules")
        # DEBUG: count and rule_ids so we can verify rule 74 (code_group) is in the list
        _ids = [r.rule_id for r in rules_for_stage]
        print(f"[RESOLVER] resolve_for_stage({stage_key}): {len(rules_for_stage)} candidate rules rule_ids={_ids} (before _matches)")

        # Build context with optional state so ADJUSTMENT rules can use base_allowed_amount, etc.
        line_ctx: Optional[dict] = build_line_context(request, state) if state is not None else None
        if line_ctx is not None:
            print(f"[RESOLVER] line_ctx keys: {list(line_ctx.keys())} | revenue_code={line_ctx.get('revenue_code')!r} | base_allowed_amount={line_ctx.get('base_allowed_amount')} | current_allowed_amount={line_ctx.get('current_allowed_amount')}")
        print(f"[RESOLVER] request.revenue_code={getattr(request, 'revenue_code', None)!r} (PricingInput)")

        result = []
        for rule in rules_for_stage:
            if request.claim_type:
                rule_ct = getattr(rule, 'claim_type', None) or ''
                if rule_ct and rule_ct != request.claim_type:
                    print(f"[RESOLVER] SKIP rule_id={rule.rule_id} ({rule.rule_name}): claim_type mismatch (rule={rule_ct!r}, request={request.claim_type!r})")
                    continue
            matched, reason = self._matches_with_reason(rule, request, trace, context=line_ctx)
            if matched:
                result.append(rule)
                trace.log("RESOLVER", f"  MATCH: {rule.rule_name} (Score: {rule.specificity_score})")
                print(f"[RESOLVER] MATCH rule_id={rule.rule_id} | {rule.rule_name} | type={getattr(rule, 'rule_type', None)} | methodology={getattr(rule, 'methodology_code', None)}")
            else:
                print(f"[RESOLVER] SKIP rule_id={rule.rule_id} ({rule.rule_name}): {reason}")

        print(f"[RESOLVER] resolve_for_stage({stage_key}): returning {len(result)} rules after conditions\n")
        return result

    def _matches(
        self,
        rule: PricingRule,
        request: PricingInput,
        trace: PricingTrace,
        context: Optional[dict] = None,
    ) -> bool:
        matched, _ = self._matches_with_reason(rule, request, trace, context=context)
        return matched

    def _matches_with_reason(
        self,
        rule: PricingRule,
        request: PricingInput,
        trace: PricingTrace,
        context: Optional[dict] = None,
    ) -> tuple:
        """Returns (True, '') if rule matches; (False, reason_string) otherwise. Uses Decimal for LT/GT/LTE/GTE and for EQ on numeric fields."""
        conditions = rule.conditions.all()

        if not conditions:
            return False, "rule has no conditions (all rules must have at least one condition to match)"

        for condition in conditions:
            request_attr = condition.attribute_name

            # Map 'code' to 'procedure_code'
            if request_attr == 'code':
                request_attr = 'procedure_code'

            # Phase C: code_group — attribute_value is code_group_id; match if procedure_code in group
            if request_attr.strip().lower() == 'code_group':
                rule_val_str = (condition.attribute_value or "").strip()
                if not rule_val_str:
                    return False, "condition code_group requires attribute_value (code_group_id)"
                try:
                    code_group_id = int(rule_val_str)
                except ValueError:
                    return False, f"condition code_group attribute_value must be integer code_group_id, got {rule_val_str!r}"
                service_date = _safe_date(request.service_date)
                cache_key = (code_group_id, service_date)
                if cache_key not in self._code_group_cache:
                    # Filter: effective_start_date <= service_date AND (effective_end_date IS NULL OR effective_end_date >= service_date)
                    members_qs = CodeGroupMember.objects.filter(
                        code_group_id=code_group_id,
                        effective_start_date__lte=service_date,
                    ).filter(
                        Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
                    )
                    members_list = list(members_qs)
                    # Normalize to stripped strings so "99998" matches " 99998 " or 99998
                    self._code_group_cache[cache_key] = set(
                        str(m.code_id).strip() for m in members_list if getattr(m, 'code_id', None) is not None
                    )
                    # Debug: exact members loaded for this service_date (proves date filter is applied)
                    members_debug = [
                        (getattr(m, 'code_id', None), getattr(m, 'effective_start_date', None), getattr(m, 'effective_end_date', None))
                        for m in members_list
                    ]
                    print(
                        f"[RESOLVER] code_group members loaded: group_id={code_group_id}, service_date={service_date}, "
                        f"filter=effective_start_date<={service_date} AND (effective_end_date IS NULL OR effective_end_date>={service_date}), "
                        f"count={len(members_list)}, members={members_debug}"
                    )
                code_ids = self._code_group_cache[cache_key]
                procedure_code_val = str(request.procedure_code or "").strip()
                in_group = procedure_code_val in code_ids
                op = (getattr(condition, "operator", None) or "EQ").strip().upper() or "EQ"
                # Debug: confirm branch runs and show group_id, members, procedure_code
                print(
                    f"[RESOLVER] code_group check: group_id={code_group_id}, members={sorted(code_ids)!r}, "
                    f"procedure_code={procedure_code_val!r}, in_group={in_group}, op={op}"
                )
                if op == "EQ" and not in_group:
                    return False, f"condition code_group: procedure_code {request.procedure_code!r} not in group {code_group_id}"
                if op == "NEQ" and in_group:
                    return False, f"condition code_group: procedure_code {request.procedure_code!r} is in group {code_group_id} (NEQ required)"
                continue

            # Phase C: revenue_code — compare request.revenue_code to condition.attribute_value
            if request_attr == 'revenue_code':
                request_value = context.get('revenue_code') if context is not None else getattr(request, 'revenue_code', None)
                op = (getattr(condition, "operator", None) or "EQ").strip().upper() or "EQ"
                rule_val_str = (condition.attribute_value or "").strip()
                target_value = rule_val_str if rule_val_str else condition.attribute_value
                if op == "EQ":
                    if str(request_value or "") != str(target_value or ""):
                        return False, f"condition revenue_code: {request_value!r} != {target_value!r}"
                elif op == "NEQ":
                    if str(request_value or "") == str(target_value or ""):
                        return False, f"condition revenue_code: {request_value!r} == {target_value!r} (NEQ required)"
                else:
                    return False, f"unsupported operator {op!r} for revenue_code"
                continue

            if context is not None:
                request_value = context.get(request_attr)
            else:
                request_value = getattr(request, request_attr, None)

            if request_value is None and (condition.attribute_value or "").strip() != "":
                return False, f"condition field {request_attr!r} not in context/request or is None"

            op = (getattr(condition, "operator", None) or "EQ").strip().upper() or "EQ"
            rule_val_str = (condition.attribute_value or "").strip()

            # Dynamic context reference: @field_name means use value from line_ctx
            target_value = None
            if rule_val_str.startswith("@"):
                ref_key = rule_val_str[1:].strip()
                if not ref_key:
                    return False, "condition attribute_value is @ but key is empty"
                if context is None:
                    return False, f"dynamic reference @{ref_key} requires line context (context is None)"
                if ref_key not in context:
                    trace.log(
                        "RESOLVER",
                        f"Dynamic reference @{ref_key} not found in context; keys: {list(context.keys())}",
                    )
                    return False, f"dynamic reference @{ref_key} not found in context"
                target_value = context[ref_key]
            else:
                target_value = rule_val_str if rule_val_str else condition.attribute_value

            # Numeric comparison: safely cast both sides to Decimal for LT, GT, LTE, GTE, and for EQ/NEQ on numeric fields
            if op in ("LT", "GT", "LTE", "GTE") or (op in ("EQ", "NEQ") and request_attr in _NUMERIC_CONDITION_FIELDS):
                ctx_dec = _safe_decimal_for_compare(request_value)
                val_dec = _safe_decimal_for_compare(target_value)
                if ctx_dec is not None and val_dec is not None:
                    if op == "LT":
                        if not (ctx_dec < val_dec):
                            return False, f"condition {request_attr!r}: {ctx_dec!s} < {val_dec!s} is False"
                    elif op == "LTE":
                        if not (ctx_dec <= val_dec):
                            return False, f"condition {request_attr!r}: {ctx_dec!s} <= {val_dec!s} is False"
                    elif op == "GT":
                        if not (ctx_dec > val_dec):
                            return False, f"condition {request_attr!r}: {ctx_dec!s} > {val_dec!s} is False"
                    elif op == "GTE":
                        if not (ctx_dec >= val_dec):
                            return False, f"condition {request_attr!r}: {ctx_dec!s} >= {val_dec!s} is False"
                    elif op == "EQ":
                        if ctx_dec != val_dec:
                            return False, f"condition {request_attr!r}: {ctx_dec!s} != {val_dec!s}"
                    elif op == "NEQ":
                        if ctx_dec == val_dec:
                            return False, f"condition {request_attr!r}: {ctx_dec!s} == {val_dec!s} (NEQ required)"
                    continue
                # Non-numeric op or conversion failed: for LT/GT/LTE/GTE we must fail; for EQ/NEQ fall through to string
                if op in ("LT", "GT", "LTE", "GTE"):
                    return False, f"condition {request_attr!r}: could not convert to Decimal for {op} (ctx={request_value!r}, target={target_value!r})"

            # String comparison for EQ/NEQ or non-numeric fields
            if op == "EQ":
                if str(request_value) != str(target_value):
                    return False, f"condition {request_attr!r}: context value {request_value!r} != target value {target_value!r}"
            elif op == "NEQ":
                if str(request_value) == str(target_value):
                    return False, f"condition {request_attr!r}: context value {request_value!r} == target value {target_value!r} (NEQ required)"
            else:
                return False, f"unsupported operator {op!r} for non-numeric comparison"

        return True, ""