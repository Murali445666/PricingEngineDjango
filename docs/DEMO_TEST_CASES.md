# Demo test cases — deterministic pricing scenarios

Run seed (idempotent):

```bash
cd PricingEngineDjango
python manage.py seed_demo
```

Then use **Claim Simulation** (`http://localhost:5173/claim-simulation`) or `POST /api/price-claim-simulate/` with `contract_id` + `version_id` from the seed output.

**Service date for all scenarios:** `2026-06-01`

Regression tests: `python manage.py test tests.demo`

---

## Base payment contracts

| Contract | Payment type | Service type | Procedure | Expected allowed / total | Explanation |
|----------|--------------|--------------|-----------|--------------------------|-------------|
| **DEMO_RBRVS** | RBRVS | PROFESSIONAL | 99213 | **$150.00** | Fee schedule $100 × multiplier 1.5 |
| **DEMO_DRG** | DRG (claim-level) | INPATIENT | 470 | **$12,000.00** claim total | Facility base $6,000 × DRG weight 2.0 |
| **DEMO_FLAT** | FLAT_RATE | OUTPATIENT | 00100 | **$250.00** | Fixed flat rate (billed ignored) |
| **DEMO_PCT_BILLED** | PCT_BILLED | OUTPATIENT | 99213 | **$160.00** | 80% of $200 billed |
| **DEMO_APC** | APC | OUTPATIENT | 5121 | **$150.00** | APC weight 1.5 × CF $100 |
| **DEMO_ASP** | ASP | PROFESSIONAL | J0129 | **$24.00** | Payment limit $12 × 2 units (2026-Q2) |
| **DEMO_PER_DIEM** | PER_DIEM | INPATIENT | 0120 | **$1,200.00** | $400/day × 3 units |
| **DEMO_ANESTHESIA** | ANESTHESIA | PROFESSIONAL | 00100 | **$315.00** | (5 base + 2 time) × $45 CF; 30 minutes |

---

### DEMO_RBRVS

**Claim JSON (`claim` only):**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    { "line_id": "L1", "procedure_code": "99213", "billed_amount": "200.00", "units": 1, "modifiers": [] }
  ]
}
```

**Expected:** line `SUCCESS`, methodology `RBRVS`, allowed **150.00**, rule **RBRVS 99213**.

---

### DEMO_DRG

**Claim JSON:**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "INPATIENT",
  "drg_code": "470",
  "lines": [
    { "line_id": "L1", "procedure_code": "470", "billed_amount": "50000.00", "units": 1, "modifiers": [] }
  ]
}
```

**Expected:** claim total **12000.00**; claim trace contains `CLAIM_DRG_APPLIED`. Version has `claim_level_drg_enabled=true`.

---

### DEMO_FLAT

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    { "line_id": "L1", "procedure_code": "00100", "billed_amount": "300.00", "units": 1, "modifiers": [] }
  ]
}
```

**Expected:** **250.00** flat allowed.

---

### DEMO_PCT_BILLED

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    { "line_id": "L1", "procedure_code": "99213", "billed_amount": "200.00", "units": 1, "modifiers": [] }
  ]
}
```

**Expected:** **160.00** (0.8 × 200).

---

### DEMO_APC

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    { "line_id": "L1", "procedure_code": "5121", "billed_amount": "500.00", "units": 1, "modifiers": [] }
  ]
}
```

**Expected:** **150.00** APC allowed.

---

### DEMO_ASP

```json
{
  "service_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    { "line_id": "L1", "procedure_code": "J0129", "billed_amount": "50.00", "units": 2, "modifiers": [] }
  ]
}
```

**Expected:** **24.00** ASP allowed.

---

### DEMO_PER_DIEM

```json
{
  "service_date": "2026-06-01",
  "claim_type": "INPATIENT",
  "lines": [
    { "line_id": "L1", "procedure_code": "0120", "billed_amount": "5000.00", "units": 3, "modifiers": [] }
  ]
}
```

**Expected:** **1200.00** ($400 × 3 days).

---

### DEMO_ANESTHESIA

```json
{
  "service_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    { "line_id": "L1", "procedure_code": "00100", "billed_amount": "1000.00", "units": 30, "modifiers": [] }
  ]
}
```

**Expected:** **315.00** — base units 5 from fee schedule + 30÷15 time units, × $45.

---

## DEMO_POLICY — non-base behaviors

Base rules on this contract: **99213** RBRVS $150, **99100** RBRVS $100, **73030** FLAT $75.

`seed_demo` attaches **all** policy rows for UI exploration. Regression tests isolate **one policy at a time** (`tests/demo/policy_fixtures.py`).

| Scenario | Trigger | Before | After | Explanation |
|----------|---------|--------|-------|-------------|
| Carve-out EXCLUDE | 99100 line | $100 base | **$0** line | EXCLUDE carve-out zeros line |
| Stop-loss | 99213, cost $9,000 | $150 line | **$5,000** claim | $1,000 + 50% of $8,000 excess |
| Outlier | 73030, billed $5,000 | $75 line | **$4,000** claim | 80% of charges above threshold |
| Blending ADD | 73030, billed $1,000 | $75 | **$175** claim | +10% of billed |
| Claim CAP | two × 99213 | $300 | **$250** claim | Claim cap clamps total |
| Claim FLOOR | 73030 | $75 | **$100** claim | Claim floor raises total |
| MPPR | two × 99213 | $150 + $150 | **$150 + $75** lines | 100% / 50% MPPR → $225 total |

### Carve-out example

```json
{
  "service_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    { "procedure_code": "99100", "billed_amount": "150.00", "units": 1, "modifiers": [] }
  ]
}
```

### Stop-loss example (include `cost_amount` on line)

```json
{
  "service_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    {
      "procedure_code": "99213",
      "billed_amount": "200.00",
      "units": 1,
      "modifiers": [],
      "cost_amount": "9000.00"
    }
  ]
}
```

---

## Negative test (DEMO_RBRVS)

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    { "procedure_code": "NOMATCH999", "billed_amount": "100.00", "units": 1, "modifiers": [] }
  ]
}
```

**Expected:** `DENIED_NO_RULE`, allowed **0.00**.

---

## Resolve IDs after seed

```bash
python manage.py shell -c "
from core.demo.deterministic_seed import resolve_demo_registry
for k, v in resolve_demo_registry().items():
    print(k, 'contract_id', v['contract_id'], 'version_id', v['version_id'])
"
```

---

## Source of truth

- Seed logic: `core/demo/deterministic_seed.py`
- Scenario metadata: `core/demo/scenarios.py`
- Tests: `tests/demo/test_demo_*.py`
