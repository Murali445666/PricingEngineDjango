# Contract Authoring System — Product Ideation

> Working ideation doc. Captures the problem space, enterprise context, and a
> critique of the current platform. Solutions are intentionally deferred — this
> doc is for framing the problem first. Meant to be continued/edited in a
> dedicated thread (new chat or Cowork session).

**Status:** Problem-framing stage. No solution committed yet.
**Sibling system:** Pricing Investigator (AI explainability over claim pricing) —
tracked separately. Contract Authoring and Pricing Investigator are two distinct
systems sharing the same underlying engine + data.

---

## 1. Vision in one line

Make Matrix's contract layer a first-class, multi-entity, versioned, auditable,
**human-legible** object that bridges the gap between a signed legal contract and
the claims-system configuration that prices against it.

---

## 2. Who is the user

| Persona | Role in contracting |
|---|---|
| **Contract / Network Manager** (primary) | Authors and maintains contracts, rates, rules; predicts impact before go-live |
| **Contract Configuration / IT Loading Analyst** | Translates signed legal terms into system config (the Phase-4 role below) |
| **Reimbursement / Payment Integrity Analyst** | Validates that loaded config matches intent; feeds disputes back to authoring |
| **Actuary / Finance** | Models the financial impact of contract terms and changes |

---

## 3. The enterprise contract lifecycle

Only the back half touches IT. The IT handoff is **Phase 4**.

| Phase | Owner | What happens |
|---|---|---|
| 1. Network strategy | Payer network / actuarial | Market need + rate targets (e.g., % of Medicare) |
| 2. Negotiation | Contracting, legal, finance | Rates, methodologies, escalators, value-based terms. Months–years for large systems; bespoke |
| 3. Legal execution | Legal | Signed agreement = **prose + rate exhibits** (Excel fee schedules/rate tables). "The paper." |
| 4. **Contract loading / configuration** ← IT begins | Config / IT analysts | Signed terms **translated** into the claims system: rate tables, rules, edits, effective dates |
| 5. Validation / testing | Config QA | Test claims priced vs. expected; reconcile |
| 6. Go-live | Ops | Effective-dated activation |
| 7. Maintenance | Config + contracting | Amendments, annual CMS rate updates, renegotiations, terminations |
| 8. Dispute / audit | Payment integrity / provider relations | Misprice investigation (→ Pricing Investigator system) |

### The core industry problem: the legal-to-config gap (Phase 4)
A human reads legal prose + an Excel exhibit and hand-configures a claims system.
This translation is:
- **Slow** — weeks to months to load a complex contract.
- **Error-prone** — one wrong multiplier silently mis-prices thousands of claims (millions in leakage).
- **Opaque** — no link between the legal clause and the config row → audits are archaeology.
- **Re-done constantly** — annual updates and amendments force re-translation.

This gap is the enterprise problem the authoring system should attack.

---

## 4. How contracts vary by scale

The model must stretch ~1000× in complexity, from one fee schedule to a multi-entity
system agreement.

| Dimension | Large IDN (Penn, AHN, UPMC) | Mid group / regional | Small / solo practice |
|---|---|---|---|
| Entities covered | Many hospitals + physician groups + ambulatory sites, multiple TINs/NPIs under one parent | A few sites, one TIN | Single TIN/NPI |
| Leverage | High → bespoke | Some | None → **adhesion** (payer's standard contract) |
| Methodologies | DRG (IP), APC (OP), RBRVS (prof), per-diem, case rates by service line, carve-outs (implants/drugs), stop-loss, outliers | Standard FFS + a few carve-outs | Usually one: % of Medicare RBRVS |
| LOBs | Commercial, MA, Medicaid managed, exchange | 1–2 | 1 |
| Value-based | Shared savings, quality bonuses, capitation/risk | Occasionally | Rare |
| Differentiation | Site-of-service, specialty, tiered network | Limited | None |
| Amendments | Constant; multi-year terms with escalators | Annual | Annual rate refresh |

---

## 5. Industry challenges with contracts (the problem set)

1. **Legal-to-config translation** — the Phase-4 gap. *The* problem.
2. **Heterogeneity** — every large contract is bespoke; no standard schema; config is artisanal.
3. **Multi-entity hierarchy** — one contract, many billing entities; map claim → right entity *and* its rate.
4. **Amendments & versioning** — constant partial changes (e.g., just the 2025 rate exhibit) with effective dating + history.
5. **Rate-exhibit sprawl** — huge external fee schedules; syncing to CMS annual updates is perpetual.
6. **Provenance / auditability** — trace a paid amount back to the contract clause that drove it.
7. **Pre-go-live testing** — validate a loaded contract before it touches real claims.
8. **Conflict / overlap** — overlapping contracts/scopes; deterministic "which applies."
9. **Value-based arrangements** — capitation, shared savings, quality — beyond pure FFS.
10. **Knowledge concentration** — config is tribal; few understand any given contract.

---

## 6. Critique of the current authoring + rule layer

### Strengths (genuinely enterprise-grade in places)
- **Rule/methodology breadth**: 8 methodologies + carve-outs, caps/floors, outliers,
  stop-loss, blending, MPPR, per-diem, modifier adjustments, code groups, tier
  multipliers. Comparable to commercial rule engines.
- **Versioning + lifecycle**: DRAFT/ACTIVE/SUPERSEDED/ARCHIVED, audit, activation service.
- **Effective dating** pervasive.
- **Conflict detection** exists.
- **Scope-based resolution** (specificity) exists.

### Deficits that block enterprise scale (mapped to §5 challenges)

| # | Deficit | Impact | Challenge |
|---|---|---|---|
| 1 | **Thin, flat contract header — no entity hierarchy.** `ProviderContract` binds to ONE `provider_org` + ONE `network`. `parent_org` exists on the org but the contract doesn't use it. | **Cannot model Penn.** #1 scale blocker. | #3 |
| 2 | **No contract-document / provenance layer.** No store for the source paper, exhibits, clauses, amendment letters; no clause→config link. | No auditability, no legal-to-config bridge. | #1, #6 |
| 3 | **No first-class amendment model.** Versioning snapshots the whole contract; real amendments change a subset. | Annual updates = clumsy full-version clones. | #4 |
| 4 | **Weak rate/fee-schedule management.** `base_fee_schedule` exists but no living "120% of 2025 MPFS, auto-refresh on CMS publish." | Rate exhibits not modeled as objects. | #5 |
| 5 | **No human-readable contract abstraction.** Rules are atomized rows; no "contract summary" panel. | Analyst can't see the forest. | #10 |
| 6 | **No value-based constructs.** Pure FFS line/claim pricing. | No capitation/shared-savings/quality/risk. | #9 |
| 7 | **Contract "terms" are just multipliers.** `ContractTerm` is a scalar. | No escalators, annual-increase caps, lesser/greater-of across methods, timely filing. | — |
| 8 | **No templating / bulk authoring.** | Small practices need standard templates; big systems need bulk rate loads. Neither is first-class. | #2 |
| 9 | **Scope schema sprawl.** `ContractScope` vs `ContractProductScope` redundancy. | Confuses enterprise config; needs consolidation. | #8 |

### Verdict
The **rule engine is enterprise-grade; the contract abstraction is not.** Today a
"contract" is a thin label over a bag of rules. To solve an enterprise problem, the
contract itself must become a first-class, hierarchical, document-anchored,
**summarizable** object. That gap — sophisticated pricing vs. weak contract object —
is the sharp, defensible thesis for this system.

---

## 7. What the authoring UI must eventually expose (captured requirements)

- **Contract summary / abstract panel** — primary features of the contract in plain
  language (LOB, methodologies, base rates, carve-outs, outlier/stop-loss terms).
- **Rules panel** — the atomized rules behind the summary, drillable.
- **Configure** — author/edit contracts, versions, rules.
- **Simulate** — price across configurations before go-live (reuses existing
  `price-claim-simulate`).

---

## 8. Open forks (for the next session — DO NOT decide yet)

1. **Anchor of the authoring system:**
   - (a) **Abstraction/summary layer** — make contracts legible + templatable.
   - (b) **Document-ingestion layer** — AI reads the paper/exhibit → proposes config.
   Both strong; different bets.
2. **How far to push multi-entity hierarchy** vs. keep single-org for portfolio scope.
3. **Whether value-based constructs are in-scope** or explicitly deferred.

---

## 9. Cross-references
- Pricing engine + rule layer details: `docs/ARCHITECTURE.md`, `core/models.py`
- Known limitations (incl. methodology gaps): `docs/KNOWN_LIMITATIONS.md`
- Upgrade history (Stages 1–6): `docs/UPGRADE_PLAN.md`
- Sibling system: Pricing Investigator (AI explainability) — to be documented separately.

---

## 10. Current State Audit — Contract Resolution Layer (Cursor codebase findings)

> Conducted 2026-06-25. Reflects actual codebase state, not intended design.

### Three resolution paths exist today

| Path | Entry point | Mechanism | Used by |
|---|---|---|---|
| **A — Caller-supplied ID** | `POST /api/price-claim/`, bulk, line, simulate | `_get_contract(contract_id)` → direct PK or legacy number lookup. No resolution logic. | Most API flows |
| **B — Legacy participation resolver** | `GET\|POST /api/claims/<pk>/price/` | `resolve_contract_for_claim()` in `core/engine/loader.py`. Filters `ContractProviderParticipation` by `provider_org_id` / bare NPI + DOS. Ranks by specificity; raises `ContractResolutionTieError` on tie. | Stored claims with null contract |
| **C — Context resolver** | `POST /api/reprice-claim/`, batch reprice | `PricingContextResolver` → `ContractResolver`. Resolves org by billing NPI, enrollment, network, LOB. Specificity waterfall; silently picks `.last()` on ties. | Repricing flows |

Direct override (`override_contract_id`) in Path C bypasses all resolution logic.

### Key facts per dimension

| Dimension | Finding |
|---|---|
| Provider hierarchy | **Flat NPI lookup only.** `ProviderOrganization.parent_org` self-FK exists in schema but is **never read** in any resolver or service. No TIN/IDN upward traversal. |
| Temporal logic | **DOS-driven throughout.** `resolve_active_contract_version()` uses `effective_start_date ≤ DOS ≤ effective_end_date` + ACTIVE status + highest `version_number`. Correct. |
| Tie-breaking | **Inconsistent.** Path B raises `ContractResolutionTieError`. Path C silently picks by `effective_start_date DESC` with no error, no audit record. |
| version_id in context path | **Always None.** `PricingContextResolver` resolves `contract_id` but sets `version_id=None`. Version is re-resolved independently inside `price_claim()`. Two separate DB reads, no atomicity. |
| Audit persistence | **Nothing is stored.** `ClaimPricingResult` is a dataclass returned in the HTTP response only. `ClaimHeader.contract` is not written back after pricing. No resolution log, no snapshot ID, no config hash. |
| Provider directory | **Local DB only.** `ProviderNetworkParticipation` and `ContractProviderParticipation` are separate tables used by different paths. No external NPPES/CMS calls at runtime. |

### The five gaps

| # | Gap | Root cause |
|---|---|---|
| G1 | `version_id` dropped in context path | `ClaimPricingContext.version_id` always set to `None` by `PricingContextResolver`; re-resolved at price time |
| G2 | Silent tie-breaking in `ContractResolver` | No `contract_origin_type` or priority field; falls back to `effective_start_date` ordering |
| G3 | No resolution audit trail | No `ClaimResolutionLog` table; result is API-response-only |
| G4 | `parent_org` is dead schema | Hierarchy self-FK exists but `ProviderLookupService` never traverses it |
| G5 | Two participation tables, two paths | `ContractProviderParticipation` (Path B) and `ProviderNetworkParticipation` (Path C) are independent; same provider can resolve to different contracts depending on entry path |

---

## 11. Required Data Model Changes

> Schema changes only. Service-layer changes are in §12 Roadmap.

### 11.1 New table: `ClaimResolutionLog`

Persists the resolution artifact atomically with each pricing call. This is the audit anchor for the Pricing Investigator.

```
ClaimResolutionLog
─────────────────────────────────────────────────────
id                  BigAutoField          PK
claim_header        FK → ClaimHeader      nullable  (null for API flows with no stored claim)
trace_id            UUIDField             indexed   (correlates with API response trace_id)
resolved_contract   FK → ProviderContract NOT NULL
resolved_version    FK → ContractVersion  NOT NULL
resolution_path     ENUM                  NOT NULL
                    CALLER_SUPPLIED       Path A
                    LEGACY_PARTICIPATION  Path B
                    CONTEXT_RESOLVER      Path C
service_date        DateField             NOT NULL
resolver_inputs     JSONField             NOT NULL  (org_id, network_id, lob, product_id used)
is_repricing        BooleanField          default False
resolved_at         DateTimeField         auto_now_add
```

Indexes: `(resolved_contract, service_date)`, `(claim_header)`, `(trace_id)`.

This table is **append-only and immutable** after write. Re-adjudication writes a new row; it does not update the original.

### 11.2 New columns on `ProviderContract`

Provides the deterministic tie-breaking signal missing from both resolvers.

```
ProviderContract (additions)
─────────────────────────────────────────────────────
contract_origin_type  ENUM          NOT NULL  default DIRECT
                      DIRECT        Payer-provider direct agreement
                      LEASED        Via rented network (MultiPlan, PHCS, etc.)
                      DELEGATED     Delegated entity or sub-contracted arrangement

resolution_priority   SmallInt      NOT NULL  default 10
                      Lower value = wins on tie. Suggested defaults:
                      DIRECT=10, DELEGATED=15, LEASED=20
```

`ContractResolver` sorts candidates by `resolution_priority ASC` before the existing specificity waterfall. Replaces the implicit `.last()` by date.

### 11.3 New columns on `ProviderNetworkParticipation`

Bridges the participation table split (Gap G5) without requiring immediate migration.

```
ProviderNetworkParticipation (additions)
─────────────────────────────────────────────────────
contract            FK → ProviderContract   nullable
                    If set, this participation record is tied to a specific contract.
                    Enables Path C to resolve both network membership AND contract in one query.

participation_source  ENUM                  NOT NULL  default NETWORK_ARRANGEMENT
                      DIRECT_CONTRACT       Loaded from a direct payer-provider contract
                      NETWORK_ARRANGEMENT   Provider participates via leased/rented network
```

### 11.4 Deprecation: `ContractProviderParticipation`

Used only by Path B (`resolve_contract_for_claim()`). Once Path B is deprecated and its data migrated into `ProviderNetworkParticipation` (with `contract` FK populated), this table is retired.

Migration requires: for each `ContractProviderParticipation` row, create a corresponding `ProviderNetworkParticipation` row with `contract` set and `participation_source=DIRECT_CONTRACT`.

### 11.5 No schema change needed

| Gap | Why no schema change |
|---|---|
| G1 (version_id propagation) | `ClaimPricingContext` is a dataclass, not a DB model. Service-layer fix only. |
| G4 (parent_org traversal) | `ProviderOrganization.parent_org` already exists. Need new `resolve_org_hierarchy()` method in `ProviderLookupService`, not a new column. |

### Schema change summary

| Change | Type | Closes gap |
|---|---|---|
| New table `ClaimResolutionLog` | New model | G3 |
| `ProviderContract.contract_origin_type` | New column | G2 |
| `ProviderContract.resolution_priority` | New column | G2 |
| `ProviderNetworkParticipation.contract` FK | New column | G5 |
| `ProviderNetworkParticipation.participation_source` | New column | G5 |
| Deprecate `ContractProviderParticipation` | Deprecation + migration | G5 |

---

## 12. Enhanced Roadmap — Filling the Resolution Layer Gaps

Sequenced so that each phase unblocks the next. Schema migrations first; service layer second; deprecations last.

### Phase R1 — Schema foundation (prerequisite for everything)

- [ ] **R1.1** Add migration: `ProviderContract.contract_origin_type` ENUM (DIRECT / LEASED / DELEGATED), `default=DIRECT`
- [ ] **R1.2** Add migration: `ProviderContract.resolution_priority` SmallInt, `default=10`
- [ ] **R1.3** Add migration: `ProviderNetworkParticipation.contract` FK nullable
- [ ] **R1.4** Add migration: `ProviderNetworkParticipation.participation_source` ENUM, `default=NETWORK_ARRANGEMENT`
- [ ] **R1.5** Add migration: create `ClaimResolutionLog` table (fields per §11.1)
- [ ] **R1.6** Backfill `ProviderContract.resolution_priority` from `contract_origin_type` (DIRECT=10, DELEGATED=15, LEASED=20) for all existing rows

### Phase R2 — Fix version_id propagation (G1)

- [ ] **R2.1** In `PricingContextResolver.resolve()`, call `resolve_active_contract_version(contract, service_date)` and set `version_id` on the returned `ClaimPricingContext`
- [ ] **R2.2** In `price_claim_from_context()` in `ClaimPricingService`, forward `version_id` from context to `ClaimPricingInput` (use explicit `resolve_contract_version()` if non-null; else fall through to active version resolver)
- [ ] **R2.3** Unit test: assert `ClaimPricingContext.version_id` is non-null after `PricingContextResolver.resolve()` for a valid claim

### Phase R3 — Deterministic tie-breaking (G2)

- [ ] **R3.1** Refactor `ContractResolver.resolve()`: after the specificity waterfall, sort remaining candidates by `resolution_priority ASC` before picking; raise `ContractResolutionAmbiguityError` only if two candidates share both specificity level AND `resolution_priority`
- [ ] **R3.2** Add `contract_origin_type` filter to `ContractResolver` so Direct+Leased overlaps resolve deterministically without erroring
- [ ] **R3.3** Align legacy `resolve_contract_for_claim()` ranking to use `resolution_priority` as the primary sort key (currently uses ad-hoc specificity + scope priority tuple)
- [ ] **R3.4** Integration test: seed one DIRECT + one LEASED contract for same org/network/DOS; assert DIRECT wins

### Phase R4 — Persist resolution artifacts (G3)

- [ ] **R4.1** Write `ClaimResolutionLog` row at the end of `ClaimOrchestrator.run()` — inside the same DB transaction as any `ClaimHeader` update
- [ ] **R4.2** For API flows with no stored claim (Path A / Path C reprice), write `ClaimResolutionLog` with `claim_header=null` and `trace_id` from the request
- [ ] **R4.3** Expose `resolution_log_id` in all pricing API responses alongside existing `trace_id`
- [ ] **R4.4** Add `GET /api/resolution-log/<trace_id>/` endpoint — returns the persisted log row; foundation for Pricing Investigator query interface
- [ ] **R4.5** Test: reprice same claim twice after amending a contract; assert two separate `ClaimResolutionLog` rows with different `resolved_version_id`

### Phase R5 — Provider hierarchy traversal (G4)

- [ ] **R5.1** Implement `ProviderLookupService.resolve_org_hierarchy(npi: str, service_date: date) → List[ProviderOrganization]` — walks `parent_org` upward from the NPI's org, returning ordered list `[leaf, group, idn]` filtered by org effective dates
- [ ] **R5.2** Refactor `PricingContextResolver._resolve_org()` to call `resolve_org_hierarchy()` and return the full list rather than a single org
- [ ] **R5.3** In `ContractResolver.resolve()`, iterate the org hierarchy list (most specific first) — try each `org_id` in the waterfall before moving to the next specificity level
- [ ] **R5.4** Add cycle guard to `resolve_org_hierarchy()` (max depth = 5; raises `OrgHierarchyDepthError` if exceeded — prevents infinite loops on malformed `parent_org` data)
- [ ] **R5.5** Integration test: anchor contract at IDN org level; submit claim with leaf-node billing NPI; assert contract resolves correctly via upward traversal

### Phase R6 — Unify participation tables, deprecate Path B (G5)

- [ ] **R6.1** Write data migration: for each `ContractProviderParticipation` row, create corresponding `ProviderNetworkParticipation` row with `contract` FK set and `participation_source=DIRECT_CONTRACT`
- [ ] **R6.2** Refactor `resolve_contract_for_claim()` (Path B) to query `ProviderNetworkParticipation` instead of `ContractProviderParticipation`; verify parity with existing test coverage
- [ ] **R6.3** Route `ClaimPriceView` (`GET|POST /api/claims/<pk>/price/`) through `PricingContextResolver` instead of legacy `resolve_contract_for_claim()` — Path B is now Path C
- [ ] **R6.4** Add deprecation warning log on any remaining call to `resolve_contract_for_claim()`
- [ ] **R6.5** After one release cycle with no warnings triggered: drop `ContractProviderParticipation` table and `resolve_contract_for_claim()` function
- [ ] **R6.6** Regression test full suite against unified path

### Dependency order

```
R1 (schema) → R2 (version_id) → R4 (audit log)
R1 (schema) → R3 (tie-breaking) → R6 (unify paths)
R1 (schema) → R5 (hierarchy)
R4 must complete before Pricing Investigator work begins
```

---

## 13. Target Contract Data Model (design of record)

The contract becomes a **first-class layered object** — a container of effective-dated,
scoped pricing arrangements applied to a set of covered entities. Six layers. All
changes are **additive**: the existing `ProviderContract.provider_org` and `.network`
FKs, all rules, scopes, and the frozen engine stay untouched; new tables are backfilled
from existing data.

### The six layers

```
Layer 1  Parties          Payer  ⇄  Provider org (contracting party)
Layer 2  Agreement        Contract header + source Document (provenance)
Layer 3  Covered Entities contract → many {ORG | FACILITY | PROVIDER}   ← crown jewel
Layer 4  Scope            LOB / product / network / site / specialty
Layer 5  Arrangements     named, typed pricing deals (group the rules)
Layer 6  Rates/Terms/Rules fee schedules, caps, carve-outs, executable rules (exists)
```

### Entity-relationship model (target)

```
products.PayerOrganization ─┐
                            │ (payer_org FK, new)
core.ProviderOrganization ──┤        ┌── ContractDocument (new)      1:many  provenance
   (parent_org self-FK)     │        │
                            ▼        │
                    ┌──────────────────────────┐
                    │     ProviderContract      │
                    │  (agreement / header)     │
                    │  origin_type, dates,      │
                    │  status, provider_org,    │
                    │  network, payer_org(new)  │
                    └──────────────────────────┘
                       │            │           │
        ┌──────────────┘            │           └───────────────┐
        ▼                           ▼                           ▼
ContractCoveredEntity (new)   ContractArrangement (new)   ContractAmendment (new)
  entity_type ORG/FAC/PROV      name, arrangement_type       number, effective_date,
  org|facility|provider FK      claim_type, eff dates        description, what_changed
  is_primary, eff dates              │
  (1 contract : many)                │ (1 arrangement : many)
                                     ▼
                               PricingRule.arrangement (new FK, null)
                               → existing rules roll up under an arrangement
```

### New / changed tables

| # | Table / column | Layer | Purpose | Key fields |
|---|---|---|---|---|
| 1 | `ProviderContract.payer_org` (col) | 1 | who the contract is *with* | FK→products.PayerOrganization, null |
| 2 | `ContractDocument` | 2 | the source paper/exhibit (provenance) | contract FK · doc_type · reference · title · notes |
| 3 | `ContractCoveredEntity` | 3 | **which entities the contract covers** | contract FK · entity_type (ORG/FACILITY/PROVIDER) · org/facility/provider FK · is_primary · eff dates |
| 4 | `ContractArrangement` | 5 | named, typed pricing arrangement | contract FK · name · arrangement_type · claim_type · eff dates · status |
| 5 | `PricingRule.arrangement` (col) | 5→6 | roll rules up under an arrangement | FK→ContractArrangement, null |
| 6 | `ContractAmendment` | 6/2 | first-class, dated amendments | contract FK · number · effective_date · description · what_changed(JSON) |

`arrangement_type` values: FEE_SCHEDULE / DRG_CASE_RATE / PER_DIEM / APC / ANESTHESIA /
DRUG_ASP / CAPITATION / BUNDLED / VALUE_BASED. New contract types = new arrangement
types, **not** a schema rewrite (extensibility principle).

### Coverage table = the multi-entity answer

One `ProviderContract` → many `ContractCoveredEntity` rows (an org, a facility, a
provider, or provider-at-facility via two rows). This is the Penn model, and it
consolidates the three tangled contract↔provider links (deficit #9 / G5) into one
source of truth. `provider_org` is mirrored in as `is_primary=True` so the existing
FK is never broken.

### Backfill (populate, don't leave empty)

- every ProviderContract → one CoveredEntity(ORG, provider_org, is_primary=True)
- existing `ContractProviderParticipation` rows → CoveredEntity rows
- one default ContractArrangement per distinct methodology on a contract's rules;
  point those rules' `.arrangement` at it
- `payer_org` left null unless derivable

### Explicitly deferred (separate, test-heavy phase)

**Resolver integration** — making resolution *use* `ContractCoveredEntity` (facility-
and provider-level specificity) — is NOT part of the model build. The resolver is the
only place a mistake causes ambiguity crashes; wire it after the model exists, with
test gates. Value-based/capitation *pricing* is also deferred (arrangement type exists;
engine math for it does not).

---

## 14. Contract Resolver — Current State & Gaps (for the two-stage redesign)

### Target design (the principle)
Two clean stages, single responsibility each:
1. **Contract Resolution** (claim/header level, once per claim) — gather the claim's
   context, walk the hierarchy, return **exactly one** contract **or refuse**. Never
   tie-break by guessing; on a true conflict, fail gracefully with a typed reason and
   **flag for analyst review**. Pricing on an ambiguous contract is not allowed.
2. **Pricing** (line level, per line, inside the resolved contract) — gather rules,
   derive price. Already exists (the engine's rule selection).
Applies to both **single and batch** claims.

### How it works today (verified 2026-06-30)
- `ContractResolver` (core/services/contract_resolver.py): specificity waterfall
  (product → LOB → network → org) + `resolution_priority` tie-break (R3). Returns one
  `contract_id`; raises `ContractResolutionError` (OON/no-contract) or
  `ContractResolutionAmbiguityError` (tie at same specificity+priority).
- `PricingContextResolver` (core/services/pricing_context_resolver.py): the orchestrator.
  Does the gather (org hierarchy via R5, member→enrollment→product→network, affiliation),
  **calls** `ContractResolver`, resolves `version_id` (R2), and packs a
  `ClaimPricingContext` DTO (contract_id + version_id + provider/member ctx + lines).
- Handoff to pricing: `ClaimPricingService.price_claim_from_context(ctx)` → `price_claim()`.
  So the effective handoff is `contract_id` + `version_id`, wrapped in the DTO.

### Gaps vs. the target
| # | Gap | Detail |
|---|---|---|
| G-A | **No clean two-stage boundary** | `ContractResolver` is buried inside `PricingContextResolver`, which entangles gather + contract-pick + version + context-assembly. No standalone "resolve contract → result-or-flag" API that single AND batch call first. |
| G-B | **Ambiguity can still crash** | `PricingContextResolver.resolve()` catches `ContractResolutionError` but NOT `ContractResolutionAmbiguityError` (line ~115), so a tie propagates uncaught → HTML 500 (the A4 crash). No graceful "conflicting contracts" outcome. |
| G-C | **No "flag for review" persistence** | `ClaimResolutionLog` (R4) records only *successful* resolutions. Failed/ambiguous attempts (candidates, which step was ambiguous, why) are not persisted → no analyst review queue. |
| G-D | **Thin failure taxonomy** | Only OON / NO_CONTRACT (+ DIRECT/RESOLVED). Missing distinct, persisted outcomes: **AMBIGUOUS** (config conflict), **UNRESOLVED_ENTITY** (bad data), **NO_ACTIVE_VERSION** (dating). Each needs a different analyst action. |
| G-E | **Gather-step ambiguity unhandled** | Entity lookups assume single results — `resolve_org_hierarchy` takes `[0]`, `resolve_enrollment`/rendering lookups pick first. Multi-match at the entity level (provider in 2 orgs, dual enrollment) is silently collapsed, not flagged. Ambiguity is treated as contract-only; it can occur upstream. |
| G-F | **Coverage table unused** | `ContractResolver` resolves via `provider_org`/hierarchy, NOT the new `ContractCoveredEntity` (§13). Facility/provider-level coverage plays no role yet. |
| G-G | **No batch-first / grouped resolution** | Batch reprice loops per-claim; no grouped contract-resolution stage (shared-key claims resolved once). Grouping key correctness is an open risk. |
| G-H | **Handoff not a locked bundle** | `version_id` is resolved (R2) but the resolution result isn't a frozen snapshot (contract + version + matched coverage row + config hash) guaranteed identical to what pricing uses. Seam risk. |
| G-I | **Facility absent from resolution** | `place_of_service` / `facility_id` are hardcoded `None` in the context; facility never participates in the resolve. |

### Design decisions to lock before building
- **Contract resolution is claim-level; rule selection is line-level** (already true).
  Assume pre-split claims (837I vs 837P) so one claim = one contract.
- Resolution **never guesses**; the residual same-specificity+priority tie → flag.
- Deterministic narrowing (hierarchy, origin-type/priority, context) is *rules*, not
  guesses — those resolve cleanly; only the residual conflict is escalated.

### Status update (2026-07 — after D1–D5)
Most §14 gaps are now CLOSED: G-A (two-stage `ContractResolutionService`), G-B/G-C/G-D
(graceful typed failures + `ContractResolutionException` review queue), G-E (gather-step
UNRESOLVED_ENTITY), G-F/G-I (coverage-table + facility resolution via
`FEATURE_COVERAGE_RESOLUTION`). Remaining: G-G (batch-first grouped resolution) and G-H
(locked resolution snapshot) — deferred, not blocking.

---

## 15. Contract Summary Panel (design & build steps)

### Purpose
The human-readable **contract abstraction** — deficit #5, §7 requirement. Today a
contract is a bag of rows; an analyst cannot "see the forest." This panel renders the
finished §13 layered model as a single legible view: *what this contract is, who it
covers, how it prices, and how it changed over time.* Read-only. It is the visible
payoff of the whole contract-authoring arc, and the reference view an analyst uses when
validating config or investigating a dispute.

### Data source
`ContractSummaryService.build(contract_id)` already exists (built in the §13 iteration)
and returns: parties, documents, covered_entities, arrangements (+nested rules),
amendments, scopes, product_scopes. The panel is mostly a **render of this service** —
plus one new read endpoint and a plain-language abstract.

### What it shows (mapped to the §13 layers)
1. **Abstract (plain language, top)** — one paragraph auto-composed from the data, e.g.
   *"Commercial PPO agreement between Horizon Health Plan and Keystone Cardiology Group
   (DIRECT). Professional services priced via RBRVS. Covers Dr. Sarah Chen. Effective
   2025-01-01, active."* This is the "see the forest" line.
2. **Parties & header** — contract name, `contract_origin_type` (DIRECT/LEASED/DELEGATED),
   status, effective dates; payer (`payer_org`) ⇄ provider org.
3. **Covered entities** (crown jewel) — the `ContractCoveredEntity` rows: which ORG /
   FACILITY / PROVIDER this contract covers, primary flagged. This is the multi-entity
   view made visible.
4. **Arrangements** — each `ContractArrangement` (FEE_SCHEDULE / DRG / PER_DIEM / … ),
   its `claim_type`, and the **rules** grouped under it (drillable — collapse/expand).
5. **Terms & policy** — caps/floors, carve-outs, outlier, stop-loss, per-diem, MPPR
   (from the existing contract tables) summarized as readable lines.
6. **Amendments** — the `ContractAmendment` history (number, effective date, what changed).
7. **Documents** — `ContractDocument` provenance (source paper / rate exhibits).

### Where it lives
A dedicated **Contract Summary** view, reachable from the contracts list (a "Summary"
action per contract) and/or as a tab on the existing Contract Detail page. Route e.g.
`/contracts/:id/summary`.

### Build steps
1. **Backend endpoint** — `GET /api/contracts/<id>/summary/` → returns
   `ContractSummaryService.build(id)` as JSON. Add the plain-language **abstract** string
   (compose it in the service or the view from parties + arrangements + primary coverage
   + dates). Serializer/typed dicts only; no queryset leakage. No engine changes.
2. **Frontend types** — a `ContractSummary` type mirroring the service payload
   (parties, covered_entities, arrangements+rules, amendments, terms, documents, abstract).
3. **Frontend service** — `getContractSummary(id)` → GET the endpoint (axios `apiClient`,
   TanStack Query).
4. **Frontend page** — `ContractSummaryPage` (feature folder `features/contracts/`),
   using existing shared UI (PageLayout, cards, DataTable, StatusBadge). Sections in the
   order above; arrangements drillable to their rules. Abstract rendered as a prominent
   banner/card at the top.
5. **Wire-up** — route `/contracts/:id/summary` (append-only) + a "Summary" link from the
   contracts list / contract detail. Sidebar unchanged.
6. **Verify** — `npm run build` clean; open the KEYSTONE contracts (C-IDN / C-CARD /
   C-F1) and confirm the panel shows correct parties, covered entities (org vs facility
   vs provider), arrangements, and rates. `python manage.py test` baseline unchanged.

### Explicitly out of scope (this iteration)
- **Editing** — this is read-only. Authoring/edit forms are a later iteration.
- **Author-time conflict validation** (challenge #8) — separate, later; would flag
  overlaps at author time (the review-queue idea applied before go-live).

---

## 16. Model-gap closure plan (intensifying the contract layer)

Real large contracts differ from the demo mostly in **capability the model lacks**, not
just sparse data. Closure order: **A → B → D → E**. **C (NCCI) is set aside** — it is a
claims-adjudication concern (correct coding), not a contract-model gap; a separate lane.
**Value-based (#6) is a separate track** (population-based, retrospective; needs engine
paradigm the frozen engine lacks).

Guiding principle: close each gap at the **model + materialization** layer so the frozen
engine is never touched — the engine always receives a concrete resolved rate.

### A — Rate-schedule linkage (#4) — FIRST
Real rates are "120% of MPFS 2025," not literal dollars. Model:
- `PublishedFeeSchedule` — a named external schedule: `name`, `basis_type`
  (MPFS / MSDRG / APC / CUSTOM), `year`, `source`, effective dates.
- `FeeScheduleRate` — for CUSTOM schedules: schedule → code → amount. (For MPFS/DRG/APC,
  resolve from the existing Ref* tables rather than duplicate them.)
- `ContractRateBasis` — links a `PricingRule` (or `ContractArrangement`) to a
  `PublishedFeeSchedule` + `percentage` (e.g. 120.00). "This rule's rate = 120% of MPFS."

**Materialization (keeps engine frozen):** a service/command computes the effective rate
(schedule lookup × percentage) and **writes it to the concrete rate the engine already
reads** (`PricingRule.flat_rate` / `ContractBaseRate.base_rate`). The `ContractRateBasis`
is the authored source of truth; materialization derives the number. Annual update = bump
the schedule year, re-materialize — never hand-edit thousands of rows. Engine unchanged;
contracts without a rate basis price exactly as today.

Summary panel then shows the basis ("Professional: 120% of MPFS 2025") not a bare $150.

### B — Escalators / rich terms (#7)
`ContractTerm` is a scalar today. Model typed, effective-dated terms: annual escalator %,
cap on increase, most-favored-nation. Materialization applies the escalator to derive the
effective rate for a given year (builds on A's materialization).

### D — Templating + bulk rate authoring (#8)
Clone a standard contract as a template (small/adhesion practices) and bulk-load rate lines
(large exhibits). Authoring convenience; additive; no engine impact.

### E — Scope schema consolidation (#9)
Consolidate `ContractScope` and `ContractProductScope` into one scope model. Cleanup +
migration; touches resolution → test-gated. Lowest value, done last.

### Deferred (named, not now)
- **C — NCCI / claim edits** — pre-pricing edit layer + CMS edit tables; separate lane.
- **#6 Value-based** — separate track.
- Anesthesia medical-direction %, MPPR PC/TC split — engine-fidelity, frozen engine.

---

## 17. Analyst Authoring Layer — build plan (2026-07)

### Why now
The seed + import path is proven end-to-end: one realistic agreement
(`HM-KHS-2025-0417`, contract 217 / version 197) with a 7-entity roster, 296 affiliated
providers, 252 members, and a **1,114-row rate exhibit** across five methodologies —
resolving and pricing correctly (see `docs/TESTING.md`). The data model and the pipeline
work. **But every step of it required a management command.** The model is ready; the
analyst surface is missing. That is the whole of this phase.

### What changed since §6 (deficits now closed)
| §6 deficit | Status |
|---|---|
| 1 — multi-entity hierarchy | **Closed** — covered entities + specificity ladder |
| 4 — rate/fee-schedule management | **Closed** — Gap A rate basis + materialization |
| 5 — human-readable abstraction | **Closed** — §15 Contract Summary panel |
| 7 — terms are scalar multipliers | **Closed** — Gap B escalators |
| 8 — templating / bulk authoring | **Closed at CLI** — `clone_contract`, `bulk_add_rates`, `import_fee_schedule` |
| 9 — scope schema sprawl | **Closed** — Gap E consolidation |
| 2 — document / provenance layer | Open — this is the AI fork (§8.1b) |
| 3 — first-class amendment | Partial — versions exist; an amendment is still a full clone |
| 6 — value-based constructs | Deferred (§16) |

The §6 verdict ("enterprise-grade engine, weak contract object") is now **half-resolved**:
the contract object got strong. What's still thin is the *way a human builds one*.

### Fork decision (resolves §8.1)
**Anchor = (a) the abstraction / authoring layer.** Document ingestion (b) is not dropped —
it is the *next* layer and it **depends** on this one: an AI that reads a paper exhibit must
propose config *into* a target, and that target is the authoring API built here. Build the
target first, then let AI write into it.

### Current-state audit (verified 2026-07)
- `ContractListView` is **GET-only** and filtered to `status='ACTIVE'` → **no way to create a
  contract** via API/UI. Contracts exist only via seeds/CLI. Biggest single gap.
- No roster (Exhibit A) or scope (Exhibit B) authoring endpoints.
- Rate-exhibit load is CLI-only (`import_fee_schedule`); rate basis/escalator is
  `materialize_rates` CLI.
- Version **activate/archive** exist; version **create** does not.
- Rule create/edit + `ConditionBuilder` exist, but at *rule* altitude — useless for standing
  up a 1,114-line exhibit.
- **Guardrails already strong** and reusable: contract validation, bulk validation, conflict
  detection/resolution, version lifecycle, Contract Summary.

### Design principles
1. **Author in the shape of the contract** (Exhibit A → B → C → versions), not the shape of
   the tables. The wizard mirrors the paper agreement (`docs/Sample_Managed_Care_Agreement.pdf`).
2. **The UI is a façade over proven services.** No new pricing logic. Every action maps to an
   existing, tested service: `fee_schedule_import`, `bulk_rates`, `materialize_rates`,
   `clone_contract`.
3. **Draft-safe.** Authoring writes `DRAFT`. The resolver only sees ACTIVE + in-window
   contracts, so nothing an analyst does can affect live pricing until explicit activation.
4. **Engine stays frozen.** `core/engine/` is untouched, as it has been throughout.
5. **Validate before publish.** Reuse the existing validation + conflict services as the gate.

### Phases
| # | Phase | Delivers | Wraps / reuses | Done when |
|---|---|---|---|---|
| **A1** | Contract header + create | `POST /api/contracts/` → DRAFT (name, legacy #, payer, provider org, network, LOB, effective dates, origin, priority); "New Agreement" form | new endpoint; existing serializers | Analyst creates a DRAFT contract with no CLI |
| **A2** | Roster (Exhibit A) | `GET/POST/DELETE /api/contracts/<id>/covered-entities/`; add org/facility/practitioner + effective dates; specificity-ladder preview | `contract_covered_entities`; provider lookup | The 7-entity Keystone roster is reproducible in the UI |
| **A3** | Scope (Exhibit B) | `GET/POST /api/contracts/<id>/scope/` — product / LOB / network | consolidated scope model (Gap E) | PPO scope authored in the UI |
| **A4** | **Rate exhibit (Exhibit C)** ← the value | CSV upload → **diff preview** (added/changed/removed) → commit; rate-basis authoring (% of schedule + base year + escalator) → materialize | `fee_schedule_import`, `bulk_rates`, `materialize_rates` | The 1,114-row exhibit loads from the browser with a preview |
| **A5** | Versions & amendments | `POST /api/contracts/<id>/versions/`; clone prior version's rates + apply escalator | `clone_contract`, `materialize_rates --year` | 2026 amendment created in UI; rates escalate +3% |
| **A6** | Validate & publish | DRAFT → validate → resolve conflicts → ACTIVE; Summary panel as read-back | existing validation/conflict/activate | DRAFT→ACTIVE round-trip in UI; summary reads like Exhibit C |

**Sequencing.** A1–A3 produce a resolvable skeleton. **A4 is where the value is** — it turns
the CLI into a product. A5/A6 are lifecycle. **MVP slice = A1 + A4** (create an agreement and
load its rate exhibit from the browser); that alone removes the terminal from the analyst's path.

### Authoring validation rules — earned from real defects
These are requirements derived from bugs actually hit during the contract-217 load, not
theory. They are the seed of an **"authoring lint,"** which is arguably the differentiating
feature of this layer:

1. **`claim_type` normalization (must-have).** The importer authored
   `PricingRule.claim_type='INSTITUTIONAL'` (uppercase). The API accepts only lowercase and
   the engine matches case-sensitively (KNOWN_LIMITATIONS §2.2) → **185 rules were silently
   unreachable** and every institutional claim returned `DENIED_NO_RULE`. Any authoring
   surface that lets a human (or an importer) supply a `claim_type` will reproduce this bug.
   Authoring MUST normalize on write and reject non-canonical values.
2. **Meaningless-carve-out warning.** A practitioner carve-out whose rate equals its parent
   org's rate is indistinguishable at runtime and has no business purpose — the Dr. Chen
   99213 case authored two competing rules both paying **$108.12**, so no test could prove
   which one won. Warn when a more-specific rule's rate equals the rule it overrides.
3. **Unreachable-rule detection (generalized).** After authoring, flag rules that can never
   match: contradictory conditions, non-canonical enum values, or an effective window
   outside the parent version's.

### Explicitly out of scope (this phase)
- **Document ingestion / AI clause→config** (§8.1b) — the next layer; needs A1–A6 as its target.
- **Value-based constructs** (§6.6) — separate track.
- **Modifier-adjustment authoring** — deferred by decision during the contract-217 load.
- **Auth / roles / permissions** — there is no user model today; authoring is single-user.
  Named as a real gap, deliberately not built (portfolio scope).

### Cross-references
- Paper reference the UI must reproduce: `docs/Sample_Managed_Care_Agreement.pdf`
- Rate exhibit + load pipeline: `docs/Exhibit_C_Fee_Schedule.csv`, `docs/CURSOR_SEED_BRIEF.md`
- Test evidence for the seeded contract: `docs/TESTING.md`
- Read-back surface: §15 Contract Summary Panel
