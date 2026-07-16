# Matrix — Manual Test Runbook (current seed)

Ready-to-paste manual test set for the `DEMO-UC-*` demo data, with current IDs and
a description of what each case proves. Covers the pricing catalog **plus** the
recent resolution-layer features (R2 version capture, R4 audit log) and the
default lesser-of-billed behavior.

> **IDs valid for the current seed (contract 180–207 / version 160–187).**
> Numeric `contract_id`/`version_id` change on every `seed_use_cases --wipe`.
> The **Reprice** cases use natural keys and never go stale. To refresh the
> Claim-Simulation IDs after a reseed, re-run the master query in
> `docs/DEMO_TEST_CATALOG.md` (or query contracts whose name starts with `DEMO-UC-`).

## How to use
- **Reprice Claim page** (`/reprice-claim`) — identity-first; uses member_id + NPI.
  Used for resolution cases and the new audit-log/version tests.
- **Claim Simulation page** (`/claim-simulation`) — contract-first; uses
  `contract_id` + `version_id`. Used for methodology / modifier / edge cases.
- Service date for all cases unless noted: **2025-06-15**.
- Fill in **Actual** from the UI; derive **Expected** from the rule where marked.

---

## Part 0 — Recent feature tests (R2 / R4 / lesser-of)

### F1 — Resolution audit log + version capture  ·  Reprice page
**Proves:** R4 writes a persisted `ClaimResolutionLog`, and R2 now carries the
contract **version** through (previously null). This is the Pricing Investigator's
data foundation.
**Steps:** submit the payload, note `trace_id` + `resolution_log_id` in the response,
then open `GET /api/resolution-log/<trace_id>/` in the browser.
**Expected:** a saved record — resolved contract, non-null version, resolution_path =
CONTEXT_RESOLVER, resolver inputs. Pricing allowed = $100.
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

### F2 — Lesser-of-billed default through resolution  ·  Reprice page
**Proves:** allowed = MIN(contract rate, billed). Billed $50 is below the $100 rate.
**Expected:** allowed = **$50** (CAP_APPLIED), not $100.
```json
{
  "billing_npi": "DEMO-UC-NPI01",
  "rendering_npi": "DEMO-UC-NPI03",
  "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15",
  "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "50.00", "units": 1 }]
}
```

---

## Part A — Resolution  ·  Reprice page (natural keys, stable)

These prove the resolver picks — or correctly refuses — the right contract.

### A1 — In-network resolves to flat contract
**Proves:** enrolled member + in-network billing org → RESOLVED → priced.
**Expected:** SUCCESS, allowed **$100**.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A2 — Out-of-network billing org
**Proves:** member enrolled but billing org not participating → no contract.
**Expected:** OON, no price.
```json
{ "billing_npi": "DEMO-UC-NPI02", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A3 — Member not enrolled
**Proves:** no enrollment → resolver can't scope LOB/product.
**Expected:** NO_CONTRACT.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-NOENROLL",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A4 — Terminated enrollment before service date
**Proves:** enrollment ended 2025-05-01; service 2025-06-15 → no active coverage.
**Expected:** NO_CONTRACT.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-TERMED",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A5 — LOB-specific contract wins
**Proves:** member on MA product → MA-scoped contract chosen.
**Expected:** SUCCESS, allowed **$120** (the MA rate, not the $100 commercial).
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-MA",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A6 — Product scope beats LOB-only scope
**Proves:** product-scoped contract (A6, $175) wins over LOB-only (A6B, $100).
**Expected:** SUCCESS, allowed **$175**.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "250.00", "units": 1 }] }
```

### A7 — Org has no contract on member's network
**Proves:** member on HMO network; org's contract only on PPO.
**Expected:** OON.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-HMO",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A8 — Tiered network (TIER_2)
**Proves:** TIER_2 participation surfaces as IN_NETWORK + tier flag.
**Expected:** SUCCESS, allowed **$95**; trace shows TIER_2.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI03", "member_id": "DEMO-UC-MEM-TIER",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A9 — Rendering provider not affiliated with billing org
**Proves:** pricing still succeeds; trace shows affiliation_verified = false.
**Expected:** SUCCESS, allowed **$100**, affiliation_verified false.
```json
{ "billing_npi": "DEMO-UC-NPI01", "rendering_npi": "DEMO-UC-NPI04", "member_id": "DEMO-UC-MEM-A1",
  "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] }
```

### A10 — Direct contract override  ·  Claim Simulation (180/160)
**Proves:** caller supplies contract_id directly → DIRECT mode, resolution bypassed.
**Expected:** SUCCESS, allowed **$100**.
```json
{ "contract_id": 180, "version_id": 160, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

---

## Part B — Methodologies  ·  Claim Simulation page

### B1 — FLAT_RATE (186/166)
**Proves:** fixed dollar allowed. **Expected:** **$100**.
```json
{ "contract_id": 186, "version_id": 166, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

### B2 — PERCENT of billed (187/167)
**Proves:** allowed = 0.80 × billed. **Expected:** 0.80 × $250 = **$200**.
```json
{ "contract_id": 187, "version_id": 167, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "250.00", "units": 1 }] } }
```

### B3 — RBRVS (188/168)
**Proves:** fee-schedule × multiplier. **Expected:** $500 × 1.5 = **$750**.
```json
{ "contract_id": 188, "version_id": 168, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "29881", "billed_amount": "5000.00", "units": 1 }] } }
```

### B4 — PER_DIEM (189/169)
**Proves:** per-day rate × units. **Expected:** $400 × 3 = **$1,200**.
```json
{ "contract_id": 189, "version_id": 169, "claim": { "service_date": "2025-06-15", "claim_type": "institutional",
  "lines": [{ "procedure_code": "0120", "billed_amount": "8000.00", "units": 3, "revenue_code": "0120" }] } }
```

### B5 — Claim-level DRG (190/170)
**Proves:** DRG base × weight; `drg_code` on the claim. **Expected:** $6,000 × 2.0 = **$12,000**.
```json
{ "contract_id": 190, "version_id": 170, "claim": { "service_date": "2025-06-15", "claim_type": "institutional", "drg_code": "470",
  "lines": [{ "procedure_code": "470", "billed_amount": "50000.00", "units": 1 }] } }
```

### B6 — APC (191/171)
**Proves:** APC weight × conversion factor. **Expected:** verify against APC rate in result.
```json
{ "contract_id": 191, "version_id": 171, "claim": { "service_date": "2025-06-15", "claim_type": "institutional",
  "lines": [{ "procedure_code": "5121", "billed_amount": "3000.00", "units": 1 }] } }
```

### B7 — Anesthesia + flat add-on (192/172)
**Proves:** anesthesia = (base + time/15) × CF, plus a flat add-on line. `units` = minutes.
**Expected:** 00100 = (5 + 30/15) × $45 = **$315**; 99100 = **$25** flat; total **$340**.
```json
{ "contract_id": 192, "version_id": 172, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [ { "procedure_code": "00100", "billed_amount": "500.00", "units": 30 }, { "procedure_code": "99100", "billed_amount": "100.00", "units": 1 } ] } }
```

### B8 — ASP drug (193/173)
**Proves:** ASP payment limit × units. **Expected:** verify J1885 ASP × 2 in result.
```json
{ "contract_id": 193, "version_id": 173, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "J1885", "billed_amount": "500.00", "units": 2 }] } }
```

---

## Part C — Modifiers / policy  ·  Claim Simulation page

### C1 — Modifier -50 bilateral (194/174)
**Proves:** RBRVS base then ×150% for bilateral. **Expected:** $500 × 1.0 × 150% = **$750**.
```json
{ "contract_id": 194, "version_id": 174, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "29881", "billed_amount": "5000.00", "units": 1, "modifiers": ["50"] }] } }
```

### C2 — Multi-line flat (195/175)
**Proves:** two flat rules, one claim total. **Expected:** $100 + $75 = **$175**.
```json
{ "contract_id": 195, "version_id": 175, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [ { "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }, { "procedure_code": "73030", "billed_amount": "150.00", "units": 1 } ] } }
```

### C3 — MPPR on two imaging lines (196/176)
**Proves:** second imaging line reduced (100% / 50%). **Expected:** verify 2nd line is reduced vs 1st.
```json
{ "contract_id": 196, "version_id": 176, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [ { "procedure_code": "70450", "billed_amount": "800.00", "units": 1 }, { "procedure_code": "70450", "billed_amount": "800.00", "units": 1 } ] } }
```

### C4 — Carve-out excludes 99100 (197/177)
**Proves:** 99100 carved out / handled differently; 99213 prices normally.
**Expected:** verify 99100 line reflects the carve-out behavior.
```json
{ "contract_id": 197, "version_id": 177, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [ { "procedure_code": "99100", "billed_amount": "200.00", "units": 1 }, { "procedure_code": "99213", "billed_amount": "200.00", "units": 1 } ] } }
```

### C5 — Line cap 60% (198/178)
**Proves:** allowed capped at 60% of billed. **Expected:** min(RBRVS result, 60% × $500 = $300) → **$300**.
```json
{ "contract_id": 198, "version_id": 178, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "500.00", "units": 1 }] } }
```

### C6 — Claim outlier (199/179)
**Proves:** claim above threshold triggers outlier payment. **Expected:** verify outlier applied above $1,000.
```json
{ "contract_id": 199, "version_id": 179, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "5000.00", "units": 1 }] } }
```

### C7 — Stop-loss (200/180)  ·  needs `cost_amount`
**Proves:** claim cost above threshold switches to stop-loss %. **Expected:** verify stop-loss applied at 50%.
```json
{ "contract_id": 200, "version_id": 180, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "SL-TRIG", "billed_amount": "15000.00", "units": 1, "cost_amount": "15000.00" }] } }
```

### C8 — Blending (201/181)
**Proves:** claim total blended (ADD component). **Expected:** verify blended total vs base RBRVS.
```json
{ "contract_id": 201, "version_id": 181, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

### C9 — Code-group condition (202/182)
**Proves:** rule fires because 36415 is a member of code group 6 (not a direct code match).
**Expected:** SUCCESS, allowed **$30**.
```json
{ "contract_id": 202, "version_id": 182, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "36415", "billed_amount": "50.00", "units": 1 }] } }
```

### C10 — Specificity (203/183)
**Proves:** specific 99214 rule beats the wildcard rule. **Expected:** allowed **$175** (not $100).
```json
{ "contract_id": 203, "version_id": 183, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "300.00", "units": 1 }] } }
```

---

## Part D — Edge cases  ·  Claim Simulation page

### D1 — Unknown procedure code (204/184)
**Proves:** no rule matches → line denied. **Expected:** DENIED_NO_RULE, $0.
```json
{ "contract_id": 204, "version_id": 184, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "XXXXX", "billed_amount": "100.00", "units": 1 }] } }
```

### D2 — Service date outside contract window (205/185)
**Proves:** contract effective 2025; service dated 2024 → no active version.
**Expected:** NO_CONTRACT / no active version (note the 2024 date).
```json
{ "contract_id": 205, "version_id": 185, "claim": { "service_date": "2024-01-01", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1 }] } }
```

### D3 — Zero billed on PERCENT line (206/186)
**Proves:** 0.80 × $0 = $0, no crash. **Expected:** SUCCESS, allowed **$0.00**.
```json
{ "contract_id": 206, "version_id": 186, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99214", "billed_amount": "0.00", "units": 1 }] } }
```

### D4 — Unknown modifier ignored (207/187)
**Proves:** modifier XX not in reference → no adjustment, base price stands.
**Expected:** SUCCESS, allowed **$100** (same as plain flat).
```json
{ "contract_id": 207, "version_id": 187, "claim": { "service_date": "2025-06-15", "claim_type": "professional",
  "lines": [{ "procedure_code": "99213", "billed_amount": "200.00", "units": 1, "modifiers": ["XX"] }] } }
```

---

## Verification worksheet

| Case | Page | Expected | Actual | ✓ |
|------|------|----------|--------|---|
| F1 audit log | Reprice | log row + version + $100 | | |
| F2 lesser-of | Reprice | $50 | | |
| A1 | Reprice | $100 | | |
| A2 | Reprice | OON | | |
| A3 | Reprice | NO_CONTRACT | | |
| A4 | Reprice | NO_CONTRACT | | |
| A5 | Reprice | $120 | | |
| A6 | Reprice | $175 | | |
| A7 | Reprice | OON | | |
| A8 | Reprice | $95 / TIER_2 | | |
| A9 | Reprice | $100 / affil false | | |
| A10 | Sim | $100 / DIRECT | | |
| B1 | Sim | $100 | | |
| B2 | Sim | $200 | | |
| B3 | Sim | $750 | | |
| B4 | Sim | $1,200 | | |
| B5 | Sim | $12,000 | | |
| B6 | Sim | (verify) | | |
| B7 | Sim | $340 | | |
| B8 | Sim | (verify) | | |
| C1 | Sim | $750 | | |
| C2 | Sim | $175 | | |
| C3 | Sim | (2nd reduced) | | |
| C4 | Sim | (carve-out) | | |
| C5 | Sim | $300 | | |
| C6 | Sim | (outlier) | | |
| C7 | Sim | (stop-loss) | | |
| C8 | Sim | (blended) | | |
| C9 | Sim | $30 | | |
| C10 | Sim | $175 | | |
| D1 | Sim | denied $0 | | |
| D2 | Sim | no active version | | |
| D3 | Sim | $0.00 | | |
| D4 | Sim | $100 | | |

> Not yet manually testable (need extra seed data): R3 tie-breaking (DIRECT vs LEASED)
> and R5 provider hierarchy (IDN-level contract for a leaf NPI). Both are covered by
> automated tests in `tests/test_resolution_phases.py`.
