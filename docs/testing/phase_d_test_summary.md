# Phase D — Reference-Only Pricing: Test Summary

## What Phase D Adds

- **New reference tables:** `PerDiemRate`, `ModifierAdjustment`, `ContractFlatRateOverride`.
- **PricingRule:** Optional `per_diem_rate_id`, `flat_rate_override_id` (FKs). Existing `multiplier` and `flat_rate` columns kept but deprecated when feature flag is on.
- **ContractMethodology:** Optional `contract_term_id` (FK to ContractTerm). Existing `conversion_factor` and `base_percentage` kept but deprecated when feature flag is on.
- **Loader (Phase D):**
  - **Multiplier / conversion_factor:** When `USE_REFERENCE_ONLY_PRICING = True`, resolve only from ContractTerm: `rule.contract_term_id` else `methodology.contract_term_id` else default `1.0000`. Do not read `rule.multiplier` or `methodology.conversion_factor`.
  - **Flat rate:** When flag is True, resolve from: `rule.per_diem_rate_id` (PerDiemRate), `rule.flat_rate_override_id` (ContractFlatRateOverride), or fee schedule + FeeScheduleRate. Do not read `rule.flat_rate`.
  - **Modifier adjustments:** Load `ModifierAdjustment` for contract/version and service_date; overlay on `context.modifier_adjustments` (contract overrides RefModifier for same modifier_code).
- **Feature flag:** `USE_REFERENCE_ONLY_PRICING` (Django settings). Default `False` for backward compatibility. Set to `True` after backfill.

---

## Django Setting

Add to your Django settings module (e.g. `config/settings.py`):

```python
# Phase D: When True, loader uses only reference tables for multiplier/flat_rate;
# rule.multiplier, rule.flat_rate, methodology.conversion_factor are ignored.
# Default False until backfill is done and validated.
USE_REFERENCE_ONLY_PRICING = False
```

---

## Migration

```bash
python manage.py migrate core
```

Migration `0028_phase_d_reference_only_pricing` creates:

- Tables: `per_diem_rates`, `modifier_adjustments`, `contract_flat_rate_overrides`
- Columns: `contract_methodologies.contract_term_id`, `pricing_rules.per_diem_rate_id`, `pricing_rules.flat_rate_override_id`

---

## Testing Steps

### 1. **Migration and admin**

1. Run `python manage.py migrate core`.
2. Open Django admin → **Per diem rates**, **Modifier adjustments**, **Contract flat rate overrides**. Confirm tables exist and you can add rows.
3. Open **Pricing rules** → edit a rule. Confirm **Per diem rate** and **Flat rate override** dropdowns appear (optional).
4. Open **Contract methodologies** (if registered) or DB: confirm `contract_term_id` column exists.

### 2. **Backward compatibility (flag False)**

1. Ensure `USE_REFERENCE_ONLY_PRICING = False` (or unset).
2. Run an existing simulate request that uses rules with `multiplier` / `flat_rate` (e.g. contract 10, version 2, procedure_code 99998).
3. **Expect:** Same allowed amount as before Phase D. Loader still uses `rule.multiplier` and `rule.flat_rate`.

### 3. **ContractTerm multiplier (flag True) — rule-level**

1. Create a **Contract term**: contract 10, version 2, name "Phase D term", multiplier e.g. `1.5000`, effective 2026-01-01 to 2026-12-31.
2. Edit a **Pricing rule** that uses RBRVS/PCT_BILLED: set **Contract term** to that term; leave **Multiplier** as-is.
3. Set `USE_REFERENCE_ONLY_PRICING = True` in settings.
4. Run simulate for that contract/version and a procedure that hits that rule.
5. **Expect:** Allowed amount uses 1.5000 (from ContractTerm), not rule.multiplier.
6. Set flag back to `False`; run same request. **Expect:** Uses rule.multiplier again.

### 4. **ContractTerm multiplier (flag True) — methodology-level**

1. Create a **Contract term** as above (multiplier e.g. `2.0000`).
2. Create or edit a **Contract methodology** (DB or future admin): set `contract_term_id` to that term; leave `conversion_factor` as-is.
3. Use a rule that inherits methodology (rule.methodology_code blank) and does not set rule.contract_term_id.
4. Set `USE_REFERENCE_ONLY_PRICING = True`.
5. Run simulate.
6. **Expect:** Conversion factor 2.0000 from methodology’s ContractTerm.

### 5. **PerDiemRate (flag True)**

1. Create **Per diem rate**: contract 10, version 2, rate_amount e.g. `750.00`, effective 2026-01-01 to 2026-12-31.
2. Edit a **Pricing rule** with methodology PER_DIEM: set **Per diem rate** to that row; leave **Flat rate** as-is.
3. Set `USE_REFERENCE_ONLY_PRICING = True`.
4. Run simulate for a line that matches that rule.
5. **Expect:** Line uses 750.00 (from PerDiemRate), not rule.flat_rate.

### 6. **ContractFlatRateOverride (flag True)**

1. Create **Contract flat rate override**: contract 10, version 2, procedure_code blank (or a specific code), rate_amount e.g. `25.00`, effective 2026-01-01 to 2026-12-31.
2. Edit a **Pricing rule** (FLAT_RATE, no fee schedule): set **Flat rate override** to that row.
3. Set `USE_REFERENCE_ONLY_PRICING = True`.
4. Run simulate.
5. **Expect:** Line uses 25.00 from override.

### 7. **ModifierAdjustment overlay**

1. Ensure a modifier (e.g. `26`) exists in **Ref modifiers** with percentage_adjustment e.g. 100.
2. Create **Modifier adjustment**: contract 10, version 2, modifier_code `26`, adjustment_type PERCENT, adjustment_value e.g. `90`, effective 2026-01-01 to 2026-12-31.
3. Run simulate with a line that has modifier `26` and a rule that applies modifier logic.
4. **Expect:** Context uses 90% (contract override) instead of 100% (RefModifier). (Exact impact depends on strategy; confirm modifier_adjustments in trace or by allowed amount.)

### 8. **Backfill validation (recommended before enabling flag globally)**

1. For a sample of rules that have `multiplier` set:
   - Create a ContractTerm with the same multiplier and effective dates; set rule.contract_term_id.
2. Run the same simulate with flag False and with flag True (and only reference data).
3. **Expect:** Same allowed amounts. Document any discrepancies and fix backfill or data.

### 9. **Rollback**

1. Set `USE_REFERENCE_ONLY_PRICING = False`.
2. **Expect:** All pricing reverts to rule.multiplier, rule.flat_rate, methodology.conversion_factor. No schema or data change required.

---

## Summary

| Test | Purpose |
|------|--------|
| 1. Migration and admin | Schema and UI for Phase D models and FKs |
| 2. Flag False | Backward compatibility |
| 3–4. ContractTerm | Multiplier from reference (rule and methodology) |
| 5–6. PerDiemRate / ContractFlatRateOverride | Flat rate from reference |
| 7. ModifierAdjustment | Contract overrides RefModifier |
| 8. Backfill validation | Compare old vs new loader output before enabling flag |
| 9. Rollback | Safe revert with flag only |

After all tests pass and backfill is validated, set `USE_REFERENCE_ONLY_PRICING = True` in production and plan a follow-up migration to drop deprecated columns (`multiplier`, `flat_rate`, `conversion_factor`, `base_percentage`) once no longer needed.
