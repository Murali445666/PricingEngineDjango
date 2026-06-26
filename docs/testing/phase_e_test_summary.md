# Phase E — Claim-Level Methodology Registry: Test Summary

**Claim-level DRG runs in both LEGACY and STAGED line-pricing modes.** The "ENGINE STARTING - Mode: LEGACY" log refers only to per-line resolution (single rule vs BASE then ADJUSTMENT). The CLAIM_METHOD phase (DRG, then stop-loss, then outlier) runs after the line loop in `ClaimOrchestrator.run()` regardless of mode.

## What Phase E Adds

- **FacilityBaseRate:** Contract/version (optional facility_id), rate_type (DRG/APC), base_rate, effective dates. Used when claim-level DRG runs: payment = base_rate × RefDrg.relative_weight.
- **CaseRateDefinition:** Contract/version, case_rate_code, lump_sum_amount, effective dates (stub plugin; opt-in later).
- **ContractVersion.claim_level_drg_enabled:** Boolean, default False. When True, CLAIM_METHOD phase runs DRG plugin after line pricing.
- **Claim payload:** `drg_code`, `facility_id`, `provider_id` at claim level (optional). DRG code can also be taken from first line procedure_code when not set.
- **ExecutionContext:** `claim_level_payment`, `drg_applied`, `drg_code`.
- **Orchestrator:** After line loop and carve-outs, before stop-loss: run **CLAIM_METHOD** (DRG if enabled, then stop-loss, then outlier). Order: LINE → **CLAIM_METHOD** (DRG → stop-loss → outlier) → BLENDING → CLAIM_CAP_FLOOR.
- **Registry:** `core/engine/claim_strategies.py` — `CLAIM_METHODOLOGY_REGISTRY` with DRG and CASE_RATE plugins.

No change to line-level resolver or loader. When claim_level_drg_enabled, document that line-level DRG rules should not be used for that version (or skip line-level DRG for that claim type) to avoid double-apply.

---

## Migration

```bash
python manage.py migrate core
```

Migration `0029_phase_e_claim_level_methodology` adds:

- `contract_versions.claim_level_drg_enabled` (boolean, default False)
- Tables: `facility_base_rates`, `case_rate_definitions`

---

## Testing Steps

### 1. Migration and admin

1. Run `python manage.py migrate core`.
2. In admin: **Contract versions** — confirm **Claim level drg enabled** column and checkbox.
3. **Facility base rates** and **Case rate definitions** — add/edit rows.

### 2. Backward compatibility (claim_level_drg_enabled = False)

1. Leave `claim_level_drg_enabled` False for all versions.
2. Run an existing simulate (e.g. contract 10, version 2, one line).
3. **Expect:** Same total_allowed as before. No CLAIM_DRG_APPLIED in trace.

### 3. Claim-level DRG (enabled)

**Setup:**

1. Ensure **RefDrg** has a row for a drg_code and year (e.g. drg_code=`001`, year=2026, relative_weight=1.5).
2. **Contract version** (e.g. 10 / version 2): set **Claim level drg enabled** = True.
3. **Facility base rates** → Add: contract 10, version 2, facility_id blank, rate_type=DRG, base_rate=10000, effective 2026-01-01 to 2026-12-31.

**Test:**

1. POST `/api/price-claim-simulate/` with:
   - contract_id=10, version_id=2
   - claim: lines (one line is enough), service_date=2026-06-01, **drg_code**=001 (or omit and use procedure_code on first line = 001)
2. **Expect:** total_allowed = 10000 × 1.5 = 15000 (or base_rate × weight from your data). claim_trace contains "CLAIM_DRG_APPLIED". execution_trace has CLAIM phase CLAIM_METHOD with message drg_code=001.

### 4. DRG code from first line

1. Same setup as 3, but do **not** send drg_code in claim. Send first line with procedure_code=001 (matching a RefDrg drg_code).
2. **Expect:** Same result; plugin uses first line procedure_code as drg_code.

### 5. Facility-specific base rate (optional)

1. Add a **Facility base rate** with facility_id=99, same version, rate_type=DRG, base_rate=12000.
2. Send claim with **facility_id**=99.
3. **Expect:** total_allowed = 12000 × weight (facility-specific rate used). With facility_id null or missing, expect the facility_id=null row.

### 6. Stop-loss / outlier after DRG

1. With claim-level DRG enabled and returning 15000, add a stop-loss rule that triggers on total cost (e.g. threshold 1000, so stop-loss applies).
2. **Expect:** After DRG sets claim total to 15000, stop-loss runs and can replace it; or if stop-loss does not trigger, 15000 remains. Order: DRG → stop-loss → outlier → blending → cap/floor.

### 7. Rollback

1. Set **Claim level drg enabled** = False for the version.
2. **Expect:** No claim-level DRG; total_allowed is sum of line allowed amounts (or stop-loss/outlier if they apply).

---

## Summary

| Test | Purpose |
|------|--------|
| 1 | Schema and admin for Phase E |
| 2 | No behavior change when flag off |
| 3–4 | Claim-level DRG payment and drg_code from payload or first line |
| 5 | Facility-specific FacilityBaseRate |
| 6 | CLAIM_METHOD order (DRG then stop-loss/outlier) |
| 7 | Rollback by disabling flag |

When claim_level_drg_enabled is True, avoid using line-level DRG rules for that version so the claim is not priced twice (line-level + claim-level).
