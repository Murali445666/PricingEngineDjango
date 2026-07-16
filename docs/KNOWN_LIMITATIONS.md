# Matrix — Known Limitations

A deliberately maintained list of where the pricing platform simplifies, diverges
from real-world reimbursement, or carries known constraints. Each item is something
we verified during development — captured here as a conscious design decision and a
roadmap of "next layer to add," not an oversight.

Status legend: **By design** (intentional scope cut) · **Gap** (diverges from real
practice, worth fixing) · **Quirk** (works, but behaves in a non-obvious way).

---

## 1. Pricing methodology fidelity

### 1.1 Anesthesia — qualifying circumstances priced as a separate line — **Gap**
Real anesthesia pricing (ASA / CMS Relative Value Guide) is:
`Payment = (Base Units + Time Units + Modifying Units) × Conversion Factor`.

The engine correctly implements the core `(base_units + time_units) × CF` formula
(verified: 00100 = 5 base units, time = minutes/15, CF = $45 → $228 for 1 minute).
However:
- **99100 (qualifying circumstance, extreme age) is priced as a standalone FLAT
  line.** In reality 99100 is a *modifying unit* (+1 unit) folded into the primary
  anesthesia code's formula and has **no independent fee**. Correct behavior:
  `(base + time + 1) × CF`, i.e. +$45 — not a separate $25 line.

### 1.2 Anesthesia — physical status & medical direction not modeled — **Gap**
- **Physical status modifiers P1–P6** (add 0–3 units for patient acuity) are not
  applied as modifying units.
- **Medical direction / supervision** (modifiers AA, QK, QX, QY, QZ — which pay a
  percentage, often 50%, when a CRNA is directed by an anesthesiologist) is not
  modeled. This is a material real-world payment factor.
- **Time-unit rounding conventions** (tenth vs. decimal) are not configurable.

### 1.4 Modifiers ARE applied, but invisible in the trace — **Quirk** (corrects an earlier misdiagnosis)
Runtime investigation (2026-06) confirmed **modifiers do apply correctly.** Code 29881
with modifier 50 prices base **$400 × 150% = $600** — the modifier fired. An earlier
entry here wrongly claimed modifiers were ignored; that was a misread of the base
amount, not a real defect. Notes:
- **The true RBRVS base for 29881 is $400, not $600.** RBRVS uses the fee-schedule
  fallback ($400 × CF 1.0) because GPCI data is null, so the RVU×GPCI path is skipped.
  $600 is already the post-modifier figure. (Runbook expected values that assumed a
  $500/$600 base are wrong for this reason.)
- **Observability gap (real):** `apply_modifiers()` emits NO trace entry, so the
  execution trace shows no modifier step even when one fires. You can only confirm a
  modifier applied by comparing modified vs. unmodified runs — not from the trace
  itself. This is a genuine explainability gap (and a prime use case for the Pricing
  Investigator: surface "input had modifier X → applied/ignored").
- **Cache-poisoning bug (FIXED):** the per-claim loader cache treated a cached
  `('mod', code) → None` as final, skipping re-query and leaving `modifier_adjustments`
  empty on a primed cache. Fixed at `loader.py:930-936` to re-query on a negative
  cache. Full suite at baseline after the fix.

### 1.5 MPPR applies a flat reduction to the whole line, not just the technical component — **Gap**
MPPR (Multiple Procedure Payment Reduction) works correctly at the high level:
multiple same-category procedures on one claim pay on a 100% / 50% / 25% ladder —
primary full, subsequent reduced (verified: two 70450 lines at base $200 → $200 +
$100 = $300). However, the engine applies the reduction percentage to the **entire
line allowed amount**. Real CMS MPPR typically reduces only the **technical component**
(equipment/facility overhead, which does overlap on repeat procedures), NOT the
**professional component** (the physician's separate interpretation of each image,
which does not overlap). Consequence: for imaging/surgery where a PC/TC split applies,
the engine over-reduces the repeat lines versus true CMS behavior. The simplification
is reasonable for a demo but is not full-fidelity MPPR.

### 1.3 DRG / per-diem and the line-level lesser-of cap — **By design (watch-item)**
The default lesser-of-billed cap (see §2.1) is **LINE scope**, while DRG/per-diem
price at the **claim level**, so the two should not interact. This is architecturally
correct (bundled/case rates should not be capped to line charges) but has **not been
proven green end-to-end**, because the DRG reference tests are currently failing for
unrelated reasons (§3.2). Re-verify once DRG ref data is fixed.

---

## 2. Engine behavior quirks

### 2.1 Lesser-of-billed is default-ON via signal, not engine logic — **By design**
"Allowed = MIN(contract rate, billed charge)" is applied by auto-attaching a
`ContractCapFloor` (scope=LINE, cap_type=PCT_BILLED_CAP, percentage=100) to every
`ContractVersion` on creation, via a `post_save` signal gated by
`FEATURE_DEFAULT_LESSER_OF_BILLED`. Consequences:
- It is **data-driven, not engine-driven** (the frozen engine is untouched).
- Existing versions need the `backfill_lesser_of_billed` management command.
- Turning it off is **global** (the feature flag); there is no per-contract opt-out
  beyond deleting the auto-cap row.

### 2.4 Resolution audit log skips contracts with no ContractVersion — **Gap**
The R4 `ClaimResolutionLog` requires a non-null `resolved_version`. Legacy contracts
that have no `ContractVersion` row resolve and **price normally**, but the audit write
is skipped and the API returns `resolution_log_id = null`. Consequence: such claims
are **invisible to the Pricing Investigator** (no saved "why"). Fixing requires either
backfilling `ContractVersion` rows for legacy contracts or relaxing the log to permit
a null version. Tracked as part of the resolution-layer roadmap (§12 R1–R6, post-R4).

### 2.5 Provider hierarchy traversal capped at depth 5 — **By design**
`ProviderLookupService.resolve_org_hierarchy()` walks `parent_org` upward with a
max depth of 5 (raises `OrgHierarchyDepthError` beyond that, as a cycle guard).
Org structures deeper than 5 levels (rare, but possible in very large IDNs) would
not fully traverse. Intentional safety cap, not a hard architectural limit.

### 2.6 Unenrolled member short-circuits to NO_CONTRACT — **Fixed**
Previously, a member with no active enrollment on the service date (unenrolled or
terminated) fell through to org-level contract matching. When the billing org had
multiple contracts (e.g. `DEMO-UC-ORG-IN` with 28), this surfaced as **AMBIGUOUS** —
mislabeling a *coverage gap* as a *config conflict*, which routes to the wrong team.
`ContractResolutionService.resolve()` now guards on `member_context and raw.member_id
and gathered.enrollment is None`, returning **NO_CONTRACT** ("no active enrollment")
before contract matching. F2/F3 report the coverage gap correctly; F4 (member *is*
enrolled) still returns AMBIGUOUS because its org-level tie is a genuine conflict.
Provider-only resolution (`member_context=False`) is unaffected.

### 2.7 Rule ambiguity vs contract ambiguity — **By design**
**Rule-level ambiguity** (two rules in the same contract version that match the same
procedure code with identical `specificity_score` but different `flat_rate`) is a static
configuration defect: those rules tie on every claim that hits that code, forever.
`StrictRuleResolver` resolves ties by insertion order today; failing at claim time would
punish the claim for a config error that validation should catch first. Contract
validation (`POST /api/validate-contract/<id>/`) flags `AMBIGUOUS_RULE` errors before
activation. The engine does **not** add runtime tie-detection for rule ambiguity.

**Contract-level ambiguity** (multiple contracts match the same claim's entities) is
genuinely claim-dependent — which contracts apply depends on billing org, enrollment,
network, and date. That stays a **runtime** outcome (`AMBIGUOUS` resolution status plus
analyst review queue), not a pre-activation validation error.

### 2.2 `claim_type` matching is case-sensitive — **Quirk**
The engine matches a rule's `claim_type` against the request value **case-sensitively**,
and treats a null/empty request `claim_type` as a wildcard. A rule stored as
`'PROFESSIONAL'` will NOT match an API request of `'professional'`. Because the
Stage 5 APIs send lowercase (enforced by the serializer `ChoiceField`), all seeded
rules use `claim_type = NULL` to stay match-safe. Any new rule authored with an
uppercase `claim_type` will silently fail to match API-driven pricing.

### 2.3 `ContractMethodology` table is unused by current pricing — **Quirk**
Methodology is encoded directly on each `PricingRule` (`methodology_code` +
`flat_rate`/`multiplier`), not via the separate `ContractMethodology` table (which is
empty for all seeded contracts). The table exists but is not on the active pricing path.

---

## 3. Data / reference constraints

### 3.1 Reference lookups are year-scoped to `service_date.year` — **Quirk**
DRG, APC, and ASP reference rows are matched by the **year of the service date**.
A 2025-dated claim requires a 2025 reference row; a mismatch causes the engine to
correctly find nothing and price $0 (not an error). This is a frequent seeding
gotcha — verified via DEMO-UC-B5, where a `RefDrg('470', year=2026)` row silently
yielded $0 for a 2025 claim until corrected to 2025.

### 3.2 Legacy reference-only DRG path returns $0 — **Gap (pre-existing)**
`test_drg_01_base_weight` and `test_drg_02_low_weight` fail ($0 vs. expected) because
the legacy `PricingEngine.calculate_line()` path under `USE_REFERENCE_ONLY_PRICING=True`
resolves DRG flat rate to `None` (DRG is not handled by
`_resolve_flat_rate_from_reference()`), yielding `0 × weight = 0`. Distinct from the
claim-level DRG path (DEMO-UC-B5), which works. A fix requires reference-data wiring
(e.g. `ContractFlatRateOverride`, or excluding DRG from reference-only), not an engine
change.

---

## 4. Test suite baseline

7 pre-existing failures are tracked as the known baseline (not regressions):
- `test_apc_01_allowed_amount`, `test_apc_02_units`, `test_apc_03_no_apc_found` — setUp/ref-data errors
- `test_drg_01_base_weight`, `test_drg_02_low_weight` — see §3.2
- `test_err_01_missing_rule` — expected error status vs. empty
- `test_wrong_version_for_contract_returns_400` — setUp error

Any change should be measured against this baseline: same 7 failing = no regression.

**Plus one known, un-fixed failure introduced by lesser-of-billed (§2.1):**
- `test_explorer_includes_cap_floors` — asserts an exact cap-floor count of 1, but the
  default lesser-of signal now auto-attaches a baseline LINE cap, so the explorer
  returns 2. Fix is to make the assertion count-independent (assert the explicitly
  created cap is present). Not a pricing regression. Until fixed, the working baseline
  is **8 failing** (7 original + this one).

---

## 5. Scope boundaries (intentionally out of scope for now)

- **No eligibility/benefits adjudication** — member cost-share (deductible, copay,
  coinsurance, out-of-pocket max) is not computed; the engine produces *allowed
  amount*, not *member/plan liability split*.
- **No claim edits / NCCI / medical necessity** — bundling, mutually-exclusive edits,
  and clinical edits are not performed.
- **No coordination of benefits (COB)** — single-payer pricing only.
- **Provider/pricing engine is frozen** — all new capability is added around it
  (resolution, APIs, data model), never inside `core/engine/`.

---

## 6. Enterprise-scale pricing gaps (the wider adjudication picture)

**Framing:** this system is a *contract-pricing engine* — it computes the **allowed
amount** for a resolved contract. Full enterprise claims **adjudication** is a longer
pipeline (edits → pricing → benefits → member split → payment). The items below are the
stages/behaviors a production system has that this one does not. None are bugs; they are
scope. Grouped by kind.

### 6.1 Allowed-amount gaps (what the service is worth) — **Gap**
- **OON default pricing** — when no contract resolves, real payers still price the claim
  via a default out-of-network methodology (most commonly a **% of Medicare**, e.g. 150%;
  also UCR/percentile via FAIR Health, or % of billed). This system returns
  NO_CONTRACT/OON with **no price**. The natural fix reuses the Gap A rate-basis machinery
  ("OON default = 150% of MPFS") as a fallback when resolution finds no contract.
  Emergency/traveling care is additionally protected (ACA emergency coverage; the No
  Surprises Act limits balance billing) — also not modeled.
- **DRG grouping, outliers, transfers** — the engine takes a `drg_code` as given; real
  systems **group** the claim into a DRG from diagnoses/procedures, and apply cost
  outliers, transfer-DRG adjustments, and readmission logic.
- **APC/OPPS nuances** — packaging, composite APCs, status-indicator logic, multiple-
  procedure discounting.
- **Global surgical periods / bundling** — post-op visits included in a surgery's global
  fee; not modeled.
- **Site-of-service and provider-type differentials** — facility vs non-facility RVUs;
  reduced payment for NP/PA vs physician.
- **Sequestration / regulatory adjustments** — e.g. the 2% Medicare sequestration cut.
- **NCCI / claim edits** — PTP bundling, mutually-exclusive edits, MUE unit caps
  (already noted; a pre-pricing edit layer).

### 6.2 Benefit-adjudication gaps (allowed → who pays what) — **Gap**
- **Member cost-share split** — the single biggest gap: turning the *allowed amount* into
  plan-paid vs member-responsibility (deductible, copay, coinsurance, out-of-pocket max).
  This is the other half of "pricing" and is entirely absent.
- **Coordination of Benefits (COB)** — primary/secondary payer coordination when a member
  has two plans.
- **Benefit limits / medical necessity / prior auth** — visit maximums (e.g. 20 PT
  visits/yr), age/gender edits, authorization and referral requirements affecting payment.
- **Adjustment reason codes (CARC/RARC)** — the standardized codes on the EOB/835 that
  explain each adjustment; not produced.

### 6.3 Claim-lifecycle / operational gaps — **Gap**
- **Duplicate detection, timely-filing limits** — not enforced.
- **Adjustments / voids / replacements / mass reprocessing** — the claim lifecycle
  (corrections, reversals, retroactive rate changes) is not modeled.
- **Prompt-pay interest / penalties** — not computed.

### 6.4 Population / value-based — **Separate track**
- **Value-based, capitation, shared savings, quality withholds** — a different paradigm
  (population-based, retrospective settlement), not per-claim line pricing. Deferred as
  its own initiative.
