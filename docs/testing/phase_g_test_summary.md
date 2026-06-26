# Phase G — Line & Claim Cap/Floor Hardening: Test Summary

## What Phase G Adds

- **LINE scope on ContractCapFloor:** Existing `ContractCapFloor` supports `scope='LINE'` in addition to CLAIM, DRG, APC. No new table; same model.
- **Config:** `ContractPricingConfig.line_cap_floors` — LINE-scope rules only; claim-level step uses `cap_floors` but skips LINE.
- **Execution order:** Per line: BASE → ADJUSTMENT → carve-out → **LINE_CAP_FLOOR** (when `config.line_cap_floors`). Claim: … → CROSS_LINE → BLENDING → **CLAIM_CAP_FLOOR**.
- **Trace:** When line cap/floor is applied, `execution_trace` gets an entry with `stage="LINE"`, `phase="LINE_CAP_FLOOR"`. Claim cap/floor already had `stage="CLAIM"`, `phase="CAP_FLOOR"`.
- **LineResult:** `applied_line_cap_floor_id` set when a line-level cap/floor is applied (CAP, FLOOR, or PCT_BILLED_CAP).

No new DB migration: `ContractCapFloor.scope` is already a CharField; LINE is a new value. Existing rows remain CLAIM/DRG/APC.

---

## Loader

- `build_contract_pricing_config_from_db` builds `line_cap_floors = tuple(c for c in cap_floors if scope == 'LINE')` and passes it into `ContractPricingConfig`.
- Claim-level `_apply_cap_floor` skips any cap/floor with `scope == 'LINE'`.

---

## Testing Steps

### 1. No line cap/floors (backward compatibility)

1. Do not create any ContractCapFloor with `scope='LINE'` for your contract/version.
2. Run claim pricing. **Expect:** Same behavior as before; no LINE_CAP_FLOOR trace entries.

### 2. Line-level CAP

1. In admin, create **Contract cap floor**: version, `scope='LINE'`, `cap_type='CAP'`, `value=50`, effective dates covering test date. Optionally set `code_value` to a procedure code to restrict to that line only.
2. Price a claim with at least one line whose allowed amount would be &gt; 50 (e.g. 100). **Expect:** That line’s `allowed_amount` = 50; `status` = CAP_APPLIED; `applied_line_cap_floor_id` = that cap_floor_id; `execution_trace` has one entry with stage=LINE, phase=LINE_CAP_FLOOR.
3. Line with allowed amount already ≤ 50 should be unchanged.

### 3. Line-level FLOOR

1. Create a LINE-scope cap/floor with `cap_type='FLOOR'`, `value=25`.
2. Price a line that would otherwise be 10. **Expect:** Line `allowed_amount` = 25; status = FLOOR_APPLIED; trace entry LINE_CAP_FLOOR.

### 4. code_value filter (procedure_code)

1. Create LINE cap with `code_value='00102'`.
2. Price claim with lines 00102 (e.g. 100) and 99999 (e.g. 80). **Expect:** Only 00102 is capped; 99999 unchanged.

### 5. Claim-level cap/floor unchanged

1. Keep existing CLAIM-scope cap/floor rules. **Expect:** They still apply after blending; LINE-scope rules are not applied at claim level (skipped in `_apply_cap_floor`).

### 6. Trace completeness

1. When line cap/floor is applied: one trace entry per affected line with phase=LINE_CAP_FLOOR.
2. When claim cap/floor is applied: existing trace entry with stage=CLAIM, phase=CAP_FLOOR.

---

## Files Touched

- `core/engine/config.py` — added `line_cap_floors`.
- `core/engine/loader.py` — build `line_cap_floors` from cap_floors where scope=LINE; pass into config.
- `core/engine/orchestrator.py` — `_apply_line_cap_floor()`; line loop calls it after carve-out; claim `_apply_cap_floor` skips scope=LINE; docstring order updated.
- `core/engine/types.py` — `LineResult.applied_line_cap_floor_id`.
- `core/models.py` — ContractCapFloor docstring updated for LINE scope.
