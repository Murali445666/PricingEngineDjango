# Phase C — CodeGroup + Resolver: Test Summary

## What Phase C Adds

- **CodeGroup** and **CodeGroupMember** models: group procedure codes; effective-dated.
- **Resolver:** When a rule condition has `attribute_name='code_group'` and `attribute_value=<code_group_id>`, the resolver checks whether `request.procedure_code` is in that group (members loaded by `service_date`, cached per request).
- **Resolver:** When `attribute_name='revenue_code'`, compares `request.revenue_code` to `condition.attribute_value` (EQ/NEQ).
- **Inputs:** Optional `revenue_code` on `PricingInput` and `ClaimLineInput`; passed from API/claim lines into the resolver.

No change to loader (multiplier/flat_rate/conversion_factor) or orchestrator stage order. Existing rules that use `procedure_code` EQ continue to work unchanged.

---

## What You Can Test

### 1. **Backward compatibility (no Phase C data)**

- Run existing simulate requests that use only `procedure_code` conditions.
- **Expect:** Same results as before. No code_groups or revenue_code involved.

### 2. **Code group: procedure IN group**

**Setup in Admin:**

1. **Code groups** → Add: e.g. contract 10, version 2, `code_group_code=GROUP1`, name "Test group", effective 2026-01-01 to 2026-12-31.
2. **Code group members** → Add members to that group: e.g. `code_id=00102`, `code_id=00100` (same effective dates).
3. **Pricing rules** → Add a new rule (or clone one): contract 10, version 2, BASE, methodology e.g. FLAT_RATE, one **condition**: `attribute_name=code_group`, `operator=EQ`, `attribute_value=<id of the CodeGroup>`.

**Test in Analyst UI:**

- URL: `http://localhost:8000/contracts/10/versions/2/ui/`
- Claim JSON (procedure in group):
  ```json
  {
    "lines": [
      { "procedure_code": "00102", "billed_amount": "150.00", "units": 1, "modifiers": [] }
    ],
    "service_date": "2026-06-01"
  }
  ```
- **Expect:** Rule matches (if rule’s fee schedule/rate applies), line is priced.
- Claim JSON (procedure **not** in group):
  ```json
  {
    "lines": [
      { "procedure_code": "99999", "billed_amount": "150.00", "units": 1, "modifiers": [] }
    ],
    "service_date": "2026-06-01"
  }
  ```
- **Expect:** That rule does not match (no match or another rule matches).

### 3. **Code group: NEQ (procedure NOT in group)**

- Same CodeGroup as above. Rule condition: `attribute_name=code_group`, `operator=NEQ`, `attribute_value=<code_group_id>`.
- Procedure **00102** (in group) → rule should **not** match.
- Procedure **99999** (not in group) → rule should match.

### 4. **Revenue code (optional)**

- Add a rule condition: `attribute_name=revenue_code`, `operator=EQ`, `attribute_value=0450`.
- Call simulate with a line that includes `revenue_code` (API only; Analyst UI claim JSON does not currently expose revenue_code in the form, but you can add it to the JSON if the backend accepts it):
  ```json
  {
    "lines": [
      { "procedure_code": "00102", "billed_amount": "150.00", "units": 1, "modifiers": [], "revenue_code": "0450" }
    ],
    "service_date": "2026-06-01"
  }
  ```
- **Expect:** Rule matches when revenue_code matches; does not match when different or missing.

### 5. **Effective dating (code group members)**

- Create a CodeGroupMember with `effective_start_date=2026-06-01`, `effective_end_date=2026-06-30`.
- Run with `service_date=2026-05-01` → procedure should **not** be in the cached member set for that date.
- Run with `service_date=2026-06-15` → procedure **should** be in the set.

---

## Quick Checklist

| Test | Setup | Expectation |
|------|--------|-------------|
| Existing rules unchanged | None | Same pricing as before Phase C |
| Procedure in code_group (EQ) | CodeGroup + members; rule condition code_group EQ | Rule matches when procedure in group |
| Procedure not in code_group (EQ) | Same | Rule does not match |
| Procedure not in code_group (NEQ) | Rule condition code_group NEQ | Rule matches when procedure not in group |
| revenue_code EQ | Rule condition revenue_code EQ; line has revenue_code | Match when equal |
| CodeGroupMember effective dates | Member with narrow date range | In/out of group by service_date |

---

## Run Migrations

```bash
python manage.py migrate core
```

Apply migration `0027_phase_c_code_group` so `code_groups` and `code_group_members` tables exist.
