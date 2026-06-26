# Phase F — Cross-Line MPPR: Test Summary

## What Phase F Adds

- **MPPRDefinition:** Contract/version, name, rank_by (ALLOWED_AMOUNT | RVU | FEE_SCHEDULE), primary_pct, secondary_pct, tertiary_pct, effective dates. Defines one MPPR rule.
- **MPPRScope:** Belongs to an MPPR definition; code_group_id (nullable) and/or procedure_code (nullable). A line is in scope if its procedure_code is in the code group or matches procedure_code.
- **Execution order:** LINE → CLAIM_METHOD → **CROSS_LINE** (MPPR) → BLENDING → CLAIM_CAP_FLOOR.
- **Logic:** For each MPPR definition, (1) determine lines in scope from scopes (code_group members + explicit procedure_codes), (2) sort those lines by rank_by (e.g. current_allowed_amount descending), (3) set each line’s current_allowed_amount = base_allowed_amount × pct / 100 (primary_pct for first, secondary_pct for second, tertiary_pct for rest), (4) recompute claim_total from line_states. Line results and claim total are updated so the response reflects post-MPPR amounts.

No change to line-level or claim-level loader. MPPR uses only context.line_states and config.mppr_definitions.

---

## Migration

```bash
python manage.py migrate core
```

Migration `0030_phase_f_mppr` creates tables `mppr_definitions` and `mppr_scopes`.

---

## Testing Steps

### 1. Migration and admin

1. Run `python manage.py migrate core`.
2. In admin, open **MPPR definitions** and **MPPR scopes**. Create one MPPR definition (e.g. contract 10, version 2, name "Test MPPR", rank_by=ALLOWED_AMOUNT, primary 100, secondary 50, tertiary 25, effective dates covering test date).
3. Add one or more scopes: e.g. a **Code group** that contains procedure codes 00102 and 99998, or explicit **Procedure code** = 00102.

### 2. No MPPR (backward compatibility)

1. Do not add any MPPR definition for the contract/version you use, or use a version with no MPPR.
2. Run simulate with two lines. **Expect:** total_allowed = sum of line allowed amounts; no CROSS_LINE trace entry.

### 3. MPPR with two lines in scope

1. **Code group:** Create a code group with members 00102 and 99998 (effective for service_date). Create MPPR definition (primary 100, secondary 50, tertiary 25). Add one scope: code_group = that group.
2. **Simulate:** Two lines with procedure_code 00102 and 99998, service_date in range. Ensure each line gets a base_allowed_amount (e.g. 100 and 80).
3. **Expect:** Lines ranked by current_allowed_amount (e.g. 100 then 80). First line: 100 × 100% = 100. Second: 80 × 50% = 40. total_allowed = 140. execution_trace includes stage=CLAIM, phase=CROSS_LINE.

### 4. MPPR with procedure_code scope

1. Add an MPPR scope with procedure_code = 00102 (no code_group). Only lines with 00102 are in scope.
2. Simulate with one line 00102 and one line 99999. **Expect:** Only the 00102 line is adjusted (primary 100%); 99999 unchanged. total_allowed = adjusted + unadjusted.

### 5. Recompute claim_total

1. After CROSS_LINE, blending and cap/floor use the recomputed claim total (sum of line_states[].current_allowed_amount). **Expect:** Blending/cap/floor use the post-MPPR total, and response line[].allowed_amount and total_allowed match.

---

## Summary

| Test | Purpose |
|------|--------|
| 1 | Schema and admin |
| 2 | No change when no MPPR |
| 3 | Two lines in scope, primary/secondary pct applied |
| 4 | procedure_code-only scope |
| 5 | claim_total and response consistent after MPPR |
