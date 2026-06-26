# Pricing Architecture Alignment — Actual vs Intended

This document reconciles the **documented actual behavior** (source: [pricing_execution_flow.md](../pricing_execution_flow.md)) with the **intended canonical architecture** (source: [ROADMAP.md](../ROADMAP.md)). It is an architectural analysis only; no code is modified.

---

## 1. Compare Canonical Pricing Order vs Actual Execution

**Canonical intended order** (from ROADMAP.md):

1. Resolve contract  
2. Resolve version  
3. Base pricing (line-level)  
4. Carve-outs  
5. Adjustments / modifiers  
6. Stop-loss  
7. Outlier  
8. Blending  
9. Caps/floors  
10. Return result  

Comparison table:

| Step | Implemented? | Location | Per Line / Claim | Notes |
|------|--------------|----------|------------------|--------|
| 1. Resolve contract | Yes, partial | `core/engine/orchestrator.py` inside `calculate_claim()` when `claim_header.contract_id` is None; `core/engine/loader.py` `resolve_contract_for_claim()`. Not used by price-line or price-claim endpoints. | Claim (stored-claim path only) | Only stored-claim path uses it. Ad-hoc paths require client-supplied `contract_id` via `_get_contract()` in view. |
| 2. Resolve version | Yes, partial | `core/engine/orchestrator.py` `calculate_claim()`: `resolve_active_contract_version(contract, service_date)` from `core/engine/loader.py`. | Claim (stored-claim path only) | Batch price-claim and price-line pass `version=None`; no version resolution in view. |
| 3. Base pricing (line-level) | Yes | `core/engine/orchestrator.py` `calculate_line()`: StrictRuleResolver → load_context → get_methodology → strategy.calculate(). | Per line | Single source of line pricing; used by both stored-claim and ad-hoc paths. |
| 4. Carve-outs | No | — | — | Not implemented. No step in orchestrator; no hook. ROADMAP Step 7 defines carve-out execution after base pricing. |
| 5. Adjustments / modifiers | Yes, but not as separate step | Inside each strategy’s `calculate()` via base class `apply_modifiers(context, base_amount)` in `core/engine/strategies/base.py`. Loader populates `context.modifier_adjustments` from RefModifier. | Per line, inside strategy | Canonical order lists “Apply rule adjustments (modifiers, etc.)” as step 6 (separate). Actual behavior: modifiers are applied inside strategy execution (combined with step 3). Not duplicated elsewhere. |
| 6. Stop-loss | Yes, partial | `core/engine/orchestrator.py` inside `calculate_claim()` only. Filter ContractStopLossRule by contract, effective date, version; order by -priority; first match wins. Uses `total_cost` from line `cost_amount`. | Claim | Not applied in batch price-claim path (no calculate_claim). |
| 7. Outlier | Yes, partial | `core/engine/orchestrator.py` inside `calculate_claim()` only. Same filtering pattern; uses `total_billed` from line `billed_amount`. Runs after stop-loss; if both apply, outlier overwrites `total_allowed`/`final_total_allowed`. | Claim | Not applied in batch price-claim path. PER_LINE scope raises NotImplementedError. |
| 8. Blending | No | — | — | Not implemented. ROADMAP Step 9: after outlier, before caps. |
| 9. Caps/floors | No | — | — | Not implemented. ROADMAP Step 8: final clamp. |
| 10. Return result | Yes | `ClaimPricingResult` built in `calculate_claim()`; `LineResult` in `calculate_line()`. | Both | Stored-claim returns full ClaimPricingResult; batch price-claim returns hand-built dict with line results and sum only. |

**Summary:** Implemented in full only on the **stored-claim path** (and even there, carve-outs, blending, and caps are missing). **Modifiers** are implemented but **inside** the strategy, not as a distinct orchestrator step. **Dual logic:** claim-level steps (contract resolution, version, stop-loss, outlier) exist only in `calculate_claim()` and are **duplicated by omission** on the batch path (batch reimplements “price a claim” as a loop of `calculate_line()` without those steps).

---

## 2. Identify Dual Claim Pricing Paths

### Stored-claim pricing path

- **Trigger:** GET or POST `/api/claims/<pk>/price/` → `ClaimPriceView._price_claim(pk)`.
- **Flow:** Load `ClaimHeader` (with `select_related('contract')`), call `PricingEngine().calculate_claim(claim)`.
- **Behavior:** Contract resolved inside engine when `contract_id` is null; version resolved; lines iterated; `calculate_line(contract, inp, version=version)` per line; stop-loss then outlier applied; full `ClaimPricingResult` returned.
- **Reference:** [pricing_execution_flow.md § 1 (Stored-claim), § 2, § 3, § 11](pricing_execution_flow.md).

### Ad-hoc batch pricing path

- **Trigger:** POST `/api/price-claim/` → `PriceClaimView.post()`.
- **Flow:** Validate `PricingClaimRequest`, `_get_contract(data['contract_id'])`, loop over `data['lines']`, build `PricingInput` per line, call `engine.calculate_line(contract, inp)` (no version), sum `total_allowed`, return dict with lines and total.
- **Behavior:** No `calculate_claim()`. No contract resolution by participation/scope; no version resolution; no stop-loss; no outlier; no `ClaimPricingResult` (custom response dict).
- **Reference:** [pricing_execution_flow.md § 1 (Batch), § 2, § 11](pricing_execution_flow.md).

### Single-line pricing path

- **Trigger:** POST `/api/price-line/` → `PriceLineView.post()`.
- **Flow:** Validate `PricingRequestSerializer`, `_get_contract(data['contract_id'])`, `engine.calculate_line(contract, pricing_input)` once, return `PricingResponseSerializer(result)`.
- **Behavior:** One line only; no claim-level logic by design. No duplication concern for claim-level steps.

### Why does stored-claim pricing use calculate_claim()?

Stored claims are modeled as `ClaimHeader` with related `ClaimLine` rows and optional `contract_id`. The design is that pricing a stored claim is a **claim-level operation**: resolve contract (if missing), resolve version, price all lines with that version, then apply claim-level stop-loss and outlier. `calculate_claim()` is the single place that implements this full sequence. So stored-claim uses `calculate_claim()` by design to get contract resolution, versioning, and claim-level adjustments.

### Why does batch pricing bypass calculate_claim()?

Batch pricing accepts a payload of lines and a `contract_id`; there is no stored `ClaimHeader`. The current implementation does not build a temporary claim object and call `calculate_claim()`. Instead, the view loops over lines and calls `calculate_line()` directly. So batch pricing bypasses `calculate_claim()` because (1) the API was likely added as a convenience over multiple line-level calls, and (2) no refactor was done to route “batch of lines + contract” through the same orchestration as “stored claim.” That is **technical drift**: two ways to “price a claim” with different behavior.

### What features are lost in batch pricing?

- **Contract resolution by participation/scope:** Batch requires explicit `contract_id`; no `resolve_contract_for_claim()`.
- **Version resolution:** No `resolve_active_contract_version()`; `version=None` is passed to `calculate_line()`, so only contract-level (version_id null) rules/methodologies are used.
- **Stop-loss:** Not applied; batch total is plain sum of line allowed amounts.
- **Outlier:** Not applied.
- **Consistent result shape:** No `ClaimPricingResult` (no `original_total_allowed`, `final_total_allowed`, `applied_stop_loss_rule_id`, `applied_outlier_rule_id`, `claim_trace`, status STOP_LOSS_APPLIED/OUTLIER_APPLIED).

### Recommendation

- **Option A — Batch calls calculate_claim():** Introduce a “virtual” or in-memory claim representation (e.g. a minimal object with `contract_id`, `service_date`, `claim_type`, and a list of line-like inputs with `procedure_code`, `billed_amount`, `cost_amount`, `units`, `modifiers`). Batch endpoint builds this, then calls the same `calculate_claim()` (or a shared orchestration function that accepts this representation). Ensures one source of truth and consistent behavior (version, stop-loss, outlier). Requires either `ClaimHeader`/`ClaimLine` to be created temporarily (and perhaps not persisted) or `calculate_claim()` to accept an abstraction (e.g. “claim-like” protocol) that can be satisfied by both stored claim and batch payload.
- **Option B — Refactor orchestration into a shared layer:** Extract the logic inside `calculate_claim()` into a shared “ClaimOrchestrator” or “PricingService.price_claim(claim_like)” that: (1) resolves contract if not provided, (2) resolves version, (3) runs line pricing (existing `calculate_line()`), (4) applies stop-loss, (5) applies outlier, (6) returns `ClaimPricingResult`. Both `ClaimPriceView` (stored claim) and `PriceClaimView` (batch) would call this service with a common claim-like input (stored claim adapter vs batch payload adapter). `calculate_claim(claim_header)` becomes a thin wrapper that adapts `ClaimHeader` to that input and calls the shared layer.

**Recommendation:** **Option B** is preferable long-term: single orchestration implementation, clear adapter boundary (stored vs ad-hoc), and batch gains versioning, stop-loss, and outlier without duplicating logic. Option A is viable if the team prefers minimal change and can introduce a temporary or virtual claim model.

---

## 3. Modifier / Adjustment Placement Analysis

### Current design

- Modifiers are applied **inside** `strategy.calculate()` via the base class method `apply_modifiers(context, base_amount)`.
- The loader (`PricingDataLoader.load_context`) loads `RefModifier` by modifier codes from `input_data.modifiers` and sets `context.modifier_adjustments` (e.g. percentage per modifier).
- Each strategy computes a base amount (e.g. RVU × CF × units, or flat_rate × units) then calls `self.apply_modifiers(context, base_price)` before returning.
- There is **no** separate “apply rule adjustments” step in the claim orchestrator; the orchestrator only calls `strategy.calculate(context)` per line.

**Reference:** [pricing_execution_flow.md § 3, § 4, § 7](pricing_execution_flow.md).

### Does this align with intended canonical separation?

No. The canonical order (ROADMAP) lists:

- Step 4: Price lines (base methodology)  
- Step 5: Apply line-level carve-outs  
- Step 6: Apply rule adjustments (modifiers, etc.)  

So the **intended** separation is: base price per line → then adjustments (modifiers) as a distinct step. In the current code, “base” and “modifiers” are combined inside the strategy.

### What would break if adjustments became a separate step?

- **Strategies** would return a **base amount only** (no modifier application). Each strategy’s `calculate()` would need to stop before calling `apply_modifiers()`, or `apply_modifiers()` would be removed from strategies and invoked once in the orchestrator after strategy execution.
- **Loader** would still populate `context.modifier_adjustments`; the **orchestrator** would need to apply them to the strategy return value (e.g. `base_amount = strategy.calculate(context)`; `final_amount = apply_modifiers(context, base_amount)`). The base class `apply_modifiers()` could move to a shared helper called by the orchestrator.
- **Backward behavior:** If the formula is “base × modifier1 × modifier2” (multiplicative), moving application to the orchestrator preserves the same result. If any strategy ever applied modifiers in a methodology-specific way (e.g. only certain modifiers for APC), that would need to be preserved in the new adjustment step or remain inside that strategy by design.

### Are modifiers methodology-specific or generic?

From the code: modifiers are **generic** in form (RefModifier percentage applied multiplicatively via `apply_modifiers()` in base class). All strategies that return a base price use the same `self.apply_modifiers(context, base_price)`. So they are **generic adjustments** that happen to be applied inside the strategy today. That supports moving them to a single post-strategy step in the orchestrator without methodology-specific logic.

### Recommendation

- **Preferred: Extract to orchestrator.** Add a single “apply adjustments” step in `calculate_line()` after `strategy.calculate(context)`: strategies return base amount only; orchestrator calls a shared `apply_modifiers(context, base_amount)` (or equivalent) and uses that as the line allowed amount. Aligns with canonical order, centralizes adjustment logic, and makes it easier to add other adjustment types (e.g. carve-out reprice) in one place later.
- **Alternative: Hybrid.** Keep modifier application inside strategies but document that “step 6” is satisfied by strategy internals and add an optional orchestrator hook for **additional** adjustments (e.g. contract-level percentage) after line pricing. Less clean but minimal change.
- **Not recommended:** Keeping modifiers only inside strategies without a documented “adjustments” step, if the goal is to match the canonical order and prepare for carve-outs and other adjustments.

---

## 4. Stop-Loss and Outlier Evaluation Order

### Current behavior

- **Order:** Line pricing → Stop-loss → Outlier (both in `calculate_claim()` in `core/engine/orchestrator.py`).
- **Stop-loss:** Uses `total_cost = sum(line.cost_amount or 0)`. First rule (by -priority) where `total_cost > cost_threshold` wins. Sets `final_total_allowed = stoploss_payment`, `result_status = STOP_LOSS_APPLIED`, then breaks.
- **Outlier:** Runs **after** stop-loss. Uses `total_billed = sum(line.billed_amount)`. First rule (by -priority) where PER_CLAIM and `total_billed > threshold_amount` wins. Sets `total_allowed` and `final_total_allowed = outlier_payment`, `result_status = OUTLIER_APPLIED`, then breaks.
- So **both can apply in sequence**, but only one status is recorded: if stop-loss applies first and then outlier applies, **outlier overwrites** `total_allowed` and `final_total_allowed` and the final status is OUTLIER_APPLIED. So the **effective** final amount is the outlier payment when both match.

**Reference:** [pricing_execution_flow.md § 3, § 8](pricing_execution_flow.md).

### Can both apply?

Yes. Both loops run. The first applicable stop-loss rule is applied; then the first applicable outlier rule is applied. If both apply, the **last** one (outlier) sets the final total and status.

### Does outlier override stop-loss?

Yes. Outlier runs second and overwrites `total_allowed` and `final_total_allowed`. So when both rules match, the outcome is outlier-based.

### Is the precedence deterministic?

Yes. Order is fixed: stop-loss then outlier. Within each, first match by priority wins. So behavior is deterministic for a given claim and rule set.

### Should they be mutually exclusive?

Not mandated by the current docs. The roadmap (Step 5) specifies “stop-loss before outlier” and first applicable rule wins; it does not say they are mutually exclusive. If business intent is “at most one of stop-loss or outlier applies,” the code would need to be changed (e.g. skip outlier when stop-loss was applied, or vice versa). As written, the design allows both to run and the second (outlier) to override.

### Should they operate on original_total_allowed or cost/charge?

- **Stop-loss** correctly uses **cost** (`total_cost` from `line.cost_amount`) and a cost threshold.
- **Outlier** correctly uses **charge** (`total_billed` from `line.billed_amount`) and a charge threshold.
- Neither currently uses `original_total_allowed` (sum of line allowed amounts) for the threshold comparison; they use total cost and total billed respectively. So they operate on cost and charge as intended.

### Recommendation on sequencing clarity

- **Document** in ROADMAP or engine doc: “When both stop-loss and outlier apply, outlier runs second and overwrites the claim total and status.” So the effective precedence is: base total → stop-loss (if triggered) → outlier (if triggered, overwrites).
- **Optional product decision:** If business wants “only one of stop-loss or outlier,” add an explicit rule (e.g. “if stop_loss applied, skip outlier” or “mutually exclusive by config”) and implement it in the orchestrator.
- **Keep** operating on cost and charge; do not switch to `original_total_allowed` for threshold checks unless product specifies otherwise.

---

## 5. Snapshot Integration Gap

### Current state

- **Snapshot:** Built and cached in `core/services/contract_snapshot.py` (`build_contract_snapshot`, `get_or_build_snapshot`, `invalidate_snapshot`). Contains contract_id, name, methodologies, rules (ids, methodology_code, status, specificity_score), fee_schedule_ids, outlier_rules, stop_loss_rules. Exposed via GET `/api/contracts/<id>/snapshot/` in `ContractSnapshotView`.
- **Pricing engine:** Does **not** use the snapshot. `calculate_claim()` and `calculate_line()` always use the DB: resolver queries `PricingRule`, loader queries methodology, fee schedule rates, RefMpfsRvu, RefGeoIndex, RefDrg, RefModifier, RefAspPricing, etc. So pricing execution does not bypass DB lookups.

**Reference:** [pricing_execution_flow.md § 9](pricing_execution_flow.md).

### What would be required to plug snapshot into engine?

1. **Orchestrator** (or a new “snapshot-aware” entry): Accept an optional **preloaded config** (e.g. from snapshot) in addition to contract. When present, skip or reduce DB for: rules list, methodologies, outlier rules, stop-loss rules.
2. **Resolver:** Be able to run against a **list of rules** (from snapshot) instead of always querying `PricingRule.objects.filter(...)`. Filtering (effective date, claim_type, conditions) would still run in memory. Version handling would need to be consistent (snapshot may need to include version-scoped rules when pricing is for a specific version).
3. **Loader:** Accept **preloaded** methodology and fee schedule references where possible. Rates and reference tables (RefMpfsRvu, RefGeoIndex, RefDrg, RefModifier, RefAspPricing, RefApc) are **not** in the snapshot today; they are per-code and high volume. So loader could use snapshot for “which methodology / which fee schedule” but would still query rates and ref tables unless those are also cached or preloaded.
4. **Snapshot shape:** Possibly extend snapshot to include version-scoped rules and methodology when a version is specified, or have the engine request “snapshot for (contract, version)” so resolver/loader can use in-memory structures.

### Which layers would change?

- **Orchestrator:** Optional config/snapshot input; pass rule set (and optionally methodology/outlier/stop-loss) into resolver and claim-level steps when available.
- **Resolver:** Accept optional “rules iterable” instead of always querying; same filtering and matching logic.
- **Loader:** Accept optional pre-resolved methodology / fee schedule; still query rates and ref data unless a larger cache is introduced.
- **Views:** For stored-claim or batch, optionally call `get_or_build_snapshot(contract)` (and version-specific snapshot if needed) and pass into engine.

### Would this reduce N+1 queries?

- **Yes for rules and claim-level config:** One snapshot load per contract (or per contract+version) could replace repeated rule queries per line and separate outlier/stop-loss queries in `calculate_claim()`. That removes the per-claim N+1 for rules and the extra querysets for stop-loss and outlier.
- **Partially for loader:** Methodology and fee schedule id could come from snapshot; but FeeScheduleRate, RefMpfsRvu, RefGeoIndex, RefDrg, RefModifier, RefAspPricing (and RefApc in strategy) are still per-line/per-code. So snapshot reduces “which rule set / which methodology” queries but not “what’s the rate for this code” unless reference data is also cached or batched.

### What architectural abstraction is missing?

A **contract config provider** (or “pricing config”) abstraction that can be implemented by (1) “live DB” (current behavior) and (2) “snapshot/cache.” The orchestrator and resolver would depend on this abstraction (e.g. “get rules for contract/version,” “get methodologies,” “get outlier/stop-loss rules”) instead of directly querying the DB. The snapshot would implement that interface from cached data; the current resolver/loader (or a thin adapter) would implement it from the DB. Pricing would call the provider once per claim (or per batch) and reuse the result for all lines.

### High-level design for snapshot-backed pricing

1. **Define** a `ContractPricingConfig` (or interface) with: rules (for contract/version), methodologies, stop_loss_rules, outlier_rules, optional fee_schedule_ids. Implementations: `DbContractPricingConfig` (current behavior), `SnapshotContractPricingConfig` (from `get_or_build_snapshot` + version-specific data if needed).
2. **Resolver:** `StrictRuleResolver(contract, version, config=None)`. If `config` is provided, use `config.get_rules()` (or in-memory list); else query DB as today.
3. **Orchestrator:** `calculate_claim(claim_header, config=None)`. If no config, build `DbContractPricingConfig` for resolved contract/version. If config provided (e.g. from snapshot), use it for resolver and for stop-loss/outlier rule lists. Loader can take methodology/fee schedule from config when present.
4. **Views:** For high-throughput or batch, optionally load snapshot (and version snapshot) once per contract, build `SnapshotContractPricingConfig`, pass into `calculate_claim()` or shared orchestration. Single-line pricing may still use DB-backed config unless batch preloads snapshot.
5. **Reference data:** Leave rate and ref-table lookups in the loader (or add a separate reference cache later). Snapshot-backed pricing still reduces contract/rule/methodology/outlier/stop-loss queries to one snapshot read per contract (or per version).

---

## 6. Performance Risk Analysis

Based on [pricing_execution_flow.md](pricing_execution_flow.md) (especially § 12):

| Risk | Description | Severity | Notes |
|------|-------------|----------|--------|
| **Repeated claim_header.lines** | In `calculate_claim()`, `claim_header.lines.all()` is used three times: once in the line loop, once for `total_cost`, once for `total_billed`. No `prefetch_related('lines')` in `ClaimPriceView._price_claim()`. | **Medium** | Each evaluation can trigger a query if lines are not prefetched. Fix: prefetch `lines` in the view and/or compute total_cost and total_billed from the already-fetched `line_results` and line list in one pass. |
| **Per-line resolver query** | For each line, `StrictRuleResolver.resolve()` runs a query (or list of rules). With version, filter and order; then iteration. | **High** | N lines → N rule querysets. Mitigation: when a claim is priced, resolve rules once per contract/version and reuse the list for all lines (or use snapshot). |
| **Per-line loader queries** | For each line, `load_context()` may hit ContractMethodology, FeeScheduleRate, RefMpfsRvu, RefGeoIndex, RefDrg, RefModifier, RefAspPricing; APC strategy also queries RefApc. | **High** | Many queries per line. Mitigation: batch load reference data by code/year/quarter where possible; pass contract/version config (or snapshot) to avoid repeated methodology/rule loads. |
| **Redundant effective-date filters** | Stop-loss and outlier each build a new queryset with the same contract and date filters. | **Low** | Two querysets per claim. Can be combined or supplied from snapshot. |
| **No prefetch of lines** | `ClaimPriceView` uses `ClaimHeader.objects.select_related('contract')` only. | **Medium** | Adding `prefetch_related('lines')` reduces queries when iterating lines and when summing cost/billed. |
| **Batch path** | Batch price-claim calls `calculate_line()` N times with no shared config; each line pays full resolver + loader cost. | **High** | Same as above but for ad-hoc batch: no shared rule list, no snapshot. |

### Prefetch candidates

- **ClaimPriceView:** `ClaimHeader.objects.select_related('contract').prefetch_related('lines')` so that `calculate_claim()` does not trigger extra queries for lines.
- **Orchestrator:** In `calculate_claim()`, compute `total_cost` and `total_billed` from the same iteration used for line pricing (or from prefetched lines in one pass) instead of calling `claim_header.lines.all()` again.

### Caching candidates

- **Contract/version config:** Use snapshot (or a similar cache) to supply rules, methodologies, outlier rules, stop-loss rules for a contract/version so resolver and claim-level steps do not query repeatedly.
- **Reference data:** Consider caching RefMpfsRvu, RefApc, RefAspPricing (and optionally FeeScheduleRate) by code/year/quarter for the duration of a request or a batch run to avoid repeated lookups for the same code.

### Query consolidation opportunities

- **Rules:** Load rules for (contract, version) once per claim; pass the list to the resolver so each line does not trigger a new rule query.
- **Methodology:** Resolve methodology once per contract/version/claim_type and reuse for all lines that share the same methodology (or use snapshot).
- **Stop-loss and outlier:** Load rule lists once per claim (or from snapshot) and iterate in memory.

---

## 7. Missing Hooks for Future Roadmap

Canonical order (ROADMAP): after base pricing → carve-outs → adjustments → stop-loss → outlier → blending → caps/floors → return.

### Where carve-out hook should live

- **Per line, after base price is computed, before adding to claim total.** So inside `calculate_claim()`, after `result = self.calculate_line(...)` and before `total_allowed += result.allowed_amount`. Alternatively, carve-outs could be applied **inside** `calculate_line()` (e.g. after strategy.calculate, check carve-out and overwrite or zero the amount). Preferred: **orchestrator** so that carve-out logic stays in one place and can see both line result and claim context.
- **Pseudocode:**

```python
for line in claim_header.lines.all().order_by(...):
    result = self.calculate_line(contract, inp, version=version)
    # <- carve-out hook here: if line matches carve-out, set result.allowed_amount = 0 or reprice
    line_results.append(result)
    if result.status == SUCCESS:
        total_allowed += result.allowed_amount
```

### Where blending hook should live

- **Per claim, after outlier, before caps.** So in `calculate_claim()`, after the outlier loop and before building the return value. Blending would combine or override line-level or claim-level amounts; it operates on `total_allowed` / `final_total_allowed` and possibly per-line results.
- **Pseudocode:**

```python
# ... stop-loss loop ...
# ... outlier loop ...
# <- blending hook here: apply blending rules to total_allowed / line_results
# <- caps/floor hook here: final_total_allowed = clamp(final_total_allowed, floor, cap)
return ClaimPricingResult(...)
```

### Where caps/floor hook should live

- **Per claim, after blending, before return.** Single final clamp step.
- **Pseudocode:** Same as above; caps/floor is the last step before `return ClaimPricingResult(...)`.

### Does current calculate_claim() structure support easy insertion?

- **Carve-outs:** Yes. One block after `result = self.calculate_line(...)` and before appending and adding to `total_allowed`. No refactor of `calculate_line()` required if carve-out only adjusts the result amount or status.
- **Blending:** Yes. After outlier loop, before `return ClaimPricingResult(...)`.
- **Caps/floors:** Yes. After blending (or after outlier if no blending), before return.

So the current structure supports insertion; the main gap is that these steps are not yet implemented and are not called out as no-op hooks in the code.

---

## 8. Proposed Unified Pricing Architecture

### Target layout

```
API Layer (views)
    ↓
PricingService (single entry for “price a claim” and “price a line”)
    ↓
ClaimOrchestrator (contract resolution, version, line loop, carve-outs, stop-loss, outlier, blending, caps)
    ↓
LineOrchestrator / calculate_line (rule resolve, load context, strategy, adjustments)
    ↓
RuleResolver (with optional config: DB or snapshot)
    ↓
ContextLoader (with optional config)
    ↓
Strategy (base amount only; adjustments in orchestrator if extracted)
```

### Which endpoints call which service

| Endpoint | Calls | Notes |
|----------|--------|--------|
| GET/POST `/api/claims/<pk>/price/` | PricingService.price_claim(claim_header) or equivalent | Claim loaded from DB; adapter wraps ClaimHeader as claim-like input. |
| POST `/api/price-claim/` | Same PricingService.price_claim(batch_adapter) | Adapter builds claim-like input from request body (contract_id, service_date, lines). Same orchestration as stored claim. |
| POST `/api/price-line/` | PricingService.price_line(contract, pricing_input) or engine.calculate_line() | Single line; no claim-level steps. Can remain as-is or go through a thin service. |

### Single source of truth

- **ClaimOrchestrator** (or the logic that today lives in `calculate_claim()`) is the **single** place that runs: resolve contract (if needed), resolve version, price lines, apply carve-outs (when implemented), apply adjustments (if extracted), apply stop-loss, apply outlier, apply blending (when implemented), apply caps/floors (when implemented), return ClaimPricingResult.
- Both stored-claim and batch endpoints call this orchestrator with different adapters (stored claim vs in-memory batch payload). No separate “batch loop” that only calls `calculate_line()`.

### Eliminate dual logic

- Remove the duplicate “batch claim” path that only sums `calculate_line()` results. Replace with: build a claim-like input from the batch request (contract_id, default service_date, lines with procedure_code, billed_amount, cost_amount, units, modifiers), then call the same ClaimOrchestrator. Batch responses then include stop-loss, outlier, versioning, and same result shape as stored-claim pricing (or a documented subset).

### Ensure stop-loss and outlier always apply when appropriate

- Any flow that is “pricing a claim” (multiple lines with a contract and optional version) should go through ClaimOrchestrator, so stop-loss and outlier always run. Single-line pricing remains line-only with no claim-level steps.

---

## 9. Executive Summary

### Is the current implementation structurally sound?

**Partially.** The **line-level** flow (resolver → loader → strategy) is clear and single-path. The **claim-level** flow is correct for **stored claims** but **duplicated by omission** for **batch** pricing: batch reimplements “price a claim” without contract resolution, versioning, stop-loss, or outlier. Modifiers are applied inside strategies instead of as a separate canonical “adjustments” step. Carve-outs, blending, and caps are not implemented but insertion points exist.

### Is it enterprise-scalable?

**Not yet.** N+1 patterns (rules and loader per line, repeated `lines.all()`), no use of snapshot in the pricing path, and no shared orchestration for batch vs stored claim will scale poorly for bulk pricing and high throughput. Prefetching, snapshot-backed config, and a single claim orchestration path would improve scalability.

### Is there technical debt?

**Yes.** (1) Two ways to “price a claim” with different behavior (stored vs batch). (2) Snapshot built and invalidated but unused by pricing. (3) Modifiers embedded in strategies instead of a single adjustments step. (4) Missing prefetch for claim lines and repeated evaluation of `lines.all()`. (5) No carve-out, blending, or caps yet, though the roadmap defines them.

### What should be refactored first?

1. **Unify claim pricing:** Make batch pricing go through the same orchestration as stored-claim (shared ClaimOrchestrator or `calculate_claim()` with a claim-like adapter). This removes behavioral divergence and restores stop-loss, outlier, and versioning for batch. **Highest impact.**
2. **Prefetch and single-pass totals:** In the view that loads the claim for pricing, use `prefetch_related('lines')`. In `calculate_claim()`, compute `total_cost` and `total_billed` in one pass (e.g. from the same loop as line pricing or from the prefetched list once). **Quick win.**
3. **Snapshot-backed config:** Introduce a contract-config abstraction and use the existing snapshot (or extended snapshot) so that resolver and claim-level steps can use cached rules and methodologies instead of querying per line and per claim. **High impact for bulk and simulation.**
4. **Modifier placement (optional):** Move modifier application from strategies to a single “apply adjustments” step in the line orchestrator to match canonical order and simplify future adjustment types.

No code was modified in this analysis. All conclusions are based on [pricing_execution_flow.md](../pricing_execution_flow.md) and [ROADMAP.md](../ROADMAP.md).
