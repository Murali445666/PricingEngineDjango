# Matrix Platform — Master Roadmap

> **Source plan:** [UPGRADE_PLAN.md](UPGRADE_PLAN.md) · **Architecture reference:** [ARCHITECTURE.md](ARCHITECTURE.md) · **Current progress:** [STATUS.md](STATUS.md)

## Summary

The Matrix pricing platform today has a **complete, production-quality pricing engine** (`core/engine/`), full contract and versioning lifecycle, rule engine (conditions, specificity, staged execution), carve-outs, stop-loss, outlier, MPPR, blending, reference data loaders, and contract validation — with **no engine gaps**. What is missing is **first-class domain modeling and context resolution** aligned to the System Architecture Design: individual providers, facilities, affiliations, network participation, payer/product/LOB/network entities, member enrollment, contract product scoping, and context-driven pricing APIs. Existing models are thin or partial (`ProviderOrganization`, `PayerNetwork`, `ClaimHeader` use bare char fields for NPI and member_id; payer is embedded in `PayerNetwork.payer_org`; LOB is a bare `CharField` on multiple models). The orchestrator still contains **14 live `print()` debug calls** that must be replaced with logging before production use. This roadmap delivers **six backend stages** (plus deferred UI) using **additive migrations only**, **new Django apps for new domains**, and **zero breakage** of the 43 existing tests and all current API endpoints. **Total estimated backend timeline: ~12–16 weeks.** UI work is deferred to a separate plan (Stage 6).

---

## Stage 0 — Engine Hygiene

**Goal:** Make the engine production-safe without changing any pricing behavior.

**Estimated duration:** &lt; 1 day

**Dependencies:** None (immediate).

### New models

| Model | App | Key fields |
|-------|-----|------------|
| — | — | None |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| — | — | None |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| — | — | None |

### Key acceptance criteria

- `grep -n "print(" core/engine/orchestrator.py` returns 0 results (all 14 `print()` calls replaced with `logger.debug()` via `import logging; logger = logging.getLogger(__name__)`).
- `LOGGING` config added to `config/settings.py` — routes `core.engine` logger to console at DEBUG in dev, INFO in prod.
- All 43 existing tests pass (zero behavior change expected).
- Django dev server starts cleanly.

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes.

---

## Stage 1 — Provider Domain

**Goal:** Add individual provider, facility, affiliation, and network participation models with zero changes to any existing model API surface beyond additive nullable fields on `ProviderOrganization`.

**Estimated duration:** 2–3 weeks

**Dependencies:** Stage 0 complete (recommended first — engine hygiene).

### New models

| Model | App | Key fields |
|-------|-----|------------|
| `Provider` | `providers/` | `npi`, `first_name`, `last_name`, `credential`, `primary_taxonomy`, `primary_specialty` (FK `core.RefSpecialty`), `status` |
| `Facility` | `providers/` | `npi`, `ccn`, `name`, `facility_type`, `place_of_service_codes`, `address_json`, `status` |
| `ProviderOrganization` (extended) | `core/` | `org_type`, `parent_org`, `npi_type` — all nullable, additive only |
| `ProviderAffiliation` | `providers/` | `provider`, `organization`, `role`, `effective_date`, `termination_date` |
| `ProviderNetworkParticipation` | `providers/` | `organization`, `provider`, `network` (FK `core.PayerNetwork`), `status`, `effective_date`, `termination_date`, `specialty_scope` |
| `FacilityNetworkParticipation` | `providers/` | `facility`, `network` (FK `core.PayerNetwork`), `status`, `effective_date`, `termination_date` |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| `ProviderLookupService` | `providers/services.py` | `resolve_org_by_billing_npi`, `resolve_provider_by_rendering_npi`, `resolve_facility_by_npi`, `check_affiliation`, `check_org_network_participation` |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| — | — | None (APIs follow data — no endpoints until underlying models exist) |

### Key acceptance criteria

- `python manage.py migrate` runs cleanly.
- All 43 existing tests pass.
- `ProviderOrganization` existing FKs still work (backward compatible).
- Django admin shows `Provider`, `Facility`, `ProviderAffiliation`, `ProviderNetworkParticipation`.
- `ProviderLookupService.check_affiliation()` returns correct result for seeded test data.
- No changes to `core/engine/` or `core/api/`.

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes.

---

## Stage 2 — Payer / Product / LOB / Network Domain

**Goal:** Add first-class Payer, LOB, Product, and Network models; extend `PayerNetwork` with proper typing; wire `ProviderNetworkParticipation` to the new `Network` model via additive FK.

**Estimated duration:** 2–3 weeks

**Dependencies:** Stage 1 complete (`ProviderNetworkParticipation` exists; participation migrates to `products.Network` in this stage).

### New models

| Model | App | Key fields |
|-------|-----|------------|
| `PayerOrganization` | `products/` | `name`, `payer_id`, `payer_type`, `parent_name` |
| `LineOfBusiness` | `products/` | `code`, `name` |
| `Product` | `products/` | `payer`, `lob`, `name`, `product_code`, `effective_date`, `termination_date` |
| `Network` | `products/` | `payer`, `name`, `network_code`, `network_type`, `legacy_payer_network` (OneToOne `core.PayerNetwork`) |
| `ProductNetworkConfig` | `products/` | `product`, `network`, `claim_type`, `effective_date`, `termination_date` |
| `ContractProductScope` | `core/` | `contract`, `lob_code`, `product`, `effective_date`, `termination_date` |
| `PayerNetwork` (extended) | `core/` | `network_type` — nullable, additive only |
| `ProviderNetworkParticipation` (extended) | `providers/` | `network_new` FK to `products.Network` — nullable; legacy `network` FK to `core.PayerNetwork` retained |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| `NetworkLookupService` | `products/services.py` | `resolve_network(product_id, claim_type, service_date)`, `check_org_participation(org_id, network_id, service_date)` |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| — | — | None |

### Key acceptance criteria

- `python manage.py migrate` runs cleanly.
- All 43 existing tests pass.
- `PayerNetwork` existing FKs on `ProviderContract` unchanged.
- `ContractProductScope` can be created for any contract without breaking existing pricing.
- `NetworkLookupService.resolve_network()` returns correct network for a test product + date.
- Admin shows `PayerOrganization`, `LineOfBusiness`, `Product`, `Network`, `ProductNetworkConfig`, `ContractProductScope`.

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes.

---

## Stage 3 — Member / Enrollment + ClaimHeader Enrichment

**Goal:** Add member and enrollment domain; enrich `ClaimHeader` with typed nullable FK fields for rendering provider, facility, and member.

**Estimated duration:** 2–3 weeks

**Dependencies:** Stage 2 complete (`products.Product` required for `Enrollment` FK).

### New models

| Model | App | Key fields |
|-------|-----|------------|
| `Member` | `members/` | `member_id`, `first_name`, `last_name`, `date_of_birth`, `zip_code`, `subscriber_id`, `relationship_to_subscriber`, `metadata` |
| `Enrollment` | `members/` | `member`, `product`, `effective_date`, `termination_date`, `metadata` |
| `ClaimHeader` (extended) | `core/` | `rendering_provider` (FK `providers.Provider`), `facility` (FK `providers.Facility`), `member` (FK `members.Member`), `billing_npi` — all nullable; existing `npi` CharField retained (not removed) |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| `MemberLookupService` | `members/services.py` | `resolve_enrollment`, `get_product`, `get_lob`, `get_locality_zip` |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| — | — | None |

### Key acceptance criteria

- `python manage.py migrate` runs cleanly.
- All 43 existing tests pass — `ClaimHeader` FK extensions are nullable; no existing test fails.
- `MemberLookupService.resolve_enrollment()` returns correct `Enrollment` for test data.
- `ClaimHeader` can be created with `rendering_provider`, `facility`, `member` FKs populated.
- `ClaimHeader` can still be created without any of those FKs (backward compat).
- Admin shows `Member`, `Enrollment` with inline enrollments on `Member`.

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes.

---

## Stage 4 — Pricing Context Resolver

**Goal:** Build the `PricingContextResolver` service and `ClaimPricingContext` DTO; no production pricing APIs yet — resolver tested via unit tests and an internal debug endpoint only.

**Estimated duration:** 3–4 weeks

**Dependencies:** Stages 1–3 complete (`ProviderLookupService`, `MemberLookupService`, `NetworkLookupService`, `ContractProductScope`).

### New models

| Model | App | Key fields |
|-------|-----|------------|
| — | — | None (DTOs only — additive dataclasses in `core/engine/types.py`) |

**DTOs added to `core/engine/types.py` (existing types unchanged):**

| DTO | Key fields |
|-----|------------|
| `ProviderPricingContext` | `billing_org_id`, `billing_org_tax_id`, `rendering_provider_id`, `rendering_provider_specialty`, `facility_id`, `facility_type`, `place_of_service`, `network_status`, `network_tier`, `affiliation_verified` |
| `MemberPricingContext` | `member_id`, `product_id`, `lob`, `network_id`, `locality_zip`, `enrollment_id` |
| `ClaimPricingContext` | `resolution_mode`, `contract_id`, `version_id`, `provider`, `member`, `service_date`, `pricing_date`, `claim_type`, `lines`, `simulation_mode`, `draft_rule`, `trace_id`, `requested_by` |
| `RawClaimInput` | `billing_npi`, `rendering_npi`, `member_id`, `service_date`, `pricing_date`, `claim_type`, `lines`, `override_contract_id`, `override_network_id` |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| `ContractResolver` | `core/services/contract_resolver.py` | Extracted from `loader.py` `resolve_contract_for_claim()`; resolves `contract_id` by org + network + lob + product scope + service date |
| `PricingContextResolver` | `core/services/pricing_context_resolver.py` | `resolve(raw)` and `resolve_provider_only(raw)` — assembles frozen `ClaimPricingContext` |
| `ClaimPricingService.price_claim_from_context` | `core/engine/service.py` | New entry point consuming fully-resolved context; existing methods unchanged |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/resolve-context/` | Debug only — query params: `billing_npi`, `rendering_npi`, `member_id`, `service_date`, `claim_type`; returns resolved `ClaimPricingContext` JSON without executing pricing |

### Key acceptance criteria

- All 43 existing tests pass.
- `PricingContextResolver.resolve()` correctly resolves contract for a seeded test case with member + provider + network.
- `PricingContextResolver.resolve_provider_only()` works without member context.
- `ContractResolver` produces same results as current `resolve_contract_for_claim()` for direct `contract_id` calls (regression test).
- `ClaimPricingService.price_claim_from_context()` produces identical output to `price_claim()` when given equivalent inputs.
- `/api/resolve-context/` returns correct JSON for a known test case.
- OON path: when no in-network contract found, resolver raises `ContractResolutionError` with `OON` status (engine handles gracefully).

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes.

---

## Stage 5 — Context-Driven Pricing APIs

**Goal:** Expose the resolver via new API endpoints aligned with payer repricing and provider-side pricing use cases; all existing endpoints remain unchanged.

**Estimated duration:** 2–3 weeks

**Dependencies:** Stage 4 complete (`PricingContextResolver`, `ClaimPricingContext`, debug `/api/resolve-context/`).

### New models

| Model | App | Key fields |
|-------|-----|------------|
| — | — | None |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| — | — | No new service classes — views call existing `PricingContextResolver` and `ClaimPricingService` |

**New serializers (per UPGRADE_PLAN):**

| Serializer | Location |
|------------|----------|
| `RawClaimInputSerializer` | `core/api/serializers.py` |
| `RepricingResultSerializer` | `core/api/serializers.py` (extends `ClaimPricingResultSerializer`) |
| `ProviderSerializer` | `providers/` app |
| `ProviderNetworkParticipationSerializer` | `providers/` app |
| `MemberSerializer` | `members/` app |
| `EnrollmentSerializer` | `members/` app |
| `ProductSerializer` | `products/` app |
| `NetworkSerializer` | `products/` app |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/reprice-claim/` | Payer repricing — submit claim with member + provider context; system resolves contract and returns pricing + `resolution_context` |
| `POST` | `/api/price-claim-by-provider/` | Provider-side pricing without member context; `resolution_mode` = `RESOLVED` or `NO_CONTRACT` |
| `POST` | `/api/reprice-claim-batch/` | Batch repricing — multiple claims, context resolved per claim; `max_claims` default cap 500 |
| `GET` | `/api/resolve-context/` | Promoted from Stage 4 internal debug to documented analyst endpoint |
| `GET` | `/api/providers/` | Provider lookup by `npi` or `name` + `specialty` |
| `GET` | `/api/providers/<id>/network-status/` | Network participation check — query params: `network_id`, `service_date` |
| `GET` | `/api/members/<member_id>/enrollment/` | Member enrollment lookup — query param: `service_date` |
| `GET` | `/api/products/` | Product / LOB lookup — query param: `payer_id` |

### Key acceptance criteria

- All 43 existing tests pass (no regressions).
- `POST /api/reprice-claim/` returns correct pricing + resolution context for end-to-end test with seeded member, provider, product, network, and contract.
- `POST /api/price-claim-by-provider/` works without member context.
- `POST /api/reprice-claim-batch/` handles 10 claims and returns correct results.
- `GET /api/providers/?npi=` returns provider record.
- `GET /api/members/<id>/enrollment/?service_date=` returns correct enrollment.
- All new endpoints documented in a Postman collection or API doc.
- OON case: `POST /api/reprice-claim/` with OON provider returns `{ "network_status": "OUT_OF_NETWORK", "contract_id": null, "status": "NO_CONTRACT" }`.

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes (including `/api/price-line/`, `/api/price-claim/`, etc.).

---

## Stage 6 — UI Enhancements

**Goal:** UI work deferred to a separate planning document — placeholder only; not planned in [UPGRADE_PLAN.md](UPGRADE_PLAN.md).

**Estimated duration:** TBD (ongoing)

**Dependencies:** Stages 1–5 backend complete.

### New models

| Model | App | Key fields |
|-------|-----|------------|
| — | — | None |

### New services

| Service | Location | Purpose |
|---------|----------|---------|
| — | — | None |

### New API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| — | — | None (uses Stage 5 endpoints when built) |

### Anticipated UI work (not planned here — from UPGRADE_PLAN.md)

- Provider lookup and network status page (uses Stage 5 provider endpoints).
- Member enrollment lookup and product display.
- Repricing sandbox (uses `/api/reprice-claim/` instead of direct contract selection).
- Contract product scope editor (links contracts to LOB/products).
- Batch repricing job submission and results viewer.
- Network participation management (admin-grade CRUD for Stage 1 models).

### Key acceptance criteria

- Not defined in UPGRADE_PLAN.md — to be specified in separate UI plan.

### What must NOT break

- All 43 existing tests in `tests/`.
- All existing API endpoints and their request/response shapes.

---

## Frozen Scope

The following will **not** be changed under any circumstances during this upgrade, except where [UPGRADE_PLAN.md](UPGRADE_PLAN.md) explicitly notes an exception (Stage 0: `print()` → `logging` in `orchestrator.py`; Stage 4: additive DTOs in `types.py` and `price_claim_from_context` in `core/engine/service.py`):

| Area | Constraint |
|------|------------|
| `core/engine/orchestrator.py` | Frozen — Stage 0 logging replacement only |
| `core/engine/resolver.py` | No changes |
| `core/engine/loader.py` | No changes (contract resolution logic extracted to `core/services/contract_resolver.py`, not inlined changes) |
| `core/engine/strategies/` | No changes |
| `core/engine/simulation/` | No changes |
| `core/engine/conditions.py` | No changes |
| `core/engine/config.py` | No changes |
| `core/engine/types.py` | No changes except Stage 4 additive DTOs |
| `core/engine/exceptions.py` | No changes |
| All existing API endpoints | Request/response shapes unchanged throughout Stages 0–5 |
| All existing Django migrations | **Additive only** — no column renames or drops on existing tables |
| All existing tests in `tests/` | Must pass after every stage (43 tests — test suite is the gate) |

**Upgrade principles (from UPGRADE_PLAN.md):**

1. Freeze the engine — `core/engine/` not touched except logging (Stage 0) and additive types (Stage 4).
2. Additive migrations only — new FK fields on existing models are `nullable=True`; no existing column renamed or removed.
3. Test suite is the gate — all 43 existing tests must pass after every stage.
4. New domains = new Django apps — `providers/`, `members/`, `products/`.
5. APIs follow data — no new API endpoints until underlying models exist.
6. Backward compatibility — all existing API endpoints (`/api/price-line/`, `/api/price-claim/`, etc.) continue to work unchanged throughout.

---

## Feature Flags

| Flag | Stage introduced | Purpose |
|------|------------------|---------|
| `FEATURE_CONTEXT_RESOLVER` | Stage 4 | Gates `/api/resolve-context/` and the context resolution path |
| `FEATURE_REPRICE_API` | Stage 5 | Gates `/api/reprice-claim/` and batch endpoints |
| `FEATURE_TIERED_RESOLUTION` | Keep disabled until Stage 5 | Enable in Stage 5 once network context is real |

---

## Cross-Stage Standards

From UPGRADE_PLAN.md — apply to all stages:

**Migration standards**

- All new FK columns on existing models: `null=True, blank=True`.
- No column renames on existing tables.
- Every migration must be reversible.
- New tables use snake_case `db_table` names explicitly set.

**Code standards**

- All new models: `created_at`, `updated_at` auto fields.
- All currency: `DecimalField(max_digits=12, decimal_places=2)` — no `FloatField`.
- All services return typed Python objects or `None` — never raw querysets from service layer.
- All new API views: DRF `APIView` or `GenericAPIView` — no function-based views.

**Test requirements**

- Each stage adds a test file: `tests/test_stage1_provider_domain.py`, etc.
- Each new service class gets a unit test file.
- Context resolver integration test seeded against demo data.
- The 43 existing tests must pass after every stage — checked in CI before merge.

---

## Summary Table

| Stage | Duration | New Models | New APIs | Risk |
|-------|----------|------------|----------|------|
| 0 — Engine hygiene | &lt; 1 day | None | None | Zero |
| 1 — Provider domain | 2–3 weeks | Provider, Facility, ProviderAffiliation, ProviderNetworkParticipation, FacilityNetworkParticipation (+ additive `ProviderOrganization` fields) | None | Very low |
| 2 — Payer/Product/LOB/Network | 2–3 weeks | PayerOrganization, LineOfBusiness, Product, Network, ProductNetworkConfig, ContractProductScope (+ additive `PayerNetwork`, `ProviderNetworkParticipation.network_new`) | None | Low |
| 3 — Member/Enrollment + ClaimHeader | 2–3 weeks | Member, Enrollment (+ additive `ClaimHeader` FKs) | None | Low (all nullable) |
| 4 — Context Resolver | 3–4 weeks | None (DTO only) | `/api/resolve-context/` (debug) | Medium |
| 5 — Context-Driven APIs | 2–3 weeks | None | 7 new endpoints | Medium |
| 6 — UI | TBD | None | None | TBD |

**Total estimated backend timeline:** ~12–16 weeks  
**Engine changes:** zero (except Stage 0 logging and Stage 4 additive DTOs / service entry point)  
**Existing API breakage:** zero
