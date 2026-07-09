# Contract Resolution — Scenario Catalog

The complete space of contract-resolution outcomes. Drives both the build (the resolver
must handle every row) and the test suite (each row becomes a seeded, runnable case).

**The rule:** resolution returns **exactly one contract** OR a **typed failure that is
flagged** — it never guesses. Deterministic narrowing (specificity, origin priority,
temporal) resolves cleanly; only a residual same-level tie is escalated.

---

## The resolution precedence ladder (the "final stage")

Applied top to bottom. The first rung that yields a single contract wins.

1. **Direct override** — caller supplied `contract_id` → use it (bypass everything).
2. **Entity specificity** (most specific covered entity wins):
   `provider-at-facility` > `provider` > `facility` > `group/org` > `IDN parent`
3. **Scope specificity** (within the same entity level):
   `product` > `LOB` > `network` > `unscoped`
4. **Origin priority** (within the same specificity):
   `DIRECT (10)` > `DELEGATED (15)` > `LEASED (20)`
5. **Temporal** — contract effective on DOS **and** a version active on DOS.
6. **Residual** — if >1 contract still survives all rungs → **AMBIGUOUS → flag**.

Upstream of rung 1, the **gather** must resolve each entity to exactly one value
(billing org, member enrollment, rendering provider); a genuine multi-match there →
**UNRESOLVED_ENTITY → flag**.

---

## Status legend
- ✅ **Works today** (D1–D4: org/network/LOB/product specificity, hierarchy, origin
  priority, all failure flagging)
- 🔶 **Needs D5** (facility- / provider- / provider-at-facility-level coverage via
  `ContractCoveredEntity`)
- 🌱 **Needs seed data** to be manually demoable (logic may exist, no demo rows)

---

## Group R — RESOLVED (deterministic single match)

| ID | Scenario | Claim facts | Resolves to | Tests | Status |
|---|---|---|---|---|---|
| R1 | Exact single match | org + network + LOB + product all match one contract | that contract | baseline happy path | ✅ |
| R2 | Group beats IDN (specificity) | provider's group has a contract; group also rolls up to IDN which also has one | **group** contract | rung 2: more specific entity wins | 🔶 |
| R3 | Hierarchy fallback | facility/group has NO specific contract; parent IDN does | **IDN** contract | rung 2: inherit parent when no specific | ✅ (org hierarchy) / 🔶 (facility) |
| R4 | Facility-specific wins | claim at facility F1 which has its own contract; org also has one | **F1** contract | rung 2: facility level | 🔶 |
| R5 | Provider-at-facility wins | contract specifically for provider P at facility F1 | that contract | rung 2: most specific of all | 🔶 |
| R6 | LOB-specific | member on Medicare Advantage → MA-scoped contract chosen over generic | MA contract | rung 3: LOB | ✅ |
| R7 | Product beats LOB | product-scoped contract vs LOB-only scope | product-scoped | rung 3: product > LOB | ✅ |
| R8 | Network-specific | member on PPO → PPO contract (not the HMO one) | PPO contract | rung 3: network | ✅ |
| R9 | Direct beats leased | same entity covered by a DIRECT and a LEASED contract | **DIRECT** | rung 4: origin priority | ✅ 🌱 |
| R10 | Direct beats delegated | DIRECT vs DELEGATED both cover | **DIRECT** | rung 4 | ✅ 🌱 |
| R11 | Tiered network | provider participates as TIER_2 on a tiered network | tiered contract | network tier handling | ✅ 🌱 |
| R12 | Direct override | caller passes `contract_id` | that contract, DIRECT mode | rung 1: bypass | ✅ |
| R13 | Amendment in effect | contract amended; DOS falls under the amended terms | amended version | rung 5: temporal / amendment boundary | 🔶 🌱 |
| R14 | Leased-network fallback | NO direct contract, but a LEASED network covers the provider | **LEASED** contract | rung 4 fallback when no direct | ✅ 🌱 |
| R15 | Delegated arrangement | member's benefits delegated to an entity with its own contract | delegated contract | rung 4 / delegation | 🔶 🌱 |

---

## Group F — FAILURE (graceful, flagged to review queue)

| ID | Scenario | Claim facts | Outcome | Tests | Status |
|---|---|---|---|---|---|
| F1 | OON provider | billing org not participating in member's network | **OON** | no participation | ✅ |
| F2 | Not enrolled | member has no enrollment | **NO_CONTRACT** | no LOB/product to scope | ✅ |
| F3 | Terminated enrollment | enrollment ended before DOS | **NO_CONTRACT** | temporal enrollment | ✅ |
| F4 | Wrong network | org has a contract, but not on member's network (HMO vs PPO) | **OON** | network mismatch | ✅ |
| F5 | No active version | contract found; versions exist but none active on DOS | **NO_ACTIVE_VERSION** | rung 5 (D4) | ✅ |
| F6 | Two DIRECT, same level | two DIRECT contracts, same entity, same specificity+priority | **AMBIGUOUS** | rung 6 residual tie | ✅ 🌱 |
| F7 | Unterminated old contract | old contract not terminated overlaps the new one | **AMBIGUOUS** | real-world config error | ✅ 🌱 |
| F8 | Two facility contracts | facility F1 has two overlapping contracts | **AMBIGUOUS** | rung 6 at facility level | 🔶 🌱 |
| F9 | Split billing NPI | billing NPI maps to two unrelated orgs | **UNRESOLVED_ENTITY** | gather ambiguity (D4) | ✅ 🌱 |
| F10 | Dual enrollment | member has two active enrollments, different products | **UNRESOLVED_ENTITY** | gather ambiguity (D4) | ✅ 🌱 |
| F11 | Shared rendering NPI | rendering NPI maps to >1 provider | **UNRESOLVED_ENTITY** | gather ambiguity (D4) | ✅ 🌱 |
| F12 | Date outside window | DOS before contract effective / after termination | **NO_CONTRACT** | temporal | ✅ |
| F13 | Entity not found | billing NPI not in system | **NO_CONTRACT / UNRESOLVED_ENTITY** | missing data | ✅ |

---

## Group S — Split / line-level

| ID | Scenario | Claim facts | Outcome | Tests | Status |
|---|---|---|---|---|---|
| S1 | Professional / facility split | one encounter → separate professional claim (billed by group) and facility claim (billed by hospital) | professional → group contract; facility → facility contract (two claims, two contracts) | one-claim-one-contract holds because claims are pre-split | 🔶 |
| S2 | Single claim spanning contracts | one claim with lines governed by different contracts | **out of scope** — require pre-split claims; if attempted → flag | decision: not supported | ❌ (deferred) |

---

## Group E — Interaction / disambiguation

| ID | Scenario | Disambiguated by | Resolves to | Status |
|---|---|---|---|---|
| E1 | Provider in multiple contracts, billed under group A vs group B | **billing TIN/org** | the contract for the billing org | 🔶 |
| E2 | Same provider, office vs at facility | **place of service / facility** | office → group contract; facility → facility contract | 🔶 |
| E3 | Same provider, facility F1 vs F2 | **facility** | F1 → contract A; F2 → contract B (or IDN fallback) | 🔶 |
| E4 | Provider in direct + leased network | **origin priority** | direct (see R9) | ✅ 🌱 |

---

## Coverage summary

- **Already handled (D1–D4):** all failure flagging (OON, NO_CONTRACT, NO_ACTIVE_VERSION,
  AMBIGUOUS, UNRESOLVED_ENTITY), org/network/LOB/product specificity, org hierarchy
  fallback, origin-priority tiebreak, direct override.
- **Needs D5 (coverage table):** facility-, provider-, and provider-at-facility-level
  resolution — R2, R4, R5, F8, S1, E1, E2, E3, and the facility part of R3.
- **Needs seed data (🌱):** the direct/leased/delegated, amendment, tiered, and
  conflict rows — logic may exist but no demo rows to trigger them in the UI.

---

## How this drives build + test

1. **Build:** D5 must make every 🔶 row resolve correctly via `ContractCoveredEntity`,
   respecting the precedence ladder. Feature-flagged, with the review-queue net catching
   any residual tie.
2. **Seed:** the Keystone scenario (IDN + F1/F2 + Cardiology Group + Dr. Chen + Horizon
   contracts) provides the 🌱 rows — one dataset that exercises R2/R3/R4/R5/S1/E2/E3/F7.
3. **Test:** each row becomes a runnable case — Reprice payload (identity-first) with an
   expected status/contract, checked against this table.
