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
