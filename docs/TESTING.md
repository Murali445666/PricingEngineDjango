# Testing — Manual Scenario Guide

The single source of truth for manually exercising the platform. Three surfaces:

| Surface | URL | Tests |
|---|---|---|
| **Reprice Claim** page | `/reprice-claim` | Identity-first: resolution (which contract, or a flagged failure). Uses `member_id` + NPIs. |
| **Claim Simulation** page | `/claim-simulation` | Contract-first: pricing math for a chosen `contract_id` + `version_id`. |
| **Management commands** | terminal | Rate materialization, cloning, bulk load. |

**Answer-key logic:** each contract prices a code at a distinct rate, so the **allowed
amount tells you which contract resolved.**

**Baseline:** `python manage.py test --keepdb` → **8 failing is the accepted baseline**
(7 pre-existing: `test_apc_01/02/03`, `test_drg_01/02`, `test_err_01_missing_rule`,
`test_wrong_version_for_contract_returns_400`; + `test_explorer_includes_cap_floors` from
the lesser-of-billed feature). Any *other* failure is a real regression. See
`KNOWN_LIMITATIONS.md`.

---

## Getting current IDs

DEMO-UC contract/version IDs change on every `seed_use_cases --wipe`. KEYSTONE IDs
(212–216) are stable unless re-seeded. Reprice cases use **natural keys** and never go
stale. To refresh Claim-Simulation IDs, run this in MySQL Workbench:

```sql
SELECT c.contract_id, c.contract_name, v.version_id,
       r.methodology_code, r.flat_rate, r.multiplier,
       GROUP_CONCAT(CONCAT(cond.attribute_name,' ',cond.operator,' ',cond.attribute_value) SEPARATOR '  |  ') AS conditions
FROM contracts c
JOIN contract_versions v ON v.contract_id = c.contract_id
LEFT JOIN pricing_rules r ON r.version_id = v.version_id
LEFT JOIN pricing_rule_conditions cond ON cond.rule_id = r.rule_id
WHERE c.contract_name LIKE 'DEMO-UC-%'
GROUP BY c.contract_id, c.contract_name, c.status, v.version_id,
         r.rule_id, r.methodology_code, r.flat_rate, r.multiplier
ORDER BY c.contract_name, r.rule_id;
```

---

## Part 1 — Resolution (Reprice page)

Proves the resolver picks the right contract or flags a failure. Multi-entity data lives
in the **KEYSTONE** seed (`python manage.py seed_keystone`).

### KEYSTONE answer keys
| Contract | id | 99213 rate | Covers |
|---|---|---|---|
| C-IDN | 212 | $130 (literal) | ORG Keystone Health |
| C-CARD | 213 | $108.06 (2025) / $111.30 (2026) — *materialized* | ORG Keystone Cardiology + PROVIDER Dr. Chen |
| C-F1 | 214 | $200 (literal) | FACILITY Keystone General |
| C-CARD-OLD | 215 | $999 (the conflict) | ORG Keystone Cardiology |

Natural keys: member `KEYSTONE-MEM-1`; billing NPIs `KEYSTONE-NPI01` (IDN),
`KEYSTONE-NPI02` (Cardiology group); facility NPIs `KEYSTONE-NPI03` (F1), `KEYSTONE-NPI04`
(F2); rendering `KEYSTONE-NPI05` (Dr. Chen). *(Materialize 213 for 2025 first so C-CARD reads $108.06.)*

| # | Scenario | billing / rendering / facility | claim_type | Expected |
|---|---|---|---|---|
| R1 | IDN professional | NPI01 | professional | **$130** (C-IDN) |
| R2 | Provider-specific wins | NPI01 + NPI05 (Chen) | professional | **$108.06** (C-CARD, provider beats org) |
| R3 | Facility resolution | NPI01, facility NPI03 | institutional | **$200** (C-F1) |
| R4 | Hierarchy fallback | NPI01, facility NPI04 (no F2 contract) | institutional | **$130** (up to C-IDN) |
| R5 | Genuine conflict | NPI02, no rendering | professional | **AMBIGUOUS** (213 vs 215) |

**Base payload** (Reprice page; add `rendering_npi` / `facility_npi` per row):
```json
{ "billing_npi": "KEYSTONE-NPI01", "member_id": "KEYSTONE-MEM-1",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "500.00", "units": 1 }] }
```

### Graceful failures (DEMO-UC keys)
| # | Scenario | member / billing | Expected |
|---|---|---|---|
| F1 | OON provider | `DEMO-UC-MEM-A1` / `DEMO-UC-NPI02` | **OON**, no price |
| F2 | Not enrolled | `DEMO-UC-MEM-NOENROLL` / `DEMO-UC-NPI01` | **NO_CONTRACT** ("no active enrollment") |
| F3 | Terminated enrollment | `DEMO-UC-MEM-TERMED` / `DEMO-UC-NPI01` | **NO_CONTRACT** ("no active enrollment") |
| F4 | Ambiguous org | `DEMO-UC-MEM-A1` / `DEMO-UC-NPI01` | **AMBIGUOUS** + candidates |

**Coverage-gap vs config-conflict.** F2/F3 (member unenrolled or termed) resolve to
**NO_CONTRACT** — a coverage problem. F4's member *is* enrolled, so its org-level tie is a
real config conflict → **AMBIGUOUS**. The resolver short-circuits on "no enrollment" before
org-level contract matching so the two never get confused (see KNOWN_LIMITATIONS §2.6).

### Review queue
After any failure above: `GET http://localhost:8000/api/resolution-exceptions/`
→ a row per flagged resolution (status, candidates, gathered inputs).
`PATCH /api/resolution-exceptions/<id>/` `{ "is_reviewed": true, "review_notes": "..." }`.

---

## Part 2 — Pricing methodology catalog (Claim Simulation page)

The DEMO-UC contracts exercise every methodology. Pull current `contract_id`/`version_id`
from the SQL query above; on the page, pick contract + version and paste the **inner claim
object** (service_date, claim_type, lines) into the JSON box.

| Case | Methodology | Code(s) | Expected (literal seed rates) |
|---|---|---|---|
| B1 | FLAT_RATE | 99213 | $100 |
| B2 | PERCENT | 99214 @ $250 | $200 (0.80×) |
| B3 | RBRVS | 29881 | base $400 × 1.5 (verify) |
| B4 | PER_DIEM | 0120 ×3 | $1,200 |
| B5 | DRG | 470 (institutional, `drg_code:"470"`) | $12,000 |
| B6 | APC | 5121 (institutional) | verify |
| B7 | ANESTHESIA + add-on | 00100 (units=minutes) + 99100 | (5+min/15)×$45 + $25 |
| B8 | DRUG/ASP | J1885 ×2 | verify |
| C1 | Modifier -50 | 29881 + `modifiers:["50"]` | base × 150% (see §1.4 KNOWN_LIMITATIONS) |
| C2 | Multi-line | 99213 + 73030 | $175 |
| C3 | MPPR | 70450 ×2 | 100% / 50% (see §1.5) |
| C5 | Line cap | 99213 @ billed low | capped |
| C7 | Stop-loss | SL-TRIG + `cost_amount` | stop-loss % |
| C9 | Code group | 36415 | $30 (via group) |
| C10 | Specificity | 99214 | $175 (specific beats wildcard) |
| D1 | Unknown code | XXXXX | DENIED, $0 |
| D3 | Zero billed | 99214 @ $0 | $0 |
| D4 | Unknown modifier | 99213 + `["ZZ"]` | $100 (ignored — use a code NOT in RefModifier) |

**Inner-claim JSON template:**
```json
{ "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```
DRG/APC/per-diem use `"claim_type": "institutional"`; B5 adds `"drg_code": "470"`.

**Note:** modifiers and caps only appear in the trace when they *bind*; a configured cap
that doesn't reduce the price leaves no trace line (see KNOWN_LIMITATIONS §1.4/§2.x).

---

## Part 3 — Contract intensification (management commands)

### A — Rate-schedule linkage
```
python manage.py setup_rate_basis_demo
python manage.py materialize_rates --contract 213 --year 2025
```
- rule 293 (99213) → **$108.06** (2.75 RVU × $32.7442 CF × 120%). Prints `old -> new`.
- C-IDN (212) unchanged at **$130** (no basis). Idempotent on re-run.
- `/contracts/213/summary` shows "120% of MPFS 2025".

### B — Escalators
```
python manage.py materialize_rates --contract 213 --year 2026
```
- 99213 → **$111.30** ($108.06 × 1.03). `--year 2025` → $108.06 (base year, no escalation).
- Idempotent per year. Summary shows "120% of MPFS 2025, +3%/yr".

### D — Templating + bulk
```
python manage.py clone_contract --source 213 --name "Test Clone" --org KEYSTONE-IDN
python manage.py bulk_add_rates --contract <clone_id> --contract-version <vid> --schedule <sid> --percentage 120 --codes 99215,99204
```
- Clone gets its own PKs; **source 213 untouched**. Bulk codes materialize to concrete rates.
- Clone `/contracts/<id>/summary` reads like a real rate exhibit.

### E — Scope consolidation
No new behavior to test — the check is that **KEYSTONE resolution (Part 1) is unchanged**
after the scope tables were unified. Run R1–R5 and confirm same contracts/prices.

---

## Part 4 — HM-KHS agreement exhibit (contract 217)

Full Exhibit C fee schedule on `HM-KHS-2025-0417` (contract **217**, version **197**).
Seed with `python manage.py seed_agreement`, then load rates:

```
python manage.py import_fee_schedule --csv docs/Exhibit_C_Fee_Schedule.csv --contract 217 --contract-version 197 --year 2025
```

Natural keys: member `KHS-MEM-0001`; billing NPI `KEYSTONE-NPI02` (Cardiology group);
rendering `KEYSTONE-NPI05` (Dr. Chen). DOS `2025-06-15`, claim_type `professional`.

| # | Scenario | billing / rendering | Expected |
|---|---|---|---|
| P1 | Org rule (no carve-out) | NPI02, no rendering | **$108.12** (99213 org rule, score 10) |
| P5 | Provider carve-out | NPI02 + NPI05 (Chen) | **$116.44** (99213 Chen rule, score 70) |

**P5 proves practitioner-level specificity:** Dr. Chen's rule carries a `provider_id`
condition (140% MPFS → $116.44) and beats the org-wide 130% rule ($108.12) because its
`specificity_score` is higher (70 vs 10), not because of contract ambiguity.

**Base payload** (Reprice page; add `rendering_npi` for P5):
```json
{ "billing_npi": "KEYSTONE-NPI02", "member_id": "KHS-MEM-0001",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

Post-import checks:
- `POST /api/validate-contract/217/` → **0 errors, 0 warnings**
- Version 197 rule count → **1113** (92920 deduped)
- `ContractRateBasis` rows on version 197 → **768** (RBRVS percentage rows; 345 APC/DRG/per-diem/fee-schedule/drug rows skipped)
- Re-run `import_fee_schedule` → **0 created**, rule ids unchanged (upsert, not replace)

---

## Regression checks
- **DEMO-UC prices unchanged** — DEMO-UC contracts have no rate basis, so Part 2 values are
  identical to before the intensification work.
- **Full suite** — `python manage.py test --keepdb` → the 8-failing baseline, no new failures.
