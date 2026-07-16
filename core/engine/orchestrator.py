"""
Step 4 extension: ClaimOrchestrator and LineOrchestrator.

ClaimOrchestrator encapsulates the canonical claim pricing execution order:
  1  Resolve contract
  2  Resolve contract version
  3  Build ContractPricingConfig (rules, methodologies, stop-loss, outlier, carve-outs, caps, blending)
  4  Price lines (base methodology via LineOrchestrator)
  5  Apply line-level carve-outs           [Step 7]
  6  Phase G: Apply line-level cap/floor    [LINE_CAP_FLOOR] when config.line_cap_floors
  7  Accumulate total_allowed
  8  CLAIM_METHOD (DRG, stop-loss, outlier)
  9  Phase F: Cross-line (MPPR)
  10 Apply blending (additive/override)    [Step 9]
  11 Apply claim-level caps/floors        [Step 8]
  12 Return ClaimPricingResult

LineOrchestrator handles per-line rule resolution, context loading, and strategy execution.
Both accept optional ContractPricingConfig (live DB when config is None).
"""
import logging
import time
import traceback
from decimal import Decimal
from typing import Optional

from django.db import models

from core.models import ProviderContract, ClaimHeader, ContractOutlierRule, ContractStopLossRule
from .types import (
    PricingInput,
    LineResult,
    PricingStatus,
    PricingTrace,
    ClaimPricingResult,
    LinePricingState,
    ExecutionContext,
    LineState,
    TraceEntry,
    PricingContext,
)
from .config import ClaimPricingInput, ClaimLineInput, ContractPricingConfig
from .loader import (
    PricingDataLoader,
    resolve_active_contract_version,
    resolve_contract_for_claim,
    build_contract_pricing_config_from_db,
)
from .resolver import StrictRuleResolver, _safe_date
from .strategies import get_methodology
from .claim_strategies import CLAIM_METHODOLOGY_REGISTRY
from .exceptions import NoApcFoundError, NoAspFoundError
from .conditions import evaluate_conditions, build_line_context, build_claim_context

logger = logging.getLogger(__name__)

VERSION = "1.0.1-Traceability"


def _emit_rule_select_trace(
    exec_context: Optional[ExecutionContext],
    line_index: Optional[int],
    rule,
) -> None:
    if exec_context is None or line_index is None or rule is None:
        return
    exec_context.trace.append(TraceEntry(
        stage="LINE",
        phase="RULE_SELECT",
        line_index=line_index,
        rule_id=rule.rule_id,
        methodology_code=rule.methodology_code or "",
        message=(
            f"rule={rule.rule_name} id={rule.rule_id} "
            f"methodology={rule.methodology_code}"
        ),
    ))


def _emit_strategy_observability(
    exec_context: Optional[ExecutionContext],
    line_index: Optional[int],
    rule,
    pricing_context: PricingContext,
) -> None:
    if exec_context is None or line_index is None:
        return
    rid = rule.rule_id if rule else None
    meth = (rule.methodology_code or "") if rule else ""
    for msg in pricing_context.methodology_events:
        exec_context.trace.append(TraceEntry(
            stage="LINE",
            phase="METHOD_BASE",
            line_index=line_index,
            rule_id=rid,
            methodology_code=meth,
            message=msg,
        ))
    for ev in pricing_context.modifier_events:
        exec_context.trace.append(TraceEntry(
            stage="LINE",
            phase="MODIFIER",
            line_index=line_index,
            rule_id=rid,
            methodology_code=meth,
            message=ev.message,
        ))


def _line_cap_floor_eligible(cf, inp: PricingInput, service_date) -> bool:
    """True when a line cap/floor rule passes date, code, and condition filters."""
    if getattr(cf, 'effective_start_date', None) and cf.effective_start_date > service_date:
        return False
    end = getattr(cf, 'effective_end_date', None)
    if end is not None and end < service_date:
        return False
    if getattr(cf, 'code_value', None):
        code_val = (cf.code_value or '').strip()
        if code_val and (inp.procedure_code or '').strip() != code_val:
            return False
    cf_conditions = getattr(cf, 'conditions', None)
    if cf_conditions:
        line_ctx = build_line_context(inp)
        try:
            if not evaluate_conditions(cf_conditions, line_ctx):
                return False
        except Exception:
            return False
    return True


def _pct_billed_cap_label(cf) -> str:
    pct = getattr(cf, 'percentage', None)
    code_val = getattr(cf, 'code_value', None)
    if pct == Decimal('100') and not (code_val or '').strip():
        return f"lesser-of PCT_BILLED_CAP pct={pct}"
    return f"PCT_BILLED_CAP pct={pct}"


def _claim_cap_floor_eligible(
    cf,
    service_date,
    final_total: Decimal,
    total_billed: Decimal,
    line_methodologies: set,
    line_results: list,
    claim_type: str,
) -> bool:
    """True when a claim cap/floor rule passes date, scope, and condition filters."""
    if getattr(cf, 'effective_start_date', None) and cf.effective_start_date > service_date:
        return False
    end = getattr(cf, 'effective_end_date', None)
    if end is not None and end < service_date:
        return False
    cf_conditions = getattr(cf, "conditions", None)
    if cf_conditions:
        claim_ctx = build_claim_context(total_billed, final_total, claim_type=claim_type)
        try:
            if not evaluate_conditions(cf_conditions, claim_ctx):
                return False
        except Exception:
            return False
    scope = (cf.scope or 'CLAIM').upper()
    if scope == 'LINE':
        return False
    if scope == 'DRG' and 'DRG' not in line_methodologies:
        return False
    if scope == 'APC' and 'APC' not in line_methodologies and 'OPPS' not in line_methodologies:
        return False
    if cf.code_value and scope in ('DRG', 'APC'):
        code_used = any(
            r.status in (PricingStatus.SUCCESS, PricingStatus.CARVEOUT_REPRICED)
            and r.methodology in (scope, 'OPPS')
            for r in line_results
        )
        if not code_used:
            return False
    return True


def _run_cross_line_phase(context, config) -> None:
    """
    Phase F: Cross-line MPPR. For each MPPRDefinition in config, determine lines in scope
    (procedure in code_group or matches procedure_code), rank by rank_by (e.g. current_allowed_amount),
    apply primary_pct to first, secondary_pct to second, tertiary_pct to rest. Mutates context.line_states
    and context.claim_total; appends to context.trace.
    """
    mppr_defs = getattr(config, "mppr_definitions", None) or ()
    if not mppr_defs:
        return
    from django.db.models import Q
    from core.models import CodeGroupMember

    service_date = context.service_date
    if not service_date:
        return
    for mppr in mppr_defs:
        # Iterate .all() so we get a queryset (uses prefetch_related cache when available); RelatedManager is not iterable.
        scopes_rel = getattr(mppr, "scopes", None)
        scope_list = list(scopes_rel.all()) if scopes_rel is not None and hasattr(scopes_rel, "all") else []
        scope_debug = [
            {"procedure_code": getattr(s, "procedure_code", None), "code_group_id": getattr(s, "code_group_id", None)}
            for s in scope_list
        ]
        logger.debug(
            f"[CROSS_LINE] mppr_definition_id={getattr(mppr, 'pk', None)} scope_count={len(scope_list)} scopes={scope_debug}"
        )
        # Build set of procedure codes in scope (code_group members + explicit procedure_codes)
        scope_codes = set()
        for scope in scope_list:
            if getattr(scope, "code_group_id", None):
                members = CodeGroupMember.objects.filter(
                    code_group_id=scope.code_group_id,
                    effective_start_date__lte=service_date,
                ).filter(
                    Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
                ).values_list("code_id", flat=True)
                for c in members:
                    scope_codes.add((c or "").strip())
            pc = (getattr(scope, "procedure_code", None) or "").strip()
            if pc:
                scope_codes.add(pc)
        if not scope_codes:
            continue
        # Lines in scope: (line_index, base_allowed, current_allowed)
        in_scope = []
        for idx, state in enumerate(context.line_states):
            proc = (getattr(state.input, "procedure_code", None) or "").strip()
            if proc in scope_codes:
                base_val = getattr(state, "base_allowed_amount", None) or Decimal("0")
                cur_val = getattr(state, "current_allowed_amount", None) or Decimal("0")
                in_scope.append((idx, base_val, cur_val))
        if not in_scope:
            continue
        # Sort by rank_by: ALLOWED_AMOUNT = current descending; RVU/FEE_SCHEDULE not supported here, treat as ALLOWED_AMOUNT
        rank_by = (getattr(mppr, "rank_by", None) or "ALLOWED_AMOUNT").strip().upper()
        if rank_by == "ALLOWED_AMOUNT":
            in_scope.sort(key=lambda x: x[2], reverse=True)
        else:
            in_scope.sort(key=lambda x: x[2], reverse=True)
        primary_pct = getattr(mppr, "primary_pct", None) or Decimal("100")
        secondary_pct = getattr(mppr, "secondary_pct", None) or Decimal("50")
        tertiary_pct = getattr(mppr, "tertiary_pct", None) or Decimal("25")
        for i, (line_index, base_val, cur_before) in enumerate(in_scope):
            if i == 0:
                pct = primary_pct
            elif i == 1:
                pct = secondary_pct
            else:
                pct = tertiary_pct
            new_amount = (base_val * pct / Decimal("100")).quantize(Decimal("0.01"))
            proc = (getattr(context.line_states[line_index].input, "procedure_code", None) or "").strip()
            logger.debug(
                f"[CROSS_LINE] in_scope line line_index={line_index} procedure_code={proc} "
                f"base_allowed_amount={base_val} current_before={cur_before} pct={pct} -> current_after={new_amount}"
            )
            context.line_states[line_index].current_allowed_amount = new_amount
            read_back = getattr(context.line_states[line_index], "current_allowed_amount", None)
            logger.debug(f"[CROSS_LINE] read_back line_states[{line_index}].current_allowed_amount={read_back}")
        context.trace.append(
            TraceEntry(
                stage="CLAIM",
                phase="CROSS_LINE",
                methodology_code="MPPR",
                message=f"mppr_def={getattr(mppr, 'name', mppr.pk)} in_scope={len(in_scope)} primary_pct={primary_pct} secondary_pct={secondary_pct} tertiary_pct={tertiary_pct}",
            )
        )
    # Recompute claim_total from line_states
    context.claim_total = sum(
        getattr(s, "current_allowed_amount", None) or Decimal("0") for s in context.line_states
    )
    logger.debug(f"[CROSS_LINE] after phase: context.claim_total={context.claim_total} line_states amounts={[getattr(s, 'current_allowed_amount', None) for s in context.line_states]}")


class LineOrchestrator:
    """
    Per-line pricing: rule resolution, context loading, strategy execution.
    Used by ClaimOrchestrator for each line and by ClaimPricingService for single-line endpoint.
    """

    def __init__(self):
        self.loader = PricingDataLoader()

    def run(
        self,
        contract: ProviderContract,
        request: PricingInput,
        version=None,
        config: Optional[ContractPricingConfig] = None,
        context: Optional[ExecutionContext] = None,
        line_index: Optional[int] = None,
    ) -> LineResult:
        start_time = time.perf_counter()
        exec_context = context  # Phase A: preserve ExecutionContext (name 'context' is used by loader later)
        trace = PricingTrace()
        trace.log("ORCHESTRATOR", f"Processing {request.procedure_code} | TraceID: {trace.trace_id}")

        def build_result(status, amount=None, method="", details="", rule=None, applied_rule_ids=None, base_allowed_amount=None):
            duration = (time.perf_counter() - start_time) * 1000
            r_id = rule.rule_id if rule else 0
            c_id = str(contract.pk) if contract else "UNKNOWN"
            return LineResult(
                status=status,
                allowed_amount=amount if amount else Decimal("0.00"),
                methodology=method,
                details=details,
                contract_id=c_id,
                rule_id=r_id,
                trace=trace,
                engine_version=VERSION,
                execution_time_ms=round(duration, 2),
                applied_rule_ids=applied_rule_ids if applied_rule_ids is not None else [],
                base_allowed_amount=base_allowed_amount,
            )

        resolver = StrictRuleResolver(contract, version=version, config=config)

        # Phase 1: pricing_engine_mode from version or config.version; default LEGACY. STAGED = staged path.
        pricing_engine_mode = "LEGACY"
        if version is not None:
            pricing_engine_mode = getattr(version, "pricing_engine_mode", None) or "LEGACY"
        elif config is not None and getattr(config, "version", None) is not None:
            pricing_engine_mode = getattr(config.version, "pricing_engine_mode", None) or "LEGACY"
        if isinstance(pricing_engine_mode, str):
            pricing_engine_mode = (pricing_engine_mode or "LEGACY").strip().upper() or "LEGACY"

        logger.debug(f"\n[!] ENGINE STARTING - Mode: {pricing_engine_mode} | Contract: {contract.pk if contract else 'N/A'} | Version: {version.version_id if version else 'N/A'}\n")

        if pricing_engine_mode != "STAGED":
            # Legacy path: single rule, unchanged. Do not change a single line below.
            rule = resolver.resolve(request, trace)

            if not rule:
                return build_result(PricingStatus.DENIED_NO_RULE, details="No matching rule found in contract.")

            _emit_rule_select_trace(exec_context, line_index, rule)

            # Step 12c: check ContractMethodology conditions before applying the methodology.
            # Only evaluated when config carries preloaded methodologies (no DB query).
            if config is not None and config.methodologies:
                matched_meth = next(
                    (
                        m for m in config.methodologies
                        if m.methodology_type == rule.methodology_code
                        and getattr(m, "conditions", None)
                    ),
                    None,
                )
                if matched_meth is not None:
                    line_ctx = build_line_context(request)
                    try:
                        if not evaluate_conditions(matched_meth.conditions, line_ctx):
                            trace.log("CONDITIONS", f"Methodology {rule.methodology_code} skipped: conditions not met")
                            return build_result(
                                PricingStatus.DENIED_NO_RULE,
                                details=f"Methodology {rule.methodology_code} conditions not met.",
                                rule=rule,
                            )
                    except Exception as exc:
                        trace.log("CONDITIONS", f"Methodology conditions error: {exc}")
                        return build_result(
                            PricingStatus.DENIED_CALCULATION_ERROR,
                            details=f"Methodology conditions error: {exc}",
                            rule=rule,
                        )

            try:
                context = self.loader.load_context(
                    request, rule, version=version, config=config, trace=trace,
                )
            except Exception as e:
                return build_result(
                    PricingStatus.DENIED_MISSING_DATA,
                    method=PricingStatus.DENIED_MISSING_DATA.value,
                    details=str(e),
                    rule=rule,
                )

            try:
                strategy = get_methodology(context.methodology_code)
                price = strategy.calculate(context)
                _emit_strategy_observability(exec_context, line_index, rule, context)
                if exec_context is not None and line_index is not None:
                    exec_context.trace.append(TraceEntry(
                        stage="LINE",
                        phase=rule.methodology_code or "BASE",
                        line_index=line_index,
                        rule_id=rule.rule_id,
                        methodology_code=rule.methodology_code or "",
                        message=f"allowed_amount={price}",
                    ))
                return build_result(
                    PricingStatus.SUCCESS,
                    amount=price,
                    method=rule.methodology_code,
                    rule=rule,
                )
            except Exception as e:
                if isinstance(e, NoApcFoundError):
                    return build_result(
                        PricingStatus.NO_APC_FOUND,
                        amount=Decimal("0.00"),
                        method=rule.methodology_code or "APC",
                        details="NO_APC_FOUND",
                        rule=rule,
                    )
                if isinstance(e, NoAspFoundError):
                    return build_result(
                        PricingStatus.NO_ASP_FOUND,
                        amount=Decimal("0.00"),
                        method=rule.methodology_code or "ASP",
                        details="NO_ASP_FOUND",
                        rule=rule,
                    )
                return build_result(
                    PricingStatus.DENIED_CALCULATION_ERROR,
                    method=PricingStatus.DENIED_CALCULATION_ERROR.value,
                    details=str(e),
                    rule=rule,
                )

        # STAGED path (Phase 2: BASE then ADJUSTMENT)
        state = LinePricingState(
            input=request,
            base_allowed_amount=None,
            current_allowed_amount=Decimal("0.00"),
        )
        applied_rule_ids = []
        primary_rule = None
        methodology_used = ""

        for stage in ["BASE", "ADJUSTMENT"]:
            rules = resolver.resolve_for_stage(request, trace, stage, state)
            logger.debug(f"\n--- DEBUG {stage} STAGE ---")
            logger.debug(f"Rules found by resolver: {len(rules)}")
            for r in rules:
                logger.debug(f" -> Rule ID: {r.rule_id} | Type: {r.rule_type} | Methodology: {r.methodology_code}")
            logger.debug("---------------------------\n")
            for rule in rules:
                _emit_rule_select_trace(exec_context, line_index, rule)
                try:
                    context = self.loader.load_context(
                        request, rule, version=version, config=config, trace=trace,
                    )
                except Exception as e:
                    trace.log("ORCHESTRATOR", f"STAGED load_context failed for {rule.rule_name}: {e}")
                    continue
                try:
                    strategy = get_methodology(context.methodology_code)
                    amount = strategy.calculate(context)
                    _emit_strategy_observability(exec_context, line_index, rule, context)
                except Exception as e:
                    if isinstance(e, NoApcFoundError):
                        return build_result(
                            PricingStatus.NO_APC_FOUND,
                            amount=Decimal("0.00"),
                            method=rule.methodology_code or "APC",
                            details="NO_APC_FOUND",
                            rule=rule,
                            applied_rule_ids=applied_rule_ids,
                        )
                    if isinstance(e, NoAspFoundError):
                        return build_result(
                            PricingStatus.NO_ASP_FOUND,
                            amount=Decimal("0.00"),
                            method=rule.methodology_code or "ASP",
                            details="NO_ASP_FOUND",
                            rule=rule,
                            applied_rule_ids=applied_rule_ids,
                        )
                    # Log full traceback for PCT_BILLED/PERCENT_BILLED so type/calc errors are visible
                    meth = (rule.methodology_code or "").strip().upper()
                    if meth in ("PCT_BILLED", "PERCENT_BILLED"):
                        logging.exception(
                            "PCT_BILLED/PERCENT_BILLED calculation failed: %s",
                            e,
                            exc_info=True,
                        )
                        traceback.print_exc()
                    return build_result(
                        PricingStatus.DENIED_CALCULATION_ERROR,
                        method=PricingStatus.DENIED_CALCULATION_ERROR.value,
                        details=str(e),
                        rule=rule,
                        applied_rule_ids=applied_rule_ids,
                    )
                state.current_allowed_amount = amount
                if stage == "BASE":
                    state.base_allowed_amount = amount
                applied_rule_ids.append(rule.rule_id)
                if primary_rule is None:
                    primary_rule = rule
                    methodology_used = rule.methodology_code or ""
                if exec_context is not None and line_index is not None:
                    exec_context.trace.append(TraceEntry(
                        stage="LINE",
                        phase=stage,
                        line_index=line_index,
                        rule_id=rule.rule_id,
                        methodology_code=rule.methodology_code or "",
                        message=f"allowed_amount={amount}",
                    ))

        if not applied_rule_ids:
            return build_result(
                PricingStatus.DENIED_NO_RULE,
                details="No matching rule found in contract (STAGED).",
                applied_rule_ids=[],
            )

        duration = (time.perf_counter() - start_time) * 1000
        return LineResult(
            status=PricingStatus.SUCCESS,
            allowed_amount=state.current_allowed_amount,
            methodology=methodology_used,
            details="",
            contract_id=str(contract.pk) if contract else "UNKNOWN",
            rule_id=primary_rule.rule_id if primary_rule else applied_rule_ids[0],
            trace=trace,
            engine_version=VERSION,
            execution_time_ms=round(duration, 2),
            applied_rule_ids=applied_rule_ids,
            base_allowed_amount=state.base_allowed_amount,
        )


class ClaimOrchestrator:
    """
    Canonical claim pricing execution order: contract resolution, version resolution,
    line pricing (via LineOrchestrator), stop-loss, outlier. Single orchestration path.
    """

    def __init__(self):
        self.line_orchestrator = LineOrchestrator()

    def run(
        self,
        claim_input: ClaimPricingInput,
        config: Optional[ContractPricingConfig] = None,
    ) -> ClaimPricingResult:
        # N+1 ELIMINATED: reset reference data cache once per claim so all lines share it.
        self.line_orchestrator.loader.reset_execution_cache()

        contract = claim_input.contract
        if contract is None and claim_input.contract_id is not None:
            from core.models import ProviderContract
            contract = ProviderContract.objects.get(pk=claim_input.contract_id)
        if contract is None:
            raise ValueError("ClaimPricingInput must have contract or contract_id set.")
        # Normalize dates from payload (may be ISO strings) so claim-level rules compare date-to-date
        service_date = _safe_date(claim_input.service_date)
        if config is not None and getattr(config, "version", None) is not None:
            version = config.version
        else:
            version = resolve_active_contract_version(contract, service_date)
        if config is None:
            config = build_contract_pricing_config_from_db(contract, version, service_date)
        pricing_date = _safe_date(claim_input.pricing_date) if getattr(claim_input, 'pricing_date', None) else service_date
        claim_type = claim_input.claim_type
        contract_effective_date = getattr(contract, 'effective_start_date', None)

        # Phase A: single ExecutionContext per claim (unified trace). Phase E: drg_code for claim-level DRG.
        exec_context = ExecutionContext(
            claim_id=claim_input.claim_id,
            contract=contract,
            version=version,
            provider_id=getattr(claim_input, 'provider_id', None),
            facility_id=getattr(claim_input, 'facility_id', None),
            service_date=service_date,
            claim_type=claim_type,
            pricing_date=pricing_date,
            line_states=[],
            claim_total=Decimal("0.00"),
            trace=[],
            drg_code=getattr(claim_input, 'drg_code', None),
        )

        # Step 7: build O(1) carve-out lookup keyed by code_value.
        # Populated once per claim from config (no per-line DB query).
        carveout_by_code: dict = {}
        for co in config.carveouts:
            carveout_by_code[co.code_value] = co

        # --- Steps 4 + 5: Base methodology → carve-out override (per line) ---
        line_results = []
        total_allowed = Decimal("0.00")
        for line_index, line in enumerate(claim_input.lines):
            modifiers = line.modifiers if isinstance(line.modifiers, list) else []
            line_revenue_code = getattr(line, 'revenue_code', None)
            logger.debug(f"[ORCH] line[{line_index}] ClaimLineInput.revenue_code={line_revenue_code!r} -> PricingInput.revenue_code={line_revenue_code!r}")
            inp = PricingInput(
                procedure_code=line.procedure_code,
                billed_amount=line.billed_amount,
                units=line.units,
                modifiers=modifiers,
                service_date=service_date,
                claim_type=claim_type,
                pricing_date=pricing_date,
                contract_effective_date=contract_effective_date,
                revenue_code=line_revenue_code,
                product_id=getattr(claim_input, 'product_id', None) or None,
                network_id=getattr(claim_input, 'network_id', None) or None,
                provider_id=getattr(claim_input, 'provider_id', None),
            )
            # Step 4: base methodology pricing (pass context for unified trace)
            result = self.line_orchestrator.run(
                contract, inp, version=version, config=config,
                context=exec_context, line_index=line_index,
            )
            # Step 5: apply line-level carve-out (canonical order step 5)
            result, carveout_traces = _apply_carveout(
                result, inp, carveout_by_code, line_index=line_index,
            )
            for te in carveout_traces:
                exec_context.trace.append(te)
            # Phase G: line-level cap/floor (LINE_CAP_FLOOR stage) — after ADJUSTMENT/carve-out
            line_cap_floors = getattr(config, 'line_cap_floors', None) or ()
            if line_cap_floors:
                result, line_cap_traces = _apply_line_cap_floor(
                    result, inp, line_cap_floors, service_date, line_index=line_index
                )
                for te in line_cap_traces:
                    exec_context.trace.append(te)

            # Phase A: append line state and one trace entry per line
            exec_context.line_states.append(LineState(
                input=inp,
                base_allowed_amount=(
                    result.base_allowed_amount
                    if result.base_allowed_amount is not None
                    else result.allowed_amount
                ),
                current_allowed_amount=result.allowed_amount,
            ))
            exec_context.trace.append(TraceEntry(
                stage="LINE",
                phase=result.methodology or "BASE",
                line_index=line_index,
                rule_id=result.rule_id or None,
                methodology_code=result.methodology or "",
                message=f"procedure_code={inp.procedure_code} allowed_amount={result.allowed_amount} status={result.status.value if hasattr(result.status, 'value') else result.status}",
            ))

            line_results.append(result)
            # Include priced lines in claim total; excluded lines contribute $0.
            # Line-level cap/floor (lesser-of billed) sets CAP_APPLIED / FLOOR_APPLIED
            # but still has a valid allowed_amount that must roll up.
            if result.status in (
                PricingStatus.SUCCESS,
                PricingStatus.CARVEOUT_REPRICED,
                PricingStatus.CARVEOUT_EXCLUDED,
                PricingStatus.CAP_APPLIED,
                PricingStatus.FLOOR_APPLIED,
            ):
                total_allowed += result.allowed_amount

        original_total_allowed = total_allowed
        final_total_allowed = total_allowed
        claim_trace = []
        result_status = PricingStatus.SUCCESS
        applied_stop_loss_rule_id = None
        applied_outlier_rule_id = None

        # Phase E: set context.claim_total from line sum; run CLAIM_METHOD (DRG, then stop-loss, then outlier).
        exec_context.claim_total = total_allowed
        # Debug: claim-level DRG (version.claim_level_drg_enabled is independent of LEGACY vs STAGED line mode)
        _version_id = getattr(version, 'version_id', getattr(version, 'pk', None))
        _claim_drg_enabled = bool(getattr(version, 'claim_level_drg_enabled', False))
        logger.debug(
            f"[CLAIM_METHOD] version_id={_version_id} claim_level_drg_enabled={_claim_drg_enabled} "
            f"(raw={getattr(version, 'claim_level_drg_enabled', 'MISSING')!r})"
        )
        if _claim_drg_enabled:
            drg_plugin = CLAIM_METHODOLOGY_REGISTRY.get("DRG")
            logger.debug(f"[CLAIM_METHOD] DRG plugin present={drg_plugin is not None}, invoking run()")
            if drg_plugin:
                drg_plugin.run(exec_context, config)
                logger.debug(f"[CLAIM_METHOD] after DRG plugin: drg_applied={exec_context.drg_applied} claim_total={exec_context.claim_total}")
                if exec_context.drg_applied:
                    final_total_allowed = exec_context.claim_total
                    total_allowed = exec_context.claim_total
                    claim_trace.append(
                        f"CLAIM_DRG_APPLIED drg_code={getattr(exec_context, 'drg_code', '')} "
                        f"claim_total={exec_context.claim_total}"
                    )
                    exec_context.trace.append(TraceEntry(
                        stage="CLAIM", phase="CLAIM_METHOD", methodology_code="DRG",
                        message=f"drg_code={exec_context.drg_code} claim_total={exec_context.claim_total}",
                    ))

        # --- Step 7 (claim-level): stop-loss (cost-based) ---
        total_cost = sum(
            Decimal(str(line.cost_amount or 0)) for line in claim_input.lines
        )
        for rule in config.stop_loss_rules:
            if total_cost <= rule.cost_threshold:
                exec_context.trace.append(TraceEntry(
                    stage="CLAIM", phase="STOP_LOSS", rule_id=rule.id,
                    message=(
                        f"total_cost={total_cost} threshold={rule.cost_threshold} "
                        f"→ NOT APPLIED (cost ≤ threshold)"
                    ),
                ))
                continue
            excess_cost = total_cost - rule.cost_threshold
            stoploss_payment = rule.cost_threshold + (
                excess_cost * (rule.reimbursement_percentage / Decimal('100'))
            )
            final_total_allowed = stoploss_payment
            total_allowed = stoploss_payment
            applied_stop_loss_rule_id = rule.id
            result_status = PricingStatus.STOP_LOSS_APPLIED
            claim_trace.append(
                f"STOP_LOSS_APPLIED rule_id={rule.id} cost_threshold={rule.cost_threshold} "
                f"total_cost={total_cost} stoploss_payment={stoploss_payment}"
            )
            exec_context.trace.append(TraceEntry(
                stage="CLAIM", phase="STOP_LOSS", rule_id=rule.id,
                message=f"total_cost={total_cost} stoploss_payment={stoploss_payment}",
            ))
            break

        # --- Step 8 (claim-level): outlier (charge-based) ---
        total_billed = sum(Decimal(str(line.billed_amount)) for line in claim_input.lines)
        for rule in config.outlier_rules:
            if rule.threshold_scope == 'PER_CLAIM':
                if total_billed <= rule.threshold_amount:
                    exec_context.trace.append(TraceEntry(
                        stage="CLAIM", phase="OUTLIER", rule_id=rule.id,
                        message=(
                            f"total_billed={total_billed} threshold={rule.threshold_amount} "
                            f"→ NOT APPLIED (billed ≤ threshold)"
                        ),
                    ))
                    continue
                if rule.reimbursement_percentage is not None:
                    outlier_payment = total_billed * (rule.reimbursement_percentage / Decimal('100'))
                else:
                    outlier_payment = total_billed * rule.cost_to_charge_ratio
                total_allowed = outlier_payment
                final_total_allowed = outlier_payment
                applied_outlier_rule_id = rule.id
                claim_trace.append(
                    f"OUTLIER_APPLIED rule_id={rule.id} threshold={rule.threshold_amount} "
                    f"total_billed={total_billed} outlier_payment={outlier_payment}"
                )
                exec_context.trace.append(TraceEntry(
                    stage="CLAIM", phase="OUTLIER", rule_id=rule.id,
                    message=f"total_billed={total_billed} outlier_payment={outlier_payment}",
                ))
                result_status = PricingStatus.OUTLIER_APPLIED
                break
            elif rule.threshold_scope == 'PER_LINE':
                raise NotImplementedError("PER_LINE outlier scope is not implemented.")

        # --- Phase F: Cross-line MPPR — after CLAIM_METHOD (DRG/stop-loss/outlier), before blending ---
        _run_cross_line_phase(exec_context, config)
        mppr_defs = getattr(config, "mppr_definitions", None)
        if mppr_defs and len(mppr_defs) > 0:
            total_allowed = exec_context.claim_total
            final_total_allowed = exec_context.claim_total
            for i in range(len(line_results)):
                if i < len(exec_context.line_states):
                    old_line_allowed = line_results[i].allowed_amount
                    line_results[i].allowed_amount = exec_context.line_states[i].current_allowed_amount
                    logger.debug(
                        f"[CROSS_LINE] sync line_results[{i}].allowed_amount: {old_line_allowed} -> {line_results[i].allowed_amount} "
                        f"(from line_states[{i}].current_allowed_amount={exec_context.line_states[i].current_allowed_amount})"
                    )
            logger.debug(f"[CROSS_LINE] sync done: total_allowed=final_total_allowed={total_allowed}")

        # --- Step 9: Blending — additive or override, after stop-loss/outlier ---
        blended_total_allowed = final_total_allowed
        applied_blending_rule_ids: list = []
        if config.blending_rules:
            blended_total_allowed, applied_blending_rule_ids, blend_status, blend_traces, blend_exec_traces = (
                _apply_blending(
                    final_total_allowed,
                    total_billed,
                    line_results,
                    list(claim_input.lines),
                    config.blending_rules,
                    service_date,
                    claim_type=claim_type or "",
                )
            )
            if blend_traces:
                claim_trace.extend(blend_traces)
            for te in blend_exec_traces:
                exec_context.trace.append(te)
            if applied_blending_rule_ids:
                final_total_allowed = blended_total_allowed
                total_allowed = blended_total_allowed
                if blend_status is not None:
                    result_status = blend_status
        else:
            blended_total_allowed = final_total_allowed

        # --- Step 10: Caps/floors — final clamp (canonical step 10) ---
        pre_cap_total_allowed = final_total_allowed
        applied_cap_floor_id = None
        final_total_allowed, applied_cap_floor_id, cap_floor_status, cap_floor_trace, cap_floor_exec_traces = (
            _apply_cap_floor(
                final_total_allowed,
                total_billed,
                config.cap_floors,
                service_date,
                line_results,
                claim_type=claim_type or "",
            )
        )
        if cap_floor_trace:
            claim_trace.extend(cap_floor_trace)
        for te in cap_floor_exec_traces:
            exec_context.trace.append(te)
        if cap_floor_status is not None:
            result_status = cap_floor_status
        total_allowed = final_total_allowed

        exec_context.claim_total = total_allowed
        claim_id = claim_input.claim_id if claim_input.claim_id is not None else 0
        execution_trace_serialized = [e.to_dict() for e in exec_context.trace]
        return ClaimPricingResult(
            claim_id=claim_id,
            contract_id=str(contract.pk),
            lines=line_results,
            total_allowed=total_allowed,
            line_count=len(line_results),
            status=result_status,
            claim_trace=claim_trace,
            original_total_allowed=original_total_allowed,
            final_total_allowed=final_total_allowed,
            applied_outlier_rule_id=applied_outlier_rule_id,
            applied_stop_loss_rule_id=applied_stop_loss_rule_id,
            pre_cap_total_allowed=pre_cap_total_allowed,
            applied_cap_floor_id=applied_cap_floor_id,
            blended_total_allowed=blended_total_allowed,
            applied_blending_rule_ids=applied_blending_rule_ids,
            execution_trace=execution_trace_serialized,
        )


def _apply_carveout(
    result: LineResult,
    inp: PricingInput,
    carveout_by_code: dict,
    line_index: int = 0,
) -> tuple:
    """
    Step 7: Apply a line-level carve-out after base methodology pricing.
    Canonical execution order step 5: after base methodology (step 4), before rule adjustments (step 6).

    carveout_methodology values:
      EXCLUDE    → zero allowed; status = CARVEOUT_EXCLUDED
      PCT_BILLED → allowed = billed * pct / 100; status = CARVEOUT_REPRICED
      FIXED_RATE → allowed = carveout_rate; status = CARVEOUT_REPRICED

    Preserves base_allowed_amount in result for auditability.
    No DB queries — operates entirely on the preloaded carveout_by_code dict.

    Returns: (result, trace_entries)
    """
    carveout = carveout_by_code.get(inp.procedure_code)
    if carveout is None:
        traces = []
        if carveout_by_code:
            traces.append(TraceEntry(
                stage="LINE",
                phase="CARVEOUT",
                line_index=line_index,
                message=(
                    f"procedure_code={inp.procedure_code} not in carve-out set "
                    f"→ NOT APPLIED"
                ),
            ))
        return result, traces

    # Step 12c: evaluate optional structured conditions before applying carve-out.
    carveout_conditions = getattr(carveout, "conditions", None)
    if carveout_conditions:
        line_ctx = build_line_context(inp)
        try:
            if not evaluate_conditions(carveout_conditions, line_ctx):
                return result, [TraceEntry(
                    stage="LINE",
                    phase="CARVEOUT",
                    line_index=line_index,
                    message=(
                        f"carveout_id={carveout.carveout_id} code={inp.procedure_code} "
                        f"conditions not met → NOT APPLIED"
                    ),
                )]
        except Exception:
            return result, [TraceEntry(
                stage="LINE",
                phase="CARVEOUT",
                line_index=line_index,
                message=(
                    f"carveout_id={carveout.carveout_id} code={inp.procedure_code} "
                    f"conditions error → NOT APPLIED"
                ),
            )]

    methodology = (carveout.carveout_methodology or '').upper()
    base_amount = result.allowed_amount
    result.base_allowed_amount = base_amount
    result.carveout_applied = True
    result.carveout_id = carveout.carveout_id

    if methodology == 'EXCLUDE':
        result.allowed_amount = Decimal('0.00')
        result.status = PricingStatus.CARVEOUT_EXCLUDED
        result.details = (
            f"CARVEOUT_EXCLUDED carveout_id={carveout.carveout_id} "
            f"code={inp.procedure_code} base_allowed={base_amount}"
        )
    elif methodology == 'PCT_BILLED':
        pct = carveout.carveout_percentage or Decimal('0')
        new_amount = (inp.billed_amount * pct / Decimal('100')).quantize(Decimal('0.01'))
        result.allowed_amount = new_amount
        result.status = PricingStatus.CARVEOUT_REPRICED
        result.methodology = 'PCT_BILLED_CARVEOUT'
        result.details = (
            f"CARVEOUT_REPRICED carveout_id={carveout.carveout_id} "
            f"code={inp.procedure_code} pct={pct} "
            f"base_allowed={base_amount} new_allowed={new_amount}"
        )
    elif methodology == 'FIXED_RATE':
        rate = carveout.carveout_rate or Decimal('0')
        result.allowed_amount = rate
        result.status = PricingStatus.CARVEOUT_REPRICED
        result.methodology = 'FIXED_RATE_CARVEOUT'
        result.details = (
            f"CARVEOUT_REPRICED carveout_id={carveout.carveout_id} "
            f"code={inp.procedure_code} fixed_rate={rate} "
            f"base_allowed={base_amount}"
        )
    trace = TraceEntry(
        stage="LINE",
        phase="CARVEOUT",
        line_index=line_index,
        message=result.details or f"carveout_id={carveout.carveout_id} methodology={methodology}",
    )
    return result, [trace]


def _apply_line_cap_floor(
    result: LineResult,
    inp: PricingInput,
    line_cap_floors: tuple,
    service_date,
    line_index: int = 0,
) -> tuple:
    """
    Phase G: Apply line-level caps/floors after ADJUSTMENT/carve-out (LINE_CAP_FLOOR stage).
    First matching rule wins. Mutates result.allowed_amount and optionally result.status.
    code_value: when set, restrict to line procedure_code (exact match).

    Returns: (result, trace_entries: list of TraceEntry)
    """
    if not line_cap_floors:
        return result, []
    traces = []
    amount = result.allowed_amount
    line_billed = getattr(inp, 'billed_amount', None) or Decimal('0')

    for cf in line_cap_floors:
        if not _line_cap_floor_eligible(cf, inp, service_date):
            continue
        cap_type = (getattr(cf, 'cap_type', None) or '').upper()
        cf_id = getattr(cf, 'cap_floor_id', None)
        if cap_type == 'CAP':
            cap_val = getattr(cf, 'value', None)
            if cap_val is not None and amount > cap_val:
                result.allowed_amount = cap_val
                result.status = PricingStatus.CAP_APPLIED
                result.applied_line_cap_floor_id = cf_id
                traces.append(TraceEntry(
                    stage="LINE", phase="LINE_CAP_FLOOR", line_index=line_index,
                    rule_id=cf_id,
                    message=f"procedure_code={inp.procedure_code} LINE_CAP cap={cap_val} pre={amount} post={cap_val}",
                ))
                return result, traces
            if cap_val is not None:
                traces.append(TraceEntry(
                    stage="LINE", phase="LINE_CAP_FLOOR", line_index=line_index,
                    rule_id=cf_id,
                    message=(
                        f"cap_floor_id={cf_id} type=CAP cap={cap_val} current={amount} "
                        f"→ NOT APPLIED (current ≤ cap)"
                    ),
                ))
        elif cap_type == 'FLOOR':
            floor_val = getattr(cf, 'value', None)
            if floor_val is not None and amount < floor_val:
                result.allowed_amount = floor_val
                result.status = PricingStatus.FLOOR_APPLIED
                result.applied_line_cap_floor_id = cf_id
                traces.append(TraceEntry(
                    stage="LINE", phase="LINE_CAP_FLOOR", line_index=line_index,
                    rule_id=cf_id,
                    message=f"procedure_code={inp.procedure_code} LINE_FLOOR floor={floor_val} pre={amount} post={floor_val}",
                ))
                return result, traces
            if floor_val is not None:
                traces.append(TraceEntry(
                    stage="LINE", phase="LINE_CAP_FLOOR", line_index=line_index,
                    rule_id=cf_id,
                    message=(
                        f"cap_floor_id={cf_id} type=FLOOR floor={floor_val} current={amount} "
                        f"→ NOT APPLIED (current ≥ floor)"
                    ),
                ))
        elif cap_type == 'PCT_BILLED_CAP':
            pct = getattr(cf, 'percentage', None)
            if pct is not None:
                cap_val = (line_billed * pct / Decimal('100')).quantize(Decimal('0.01'))
                type_label = _pct_billed_cap_label(cf)
                if amount > cap_val:
                    result.allowed_amount = cap_val
                    result.status = PricingStatus.CAP_APPLIED
                    result.applied_line_cap_floor_id = cf_id
                    traces.append(TraceEntry(
                        stage="LINE", phase="LINE_CAP_FLOOR", line_index=line_index,
                        rule_id=cf_id,
                        message=(
                            f"procedure_code={inp.procedure_code} LINE_{type_label} "
                            f"cap={cap_val} pre={amount} post={cap_val}"
                        ),
                    ))
                    return result, traces
                traces.append(TraceEntry(
                    stage="LINE", phase="LINE_CAP_FLOOR", line_index=line_index,
                    rule_id=cf_id,
                    message=(
                        f"cap_floor_id={cf_id} type={type_label} ceiling={cap_val} "
                        f"current={amount} → NOT APPLIED (current ≤ ceiling)"
                    ),
                ))
    return result, traces


def _apply_cap_floor(
    final_total: Decimal,
    total_billed: Decimal,
    cap_floors: tuple,
    service_date,
    line_results: list,
    claim_type: str = "",
) -> tuple:
    """
    Step 8: Apply caps/floors as the final clamp (canonical execution order step 10).
    Iterates cap_floors in priority order (highest priority first, already sorted by config).
    First matching rule wins; returns updated total + audit info.

    Returns: (clamped_total, applied_id, status_or_None, claim_trace_strings, exec_trace_entries)
    """
    applied_id = None
    status = None
    traces = []
    exec_traces = []

    line_methodologies = {(r.methodology or '').upper() for r in line_results}

    for cf in cap_floors:
        if not _claim_cap_floor_eligible(
            cf, service_date, final_total, total_billed,
            line_methodologies, line_results, claim_type,
        ):
            continue

        scope = (cf.scope or 'CLAIM').upper()
        cap_type = (cf.cap_type or '').upper()
        cf_id = cf.cap_floor_id

        if cap_type == 'CAP':
            cap_val = cf.value
            if cap_val is not None and final_total > cap_val:
                msg = (
                    f"CAP_APPLIED cap_floor_id={cf_id} scope={scope} "
                    f"cap={cap_val} pre_cap={final_total} post_cap={cap_val}"
                )
                traces.append(msg)
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="CAP_FLOOR", rule_id=cf_id, message=msg,
                ))
                final_total = cap_val
                applied_id = cf_id
                status = PricingStatus.CAP_APPLIED
                break
            if cap_val is not None:
                msg = (
                    f"cap_floor_id={cf_id} type=CAP scope={scope} cap={cap_val} "
                    f"current={final_total} → NOT APPLIED (current ≤ cap)"
                )
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="CAP_FLOOR", rule_id=cf_id, message=msg,
                ))

        elif cap_type == 'FLOOR':
            floor_val = cf.value
            if floor_val is not None and final_total < floor_val:
                msg = (
                    f"FLOOR_APPLIED cap_floor_id={cf_id} scope={scope} "
                    f"floor={floor_val} pre_floor={final_total} post_floor={floor_val}"
                )
                traces.append(msg)
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="CAP_FLOOR", rule_id=cf_id, message=msg,
                ))
                final_total = floor_val
                applied_id = cf_id
                status = PricingStatus.FLOOR_APPLIED
                break
            if floor_val is not None:
                msg = (
                    f"cap_floor_id={cf_id} type=FLOOR scope={scope} floor={floor_val} "
                    f"current={final_total} → NOT APPLIED (current ≥ floor)"
                )
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="CAP_FLOOR", rule_id=cf_id, message=msg,
                ))

        elif cap_type == 'PCT_BILLED_CAP':
            pct = cf.percentage
            if pct is not None:
                cap_val = (total_billed * pct / Decimal('100')).quantize(Decimal('0.01'))
                type_label = _pct_billed_cap_label(cf)
                if final_total > cap_val:
                    msg = (
                        f"CAP_APPLIED(PCT_BILLED) cap_floor_id={cf_id} scope={scope} "
                        f"{type_label} billed_cap={cap_val} pre_cap={final_total} post_cap={cap_val}"
                    )
                    traces.append(msg)
                    exec_traces.append(TraceEntry(
                        stage="CLAIM", phase="CAP_FLOOR", rule_id=cf_id, message=msg,
                    ))
                    final_total = cap_val
                    applied_id = cf_id
                    status = PricingStatus.CAP_APPLIED
                    break
                msg = (
                    f"cap_floor_id={cf_id} type={type_label} scope={scope} "
                    f"ceiling={cap_val} current={final_total} "
                    f"→ NOT APPLIED (current ≤ ceiling)"
                )
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="CAP_FLOOR", rule_id=cf_id, message=msg,
                ))

    return final_total, applied_id, status, traces, exec_traces


def _apply_blending(
    post_outlier_total: Decimal,
    total_billed: Decimal,
    line_results: list,
    line_inputs: list,
    blending_rules: tuple,
    service_date,
    claim_type: str = "",
) -> tuple:
    """
    Step 9: Apply multi-methodology blending after stop-loss/outlier, before caps/floors.

    blend_type values:
      ADD      → (CLAIM) blended = post_outlier_total + total_billed * pct / 100
                 (LINE)  line.blended_allowed_amount = line.allowed_amount + line_billed * pct / 100
      OVERRIDE → (CLAIM) blended = total_billed * pct / 100
                 (LINE)  line.blended_allowed_amount = line_billed * pct / 100

    scope values:
      CLAIM → rule modifies the post-outlier claim total directly
      LINE  → rule modifies individual lines; sum of blended_allowed_amount becomes new total

    primary_methodology filter:
      '' (empty) → applies to all lines (LINE scope) or always (CLAIM scope)
      non-empty  → LINE scope only: restrict to lines where line.methodology == primary_methodology

    Excluded lines (CARVEOUT_EXCLUDED) are never blended; they remain at $0.

    Returns: (blended_total, applied_rule_ids, status_or_None, claim_trace_strings, exec_trace_entries)
    No DB queries — operates entirely on preloaded blending_rules.
    """
    applied_ids: list = []
    traces: list = []
    exec_traces: list = []
    blended_total = post_outlier_total

    claim_rule_applied = False

    for rule in blending_rules:
        start = getattr(rule, 'effective_start_date', None)
        if start is not None and start > service_date:
            continue
        end = getattr(rule, 'effective_end_date', None)
        if end is not None and end < service_date:
            continue

        blend_conditions = getattr(rule, "conditions", None)
        if blend_conditions:
            claim_ctx = build_claim_context(total_billed, blended_total, claim_type=claim_type)
            try:
                if not evaluate_conditions(blend_conditions, claim_ctx):
                    continue
            except Exception:
                continue

        scope = (rule.scope or 'CLAIM').upper()
        blend_type = (rule.blend_type or '').upper()
        pct = rule.blend_percentage or Decimal('0')
        rule_id = rule.blending_rule_id

        if scope == 'CLAIM':
            if claim_rule_applied:
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id,
                    message=f"rule_id={rule_id} scope=CLAIM → NOT APPLIED (claim rule already applied)",
                ))
                continue
            if blend_type == 'ADD':
                addend = (total_billed * pct / Decimal('100')).quantize(Decimal('0.01'))
                blended_total = (post_outlier_total + addend).quantize(Decimal('0.01'))
                msg = (
                    f"BLENDING_APPLIED(ADD) rule_id={rule_id} "
                    f"base={post_outlier_total} addend={addend} blended={blended_total}"
                )
                traces.append(msg)
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id, message=msg,
                ))
            elif blend_type == 'OVERRIDE':
                blended_total = (total_billed * pct / Decimal('100')).quantize(Decimal('0.01'))
                msg = (
                    f"BLENDING_APPLIED(OVERRIDE) rule_id={rule_id} "
                    f"base={post_outlier_total} blended={blended_total}"
                )
                traces.append(msg)
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id, message=msg,
                ))
            else:
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id,
                    message=(
                        f"rule_id={rule_id} scope=CLAIM blend_type={blend_type or 'MISSING'} "
                        f"→ NOT APPLIED (unsupported blend_type)"
                    ),
                ))
                continue
            applied_ids.append(rule_id)
            claim_rule_applied = True

        elif scope == 'LINE':
            primary = (rule.primary_methodology or '').upper()
            if blend_type not in ('ADD', 'OVERRIDE'):
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id,
                    message=(
                        f"rule_id={rule_id} scope=LINE blend_type={blend_type or 'MISSING'} "
                        f"→ NOT APPLIED (unsupported blend_type)"
                    ),
                ))
                continue
            any_line_matched = False
            for lr, li in zip(line_results, line_inputs):
                if lr.status == PricingStatus.CARVEOUT_EXCLUDED:
                    continue
                if primary and (lr.methodology or '').upper() != primary:
                    continue
                if lr.blending_rule_id is not None:
                    continue
                line_billed = getattr(li, 'billed_amount', Decimal('0')) or Decimal('0')
                if blend_type == 'ADD':
                    addend = (line_billed * pct / Decimal('100')).quantize(Decimal('0.01'))
                    lr.blended_allowed_amount = (lr.allowed_amount + addend).quantize(Decimal('0.01'))
                else:
                    lr.blended_allowed_amount = (line_billed * pct / Decimal('100')).quantize(Decimal('0.01'))
                lr.blending_rule_id = rule_id
                any_line_matched = True

            if any_line_matched:
                new_total = Decimal('0.00')
                for lr in line_results:
                    if lr.blended_allowed_amount is not None:
                        new_total += lr.blended_allowed_amount
                    elif lr.status != PricingStatus.CARVEOUT_EXCLUDED:
                        new_total += lr.allowed_amount
                blended_total = new_total.quantize(Decimal('0.01'))
                applied_ids.append(rule_id)
                msg = (
                    f"BLENDING_APPLIED(LINE/{blend_type}) rule_id={rule_id} "
                    f"primary={primary or 'ALL'} blended_total={blended_total}"
                )
                traces.append(msg)
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id, message=msg,
                ))
            else:
                exec_traces.append(TraceEntry(
                    stage="CLAIM", phase="BLENDING", rule_id=rule_id,
                    message=(
                        f"rule_id={rule_id} scope=LINE primary={primary or 'ALL'} "
                        f"→ NOT APPLIED (no matching lines)"
                    ),
                ))

    status = PricingStatus.BLENDING_APPLIED if applied_ids else None
    return blended_total, applied_ids, status, traces, exec_traces


def _claim_header_to_pricing_input(claim_header: ClaimHeader) -> ClaimPricingInput:
    """Build ClaimPricingInput from stored ClaimHeader."""
    from .config import ClaimLineInput
    contract = getattr(claim_header, 'contract', None)
    contract_id = getattr(claim_header, 'contract_id', None)
    if contract is None and contract_id is not None:
        from core.models import ProviderContract
        try:
            contract = ProviderContract.objects.get(pk=contract_id)
        except ProviderContract.DoesNotExist:
            contract = None
    service_date = claim_header.service_date
    lines = []
    for line in claim_header.lines.all().order_by('sequence', 'line_id'):
        modifiers = line.modifiers if isinstance(line.modifiers, list) else []
        cost = getattr(line, 'cost_amount', None) or Decimal('0')
        lines.append(ClaimLineInput(
            procedure_code=line.procedure_code,
            billed_amount=line.billed_amount,
            units=line.units,
            modifiers=modifiers,
            cost_amount=cost,
        ))
    return ClaimPricingInput(
        contract_id=contract_id,
        contract=contract,
        service_date=service_date,
        claim_type=claim_header.claim_type or None,
        pricing_date=claim_header.pricing_date or service_date,
        claim_id=claim_header.claim_id,
        lines=lines,
    )


class PricingEngine:
    """
    Backward-compatibility facade. All new code should use ClaimPricingService.
    calculate_claim() and calculate_line() delegate to ClaimOrchestrator and LineOrchestrator.
    """

    VERSION = VERSION

    def __init__(self):
        self.loader = PricingDataLoader()
        self._line_orchestrator = LineOrchestrator()
        self._claim_orchestrator = ClaimOrchestrator()

    def calculate_line(
        self,
        contract: ProviderContract,
        request: PricingInput,
        version=None,
    ) -> LineResult:
        return self._line_orchestrator.run(contract, request, version=version, config=None)

    def calculate_claim(self, claim_header: ClaimHeader) -> ClaimPricingResult:
        claim_input = _claim_header_to_pricing_input(claim_header)
        if claim_input.contract is None:
            contract = resolve_contract_for_claim(claim_header)
            claim_input.contract = contract
            claim_input.contract_id = contract.pk
        return self._claim_orchestrator.run(claim_input, config=None)
