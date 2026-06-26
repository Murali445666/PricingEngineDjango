# Project Status: Matrix Pricing Engine

> **Canonical status** for PricingEngineDjango. **Roadmap:** [ROADMAP.md](ROADMAP.md) · **Upgrade plan (detail):** [UPGRADE_PLAN.md](UPGRADE_PLAN.md) · **PRD:** [PRD.md](PRD.md) · **Testing:** [testing/](testing/)

**Active roadmap:** [ROADMAP.md](ROADMAP.md) — architecture alignment upgrade (Stages 0–6). Historical delivery (Phases 1–8, refactor A–G, engine Step 14a) is recorded below.

Scope: **PricingEngineDjango** only. "Pricing Engine V2" folder is out of scope.

---

## Architecture Alignment Upgrade (Stages 0–6) — **NOT STARTED**

Staged backend work to align data model and APIs with the System Architecture Design. Full specs: [UPGRADE_PLAN.md](UPGRADE_PLAN.md). Stage breakdown: [ROADMAP.md](ROADMAP.md).

| Stage | Name | Status | Notes |
|-------|------|--------|-------|
| 0 | Engine hygiene | **Not started** | Replace 14 `print()` calls in `core/engine/orchestrator.py` with `logging`; add `LOGGING` in settings |
| 1 | Provider domain | **Not started** | New app `providers/` — Provider, Facility, affiliations, network participation |
| 2 | Payer / Product / LOB / Network | **Not started** | New app `products/` — PayerOrganization, Product, Network, ContractProductScope |
| 3 | Member / Enrollment + ClaimHeader | **Not started** | New app `members/` — Member, Enrollment; nullable FKs on ClaimHeader |
| 4 | Pricing Context Resolver | **Not started** | `PricingContextResolver`, DTOs, `GET /api/resolve-context/` (debug); flag `FEATURE_CONTEXT_RESOLVER` |
| 5 | Context-driven pricing APIs | **Not started** | `/api/reprice-claim/`, `/api/price-claim-by-provider/`, batch + lookup endpoints; flags `FEATURE_REPRICE_API`, enable `FEATURE_TIERED_RESOLUTION` |
| 6 | UI enhancements | **Deferred** | Separate UI plan — uses Stage 5 endpoints when available |

**Gate for every stage:** all 43 existing tests pass; all existing API endpoints unchanged.

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
| Docs | Runbook | [RUNBOOK.md](RUNBOOK.md). |

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

## Phase 5 — Pricing Simulation & Contract Testing Workbench — **IN PROGRESS**

| Deliverable | Status | Notes |
|-------------|--------|-------|
| **5a – Claim Simulation page (first slice)** | Complete | See Step 12f below; `/claim-simulation` + `POST /api/price-claim-simulate/`. |
| Simulation execution mode | Not started | Separate from production. |
| Batch simulation services | Not started | Bulk simulation APIs. |
| Scenario persistence | Not started | Save/load test scenarios. |
| UI: Full workbench | Not started | Upload test claim sets, compare expected vs calculated, trace drill-down. |

### Next Immediate UI/UX Deliverables (Portfolio)

Portfolio UI deliverables (12a / 12c / 12e / 12f) — no engine change; independent of architecture upgrade Stages 0–6.

- **12f Claim Simulation** — **Complete (first slice).** `/claim-simulation`: contract + version (explorer), claim JSON editor, **Load example** for DRG 470 / RBRVS 99213 / FLAT 00100 / PCT 99213, Run → `POST /api/price-claim-simulate/`. **Accept:** summary (totals, status badge, applied_* IDs, optional `request_time_ms`), line table, execution trace, claim trace; inline JSON errors; API errors via alert + banner; Copy cURL / Download result JSON. Scenario persistence / batch: TODO.
- **12c Rule simulate + conflicts** — **Complete (UI slice).** Rule create (`/contracts/:id/rules/new`) and rule detail (`/rules/:id`): **Simulate line** (`POST /api/price-line/` with `trace_logs`, or `POST /api/simulate-line/` with draft for unsaved / DRAFT rules) and **Check conflicts** (`POST /api/rules/check-conflicts/`, optional `exclude_rule_id` on detail). **Accept:** pre-save simulate; conflict list before save.
- **12a Governance badges & panel** — *Planned.* Status/conflict on contract & rule views. **Accept:** badges + drill to conflicts/history.
- **12d Bulk validation** — **Complete.** `POST /api/validate-contracts/bulk/` (cap 100, optional `?save=1`); React contracts list **Run bulk validation** modal. Tests: `tests/test_12d_bulk_validation.py`.
- **12e Contract Explorer** — **Complete.** `GET /api/contracts/<id>/explorer/` returns `contract` {id, legacy_contract_number, contract_name}, `open_conflict_counts` {errors, warnings}, `versions[]` with `rules[]` (conditions nested). CSV: `?export=csv` (not `format=`, reserved by DRF). UI: **Explorer** tab on contract detail + `/contract-explorer`; Download JSON/CSV; `core.tests.test_contract_explorer` + query budget test.
- **Demo seeds & examples (12f)** — *Planned.* DRG/RBRVS/% billed fixtures/docs. **Accept:** reproducible without ad hoc SQL.
- **Trace drill-down (12f)** — *Planned.* Richer simulate traces. **Accept:** per-line / expandable, demo-ready.

**UI note:** [archive/UI_DELIVERABLES_STATUS.md](archive/UI_DELIVERABLES_STATUS.md) — Claim Simulation (12f) examples + summary fields + empty state; Conflicts panel (12a) title/import cleanup; see `frontend/README.md`.

**Engine policy track (historical Step 14):** advanced payer behaviors below. Domain prerequisites (product, network, member context) are covered by upgrade Stages 1–5 in [ROADMAP.md](ROADMAP.md).

---

## Phase 6 — Advanced payer contract policy (engine) — **IN PROGRESS**

Large-payer behaviors: product/plan and network tiers, universal lesser-of, ordered modifier math, reusable code sets, surgical/global bundles, program-wide cuts, and adjudication audit binding. **14a** is complete (flagged); remaining items are not started. Line-level lesser-of today uses **LINE `PCT_BILLED_CAP`** (Phase G); claim total rollup for capped lines is fixed in orchestrator.

| Feature | Business / problem | Technical touchpoints | Status |
|--------|-------------------|------------------------|--------|
| **Tiered contract resolution & tier multipliers (14a)** | Rates vary by product (e.g. PPO vs Medicaid) and network tier; wrong tier misroutes to the wrong table. | **Schema:** `ContractVersion.product_id`, `tier_priority`; `TierMultiplier`; migration `0032_step14a_tiered_resolution`. **Engine (flag `FEATURE_TIERED_RESOLUTION`, default off):** resolver product filter + `tier_priority` sort; loader tier multiplier defaults + trace `[TIER_MULTIPLIER]`; optional `product_id` / `network_id` on claim and simulate payloads. **Tests:** `tests/test_step14a_tiered_resolution.py`. | **Complete (flagged)** |
| **Default lesser-of (billed vs allowed)** | Standard policy: pay min(contracted allowed, billed); inconsistent application drives overpayments/recoupments. | Config flag per contract/version/methodology (default ON); after modifiers/adjustments: `allowed = min(calculated_allowed, billed_amount)`; **LINE** trace when clamp applies. | Not started |
| **Modifier matrix (ordering & math types)** | Multiple modifiers must stack in policy order with correct math (multiply, add, flat); ad hoc stacking causes disputes. | `ModifierRule`: modifier_code, order, math_type (MULTIPLY / ADD / FLAT), value, optional code filters, effective dates, contract/version; engine sorts and applies; trace one entry per applied modifier (pre/post amounts). | Not started |
| **Code-group authoring (reuse & CSV import)** | Enterprise contracts need curated code sets; single-code rules are brittle. **Resolver already supports `code_group` conditions** (phased plan C — complete). | **UI**: condition builder selects a `CodeGroup` or CSV import to create/update groups (effective-dated); **engine**: ensure DOS locks group version; trace logs group_id/version; **governance**: conflict checks for overlapping groups on same contract/version/tier. | Not started (authoring/governance) |
| **Global / bundled period logic** | e.g. CPT 99024 within global window must pay $0 or alternate rate; per-line-only logic double-pays. | `GlobalPackage`: anchor_code, related_code or group, window_days, pricing_action (ZERO / ALT_RATE), contract/version, effective dates; **pre-pricing** hook on same-claim lines before main line pricing; **LINE** trace; cross-claim windowing later. | Not started |
| **Global adjustments layer** | Program cuts / sequestration after contract math; without a dedicated layer, application is opaque and error-prone. | `GlobalAdjustment`: scope (program / product / network), percent or flat, priority, effective dates; apply **after** caps/floors (post current canonical step 10); **CLAIM**-stage trace with adjustment_id and factor. | Not started |
| **Retro version lock & config snapshot** | Late-loaded rates must not re-price old DOS; auditors need proof of config used. | Bind pricing to version/config effective on DOS; persist `config_hash` or `snapshot_id` on pricing result; reprocessing: explicit rebind vs keep original snapshot. Touches claim pricing APIs and stored results — coordinate with **Step 4** / **Step 6** snapshot patterns. | Not started |

---

## Phase 7 — Enterprise Execution & Performance Layer — **NOT STARTED**

- Batch pricing execution services, async job queues, caching, performance telemetry.
- UI: Execution monitoring dashboard, batch job tracking, throughput/latency metrics.

---

## Phase 8 — Platform Integration & Productization — **NOT STARTED**

- Multi-tenant contract support, API gateway routing, versioned pricing services, SLA monitoring.
- UI: Tenant/client configuration, service version management, integration dashboards.

---

## Phased Refactor Plan (A–G) — see [archive/phased_refactor_plan.md](archive/phased_refactor_plan.md)

| Phase | Name | Status |
|-------|------|--------|
| A | ExecutionContext + Unified Trace | **COMPLETE** |
| B | ContractTerm (multipliers off rule) | **COMPLETE** |
| C | CodeGroup + Resolver (code_group, revenue_code) | **COMPLETE** |
| D | Reference-only pricing (no rule.multiplier/flat_rate) | **COMPLETE** — migration 0028, loader flag `USE_REFERENCE_ONLY_PRICING`, see [testing/phase_d_test_summary.md](testing/phase_d_test_summary.md) |
| E | Claim-level methodology registry | **COMPLETE** — FacilityBaseRate, CaseRateDefinition, claim_level_drg_enabled, DRG plugin, see [testing/phase_e_test_summary.md](testing/phase_e_test_summary.md) |
| F | Cross-line (MPPR) | **COMPLETE** — MPPRDefinition, MPPRScope, CROSS_LINE phase before blending, see [testing/phase_f_test_summary.md](testing/phase_f_test_summary.md) |
| G | Line & claim cap/floor hardening | **COMPLETE** — LINE_CAP_FLOOR stage, line_cap_floors in config, trace; see [testing/phase_g_test_summary.md](testing/phase_g_test_summary.md) |

---

## Summary Table

| Phase | Name | Status |
|-------|------|--------|
| 1 | Core Engine Stabilization | **COMPLETE** |
| 2 | API Layer & Pricing Execution Services | **COMPLETE** |
| 3 | Analyst Rule Visibility & Governance UI | **COMPLETE** |
| 4 | Rule Authoring & Condition Builder UI | **IN PROGRESS** |
| 5 | Pricing Simulation & Contract Testing Workbench | **IN PROGRESS** (12f first slice complete — see Phase 5 above) |
| 6 | Advanced payer contract policy (engine) | **IN PROGRESS** — **14a** complete behind `FEATURE_TIERED_RESOLUTION`; see Phase 6 above |
| — | Architecture alignment upgrade (Stages 0–6) | **NOT STARTED** — [ROADMAP.md](ROADMAP.md) · [UPGRADE_PLAN.md](UPGRADE_PLAN.md) |
| 7 | Enterprise Execution & Performance Layer | Not started |
| 8 | Platform Integration & Productization | Not started |
