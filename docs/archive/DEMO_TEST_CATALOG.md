# Matrix — Demo Test Catalog (DEMO-UC-*)

Manual pricing verification for the 32 seeded use cases. No automated tests — you
drive each scenario through the UI, read the result, and derive the expected price
by hand from the backing contract/rule.

## How to use this catalog

Two pages, two purposes:

- **Reprice Claim page** (`/reprice-claim`) — identity-first. You enter `member_id`,
  `billing_npi`, `rendering_npi`, lines. The system resolves member → product →
  network → contract automatically. **Use this for all RESOLUTION cases (A1–A10)** —
  they prove the system picks (or correctly refuses) the right contract.

- **Claim Simulation page** (`/claim-simulation`) — contract-first. You supply
  `contract_id` + `version_id` and the system prices directly against that contract,
  bypassing resolution. **Use this for METHODOLOGY / MODIFIER / EDGE cases (B, C, D)**
  to exercise the pricing rule itself.

For each case below: read **Proves**, paste the **JSON**, run it, then open the named
contract/rule in Django admin, compute the price by hand, and write it in **Expected $**.

Seed/reset: `python manage.py seed_use_cases` (idempotent) ·
`python manage.py seed_use_cases --wipe` (DEMO-UC-* only, then reload).
Service date for all cases unless noted: **2025-06-15**.

### Contract / version map (for Claim Simulation)

| UC | contract_id | version_id | UC | contract_id | version_id |
|----|----|----|----|----|----|
| A1 | 124| 104| B8 | 137 | 117 |
| A5 | 125| 105| C1 | 138 | 118 |
| A6 | 126| 106| C2 | 139 | 119 |
| A6B| 127| 107| C3 | 140 | 120 |
| A7 | 128| 108| C4 | 141 | 121 |
| A8 | 129| 109| C5 | 142 | 122 |
| B1 | 130| 110| C6 | 143 | 123 |
| B2 | 131| 111| C7 | 144 | 124 |
| B3 | 132| 112| C8 | 145 | 125 |
| B4 | 133| 113| C9 | 146 | 126 |
| B5 | 134| 114| C10| 147 | 127 |
| B6 | 135| 115| D1 | 148 | 128 |
| B7 | 136| 116| D2 | 149 | 129 |
|    |    |    | D3 | 150 | 130 |
|    |    |    | D4 | 151 | 131 |

---

## Family A — Resolution (test on **Reprice Claim** page)

These prove the resolver. Most produce a price; A2/A3/A4/A7 prove correct **refusal**.

### A1 — In-network member resolves to FLAT contract
**Proves:** member enrolled + billing org in-network → RESOLVED → priced.
**Expected status:** SUCCESS · **Expected $:** ________ (FLAT 99213 @ $100)
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A2 — Out-of-network billing org → OON
**Proves:** member enrolled but billing org not participating → no contract.
**Expected status:** OON · **Expected $:** n/a (no price)
```json
{
  "billing_npi": "DEMO-UC-NPI02",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A3 — Member not enrolled → NO_CONTRACT
**Proves:** no enrollment row → resolver cannot scope LOB/product.
**Expected status:** NO_CONTRACT · **Expected $:** n/a
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-NOENROLL",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A4 — Terminated enrollment before service date → NO_CONTRACT
**Proves:** enrollment ended 2025-05-01, service 2025-06-15 → no active coverage.
**Expected status:** NO_CONTRACT · **Expected $:** n/a
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-TERMED",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A5 — LOB-specific contract wins
**Proves:** member on MA product → MA-scoped contract chosen over generic.
**Expected status:** SUCCESS · **Expected $:** ________
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-MA",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A6 — Product scope beats LOB-only scope
**Proves:** ContractProductScope (A6) wins over LOB-only scope (A6B).
**Expected status:** SUCCESS · **Expected $:** ________ (confirm A6 contract, not A6B)
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "250.00", "units": 1 }]
}
```

### A7 — Org has no contract on member's network → OON
**Proves:** member on HMO network; org's contract only on PPO.
**Expected status:** OON · **Expected $:** n/a
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-HMO",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A8 — Tiered network (TIER_2)
**Proves:** participation status TIER_2 surfaces as IN_NETWORK + tier=TIER_2.
**Expected status:** SUCCESS · **Expected $:** ________ · check trace panel shows TIER_2
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-TIER",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A9 — Rendering provider not affiliated with billing org
**Proves:** pricing still succeeds; trace shows affiliation_verified = false.
**Expected status:** SUCCESS · **Expected $:** ________ · check affiliation_verified=false
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI04",
  "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
}
```

### A10 — Direct contract override
**Proves:** caller passes contract_id directly → DIRECT mode, OON NPI ignored.
Test on **Claim Simulation** (it is the contract-first path): contract_id 96 / version 76.
**Expected status:** SUCCESS · **Expected $:** ________ (same as A1, FLAT 99213 @ $100)
```json
{
  "contract_id": 124,
  "version_id": 104,
  "claim": {
    "service_date": "2025-06-15",
    "claim_type": "professional",
    "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }]
  }
}
```

---

## Family B — Methodologies (test on **Claim Simulation** page)

### B1 — FLAT_RATE (99213)
**Rule:** flat_rate = $100.00 · **Expected $:** ________
```json
{ "contract_id": 130, "version_id": 110, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

### B2 — PERCENT of billed (99214)
**Rule:** multiplier 0.80 × $250 → expect $200.00 · **Expected $:** ________
```json
{ "contract_id": 131, "version_id": 111, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "250.00", "units": 1 }] } }
```

### B3 — RBRVS (29881)
**Rule:** fee schedule $500 × 1.5 → expect $750 · **Expected $:** ________
```json
{ "contract_id": 132, "version_id": 112, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "29881", "billed_amount": "5000.00", "units": 1 }] } }
```

### B4 — PER_DIEM (institutional, revenue code 0120)
**Rule:** $400/day × 3 units → expect $1200 · **Expected $:** ________
```json
{ "contract_id": 133, "version_id": 113, "claim": {
  "service_date": "2025-06-15", "claim_type": "institutional",
  "lines": [{ "procedure_code": "0120", "billed_amount": "8000.00", "units": 3, "revenue_code": "0120" }] } }
```

### B5 — DRG (DRG-470, claim-level)
**Rule:** base $6000 × weight 2.0 → expect $12000. Note `drg_code` on the claim.
**Expected $:** ________
```json
{ "contract_id": 134, "version_id": 114, "claim": {
  "service_date": "2025-06-15", "claim_type": "institutional", "drg_code": "470",
  "lines": [{ "procedure_code": "470", "billed_amount": "50000.00", "units": 1 }] } }
```

### B6 — APC (institutional outpatient)
**Rule:** APC weight 1.5 × CF $100 · **Expected $:** ________
```json
{ "contract_id": 135, "version_id": 115, "claim": {
  "service_date": "2025-06-15", "claim_type": "institutional",
  "lines": [{ "procedure_code": "5121", "billed_amount": "3000.00", "units": 1 }] } }
```

### B7 — ANESTHESIA (00100 + 99100 add-on)
**Rule:** base units 5 × CF 45; +99100 flat add-on · **Expected $:** ________
```json
{ "contract_id": 136, "version_id": 116, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [
    { "procedure_code": "00100", "billed_amount": "500.00", "units": 1 },
    { "procedure_code": "99100", "billed_amount": "100.00", "units": 1 }
  ] } }
```

### B8 — DRUG / ASP (J1885)
**Rule:** ASP payment_limit × 2 units · **Expected $:** ________
```json
{ "contract_id": 137, "version_id": 117, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "J1885", "billed_amount": "500.00", "units": 2 }] } }
```

---

## Family C — Modifiers / policy (test on **Claim Simulation** page)

### C1 — Modifier -50 bilateral (29881)
**Rule:** RBRVS base then ×150% · **Expected $:** ________
```json
{ "contract_id": 138, "version_id": 118, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "29881", "billed_amount": "5000.00", "units": 1, "modifiers": ["50"] }] } }
```

### C2 — Multi-line mixed flat (99213 + 73030)
**Rule:** two flat rules, one claim total · **Expected $:** ________
```json
{ "contract_id": 139, "version_id": 119, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [
    { "procedure_code": "99213", "billed_amount": "200.00", "units": 1 },
    { "procedure_code": "73030", "billed_amount": "150.00", "units": 1 }
  ] } }
```

### C3 — MPPR on two imaging lines (70450 ×2)
**Rule:** 100% first / 50% second · **Expected $:** ________
```json
{ "contract_id": 140, "version_id": 120, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [
    { "procedure_code": "70450", "billed_amount": "800.00", "units": 1 },
    { "procedure_code": "70450", "billed_amount": "800.00", "units": 1 }
  ] } }
```

### C4 — Carve-out excludes 99100
**Rule:** carveout EXCLUDE on 99100; 99213 prices normally · **Expected $:** ________
```json
{ "contract_id": 141, "version_id": 121, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [
    { "procedure_code": "99100", "billed_amount": "200.00", "units": 1 },
    { "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }
  ] } }
```

### C5 — Line cap/floor (PCT_BILLED_CAP 60%)
**Rule:** allowed capped at 60% of $500 → $300 · **Expected $:** ________
```json
{ "contract_id": 142, "version_id": 122, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "500.00", "units": 1 }] } }
```

### C6 — Claim outlier above threshold
**Rule:** threshold $1000 @ 80% · **Expected $:** ________
```json
{ "contract_id": 143, "version_id": 123, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "5000.00", "units": 1 }] } }
```

### C7 — Stop-loss (SL-TRIG, needs cost_amount)
**Rule:** threshold $1000 @ 50%; cost on the line drives the trigger · **Expected $:** ________
```json
{ "contract_id": 144, "version_id": 124, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "SL-TRIG", "billed_amount": "15000.00", "units": 1, "cost_amount": "15000.00" }] } }
```

### C8 — Blending ADD on claim total
**Rule:** ADD 10% of billed · **Expected $:** ________
```json
{ "contract_id": 145, "version_id": 125, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

### C9 — Code-group condition (36415 in LAB_CODES)
**Rule:** rule applies only because 36415 is in the code group · **Expected $:** ________
```json
{ "contract_id": 146, "version_id": 126, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "36415", "billed_amount": "50.00", "units": 1 }] } }
```

### C10 — Specificity (specific 99214 rule beats wildcard)
**Rule:** specific flat $175 vs wildcard $100 → expect $175 · **Expected $:** ________
```json
{ "contract_id": 147, "version_id": 127, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "300.00", "units": 1 }] } }
```

---

## Family D — Edge cases (test on **Claim Simulation** page)

### D1 — Unknown procedure code
**Proves:** no rule matches → line denied. Claim status may be non-SUCCESS.
**Expected:** line DENIED_NO_RULE · **Expected $:** $0 / denied
```json
{ "contract_id": 148, "version_id": 128, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "XXXXX", "billed_amount": "100.00", "units": 1 }] } }
```

### D2 — Service date outside contract window
**Proves:** contract effective 2025-01-01..2025-12-31; service 2024-01-01 → no active version.
On Claim Simulation this should error/return no active version. On Reprice it is NO_CONTRACT.
**Expected status:** NO_CONTRACT / no active version
```json
{ "contract_id": 149, "version_id": 129, "claim": {
  "service_date": "2024-01-01", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

### D3 — Zero billed on PERCENT line
**Proves:** 80% × $0 = $0, no crash · **Expected $:** $0.00
```json
{ "contract_id": 150, "version_id": 130, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "0.00", "units": 1 }] } }
```

### D4 — Unknown modifier ignored
**Proves:** modifier XX not in RefModifier → no adjustment, base price stands.
**Expected $:** ________ (same as plain FLAT 99213)
```json
{ "contract_id": 151, "version_id": 131, "claim": {
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1, "modifiers": ["XX"] }] } }
```

---

## Verification worksheet

Fill **Actual $** from the UI and **Expected $** from your hand calculation. They should match.

| UC | Page | Expected status | Expected $ | Actual status | Actual $ | ✓ |
|----|------|-----------------|-----------|---------------|----------|---|
| A1 | Reprice | SUCCESS | | | | |
| A2 | Reprice | OON | n/a | | n/a | |
| A3 | Reprice | NO_CONTRACT | n/a | | n/a | |
| A4 | Reprice | NO_CONTRACT | n/a | | n/a | |
| A5 | Reprice | SUCCESS | | | | |
| A6 | Reprice | SUCCESS | | | | |
| A7 | Reprice | OON | n/a | | n/a | |
| A8 | Reprice | SUCCESS | | | | |
| A9 | Reprice | SUCCESS | | | | |
| A10| Sim | SUCCESS | | | | |
| B1 | Sim | SUCCESS | | | | |
| B2 | Sim | SUCCESS | | | | |
| B3 | Sim | SUCCESS | | | | |
| B4 | Sim | SUCCESS | | | | |
| B5 | Sim | SUCCESS | | | | |
| B6 | Sim | SUCCESS | | | | |
| B7 | Sim | SUCCESS | | | | |
| B8 | Sim | SUCCESS | | | | |
| C1 | Sim | SUCCESS | | | | |
| C2 | Sim | SUCCESS | | | | |
| C3 | Sim | SUCCESS | | | | |
| C4 | Sim | SUCCESS | | | | |
| C5 | Sim | SUCCESS | | | | |
| C6 | Sim | SUCCESS | | | | |
| C7 | Sim | SUCCESS | | | | |
| C8 | Sim | SUCCESS | | | | |
| C9 | Sim | SUCCESS | | | | |
| C10| Sim | SUCCESS | | | | |
| D1 | Sim | denied | $0 | | | |
| D2 | Sim | no active version | n/a | | n/a | |
| D3 | Sim | SUCCESS | $0.00 | | | |
| D4 | Sim | SUCCESS | | | | |

> Note: the `contract_id`/`version_id` values above are from the current seeded DB.
> If you run `seed_use_cases --wipe` and reload, these IDs will change (auto-increment).
> Re-query with: contracts whose name starts with `DEMO-UC-` and their ACTIVE version.
> The Reprice (Family A) payloads use natural keys and are stable across reseeds.
