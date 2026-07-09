# Test Scenarios — Contract Intensification (Gaps A / B / D / E)

Runnable tests for rate-schedule linkage, escalators, templating/bulk, and scope
consolidation. Reuses the KEYSTONE contracts and the materialization commands.

## Answer-key note (important)
After Gap A/B, contracts with a **rate basis** price at the *materialized* rate, not a
literal dollar. Current KEYSTONE answer keys:

| Contract | 99213 rate | Source |
|---|---|---|
| C-IDN (212) | **$130.00** | literal (no basis) — unchanged |
| C-CARD (213) | **$108.06** (2025) / **$111.30** (2026) | 120% of MPFS 2025, +3%/yr |
| C-F1 (214) | **$200.00** | literal (no basis) — unchanged |
| C-CARD-OLD (215) | **$999.00** | literal (the conflict) |
| Clone (216) | 8 codes @ 120% MPFS +3%/yr | cloned + bulk-added |

Set the materialization year deliberately before price-checking C-CARD.

---

## Gap A — Rate-schedule linkage

### A-1 · Materialize a rate-basis rule (command)
Run:
```
python manage.py setup_rate_basis_demo
python manage.py materialize_rates --contract 213 --year 2025
```
Expect: rule 293 (99213) flat_rate → **$108.06**
(2.75 total RVU × $32.7442 CF × 120%). Output prints `old -> new`.

### A-2 · Non-basis contract is untouched
Open `/contracts/212/summary` (C-IDN).
Expect: 99213 still **$130.00**, no rate-basis line. Confirms only basis rules materialize.

### A-3 · Idempotent
Run `materialize_rates --contract 213 --year 2025` twice.
Expect: **$108.06** both times (unchanged).

### A-4 · Summary shows the basis
Open `/contracts/213/summary` (C-CARD).
Expect: 99213 shows the rate **and** basis text "120% of MPFS 2025".

---

## Gap B — Escalators

### B-1 · Escalate to a future year
```
python manage.py materialize_rates --contract 213 --year 2026
```
Expect: 99213 → **$111.30** ($108.06 × 1.03).

### B-2 · Base year = no escalation
```
python manage.py materialize_rates --contract 213 --year 2025
```
Expect: **$108.06** (escalator factor = 1 at base year).

### B-3 · Idempotent per year
Run the 2026 command twice → **$111.30** both times (derives from source, never compounds).

### B-4 · Summary shows the escalator
Open `/contracts/213/summary` after materializing for 2026.
Expect: basis reads "120% of MPFS 2025, +3%/yr" with the 2026 materialized value.

---

## Gap D — Templating + bulk authoring

### D-1 · Clone a contract (command)
```
python manage.py clone_contract --source 213 --name "Test Clone A" --org KEYSTONE-IDN
```
Expect: prints a new `contract_id`; the clone has its own arrangements/rules/rate-basis;
`provider_org` re-pointed to KEYSTONE-IDN.

### D-2 · Source is never mutated
Open `/contracts/213/summary`.
Expect: 213 still has its 1 rule at its materialized rate — the clone did not touch it.

### D-3 · Bulk-add rate-basis rules (command)
Using the clone (216) and its version + the MPFS 2025 schedule id (from setup output):
```
python manage.py bulk_add_rates --contract 216 --contract-version <vid> --schedule <sid> --percentage 120 --codes 99215,99204
```
Expect: new PricingRules created for 99215 / 99204, each with a rate basis, materialized
to concrete rates (printed). No error.

### D-4 · Clone summary shows the full exhibit
Open `/contracts/216/summary`.
Expect: multiple rules (cloned 99213 + bulk-added codes), each with "120% of MPFS 2025,
+3%/yr". Reads like a real rate sheet.

---

## Gap E — Scope consolidation (resolution UNCHANGED)

These prove the resolver still picks the SAME contract after the scope tables were
consolidated. Run on the **Reprice Claim** page. The price reveals which contract won
(per the answer-key table). Materialize 213 for 2025 first so C-CARD reads $108.06.

### E-1 · IDN professional → C-IDN
Billing `KEYSTONE-NPI01`, member `KEYSTONE-MEM-1`, professional, 99213.
Expect: **$130** (C-IDN) — SUCCESS.

### E-2 · Provider-specific → C-CARD
Add rendering `KEYSTONE-NPI05` (Dr. Chen) to E-1.
Expect: **$108.06** (C-CARD via provider specificity) — SUCCESS.
(This is the answer-key change: C-CARD is now the materialized rate, not $150.)

### E-3 · Facility → C-F1
Billing `KEYSTONE-NPI01`, facility `KEYSTONE-NPI03`, member `KEYSTONE-MEM-1`,
institutional, 99213.
Expect: **$200** (C-F1) — SUCCESS.

### E-4 · Facility F2 fallback → C-IDN
As E-3 but facility `KEYSTONE-NPI04` (no F2 contract).
Expect: **$130** (falls back up hierarchy to C-IDN).

### E-5 · Group conflict still flags
Billing `KEYSTONE-NPI02` (CARD group), member `KEYSTONE-MEM-1`, professional, 99213,
NO rendering provider.
Expect: **AMBIGUOUS** (candidates 213 vs 215) + a row in `GET /api/resolution-exceptions/`.

---

## Regression — existing pricing unchanged

### R-1 · DEMO-UC catalog untouched
DEMO-UC contracts have no rate basis → prices identical to before A/B/D/E.
Spot-check on Claim Simulation (current IDs from the master query): B1 = $100, B2 = $200,
C10 = $175, C9 = $30.

### R-2 · Full suite
```
python manage.py test --keepdb
```
Expect: same baseline — 4 failures + 4 errors, no new failures.

---

## Coverage map

| Feature | Scenarios |
|---|---|
| A rate-schedule linkage | A-1..A-4 |
| B escalators | B-1..B-4 |
| D templating + bulk | D-1..D-4 |
| E scope consolidation (resolution unchanged) | E-1..E-5 |
| Regression | R-1, R-2 |
