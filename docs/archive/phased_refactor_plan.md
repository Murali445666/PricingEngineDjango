# Phased Refactor Plan — Enterprise Pricing Engine

> **Canonical roadmap & status:** [ROADMAP.md](../ROADMAP.md) · [STATUS.md](../STATUS.md)  
> This document is the **A–G refactor slice plan** (implementation detail). It does not replace the master roadmap.

Aligned with target architecture in [enterprise_pricing_engine_multi-phase_execution_plan](c:\Users\Murali\.cursor\plans\enterprise_pricing_engine_multi-phase_execution_plan_4f962666.plan.md).  
Refactor in vertical slices; system must run after every phase; backward compatibility preserved.

**Target invariants (do not redesign):**
1. Rules route. Reference tables price.
2. Single ExecutionContext per claim.
3. Deterministic stages: LINE (BASE → ADJUSTMENT → LINE_CAP_FLOOR) then CLAIM (CLAIM_METHOD → CROSS_LINE → BLENDING → CLAIM_CAP_FLOOR).
4. Line, claim, and cross-line methodologies are plugin-based.
5. All pricing variables in effective-dated reference tables, not in routing rules.

---

## Phase A — ExecutionContext + Unified Trace

**Objective:** Introduce a single ExecutionContext per claim and a unified trace model. No change to pricing behavior or to where pricing variables are read from. System remains fully backward compatible.

### Model changes
- **New (optional for Phase A):** None. ExecutionContext is an in-memory dataclass only; no new DB tables required in A.
- **Modified:** None. Do not add or remove columns on PricingRule, ContractMethodology, or any existing table.
- **Deprecated:** None.

### Loader changes
- **Do not change** where the loader reads multiplier, flat_rate, or conversion_factor (continue reading from rule and methodology).
- **Optional:** Loader may accept an optional `trace: ExecutionTrace` and append one entry when it populates context (e.g. “context_loaded”, rule_id, methodology_code). If not passed, loader behaves exactly as today.

### Orchestrator changes
- **ClaimOrchestrator.run():**
  - At the start, build one **ExecutionContext** (see structure below). Populate: claim_id (from claim_input), contract, version, service_date, claim_type, pricing_date, provider_id (from claim or contract, optional), facility_id (optional), line_states = [], claim_total = 0, trace = [].
  - For each claim line: build PricingInput as today; call LineOrchestrator.run() as today. After each line result, append a **LineState** to context.line_states (input=that line’s PricingInput, base_allowed_amount=result.base_allowed_amount, current_allowed_amount=result.allowed_amount). Append to context.trace one entry per line (e.g. stage=LINE, line_index=i, rule_id, methodology_code, allowed_amount).
  - Pass the same context (or a reference) into the existing stop-loss, outlier, blending, cap/floor steps; append one trace entry per step (e.g. stage=CLAIM, phase=STOP_LOSS, claim_total_after=…).
  - Build ClaimPricingResult as today; add optional field **execution_trace** = context.trace (or serialize context.trace to a list of dicts). Existing claim_trace list can remain for backward compatibility (e.g. keep populating it from current logic while also setting execution_trace).
- **LineOrchestrator.run():** Signature may gain optional `context: Optional[ExecutionContext] = None` and optional `line_index: Optional[int] = None`. If context is provided, append to context.trace when a rule matches and when strategy returns. Do not change resolution or calculation logic.
- **Do not change:** Stage order (BASE → ADJUSTMENT per line; then carve-out; then stop-loss; outlier; blending; cap/floor). Do not introduce claim-level or cross-line phases yet.

**ExecutionContext structure (e.g. in `core/engine/types.py`):**
```python
@dataclass
class LineState:
    input: PricingInput  # or a slim copy
    base_allowed_amount: Optional[Decimal] = None
    current_allowed_amount: Decimal = Decimal("0")

@dataclass
class TraceEntry:
    stage: str       # "LINE" | "CLAIM"
    phase: str       # "BASE" | "ADJUSTMENT" | "STOP_LOSS" | "OUTLIER" | "BLENDING" | "CAP_FLOOR"
    line_index: Optional[int] = None
    rule_id: Optional[int] = None
    methodology_code: str = ""
    message: str = ""
    # optional: reference_keys_used, input_value, output_value

@dataclass
class ExecutionContext:
    claim_id: Optional[int] = None
    contract: Any = None
    version: Any = None
    provider_id: Optional[int] = None
    facility_id: Optional[int] = None
    service_date: Optional[date] = None
    claim_type: Optional[str] = None
    pricing_date: Optional[date] = None
    line_states: List[LineState] = field(default_factory=list)
    claim_total: Decimal = Decimal("0")
    trace: List[TraceEntry] = field(default_factory=list)
```

### Migration strategy
- No DB migrations. Code-only change: add ExecutionContext, LineState, TraceEntry; refactor ClaimOrchestrator to build context and pass it through; keep existing LineResult and ClaimPricingResult shape; add execution_trace to result as optional.
- Data backfill: None.

### Rollback safety
- Revert commit; no schema or data changes to undo. Existing callers that ignore execution_trace keep working.

### Risk level
**Low.** Additive only; behavior and outputs unchanged except for optional execution_trace on the result.

### What NOT to change in Phase A
- Do not add ContractTerm, CodeGroup, or any new reference tables.
- Do not change PricingRule or PricingRuleCondition.
- Do not change the resolver’s condition logic.
- Do not remove or repurpose claim_trace.
- Do not change loader’s source of multiplier/flat_rate/conversion_factor.

---

## Phase B — Introduce ContractTerm (Move Multipliers Off PricingRule)

**Objective:** Add ContractTerm as the reference table for contract/version-scoped multipliers. PricingRule gets an optional FK to ContractTerm. Loader uses ContractTerm.multiplier when rule.contract_term_id is set; otherwise continues to use rule.multiplier (backward compatible). No columns removed from PricingRule.

### Model changes
- **New table — ContractTerm:**  
  `id`, `contract_id` (FK), `version_id` (FK, nullable), `name` (CharField), `multiplier` (Decimal), `effective_start_date`, `effective_end_date` (nullable).  
  Index: (contract_id, version_id, effective_start_date, effective_end_date).
- **Modified — PricingRule:** Add `contract_term_id` (FK to ContractTerm, null=True, blank=True). Do not remove `multiplier` or `flat_rate`.
- **Deprecated:** None in schema; document that when contract_term_id is set, multiplier is ignored for multiplier-sourced methodologies.

### Loader changes
- In the block that sets `conversion_factor` / multiplier for RBRVS, PCT_BILLED, etc.:
  - If `rule.contract_term_id` is set: load ContractTerm by id; check effective_start_date <= service_date <= effective_end_date (or null end); set `context.conversion_factor = contract_term.multiplier` (or equivalent). Use loader cache key e.g. `('contract_term', rule.contract_term_id, service_date)` to avoid N+1.
  - Else: keep current behavior `conversion_factor = rule.multiplier` (or from methodology).
- Do not change flat_rate sourcing yet (still rule.flat_rate or methodology/defaults). Do not touch base_fee_schedule or FeeScheduleRate logic.

### Orchestrator changes
- None required for Phase B. ExecutionContext from Phase A is unchanged; no new stages.

### Migration strategy
- Migration 1: Create ContractTerm table. Migration 2: Add PricingRule.contract_term_id (nullable). No backfill of contract_term_id required; existing rules keep using rule.multiplier. Optional: provide management command or admin action to “create ContractTerm from rule multiplier” for selected rules and set contract_term_id.

### Rollback safety
- Rollback: revert loader to always use rule.multiplier; leave new column and table in place (no data loss). Deploy previous code; rules with contract_term_id set would then use rule.multiplier again (which may be null)—document that rollback may require re-populating multiplier for those rules if they were migrated.

### Risk level
**Low.** Additive; dual read (ContractTerm if FK set, else rule.multiplier) preserves existing behavior.

### What NOT to change in Phase B
- Do not remove PricingRule.multiplier or PricingRule.flat_rate.
- Do not add CodeGroup, resolver condition changes, or revenue_code.
- Do not change orchestrator stage order or add claim/cross-line phases.
- Do not change ContractMethodology columns.

---

## Phase C — CodeGroup + Resolver Upgrades

**Objective:** Add CodeGroup and CodeGroupMember so the resolver can match “procedure_code IN code_group.” Optionally add revenue_code to input and resolver. Resolver only; no change to which methodology runs or how pricing is calculated. Loader unchanged for pricing variables.

### Model changes
- **New tables:**  
  **CodeGroup:** `id`, `contract_id` (nullable), `version_id` (nullable), `code_group_code`, `name`, `effective_start_date`, `effective_end_date`.  
  **CodeGroupMember:** `id`, `code_group_id` (FK), `code_id` (CharField, procedure code), `effective_start_date`, `effective_end_date`.  
  Indexes: (code_group_id, code_id), (contract_id, version_id, effective_*) on CodeGroup.
- **Modified (optional for C):**  
  **PricingInput / ClaimLineInput:** add `revenue_code: Optional[str] = None`.  
  **ExecutionContext / LineState:** ensure line input can carry revenue_code (if you add it to PricingInput, it flows through).  
  Do not add contract_term_id to conditions in this phase if already added in B; condition attribute_value can already store code_group_id as string.
- **PricingRuleCondition:** No schema change. Support in code: when attribute_name == `code_group`, attribute_value is code_group_id; resolver resolves membership (see below).

### Loader changes
- No change to how multiplier, flat_rate, conversion_factor, or any pricing variable is loaded. Do not read from CodeGroup for pricing; CodeGroup is for routing only in Phase C.

### Orchestrator changes
- None. ExecutionContext already built in Phase A; if revenue_code is added to PricingInput, ensure ClaimOrchestrator passes it from claim line to PricingInput when building the line loop.

### Resolver changes (core of Phase C)
- **_matches_with_reason:**  
  When `condition.attribute_name == 'code_group'` (or similar): parse `attribute_value` as code_group_id; load CodeGroupMember for that code_group_id and effective date (service_date from request or context); check `request.procedure_code in {m.code_id for m in members}`. Cache by (code_group_id, service_date) to avoid N+1.  
  When `attribute_name == 'revenue_code'`: compare `condition.attribute_value` to `request.revenue_code` (or context).  
  All other condition types (procedure_code, billed_amount, @base_allowed_amount, etc.) unchanged.
- Do not add provider_id/facility_id to resolver in Phase C unless you add them to ExecutionContext/claim input in this phase (optional; can defer to a later phase).

### Migration strategy
- Migrations: create CodeGroup and CodeGroupMember. Optional: add revenue_code to ClaimLineInput/PricingInput (and to API/serializers if needed). No backfill of existing rules required; existing conditions remain procedure_code or other attributes.

### Rollback safety
- Revert resolver and model changes. No removal of PricingRule columns; safe to roll back. CodeGroup data can remain.

### Risk level
**Medium.** Resolver logic grows; ensure code_group lookup is cached and effective-dated correctly. Unit tests for “procedure in group” and “procedure not in group” required.

### What NOT to change in Phase C
- Do not remove rule.multiplier or rule.flat_rate or change loader’s pricing variable sourcing.
- Do not introduce claim-level or cross-line phases.
- Do not add ContractTerm to resolver (ContractTerm is used in loader only in B).

---

## Phase D — Remove Pricing Variables From Rules Entirely

**Objective:** All pricing variables come from reference tables. Loader never reads rule.multiplier or rule.flat_rate; it uses rule.contract_term_id (ContractTerm), rule.base_fee_schedule + procedure (FeeScheduleRate), and future reference tables for flat rates/per diem. ContractMethodology becomes binding-only (default fee_schedule_id, default contract_term_id); no conversion_factor/base_percentage on methodology. Deprecate and then remove multiplier/flat_rate from PricingRule and conversion_factor/base_percentage from ContractMethodology after backfill and feature flag.

### Model changes
- **New tables (if not exists):**  
  **PerDiemRate:** id, contract_id, version_id, rate_amount, effective_start_date, effective_end_date.  
  **ModifierAdjustment:** id, contract_id, version_id, modifier_code, adjustment_type, adjustment_value, effective_start_date, effective_end_date.  
  (Optional) **ContractFlatRateOverride:** id, contract_id, version_id, procedure_code (nullable), rate_amount, effective_start_date, effective_end_date — for rules that today have a literal flat_rate and no fee schedule.
- **Modified — PricingRule:** Add `per_diem_rate_id` (FK, nullable). Mark `multiplier` and `flat_rate` as deprecated; keep columns. Add optional `flat_rate_override_id` (FK to ContractFlatRateOverride) if you use that table.
- **Modified — ContractMethodology:** Add `contract_term_id` (FK, nullable). Mark `conversion_factor` and `base_percentage` as deprecated; keep columns.
- **Deprecated (logically):** PricingRule.multiplier, PricingRule.flat_rate; ContractMethodology.conversion_factor, base_percentage. Remove in a later migration after flag is off and backfill verified.

### Loader changes
- **Multiplier / conversion_factor:** Always resolve from reference data. If rule.contract_term_id set, use ContractTerm (already in B). If rule has no contract_term_id, resolve from methodology.contract_term_id; if methodology has contract_term_id, load ContractTerm and use its multiplier. If neither has contract_term_id, use a default (e.g. Decimal("1.0000")) or fail fast for methodologies that require a multiplier—do not read rule.multiplier or methodology.conversion_factor. Feature flag: when `USE_REFERENCE_ONLY_PRICING = False`, fall back to rule.multiplier / methodology.conversion_factor for backward compatibility during transition.
- **Flat rate / base rate:** For FLAT_RATE/PER_DIEM: if rule.base_fee_schedule_id set, continue using FeeScheduleRate by procedure (existing). Else if rule.per_diem_rate_id set, load PerDiemRate and set context.flat_rate from it. Else if rule.flat_rate_override_id set, load ContractFlatRateOverride and set context.flat_rate. Else resolve from methodology default (e.g. methodology.fee_schedule + FeeScheduleRate, or methodology’s default rate table). Do not read rule.flat_rate or store flat rate on methodology. Feature flag: when False, fall back to rule.flat_rate.
- **Modifier adjustments:** Load ModifierAdjustment for contract/version and effective date; merge into context.modifier_adjustments (contract overrides RefModifier when same modifier_code).
- Backfill requirement: For every rule that currently has multiplier set, create a ContractTerm and set rule.contract_term_id (or set methodology.contract_term_id and let rule inherit). For every rule that has flat_rate set without a fee schedule, create FeeScheduleRate rows or ContractFlatRateOverride rows and point rule via base_fee_schedule or flat_rate_override_id. Run backfill script; then enable USE_REFERENCE_ONLY_PRICING = True; then remove deprecated columns in a follow-up migration.

### Orchestrator changes
- None for stage order. ExecutionContext and trace unchanged. Optional: add trace entry “reference_used: contract_term_id=X” when loader uses ContractTerm.

### Migration strategy
- Add new tables and new FKs (per_diem_rate_id, contract_term_id on methodology, flat_rate_override_id if used). Keep multiplier, flat_rate, conversion_factor, base_percentage. Run backfill (script or management command). Deploy with USE_REFERENCE_ONLY_PRICING = False; validate; switch to True; then migration to drop deprecated columns.

### Rollback safety
- Rollback: set USE_REFERENCE_ONLY_PRICING = False; loader again reads rule.multiplier and rule.flat_rate. Do not drop deprecated columns until all contracts have been backfilled and verified.

### Risk level
**High.** Data migration and dual-read logic; incorrect backfill can change pricing. Require backfill validation (e.g. compare old vs new loader output for a sample of rules).

### What NOT to change in Phase D
- Do not add claim-level methodology registry or cross-line phase.
- Do not change resolver condition evaluation (code_group, revenue_code, etc.) beyond what was done in C.
- Do not remove ExecutionContext or unified trace.

---

## Phase E — Claim-Level Methodology Registry (e.g. DRG-Style)

**Objective:** Run claim-level methodologies as plugins after line pricing. Introduce a claim-level registry (e.g. DRG, case rate, per diem as claim total, stop-loss, outlier). DRG: one payment per claim = FacilityBaseRate × DRGWeight; DRG code from claim header or first line. Existing line-level DRG can remain for versions that do not use claim-level DRG. No cross-line logic yet.

### Model changes
- **New tables:**  
  **FacilityBaseRate:** id, contract_id, version_id, facility_id (nullable), rate_type (e.g. 'DRG', 'APC'), base_rate, effective_start_date, effective_end_date.  
  **CaseRateDefinition:** id, contract_id, version_id, case_rate_code, lump_sum_amount, effective_start_date, effective_end_date.
- **Modified:**  
  **ContractVersion:** Add `claim_level_drg_enabled` (boolean, default False).  
  **ClaimPricingInput / claim payload:** Add `drg_code: Optional[str] = None` at claim level (and optionally facility_id, provider_id if not already present).
- **ExecutionContext:** Add fields for claim-level result: e.g. `claim_level_payment: Optional[Decimal] = None`, `drg_applied: bool = False`. Trace already supports phase=CLAIM.

### Loader changes
- No change to per-line loader for line-level methodologies. For claim-level DRG, the claim-level step (orchestrator) loads FacilityBaseRate and RefDrg by drg_code/year—either in a new “claim loader” or inside the DRG claim plugin. Do not add claim-level loading into the existing line loader.

### Orchestrator changes
- **ClaimOrchestrator.run():** After the line loop (and carve-outs), before stop-loss:
  - Build or get from config a list of **claim-level methodology configs** (e.g. enabled types: DRG, CASE_RATE, STOP_LOSS, OUTLIER). For each enabled type, run the corresponding plugin.
  - **Claim-level phase:** For DRG (when version.claim_level_drg_enabled): call DRGClaimPlugin.run(context). Plugin: read context.drg_code (or from first line procedure_code); resolve FacilityBaseRate(contract, version, facility); resolve RefDrg(drg_code, year); set context.claim_total = base_rate * weight (or set context.claim_level_payment and then set context.claim_total to it). Append trace entry. For STOP_LOSS and OUTLIER, either keep current hard-coded logic and move it into StopLossClaimPlugin and OutlierClaimPlugin that accept context, or keep as-is and only add DRG/CASE_RATE as new plugins—minimize risk by moving one at a time.
  - Order: LINE phase → **CLAIM_METHOD** (DRG, case rate, then stop-loss, then outlier) → (later: CROSS_LINE) → BLENDING → CLAIM_CAP_FLOOR. So current stop-loss/outlier become part of “claim-level methodology” execution; they can remain inline in the orchestrator or be moved to plugins that receive context and mutate context.claim_total.
- **Registry:** New module e.g. `core/engine/claim_strategies.py` with CLAIM_METHODOLOGY_REGISTRY = {'DRG': DRGClaimPlugin(), 'CASE_RATE': CaseRateClaimPlugin(), ...}. ClaimOrchestrator looks up by config (e.g. claim_level_drg_enabled → run 'DRG' plugin).

### Migration strategy
- Migrations: create FacilityBaseRate, CaseRateDefinition; add claim_level_drg_enabled to ContractVersion; add drg_code (and optional facility_id) to claim input. Backfill FacilityBaseRate from existing ContractBaseRate where rate_type='DRG' (one row per version, facility_id=null). No backfill of claim_level_drg_enabled; default False preserves current behavior.

### Rollback safety
- Set claim_level_drg_enabled = False for all versions; no claim-level DRG runs. Revert code; FacilityBaseRate/CaseRateDefinition tables can remain.

### Risk level
**Medium.** New execution path (claim-level); ensure DRG runs once per claim and does not double-apply with line-level DRG when both exist. Document: when claim_level_drg_enabled, line-level DRG rules should not be used for that version (or skip line-level DRG for that claim type).

### What NOT to change in Phase E
- Do not add cross-line phase or MPPR.
- Do not change line-level resolver or loader for line BASE/ADJUSTMENT.
- Do not remove ExecutionContext or unified trace.

---

## Phase F — Cross-Line Methodology Support

**Objective:** Add a single cross-line phase after claim-level and before blending. Implement MPPR-style logic: rank lines in scope by a defined criterion (e.g. allowed amount), apply primary/secondary/tertiary percentages to allowed amounts. Cross-line phase receives ExecutionContext and may mutate context.line_states[].current_allowed_amount. No change to line-level or claim-level loader.

### Model changes
- **New tables:**  
  **MPPRDefinition:** id, contract_id, version_id, name, rank_by (e.g. 'ALLOWED_AMOUNT' | 'RVU' | 'FEE_SCHEDULE'), primary_pct (Decimal), secondary_pct, tertiary_pct, effective_start_date, effective_end_date.  
  **MPPRScope:** id, mppr_definition_id (FK), code_group_id (nullable), procedure_code (nullable). Lines in scope if procedure in code_group or matches procedure_code.
- **Modified:** **ContractPricingConfig:** Add `mppr_definitions: Tuple[MPPRDefinition, ...]` (or list). Build in config builder from MPPRDefinition filtered by contract/version and service_date.

### Loader changes
- No change to per-line or claim-level loader. MPPR step uses context.line_states and config.mppr_definitions only; no new loader for pricing variables.

### Orchestrator changes
- **ClaimOrchestrator.run():** After claim-level phase, before blending:
  - **Cross-line phase:** Call `run_cross_line_phase(context, config)`. If config.mppr_definitions is empty, no-op. Else for each MPPRDefinition: (1) determine lines in scope (procedure in MPPRScope’s code_group or procedure_code); (2) sort those lines by rank_by (e.g. current_allowed_amount descending); (3) apply primary_pct to first, secondary_pct to second, tertiary_pct to rest; set each line’s current_allowed_amount = base_allowed_amount * pct / 100 (or current_allowed_amount * pct / 100 depending on spec); (4) append trace entries. Recompute context.claim_total from context.line_states after cross-line. Update ClaimPricingResult line results from context.line_states so response reflects post-MPPR amounts.
- **Stage order (final for CLAIM):** LINE → CLAIM_METHOD → **CROSS_LINE** → BLENDING → CLAIM_CAP_FLOOR.

### Migration strategy
- Migrations: create MPPRDefinition and MPPRScope. Config builder extended to load mppr_definitions. No backfill required; MPPR is opt-in per version.

### Rollback safety
- Revert code; config.mppr_definitions can be empty. No removal of columns. Safe.

### Risk level
**Medium.** Cross-line mutates line amounts; ensure trace and result are consistent and that claim_total is recomputed after cross-line. Unit tests: two lines in scope, expect second line reduced by secondary_pct.

### What NOT to change in Phase F
- Do not add line-level or claim-level methodology logic inside the cross-line phase beyond MPPR (e.g. global surgery can be added later as another cross-line strategy).
- Do not change loader or resolver for BASE/ADJUSTMENT.
- Do not remove ExecutionContext or trace.

---

## Phase G — Line & Claim Cap/Floor Hardening

**Objective:** Explicit line-level cap/floor stage (optional per contract/version) and consistent application of claim-level cap/floor. Trace and audit fields fully aligned with deterministic stages. No new methodologies; only stage and config hardening.

### Model changes
- **New (optional):** **ContractLineCapFloor** (or reuse ContractCapFloor with scope='LINE'): version_id, scope ('LINE'), cap_type ('CAP'|'FLOOR'), value, code_value (optional), effective_start_date, effective_end_date. If existing ContractCapFloor already supports scope=LINE, no new table.
- **Modified:** Ensure ContractCapFloor has scope (CLAIM | LINE) and effective_start_date/effective_end_date where missing. ExecutionContext: ensure line_states support line_cap_floor_applied (bool or value) if you want to record it.

### Loader changes
- No change to pricing variable loading. Config builder: when building cap_floors, include line-level cap/floors in a separate list (e.g. line_cap_floors) or tag by scope so orchestrator can apply line cap/floor in the right stage.

### Orchestrator changes
- **LineOrchestrator (or inside ClaimOrchestrator line loop):** After ADJUSTMENT stage, if config has line-level cap/floor rules for this contract/version, apply them to current_allowed_amount for the line (clamp to cap or floor); update line state and append trace. So line stage order becomes: BASE → ADJUSTMENT → **LINE_CAP_FLOOR**.
- **ClaimOrchestrator:** Claim-level cap/floor already exists; ensure it runs after CROSS_LINE and BLENDING. Ensure trace entries for both line and claim cap/floor with stage and phase.
- **Trace:** Every stage (LINE BASE, LINE ADJUSTMENT, LINE_CAP_FLOOR, CLAIM_METHOD, CROSS_LINE, BLENDING, CLAIM_CAP_FLOOR) has at least one trace entry when applied. ExecutionContext.trace is the single source of truth for the result’s execution_trace.

### Migration strategy
- Add ContractLineCapFloor if new table; or add scope to ContractCapFloor and backfill existing rows with scope='CLAIM'. Config builder returns line_cap_floors and claim cap_floors separately if needed.

### Rollback safety
- Revert line cap/floor application; claim cap/floor unchanged. Low risk.

### Risk level
**Low.** Additive; deterministic; improves auditability.

### What NOT to change in Phase G
- Do not add new methodology types or reference tables beyond line/claim cap/floor config.
- Do not change rule routing or loader pricing variable resolution.

---

## Summary Table

| Phase | Objective                         | Risk  | Key deliverable                                      |
|-------|-----------------------------------|-------|------------------------------------------------------|
| A     | ExecutionContext + unified trace | Low   | One context per claim; single trace list             |
| B     | ContractTerm; multipliers off rule| Low   | contract_term_id on rule; loader dual-read           |
| C     | CodeGroup + resolver              | Medium| procedure IN code_group; revenue_code in conditions  |
| D     | Reference-only pricing            | High  | No rule.multiplier/flat_rate; backfill + flag        |
| E     | Claim-level methodology registry  | Medium| DRG/case rate/stop-loss/outlier as plugins            |
| F     | Cross-line (MPPR)                 | Medium| MPPRDefinition; cross-line phase in orchestrator     |
| G     | Line & claim cap/floor hardening  | Low   | LINE_CAP_FLOOR stage; trace completeness             |

Execution order: A → B → C → D → E → F → G. After each phase, run full regression (unit + integration + simulation); keep backward compatibility until D is validated and deprecated columns are dropped.
