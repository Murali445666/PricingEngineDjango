# Test playbook (live data snapshot)

Generated from DB queries: **ACTIVE** `pricing_rules` with `pricing_rule_conditions.attribute_name` = `procedure_code`, plus `contracts` / `contract_versions`. IDs reflect the database at authoring time; re-query if seeds change.

---

## 1. Start services & URLs

| What | Command / URL |
|------|----------------|
| Backend | `cd PricingEngineDjango` → `python manage.py runserver` → API base `http://127.0.0.1:8000/api/` |
| Frontend | `cd PricingEngineDjango/frontend` → `npm run dev` → `http://localhost:5173` |
| **Claim Simulation** (recommended) | `http://localhost:5173/claim-simulation` — `POST /api/price-claim-simulate/` with `contract_id`, `version_id`, `claim` |
| **Pricing Sandbox** | `http://localhost:5173/pricing-sandbox` — `POST /api/price-line/` (single line, **no** contract version) |

**Important:** Sandbox resolves rules with **`version_id IS NULL` only**. In this snapshot, only contract **8** has null-version rules (20, 23), but contract **8 has no rows in `contract_versions`**, so **claim simulation cannot target it** until a version exists. Use **Claim Simulation** with explicit `version_id` for all scenarios below.

---

## 2. Reference scenarios (Claim Simulation)

Use **`service_date`**: `2026-06-01` (inside rule `effective_start_date` / `effective_end_date` **2026-01-01**–**2026-12-31** for these rules).

Wrapper for every run:

```json
{
  "contract_id": <id>,
  "version_id": <id>,
  "claim": { ... }
}
```

### A — RBRVS (contract **9** `PRO_RBRVS_2026`, version **1**)

| Field | Value |
|-------|--------|
| **Rule** | `rule_id` **27**, `methodology_code` **RBRVS**, `version_id` **1** |
| **Condition** | `procedure_code` **EQ** `00100` |
| **Version** | `version_id` **1**, `pricing_engine_mode` **LEGACY**, `claim_level_drg_enabled` **False** |

**Claim JSON (`claim` only):**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "00100",
      "billed_amount": "500.00",
      "units": 1,
      "modifiers": []
    }
  ]
}
```

**Expect:** Line `status` **SUCCESS**, `methodology` **RBRVS**, `rule_id` **27**. Execution trace is mostly **LINE**-stage rows; no claim-level DRG on this version.

---

### B — DRG (contract **15** `DRG DemoMarch26`, version **8**)

| Field | Value |
|-------|--------|
| **Rule** | `rule_id` **77**, **DRG**, `version_id` **8** |
| **Condition** | `procedure_code` **EQ** `470` |
| **Claim type on rule** | **INPATIENT** (must match claim) |
| **Version** | **DRAFT** (allowed for simulate), `claim_level_drg_enabled` **False** |

**Claim JSON:**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "INPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "470",
      "billed_amount": "50000.00",
      "units": 1,
      "modifiers": []
    }
  ]
}
```

**Expect:** Line **SUCCESS**, **DRG**, `rule_id` **77** (if `ref_drg` / base rates / weights are valid). If **`relative_weight`** for DRG **470** is wrong, allowed amount may be unrealistic — fix reference data, not the UI.

---

### C — DRG alternate (contract **12** `IP_DRG_2026`, version **4**)

| Field | Value |
|-------|--------|
| **Rule** | e.g. **43**, **DRG**, condition **001** |
| **Version** | **ACTIVE**, **`claim_level_drg_enabled` = True** |

**Claim JSON:**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "INPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "001",
      "billed_amount": "10000.00",
      "units": 1,
      "modifiers": []
    }
  ]
}
```

**Expect:** Line-level resolution **DRG** / `rule_id` **43**; **execution / claim trace may include CLAIM-level DRG** (claim methodology), not LINE-only.

---

### D — FLAT_RATE (contract **10** `OP_FLAT_OUTPATIENT`, version **2**)

| Field | Value |
|-------|--------|
| **Rule** | **35**, **FLAT_RATE**, **BASE**, condition **00100** |
| **Version** | **STAGED** mode |

**Claim JSON:**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "00100",
      "billed_amount": "250.00",
      "units": 1,
      "modifiers": []
    }
  ]
}
```

**Expect:** **SUCCESS**, **FLAT_RATE**, `rule_id` **35**; allowed follows flat-rate logic (not capped to billed unless a cap/floor applies).

---

### E — PCT_BILLED (contract **14** `HYBRID_ENTERPRISE_COMPLEX`, version **6**)

| Field | Value |
|-------|--------|
| **Rule** | **62**, **PCT_BILLED**, **ADJUSTMENT**, condition **99213** |
| **Multiplier** | **0.8000** → allowed ≈ **80%** of line billed |
| **Version** | **ACTIVE**, **LEGACY** |

**Claim JSON:**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "99213",
      "billed_amount": "200.00",
      "units": 1,
      "modifiers": []
    }
  ]
}
```

**Expect:** **SUCCESS**, **PCT_BILLED** (or serializer’s methodology label), `rule_id` **62**; allowed about **160.00** if no other rule wins first.

---

## 3. Negative test (no matching rule)

**Contract 9**, **version 1** — no rule has `procedure_code` **NOMATCH999**.

**Claim JSON:**

```json
{
  "service_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "NOMATCH999",
      "billed_amount": "100.00",
      "units": 1,
      "modifiers": []
    }
  ]
}
```

**Expect:** Line **DENIED_NO_RULE** (or equivalent status), **rule_id** **0** / empty; UI should show the error outcome clearly (Claim Simulation uses `role="alert"` for API failures).

---

## 4. Troubleshooting

| Issue | Check |
|-------|--------|
| **DENIED_NO_RULE** | Rule **ACTIVE**? `pricing_rules.version_id` = simulate **`version_id`** or **NULL**? `effective_*` includes `service_date`? Condition **procedure_code** exact match? Rule **claim_type** matches JSON? |
| **Wrong version** | Simulate uses **`contract_versions.version_id`** (PK), not `version_number`. |
| **DRAFT OK** | Simulate allows **DRAFT** / **ACTIVE** / **SUPERSEDED**; **ARCHIVED** is rejected. |
| **Reference data** | **RBRVS**: fee schedule rates + optional MPFS RVU; **DRG**: `ref_drg.relative_weight` must be real weights, not the DRG code as weight. |
| **API errors** | Claim Simulation surfaces **4xx/5xx** and parse errors (invalid JSON) as banners / inline messages. |
| **Sandbox vs simulation** | Use **Claim Simulation** for version-scoped demo contracts (**9–15**). |

---

## 5. Re-query script (optional)

```bash
cd PricingEngineDjango
python manage.py shell -c "
from core.models import PricingRule, PricingRuleCondition, ContractVersion
for r in PricingRule.objects.filter(status='ACTIVE').order_by('rule_id'):
    pcs = list(r.conditions.filter(attribute_name__iexact='procedure_code').values_list('attribute_value', flat=True))
    if not pcs: continue
    print(r.rule_id, r.contract_id, r.version_id, r.methodology_code, pcs[0])
for v in ContractVersion.objects.order_by('contract_id', 'version_id'):
    print('V', v.version_id, 'contract', v.contract_id, v.version_number, v.status)
"
```
