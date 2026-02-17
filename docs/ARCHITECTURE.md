# Architecture: How the Orchestrator Talks to the Models

This document maps how the **PricingEngine** orchestrator in `core/engine/orchestrator.py` uses Django models and the rest of the engine. No code changes—reference only.

---

## High-Level Flow

1. **Entry**: `PricingEngine.calculate_line(contract: ProviderContract, request: PricingInput) -> LineResult`
2. **Resolver** (uses DB) → picks one **PricingRule** for the request.
3. **Loader** (uses DB) → builds **PricingContext** from that rule and reference data.
4. **Strategy** (pure math) → returns allowed amount.
5. **Orchestrator** wraps the result in **LineResult** (with trace, contract_id, rule_id).

---

## Orchestrator → Components

| Component | Module | What the orchestrator does |
|-----------|--------|-----------------------------|
| **StrictRuleResolver** | `core/engine/resolver.py` | Constructs `StrictRuleResolver(contract)`, then calls `resolve(request, trace)`. Gets back a **PricingRule** or `None`. |
| **PricingDataLoader** | `core/engine/loader.py` | Calls `self.loader.load_context(request, rule)`. Gets back a **PricingContext** (dataclass). |
| **Strategy** | `core/engine/strategies/` | Calls `get_methodology(rule.methodology_code)` then `strategy.calculate(context)`. Gets back a **Decimal** price. |

The orchestrator **only** talks to:
- The **contract** (Django model instance passed in).
- **Resolver** and **Loader** (which in turn query the DB).
- **Strategies** (which receive only the context, no direct DB access).

---

## Resolver → Models

- **Reads**: `ProviderContract` (passed in), **PricingRule**, **PricingRuleCondition** (via `rule.conditions`).
- **Queries**: `PricingRule.objects.filter(contract=self.contract, is_active=1).order_by('-specificity_score').prefetch_related('conditions')`.
- **Returns**: One **PricingRule** instance or `None`. No other models are touched here.

---

## Loader → Models

- **Reads**: **PricingRule** (and its FKs: `rule.contract`, `rule.base_fee_schedule`), **PricingInput**.
- **Queries**:
  - **FeeScheduleRate**: by `fee_schedule` and `code_id` (procedure_code) for base rates and DRG weights.
  - **RefProcedureCode**: for DRG weight (e.g. `work_rvu` used as weight).
  - **RefModifier**: for modifier codes and `percentage_adjustment`.
- **Returns**: A **PricingContext** dataclass (from `core/engine/types.py`) populated with rule metadata, rates, and modifier adjustments. No model instances are returned to the orchestrator.

---

## Strategies → No Models

- Strategies take **PricingContext** only and perform arithmetic.
- They do **not** import or query Django models. All data is pre-loaded by the **Loader**.

---

## API Layer → Orchestrator

- **Views** (`core/api/views.py`): **PriceLineView** receives JSON, validates with **PricingRequestSerializer**, loads **ProviderContract** (by `legacy_contract_number` when `contract_id` is provided), builds **PricingInput**, calls `PricingEngine().calculate_line(contract, pricing_input)`, then serializes the **LineResult** with **PricingResponseSerializer**.
- **URLs**: `POST /api/price-line/` and `GET /api/contracts/` are wired in `core/api/urls.py` and included under `config/urls.py` at `api/`.

---

## Model Summary (Used by Engine / API)

| Model | Used by | Purpose |
|-------|---------|---------|
| ProviderContract | Orchestrator (in), Resolver, API | Contract for pricing; API loads it for each request. |
| PricingRule | Resolver, Loader | Rule to apply; methodology and parameters. |
| PricingRuleCondition | Resolver | Trigger conditions (e.g. procedure_code) for rule match. |
| FeeSchedule | Loader (via rule.base_fee_schedule) | Links rule to fee schedule. |
| FeeScheduleRate | Loader | Procedure code → rate (and DRG weight source). |
| RefProcedureCode | Loader | RVUs / DRG weights. |
| RefModifier | Loader | Modifier code → percentage adjustment. |
| ProviderOrganization, PayerNetwork | Via ProviderContract FKs | Organization and network identity. |
