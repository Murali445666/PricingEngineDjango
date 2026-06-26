# Pricing Execution Flow – End-to-End

This document describes the actual code paths for pricing in the Matrix Pricing Engine. All statements are derived from code traversal.

**Canonical:** [pricing_execution_flow.md](pricing_execution_flow.md) (this doc — claim pricing execution order) · [ROADMAP.md](ROADMAP.md) (upgrade Stages 0–6) · [UPGRADE_PLAN.md](UPGRADE_PLAN.md) · [STATUS.md](STATUS.md)

---

## 1. Entry Point (External System → API)

### Stored-claim pricing (claim already in DB)

| Item | Value |
|------|--------|
| **URL** | `GET /api/claims/<pk>/price/` or `POST /api/claims/<pk>/price/` |
| **Path name** | `api-claim-price` |
| **HTTP method** | GET or POST (both invoke same logic) |
| **Request payload** | GET: none (pk in path). POST: body optional; pk in path. |
| **Serializer** | None for request. Response: `ClaimPricingResultSerializer`. |
| **View** | `ClaimPriceView` in `core/api/views.py`. `get()` and `post()` both call `_price_claim(pk)`. |
| **First internal function** | `ClaimPriceView._price_claim(pk)` → `get_object_or_404(ClaimHeader.objects.select_related('contract').prefetch_related('lines'), pk=pk)` then `ClaimPricingService().price_stored_claim(claim)`. |

**Code references:**  
`core/api/views.py`: `ClaimPriceView.get()`, `ClaimPriceView.post()`, `ClaimPriceView._price_claim()`  
`core/api/urls.py`: `path('claims/<int:pk>/price/', ClaimPriceView.as_view(), name='api-claim-price')`

### Single-line pricing (ad-hoc, no stored claim)

| Item | Value |
|------|--------|
| **URL** | `POST /api/price-line/` |
| **Path name** | `api-price-line` |
| **HTTP method** | POST |
| **Request payload** | JSON: `contract_id`, `procedure_code`, `billed_amount`, optional: `units`, `modifiers`, `service_date`, `claim_type`, `pricing_date`, `contract_effective_date`. |
| **Serializer** | Request: `PricingRequestSerializer`. Response: `PricingResponseSerializer`. |
| **View** | `PriceLineView` in `core/api/views.py`, method `post()`. |
| **First internal function** | `PriceLineView.post()` → `PricingRequestSerializer(data=request.data)` → after `is_valid()`, `_get_contract(data['contract_id'])` then `ClaimPricingService().price_line(contract, pricing_input)`. |

**Code references:**  
`core/api/views.py`: `PriceLineView.post()`  
`core/api/serializers.py`: `PricingRequestSerializer`, `PricingResponseSerializer`

### Batch claim pricing (ad-hoc lines in request body)

| Item | Value |
|------|--------|
| **URL** | `POST /api/price-claim/` |
| **Path name** | `price-claim` |
| **HTTP method** | POST |
| **Request payload** | JSON: `contract_id`, `lines` (array of line objects), optional `service_date`, `pricing_date`, `contract_effective_date` at claim level. |
| **Serializer** | Request: `PricingClaimRequest`. Response: `ClaimPricingResultSerializer(result).data` plus `request_time_ms`. |
| **View** | `PriceClaimView` in `core/api/views.py`, method `post()`. |
| **First internal function** | `PriceClaimView.post()` → `PricingClaimRequest(data=request.data)` → `_get_contract(data['contract_id'])` → build `ClaimPricingInput`, then `ClaimPricingService().price_claim(claim_input)`. Full orchestration: version resolution, config build, line pricing, carve-outs, stop-loss, outlier, blending, caps/floors. |

**Code references:**  
`core/api/views.py`: `PriceClaimView.post()`  
`core/api/serializers.py`: `PricingClaimRequest`, `PricingClaimLineRequest`

### Claim simulation (specific version, no activation)

| Item | Value |
|------|--------|
| **URL** | `POST /api/price-claim-simulate/` |
| **Path name** | `price-claim-simulate` |
| **HTTP method** | POST |
| **Request payload** | JSON: `contract_id`, `version_id`, `claim` (same shape as price-claim body: `lines`, `service_date`, optional `pricing_date`). |
| **View** | `PriceClaimSimulateView` in `core/api/views.py`. Uses `ClaimPricingService().price_claim_with_version(contract_id, version_id, claim_input)`. Bypasses ACTIVE version resolver; DRAFT/ACTIVE/SUPERSEDED allowed; ARCHIVED rejected. |

### Bulk claim pricing

| Item | Value |
|------|--------|
| **URL** | `POST /api/price-claims-bulk/` |
| **Path name** | `price-claims-bulk` (no `api-` prefix in name) |
| **HTTP method** | POST |
| **Request payload** | JSON: `claims` (array of claim objects; each has `contract_id`, `lines`, optional `service_date`, `pricing_date`, `claim_type`). |
| **View** | `BulkPriceClaimsView` in `core/api/views.py`. Builds one `ClaimPricingInput` per claim; calls `ClaimPricingService().price_claims_bulk(claim_inputs)`. Config cached per (contract, version, service_date). |

---

## 2. API Layer Flow

### Validation flow

- **PriceLineView:** `PricingRequestSerializer(data=request.data)`; `serializer.is_valid()`; on success use `serializer.validated_data`. Contract resolved via `_get_contract(data['contract_id'])`; `PricingInput` built from validated_data; `ClaimPricingService().price_line(contract, pricing_input)`.
- **ClaimPriceView:** No request body validation; claim loaded by pk with `get_object_or_404(ClaimHeader.objects.select_related('contract').prefetch_related('lines'), pk=pk)`. `ClaimPricingService().price_stored_claim(claim)`.
- **PriceClaimView:** `PricingClaimRequest(data=request.data)`; `serializer.is_valid()`; build `ClaimPricingInput` with `ClaimLineInput` per line; `ClaimPricingService().price_claim(claim_input)`.
- **PriceClaimSimulateView:** `PriceClaimSimulateRequest`; nested `claim` validated via `PricingClaimRequest`; `ClaimPricingService().price_claim_with_version(contract_id, version_id, claim_input)`.
- **BulkPriceClaimsView:** `BulkPricingClaimRequest`; one `ClaimPricingInput` per claim; `ClaimPricingService().price_claims_bulk(claim_inputs)`.

### Service layer entry point

- **Stored claim:** `ClaimPricingService().price_stored_claim(claim)` in `ClaimPriceView._price_claim()`. Service lives in `core/engine/service.py`.
- **Single line:** `ClaimPricingService().price_line(contract, pricing_input)` in `PriceLineView.post()`. No claim-level version resolution; version and config are None for resolver/loader.
- **Batch claim (price-claim):** `ClaimPricingService().price_claim(claim_input)` in `PriceClaimView.post()`. Full orchestration: `ClaimOrchestrator.run(claim_input, config=None)` (version resolved, config built, then line loop, carve-outs, stop-loss, outlier, blending, caps/floors).
- **Simulation:** `ClaimPricingService().price_claim_with_version(contract_id, version_id, claim_input)`; config built via `build_contract_pricing_config_from_version(version, service_date)`; `ClaimOrchestrator.run(claim_input, config=config)`.
- **Bulk:** `ClaimPricingService().price_claims_bulk(claim_inputs)`; version and config cached per (contract_pk, version_pk, service_date); each claim runs `ClaimOrchestrator.run(claim_input, config=config)`.

### Contract resolution

- **Stored claim:** Contract resolution happens inside `price_stored_claim()`: `_claim_header_to_pricing_input(claim_header)`; if `claim_input.contract` is None, `resolve_contract_for_claim(claim_header)` from `core/engine/loader.py`. The API view does not resolve contract; it passes the stored `ClaimHeader` to the service.
- **Price-line, price-claim, simulate, bulk:** Contract is resolved in the **view** via `_get_contract(data['contract_id'])` (by PK or `legacy_contract_number`). No participation/scope resolution; contract must be supplied.

### Call chain (textual)

**Stored claim path:**

```
HTTP GET/POST /api/claims/<pk>/price/
  → ClaimPriceView.get() or .post()
    → _price_claim(pk)
      → get_object_or_404(ClaimHeader.objects.select_related('contract').prefetch_related('lines'), pk=pk)
      → ClaimPricingService().price_stored_claim(claim)
        → _claim_header_to_pricing_input(claim)
        → [if contract_id is None] resolve_contract_for_claim(claim_header)
        → ClaimPricingService().price_claim(claim_input)
          → ClaimOrchestrator.run(claim_input, config=None)
            → resolve_active_contract_version(contract, service_date)
            → build_contract_pricing_config_from_db(contract, version, service_date)
            → for each line: LineOrchestrator.run(contract, inp, version=version, config=config)
            → carve-out application per line
            → stop-loss, outlier, blending, caps/floors
            → return ClaimPricingResult
      → ClaimPricingResultSerializer(result)
    → Response(serializer.data)
```

**Single-line path:**

```
HTTP POST /api/price-line/
  → PriceLineView.post()
    → PricingRequestSerializer(data=request.data).is_valid()
    → _get_contract(data['contract_id'])
    → PricingInput(...)
    → ClaimPricingService().price_line(contract, pricing_input)
      → LineOrchestrator.run(contract, request, version=None, config=None)
        → StrictRuleResolver(contract, version=None, config=None).resolve(request, trace)
        → [rule must have version_id null when version is None]
        → PricingDataLoader.load_context(request, rule, version=None, config=None)
        → get_methodology(context.methodology_code)
        → strategy.calculate(context)
        → return LineResult
    → PricingResponseSerializer(result)
  → Response(serializer.data)
```

**Batch price-claim path (full orchestration):**

```
HTTP POST /api/price-claim/
  → PriceClaimView.post()
    → PricingClaimRequest(data=request.data).is_valid()
    → _get_contract(data['contract_id'])
    → ClaimPricingInput(lines=ClaimLineInput(...), ...)
    → ClaimPricingService().price_claim(claim_input)
      → ClaimOrchestrator.run(claim_input, config=None)
        → resolve_active_contract_version(contract, service_date)
        → build_contract_pricing_config_from_db(contract, version, service_date)
        → for each line: LineOrchestrator.run(..., version=version, config=config) + carve-out
        → stop-loss, outlier, blending, caps/floors
        → return ClaimPricingResult
    → ClaimPricingResultSerializer(result).data + request_time_ms
  → Response(response_data)
```

---

## 3. Claim Pricing Orchestrator

**File:** `core/engine/orchestrator.py`  
**Class:** `ClaimOrchestrator`  
**Method:** `run(self, claim_input: ClaimPricingInput, config: Optional[ContractPricingConfig] = None) -> ClaimPricingResult`

### Order of operations inside run()

1. **Reset cache.** `self.line_orchestrator.loader.reset_execution_cache()`.
2. **Resolve contract.** If `claim_input.contract` is None and `claim_input.contract_id` is set, load `ProviderContract` by pk. Else use `claim_input.contract`. Raise if still None.
3. **Service date.** `service_date = claim_input.service_date or date.today()`.
4. **Resolve version.** If `config is None`: `version = resolve_active_contract_version(contract, service_date)`; then `config = build_contract_pricing_config_from_db(contract, version, service_date)`. If config was provided (e.g. simulation), version comes from config.
5. **Build carve-out lookup.** From `config.carveouts` build `carveout_by_code` (code_value → carve-out) for O(1) per-line lookup.
6. **Per line.** For each `claim_input.lines`: build `PricingInput`; call `LineOrchestrator.run(contract, inp, version=version, config=config)`; apply carve-out via `_apply_carveout(result, inp, carveout_by_code)`; append to `line_results`; add `result.allowed_amount` to `total_allowed` (for SUCCESS, CARVEOUT_REPRICED, CARVEOUT_EXCLUDED).
7. **Stop-loss.** `total_cost = sum(line.cost_amount or 0)`. Iterate `config.stop_loss_rules`; first rule where `total_cost > cost_threshold` wins: set `final_total_allowed`, `applied_stop_loss_rule_id`, `result_status = STOP_LOSS_APPLIED`, break.
8. **Outlier.** `total_billed = sum(line.billed_amount)`. Iterate `config.outlier_rules`; only `threshold_scope == 'PER_CLAIM'` implemented; first match wins; set `total_allowed`, `final_total_allowed`, `applied_outlier_rule_id`, `result_status = OUTLIER_APPLIED`. `PER_LINE` raises `NotImplementedError`.
9. **Blending.** If `config.blending_rules`: `_apply_blending(...)`; may update `final_total_allowed`, `total_allowed`, `result_status`, `claim_trace`.
10. **Caps/floors.** `_apply_cap_floor(...)`; clamps `final_total_allowed`; may set `applied_cap_floor_id`, `result_status`.
11. **Return.** Build and return `ClaimPricingResult` (claim_id, contract_id, lines, total_allowed, line_count, status, claim_trace, original_total_allowed, final_total_allowed, applied_outlier_rule_id, applied_stop_loss_rule_id, pre_cap_total_allowed, applied_cap_floor_id, blended_total_allowed, applied_blending_rule_ids).

### Implemented steps

- Line-level carve-outs (Step 7) are applied after base methodology per line.
- Stop-loss and outlier (claim-level) are applied in order.
- Blending (Step 9) is applied after stop-loss/outlier.
- Caps/floors (Step 8) are applied last (final clamp).
- Modifier application is inside each strategy’s `calculate()` (e.g. `apply_modifiers()`), not a separate orchestrator step.

---

## 4. Line Pricing Flow (LineOrchestrator.run)

**File:** `core/engine/orchestrator.py`  
**Class:** `LineOrchestrator`  
**Method:** `run(self, contract, request: PricingInput, version=None, config: Optional[ContractPricingConfig] = None) -> LineResult`

1. **Trace.** Create `PricingTrace()` for the line.
2. **Rule resolution.** `StrictRuleResolver(contract, version=version, config=config).resolve(request, trace)`. Returns first matching `PricingRule` or None. When `config` is not None, resolver uses `config.rules` (filtered by service_date, ordered by version precedence and `-specificity_score`). When config is None, resolver queries DB with same filters.
3. **No rule.** If `rule is None`, return `build_result(PricingStatus.DENIED_NO_RULE, details="No matching rule found in contract.")`.
4. **Methodology conditions (Step 12c).** If `config` is not None and has methodologies with `conditions`, find methodology matching `rule.methodology_code`; if found, build line context and call `evaluate_conditions(matched_meth.conditions, line_ctx)`. If conditions not met, return DENIED_NO_RULE (methodology skipped).
5. **Context loading.** `self.loader.load_context(request, rule, version=version, config=config)` builds `PricingContext` (methodology, fee schedule, conversion factor, flat rate, base rate, RVUs, GPCI, DRG weight, modifiers, ASP, etc.). If this raises, return `build_result(DENIED_MISSING_DATA, ...)`.
6. **Strategy selection.** `strategy = get_methodology(context.methodology_code)` from `core/engine/strategies/__init__.py`; raises if code not in registry.
7. **Strategy execution.** `price = strategy.calculate(context)`. Strategies may call `apply_modifiers(context, base_price)` internally. Exceptions: `NoApcFoundError` → NO_APC_FOUND; `NoAspFoundError` → NO_ASP_FOUND; else → DENIED_CALCULATION_ERROR.
8. **Return.** `build_result(PricingStatus.SUCCESS, amount=price, method=rule.methodology_code, rule=rule)`.

---

## 5. Rule Resolver Logic

**File:** `core/engine/resolver.py`  
**Class:** `StrictRuleResolver`  
**Method:** `resolve(self, request: PricingInput, trace: PricingTrace) -> PricingRule | None`

### When config is provided

- Use `config.rules`; filter by `service_date` (effective_start_date <= service_date, effective_end_date null or >= service_date).
- If `version` is not None: sort by (0 if rule.version_id == version.pk else 1), then `-specificity_score`. Else: keep only rules with `version_id` None; sort by `-specificity_score`.
- Iterate in order; for each rule, skip if `request.claim_type` is set and rule.claim_type is set and different. Call `_matches(rule, request, trace)`. First match wins.

### When config is None (live DB)

- Queryset: `PricingRule.objects.filter(contract=..., status=ACTIVE, effective_start_date__lte=service_date, effective_end_date null or >= service_date)`, `select_related('contract', 'base_fee_schedule')`, `prefetch_related('conditions')`.
- If `version` is not None: filter `Q(version=version) | Q(version__isnull=True)`, annotate `_version_first`, order by `_version_first`, `-specificity_score`. Else: filter `version__isnull=True`, order by `-specificity_score`.
- Same iteration and `_matches()` as above.

### Condition matching (_matches)

- Rule must have **at least one** condition (`rule.conditions.all()`); if no conditions, return False.
- For each `PricingRuleCondition`: `request_attr = condition.attribute_name`; if `request_attr == 'code'` map to `'procedure_code'`. `request_value = getattr(request, request_attr, None)`. If request_value is None, return False. If `str(request_value) != str(condition.attribute_value)`, return False.
- All conditions must match (AND). First rule that passes claim_type and _matches is returned.

### Version-scoped rule handling

- When `version` is passed, rules with `version_id` equal to that version are tried before rules with `version_id` null (same contract). Ordering: `_version_first` (0 for version match, 1 else), then `-specificity_score`.

---

## 6. Loader Layer

**File:** `core/engine/loader.py`  
**Functions:** `build_contract_pricing_config_from_db(contract, version, service_date)`, `build_contract_pricing_config_from_version(version, service_date)` (Step 13 simulation).  
**Class:** `PricingDataLoader`  
**Method:** `load_context(self, input_data: PricingInput, rule: PricingRule, version=None, config: Optional[ContractPricingConfig] = None) -> PricingContext`

### Config build (from DB)

- **Rules:** Filter by contract, ACTIVE, effective dates; if version: filter (version or version null), order by version-first then `-specificity_score`; `select_related`, `prefetch_related('conditions')`.
- **Methodologies:** Filter by contract, effective_date; if version: (version or null); order by priority, effective_date; `select_related('fee_schedule')`.
- **Stop-loss / outlier:** Filter by contract, effective dates; if version: (version or null); order by `-priority`.
- **Base rates:** If version: `ContractBaseRate.objects.filter(version=version)` → dict rate_type → base_rate.
- **Carve-outs:** If version: `ContractCarveout.objects.filter(version=version)`.
- **Cap floors / blending:** If version: filter by version and service_date; order by priority.

### Reference tables queried in load_context

| Use | Table / model | When |
|-----|----------------|------|
| Fee schedule rate | `FeeScheduleRate` | When rule or methodology has fee schedule; by fee_schedule, code_id; date filtering when rate has effective dates. |
| RBRVS RVU | `RefMpfsRvu` | When methodology is RBRVS and year set; by code, year. |
| GPCI | `RefGeoIndex` | When fee schedule has geo_id. |
| DRG weight | `RefDrg` then `RefProcedureCode` | When methodology is DRG; by drg_code (procedure_code); fallback RefProcedureCode.work_rvu. |
| Modifiers | `RefModifier` | When input_data.modifiers non-empty; modifier_code__in; populates modifier_adjustments. |
| ASP | `RefAspPricing` | When methodology DRUG/ASP; by hcpcs_code, quarter. |
| Base rate (DRG/APC) | From config.base_rates | Preloaded in config; no per-line query. |

APC strategy may query `RefApc` inside its `calculate()`; loader does not load APC rows.

### service_date usage

- Used for: methodology effective_date/termination_date; FeeScheduleRate date range; RefMpfsRvu year; ASP quarter; config rule/stop-loss/outlier/cap/blending effective dates.

---

## 7. Strategy Execution

**Registry:** `core/engine/strategies/__init__.py`  
**Variable:** `METHOD_REGISTRY` (methodology code → strategy instance).  
**Function:** `get_methodology(code)` – normalizes to stripped uppercase, looks up, raises if missing.

**Strategy selection:** After `load_context()`, `get_methodology(context.methodology_code)` is called in `LineOrchestrator.run()`. Context methodology comes from rule’s `methodology_code` or resolved `ContractMethodology.methodology_type`.

**Allowed amount:** Each strategy implements `calculate(self, context: PricingContext) -> Decimal`. Base class provides `apply_modifiers(context, base_amount)` for modifier_adjustments. Strategies typically call it before returning.

### Per-strategy summary

| Code | Strategy class | Key inputs | Calculation (conceptual) |
|------|----------------|------------|---------------------------|
| RBRVS | RBRVSMethod | conversion_factor, units, work/pe/mp RVU, GPCI, or base_rate | (RVU·GPCI) × CF × units, or base_rate × CF × units; then apply_modifiers. |
| DRG | DRGMethod | base rate (from config), drg_weight, units | weight × base × units; apply_modifiers. |
| APC / OPPS | ApcPricingStrategy | conversion_factor, units; RefApc in strategy | relative_weight × conversion_factor × units; apply_modifiers. |
| ASP / DRUG | AspPricingStrategy | asp_price, asp_payment_limit, units | payment_limit or asp × units; apply_modifiers. |
| PCT_BILLED / PERCENT_BILLED | PercentBilledMethod | percent_of_billed, billed_amount, units | billed × (percent/100) × units; apply_modifiers. |
| FLAT_RATE | FlatRateMethod | flat_rate, units | flat_rate × units; apply_modifiers. |
| PER_DIEM | PerDiemMethod | flat_rate, units | flat_rate × units; apply_modifiers. |
| ANESTHESIA | AnesthesiaMethod | conversion_factor, units | Formula using units and CF; apply_modifiers. |

---

## 8. Stop-Loss and Outlier Layer

**Where in code:** `core/engine/orchestrator.py`, inside `ClaimOrchestrator.run()`, using `config.stop_loss_rules` and `config.outlier_rules`. Not applied when only `LineOrchestrator.run()` is called (e.g. single-line `price_line` with no claim context).

### Stop-loss

- **Source:** Preloaded in `config.stop_loss_rules` (from `build_contract_pricing_config_from_db` or `build_contract_pricing_config_from_version`).
- **Input:** `total_cost = sum(line.cost_amount or 0 for line in claim_input.lines)`.
- **Logic:** For each rule in order, if `total_cost <= rule.cost_threshold` skip. Else: excess = total_cost - cost_threshold; stoploss_payment = cost_threshold + (excess * reimbursement_percentage/100); set final_total_allowed, applied_stop_loss_rule_id, result_status = STOP_LOSS_APPLIED, break.
- **First match wins.**

### Outlier

- **Source:** `config.outlier_rules`.
- **Input:** `total_billed = sum(line.billed_amount for line in claim_input.lines)`.
- **Logic:** Only `threshold_scope == 'PER_CLAIM'`. If total_billed <= threshold_amount skip. Else: payment = total_billed * (reimbursement_percentage/100) or total_billed * cost_to_charge_ratio; set total_allowed, final_total_allowed, applied_outlier_rule_id, result_status = OUTLIER_APPLIED, break. `PER_LINE` raises NotImplementedError.
- **First match wins.**

### ClaimPricingResult fields set

- original_total_allowed, final_total_allowed, applied_stop_loss_rule_id, applied_outlier_rule_id, claim_trace, status (SUCCESS, STOP_LOSS_APPLIED, OUTLIER_APPLIED, CAP_APPLIED, FLOOR_APPLIED, BLENDING_APPLIED as applicable).
- pre_cap_total_allowed, applied_cap_floor_id, blended_total_allowed, applied_blending_rule_ids.

---

## 9. Snapshot Usage

**Where snapshot is loaded:** Only in `ContractSnapshotView.get()` in `core/api/views.py` (GET `/api/contracts/<id>/snapshot/`). View uses `get_or_build_snapshot(contract)` from `core/services/contract_snapshot.py` and returns it as the response body.

**Where snapshot is not used:** `ClaimOrchestrator.run()` and `LineOrchestrator.run()` do **not** use the snapshot. They use either a pre-built `ContractPricingConfig` (simulation, bulk) or build config via `build_contract_pricing_config_from_db()`. So pricing execution does not read the GET snapshot endpoint.

**Bulk pricing:** `price_claims_bulk()` builds and caches `ContractPricingConfig` per (contract_pk, version_pk, service_date) inside the service; it does not use the snapshot API.

**When snapshot is invalidated:** In `core/signals.py`, post_save/post_delete on PricingRule, ContractMethodology, ContractOutlierRule, ContractStopLossRule, ContractVersion, ContractScope, ContractProviderParticipation call `invalidate_snapshot(instance.contract_id)` (or equivalent). Next GET to snapshot URL rebuilds and caches.

---

## 10. Final Response Construction

### ClaimPricingResult structure (dataclass)

**File:** `core/engine/types.py`

- `claim_id`, `contract_id`, `lines` (list of `LineResult`), `total_allowed`, `line_count`
- `status`: PricingStatus (SUCCESS, STOP_LOSS_APPLIED, OUTLIER_APPLIED, CAP_APPLIED, FLOOR_APPLIED, BLENDING_APPLIED, etc.)
- `claim_trace`: list of strings
- `original_total_allowed`, `final_total_allowed`: Optional[Decimal]
- `applied_outlier_rule_id`, `applied_stop_loss_rule_id`: Optional[int]
- `pre_cap_total_allowed`, `applied_cap_floor_id`: Optional
- `blended_total_allowed`: Optional[Decimal]; `applied_blending_rule_ids`: List[int]

### LineResult structure (dataclass)

- `status`, `allowed_amount`, `methodology`, `details`
- `contract_id`, `rule_id`
- `trace`: PricingTrace (trace_id, logs)
- `engine_version`, `execution_time_ms`
- Step 7: `carveout_applied`, `carveout_id`, `base_allowed_amount`
- Step 9: `blended_allowed_amount`, `blending_rule_id`

### API response (price-claim, stored-claim price)

- View uses `ClaimPricingResultSerializer(result)` which exposes claim_id, contract_id, total_allowed, line_count, lines (each via PricingResponseSerializer), status, claim_trace, original_total_allowed, final_total_allowed, applied_outlier_rule_id, applied_stop_loss_rule_id, pre_cap_total_allowed, applied_cap_floor_id, blended_total_allowed, applied_blending_rule_ids.
- **File:** `core/api/serializers.py`. No model save for pricing; serializers for request validation and response only.

---

## 11. Call Graph (Textual, Actual Names)

**Stored claim (GET/POST /api/claims/<pk>/price/):**

```
ClaimPriceView.get(request, pk) / ClaimPriceView.post(request, pk)
  → ClaimPriceView._price_claim(pk)
    → get_object_or_404(ClaimHeader.objects.select_related('contract').prefetch_related('lines'), pk=pk)
    → ClaimPricingService().price_stored_claim(claim)
      → _claim_header_to_pricing_input(claim)
      → [if contract None] resolve_contract_for_claim(claim_header)
      → ClaimPricingService().price_claim(claim_input)
        → ClaimOrchestrator.run(claim_input, config=None)
          → resolve_active_contract_version(contract, service_date)
          → build_contract_pricing_config_from_db(contract, version, service_date)
          → for line: LineOrchestrator.run(contract, inp, version=version, config=config)
          → _apply_carveout per line
          → stop-loss, outlier, blending, caps/floors
          → return ClaimPricingResult
    → ClaimPricingResultSerializer(result)
  → Response(serializer.data)
```

**Single line (POST /api/price-line/):**

```
PriceLineView.post(request)
  → PricingRequestSerializer(data=request.data).is_valid()
  → _get_contract(data['contract_id'])
  → PricingInput(...)
  → ClaimPricingService().price_line(contract, pricing_input)
    → LineOrchestrator.run(contract, request, version=None, config=None)
      → StrictRuleResolver(contract, version=None, config=None).resolve(request, trace)
      → PricingDataLoader.load_context(request, rule, version=None, config=None)
      → get_methodology(context.methodology_code)
      → strategy.calculate(context)
      → return LineResult
  → PricingResponseSerializer(result)
  → Response(serializer.data)
```

**Batch claim (POST /api/price-claim/):**

```
PriceClaimView.post(request)
  → PricingClaimRequest(data=request.data).is_valid()
  → _get_contract(data['contract_id'])
  → ClaimPricingInput(...)
  → ClaimPricingService().price_claim(claim_input)
    → ClaimOrchestrator.run(claim_input, config=None)
      → resolve_active_contract_version(contract, service_date)
      → build_contract_pricing_config_from_db(contract, version, service_date)
      → for line: LineOrchestrator.run(..., version=version, config=config) + _apply_carveout
      → stop-loss, outlier, blending, caps/floors
      → return ClaimPricingResult
  → ClaimPricingResultSerializer(result).data + request_time_ms
  → Response(response_data)
```

**Bulk (POST /api/price-claims-bulk/):**

```
BulkPriceClaimsView.post(request)
  → BulkPricingClaimRequest(data=request.data).is_valid()
  → for each claim_data: _get_contract(contract_id), build ClaimPricingInput
  → ClaimPricingService().price_claims_bulk(claim_inputs)
    → per claim: version_cache (contract_pk, service_date), config_cache (contract_pk, version_pk, service_date)
    → ClaimOrchestrator.run(claim_input, config=config) for each
  → BulkPricingResultSerializer({ total_claims, priced_claims, results, request_time_ms })
  → Response(response_data)
```

---

## 12. Observations / Gaps

- **Canonical order vs actual:**  
  - **Carve-outs:** Implemented; applied per line after base methodology in `ClaimOrchestrator.run()`.  
  - **Blending:** Implemented; applied after stop-loss/outlier.  
  - **Caps/floors:** Implemented; applied after blending (final clamp).  
  - **Modifier application:** Inside each strategy’s `calculate()` via `apply_modifiers()`, not a separate orchestrator step.

- **Two pricing paths for “claim”:**  
  - **Stored claim:** `ClaimPriceView` → `price_stored_claim(claim)` → `price_claim(claim_input)` → `ClaimOrchestrator.run(claim_input, config=None)` (full flow).  
  - **Batch ad-hoc:** `PriceClaimView` → `price_claim(claim_input)` → same `ClaimOrchestrator.run(claim_input, config=None)`. Both use version resolution, config build, line pricing, carve-outs, stop-loss, outlier, blending, caps/floors.

- **Single-line path:** `PriceLineView` → `price_line(contract, pricing_input)` only calls `LineOrchestrator.run(..., version=None, config=None)`. No version resolution; resolver filters `version__isnull=True`, so only contract-level rules (no version) apply. To get a match for price-line, the rule must have `version_id` null.

- **Contract resolution:** Only used when pricing a **stored** claim whose `contract_id` is null. Price-line, price-claim, simulate, and bulk require the client to supply `contract_id`; they do not call `resolve_contract_for_claim()`.

- **Snapshot:** Not used on the pricing path. GET /api/contracts/<id>/snapshot/ is separate. Bulk uses its own config cache inside the service.

- **PER_LINE outlier:** Not implemented; raises NotImplementedError if evaluated.

- **N+1 / performance:** Stored-claim path uses `prefetch_related('lines')` to avoid repeated line queries. Bulk path caches config per (contract, version, service_date). Per-line loader may still issue multiple reference-data queries unless execution cache is used.

---

## 13. Testing & Seed Data Recipes

### 13.1 JSON payload schemas for API endpoints

All request bodies are JSON. Content-Type: `application/json`.

---

**POST /api/price-line/**

Request:

```json
{
  "contract_id": "<string or int: legacy_contract_number or contract PK>",
  "procedure_code": "<string, required>",
  "billed_amount": "<decimal string or number, required>",
  "units": 1,
  "modifiers": ["<string, max 5 chars>"],
  "service_date": "YYYY-MM-DD",
  "claim_type": "<string, optional>",
  "pricing_date": "YYYY-MM-DD",
  "contract_effective_date": "YYYY-MM-DD"
}
```

Required: `contract_id`, `procedure_code`, `billed_amount`.  
Optional: `units` (default 1), `modifiers` (default []), `service_date`, `claim_type`, `pricing_date`, `contract_effective_date`.

Response: Single line result (status, allowed_amount, methodology, details, contract_id, rule_id, trace_id, execution_time_ms, etc.).

---

**POST /api/price-claim/**

Request:

```json
{
  "contract_id": "<string or int>",
  "lines": [
    {
      "procedure_code": "<string>",
      "billed_amount": "<decimal>",
      "units": 1,
      "modifiers": [],
      "cost_amount": "<decimal or null>",
      "service_date": "YYYY-MM-DD",
      "pricing_date": "YYYY-MM-DD",
      "contract_effective_date": "YYYY-MM-DD"
    }
  ],
  "service_date": "YYYY-MM-DD",
  "pricing_date": "YYYY-MM-DD",
  "contract_effective_date": "YYYY-MM-DD"
}
```

Required: `contract_id`, `lines` (at least one element). Each line requires `procedure_code`, `billed_amount`. Optional per line: `units` (default 1), `modifiers`, `cost_amount`, dates. Optional at top level: `service_date`, `pricing_date`, `contract_effective_date` (apply to all lines when not set per line).

Response: ClaimPricingResult (claim_id, contract_id, total_allowed, line_count, lines[], status, claim_trace, original_total_allowed, final_total_allowed, applied_outlier_rule_id, applied_stop_loss_rule_id, request_time_ms, etc.).

---

**POST /api/price-claim-simulate/**

Request:

```json
{
  "contract_id": <integer, PK of contract>,
  "version_id": <integer, PK of contract version>,
  "claim": {
    "lines": [
      {
        "procedure_code": "<string>",
        "billed_amount": "<decimal>",
        "units": 1,
        "modifiers": []
      }
    ],
    "service_date": "YYYY-MM-DD",
    "pricing_date": "YYYY-MM-DD"
  }
}
```

Required: `contract_id`, `version_id`, `claim`. `claim` must have `lines` (same shape as price-claim). Optional in `claim`: `service_date`, `pricing_date`. Version must belong to contract; status must be DRAFT, ACTIVE, or SUPERSEDED (ARCHIVED rejected).

Response: `{ "version_id": <int>, "simulation": true, "result": <ClaimPricingResult serialized> }`. On error: 400 with `{ "error": "<message>" }`.

---

**POST /api/price-claims-bulk/**

Request:

```json
{
  "claims": [
    {
      "contract_id": "<string or int>",
      "lines": [
        {
          "procedure_code": "<string>",
          "billed_amount": "<decimal>",
          "units": 1,
          "modifiers": []
        }
      ],
      "service_date": "YYYY-MM-DD",
      "pricing_date": "YYYY-MM-DD",
      "claim_type": "<string>"
    }
  ]
}
```

Required: `claims` (array, length 1–500). Each element same shape as one price-claim request (contract_id, lines, optional service_date, pricing_date, claim_type).

Response: `{ "total_claims": <int>, "priced_claims": <int>, "results": [<ClaimPricingResult>, ...], "request_time_ms": <float> }`.

---

**GET or POST /api/claims/<pk>/price/**

No request body (pk in URL). Response: ClaimPricingResult serialized (same as price-claim response, without request_time_ms unless added by view).

---

### 13.2 Step-by-step recipe: Django Admin records for a positive pricing result (avoid DENIED_NO_RULE)

Use **POST /api/price-claim/** so that version is resolved and the full config (including version-scoped rules) is used. The service date must fall within the contract version and rule effective dates, and the line’s `procedure_code` must match a rule condition.

**Assumptions:** You have at least one **Provider organization** and one **Payer network** already (or create them below). Reference tables (e.g. `ref_cpt_hcpcs_codes`, `ref_modifiers`) may be empty for a FLAT_RATE-only test; the engine does not require the procedure code to exist in ref tables for FLAT_RATE.

**Step 1 – Provider organization (if needed)**  
- In Django Admin: **Core → Provider organizations → Add**.  
- **Organization id:** e.g. `TEST-PROV`.  
- **Name:** e.g. `Test Provider`.  
- **Tax id:** optional.  
- Save.

**Step 2 – Payer organization (if needed)**  
- **Core → Provider organizations → Add** (payer is also a provider org in this schema).  
- **Organization id:** e.g. `TEST-PAYER`.  
- **Name:** e.g. `Test Payer`.  
- Save.

**Step 3 – Payer network**  
- **Core → Payer networks → Add**.  
- **Network id:** e.g. `TEST-NET`.  
- **Network name:** e.g. `Test Network`.  
- **Payer org:** select the payer organization (e.g. TEST-PAYER).  
- Save.

**Step 4 – Provider contract**  
- **Core → Contracts → Add** (or **Provider contracts**, depending on admin label).  
- **Contract name:** e.g. `Test Contract`.  
- **Legacy contract number:** e.g. `TEST-CON-001` (used by `_get_contract()` when resolving by identifier).  
- **Provider org:** select the provider organization (e.g. TEST-PROV).  
- **Network:** select the payer network (e.g. TEST-NET).  
- **Status:** e.g. `ACTIVE`.  
- **Effective start date:** e.g. `2026-01-01`.  
- **Effective end date:** leave blank or e.g. `2026-12-31`.  
- Save. Note the **contract_id** (PK).

**Step 5 – Contract version**  
- **Core → Contract versions → Add**.  
- **Contract:** select the contract from Step 4.  
- **Version number:** `1`.  
- **Effective start date:** `2026-01-01` (must be <= service_date you will send).  
- **Effective end date:** blank or `2026-12-31` (must be >= service_date if set).  
- **Status:** `ACTIVE` (so `resolve_active_contract_version` returns this version).  
- Save. Note the **version_id** (PK).

**Step 6 – Pricing rule**  
- **Core → Pricing rules → Add**.  
- **Contract:** same contract.  
- **Version:** the version from Step 5 (so the rule is used when pricing with that version).  
- **Rule name:** e.g. `Flat 99213`.  
- **Rule type:** `BASE`.  
- **Methodology code:** `FLAT_RATE`.  
- **Flat rate:** e.g. `150.00` (allowed amount will be flat_rate × units).  
- **Status:** `ACTIVE`.  
- **Effective start date:** `2026-01-01`.  
- **Effective end date:** blank or `2026-12-31`.  
- **Specificity score:** e.g. `10`.  
- **Base fee schedule:** leave blank (not required for FLAT_RATE).  
- Save. Note the **rule_id** (PK).

**Step 7 – Pricing rule condition**  
- **Core → Pricing rule conditions → Add**.  
- **Pricing rule:** the rule from Step 6.  
- **Attribute name:** `procedure_code`.  
- **Operator:** `EQ`.  
- **Attribute value:** `99213` (must exactly match the procedure_code you send in the request).  
- Save.

**Step 8 – Send request**  
- **URL:** `POST /api/price-claim/`  
- **Body (JSON):**

```json
{
  "contract_id": "<contract_id from Step 4 or legacy_contract_number 'TEST-CON-001'>",
  "lines": [
    {
      "procedure_code": "99213",
      "billed_amount": "200.00",
      "units": 1
    }
  ],
  "service_date": "2026-06-01"
}
```

- **Expected:** HTTP 200. Response `total_allowed` = `150.00` (one line, FLAT_RATE 150 × 1). Each line in `lines` has `status` = `"SUCCESS"` (or equivalent enum value). No `DENIED_NO_RULE` for that line.

**Checklist to avoid DENIED_NO_RULE**

1. Contract exists and is resolvable by `contract_id` (PK or legacy_contract_number).  
2. At least one **Contract version** for that contract with **Status = ACTIVE** and **effective_start_date** ≤ **service_date** and (effective_end_date null or ≥ service_date).  
3. At least one **Pricing rule** for that contract with **Status = ACTIVE**, **methodology_code** set (e.g. FLAT_RATE), **effective_start_date** ≤ service_date, (effective_end_date null or ≥ service_date), and either **version** = that ACTIVE version or **version** null (for contract-level rule).  
4. At least one **Pricing rule condition** on that rule: **attribute_name** = `procedure_code`, **operator** = `EQ`, **attribute_value** = the exact procedure code you send (e.g. `99213`).  
5. For FLAT_RATE: **flat_rate** set on the rule. For RBRVS/DRG/etc. ensure methodology and any required reference data (fee schedule, base rate, ref tables) exist and are loadable by the loader for that methodology.

**Single-line endpoint (POST /api/price-line/)**  
- Resolver is called with `version=None` and `config=None`, so only rules with **version** = null are considered. To get a match on price-line, create a rule with **Version** left blank (contract-level rule) and the same procedure_code condition and methodology (e.g. FLAT_RATE + flat_rate). Then send the same `contract_id`, `procedure_code`, `billed_amount`, `units`, and `service_date` in the price-line request.
