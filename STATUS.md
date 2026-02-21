# Project Status: Matrix Enterprise Healthcare Pricing Engine

Status is aligned to the [Master Roadmap](ROADMAP.md).

| Phase | Name | Status |
|-------|------|--------|
| **1** | Core Engine Stabilization | **COMPLETE** |
| **2** | API Layer & Pricing Execution Services | **COMPLETE** |
| 3 | Analyst Rule Visibility & Governance UI | Not started |
| 4 | Rule Authoring & Condition Builder UI | Not started |
| 5 | Pricing Simulation & Contract Testing Workbench | Not started |
| 6 | Enterprise Execution & Performance Layer | Not started |
| 7 | Platform Integration & Productization | Not started |

---

## Phase 1 — COMPLETE

- PricingContext, LineResult, and rule metadata schemas finalized in `core/engine/types.py`.
- Resolver is metadata-driven (PricingRuleCondition, specificity_score) in `core/engine/resolver.py`.
- Strategy interfaces standardized; strategies are pluggable and tested in `core/engine/strategies/`.
- Validation, structured tracing (PricingTrace), and error status handling (PricingStatus) in place.

---

## Phase 2 — COMPLETE

- **Done:** Single-line pricing (`POST /api/price-line/`), multi-line pricing (`POST /api/price-claim/`), contract lookup (`GET /api/contracts/`), request timing middleware, Django sandbox (`/sandbox/`), React foundational UI (layout, routes, Pricing Sandbox, Contracts/Rules pages, placeholders for Simulator, Batch Monitor, Admin).
- **Remaining (optional / later):** Request/response DTO versioning, authentication; can be addressed in a later phase.
- **React app:** Lives in `frontend/`. Run with `cd frontend && npm run dev` (see [frontend/README.md](frontend/README.md)).
