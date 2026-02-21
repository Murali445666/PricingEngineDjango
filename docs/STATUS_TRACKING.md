# Status Tracking: Matrix Pricing Engine (PricingEngineDjango)

Scope: **PricingEngineDjango** only. "Pricing Engine V2" folder is out of scope.

Status is aligned to the [Master Roadmap](../ROADMAP.md). See [STATUS.md](../STATUS.md) for a short phase summary.

---

## Phase 1 — Core Engine Stabilization — **COMPLETE**

| Area | Item | Notes |
|------|------|------|
| Core domain | Orchestrator | `PricingEngine.calculate_line(contract, PricingInput)` in `core/engine/orchestrator.py`. |
| Core domain | StrictRuleResolver | Best-match rule by `specificity_score`; uses PricingRule + PricingRuleCondition. |
| Core domain | PricingDataLoader | Builds PricingContext from FeeScheduleRate, RefProcedureCode, RefModifier. |
| Core domain | Strategies | RBRVS, FLAT_RATE, PERCENT_BILLED, STOP_LOSS, DRG, PER_DIEM, ANESTHESIA in `core/engine/strategies/`. |
| Core domain | Types | PricingInput, LineResult, PricingContext, PricingTrace in `core/engine/types.py`. |
| Database | Schema & migrations | ProviderOrganization, PayerNetwork, ProviderContract, PricingRule, PricingRuleCondition, FeeSchedule, FeeScheduleRate, RefProcedureCode, RefModifier. |
| Database | Seeding | Management commands / seed scripts (e.g. seed_matrix). |
| Tests | Engine tests | Tests in `tests/` using MatrixPricingEngine helper (RBRVS, modifiers, DRG, anesthesia, etc.). |

---

## Phase 2 — API Layer & Pricing Execution Services — **COMPLETE**

| Area | Item | Notes |
|------|------|------|
| API | DRF & CORS | rest_framework and corsheaders in INSTALLED_APPS; CORS allowed for Vite dev (localhost:5173). |
| API | Serializers | PricingRequestSerializer, PricingResponseSerializer, ContractSerializer, PricingClaimRequest/Line, ClaimResponse in `core/api/serializers.py`. |
| API | Single-line pricing | PriceLineView, POST `/api/price-line/`. |
| API | Multi-line pricing | PriceClaimView, POST `/api/price-claim/`; returns total_allowed, lines, contract_id. |
| API | Contract lookup | GET `/api/contracts/`; _get_contract() supports PK and legacy_contract_number. |
| API | Request timing | RequestTimingMiddleware; X-Request-Duration-Ms header; logger `pricing_engine.request_timing`. |
| Tests | API integration | tests/test_api_multiline.py: batch pricing, empty lines, 404. |
| UI | Django sandbox | `/sandbox/` template posts to `/api/price-line/`, displays JSON. |
| UI | React platform | frontend/: Vite, React, TS, Tailwind, React Router, TanStack Query; layout, routes, shared UI; Pricing Sandbox (live), Contracts/Rules (later wired to API). |
| Docs | Runbook | docs/RUNBOOK.md. |

**Optional / later:** DTO versioning, authentication.

---

## Phase 3 — Analyst Rule Visibility & Governance UI — **COMPLETE**

| Area | Item | Notes |
|------|------|------|
| API | Rules list | GET `/api/rules/` (RuleListView); optional ?status= and ?contract_id= filter. |
| API | Rule detail | GET `/api/rules/<pk>/` (RuleDetailView) with conditions. |
| API | Contract detail | GET `/api/contracts/<pk>/`, GET `/api/contracts/<pk>/rules/`. |
| API | Rule history | GET `/api/rules/<rule_id>/history/` (RuleHistoryView). |
| Serializers | Rule list/detail | RuleListSerializer, RuleDetailSerializer, RuleConditionSerializer, ContractDetailSerializer, RuleHistorySerializer. |
| Database | Rule lifecycle | PricingRule.status: DRAFT, ACTIVE, RETIRED (TextChoices); default DRAFT. |
| Database | Audit | RuleHistory model + signals (core/signals.py) on status change; migration 0003_rulehistory. |
| UI | Contracts page | Real API; link to contract detail. |
| UI | Contract detail page | Contract metadata + DataTable of rules with link to rule detail. |
| UI | Rules page | Real API; status filter dropdown; StatusBadge (Draft/Active/Retired). |
| UI | Rule detail page | Rule fields, conditions table, Audit History table, status change dropdown (updateRuleStatus), query invalidation on success. |

---

## Phase 4 — Rule Authoring & Condition Builder UI — **IN PROGRESS**

| Area | Item | Status | Notes |
|------|------|--------|------|
| Backend | Condition schema | Done | core/engine/condition_schema.py; allowed attribute names and operators (EQ); validation in serializers. |
| Backend | Write APIs | Done | POST `/api/contracts/<pk>/rules/` (create), PATCH `/api/rules/<pk>/` (update); RuleCreateSerializer, RuleUpdateSerializer, nested conditions. |
| Backend | Fee schedules API | Done | GET `/api/fee-schedules/`. |
| Backend | Effective dates | Done | effective_start_date (required), effective_end_date (optional) on rule create/update; migration 0004. |
| Frontend | Rule create wizard | Done | RuleCreatePage: basics (name, type, methodology, effective dates), ConditionBuilder, ParameterEditor, Save as Draft. |
| Frontend | Condition builder | Done | ConditionBuilder.tsx: attribute dropdown, EQ, value input; add/remove rows. |
| Frontend | Parameter editor | Done | ParameterEditor.tsx: RBRVS (multiplier, fee schedule), FLAT_RATE (flat rate). |
| Frontend | Routing & entry | Done | contracts/:contractId/rules/new; "Create New Rule" on ContractDetailPage. |
| Frontend | Status editing | Done | Rule detail: Change Status dropdown; updateRuleStatus mutation; invalidate rule + history. |
| Backend | Conflict validation | Not done | rule_conflict.py service; GET/POST conflicts API. |
| Backend | Draft simulation | Not done | POST `/api/simulate-line/`; core/engine/simulation.py. |
| Frontend | Conflict warning | Not done | Display conflict messages in wizard. |
| Frontend | Rule Simulator UI | Not done | RuleSimulatorPage still placeholder; wire to simulate-line when backend exists. |
| Frontend | Rule edit page | Optional | RuleEditPage at rules/:id/edit; PATCH already supported. |

---

## Phase 5 — Pricing Simulation & Contract Testing Workbench — **NOT STARTED**

- Simulation execution mode separate from production.
- Batch simulation services.
- Scenario persistence.
- UI: Contract simulation dashboard, upload test claim sets, compare expected vs calculated, trace drill-down.

---

## Phase 6 — Enterprise Execution & Performance Layer — **NOT STARTED**

- Batch pricing execution services, async job queues, caching, performance telemetry.
- UI: Execution monitoring dashboard, batch job tracking, throughput/latency metrics.

---

## Phase 7 — Platform Integration & Productization — **NOT STARTED**

- Multi-tenant contract support, API gateway routing, versioned pricing services, SLA monitoring.
- UI: Tenant/client configuration, service version management, integration dashboards.

---

## Summary Table

| Phase | Name | Status |
|-------|------|--------|
| 1 | Core Engine Stabilization | **COMPLETE** |
| 2 | API Layer & Pricing Execution Services | **COMPLETE** |
| 3 | Analyst Rule Visibility & Governance UI | **COMPLETE** |
| 4 | Rule Authoring & Condition Builder UI | **IN PROGRESS** |
| 5 | Pricing Simulation & Contract Testing Workbench | Not started |
| 6 | Enterprise Execution & Performance Layer | Not started |
| 7 | Platform Integration & Productization | Not started |
