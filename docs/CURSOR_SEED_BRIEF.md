# Cursor brief — seed the clean Highmark–Keystone contract

## Goal
Stand up **one** clean, realistic managed-care contract in the DB (Highmark ↔ Keystone
Health System, Commercial PPO), populated from four CSVs. Build **two management commands**.
All existing contracts have already been soft-disabled (`disable_contracts`), so after this
runs the ONLY active contract must be the new one.

## Constraints (hard)
- **Do NOT modify `core/engine/`** — the pricing engine is frozen. This is seed/import code only.
- **Do NOT touch ref tables** (`RefModifier`, `RefMpfsRvu`, CPT/DRG/APC masters, `RefSpecialty`).
- **Do NOT re-enable** the disabled contracts. Leave them ARCHIVED.
- Everything must be **idempotent** — re-running updates in place, never duplicates.
- Wrap DB writes in `transaction.atomic()`; use `bulk_create(batch_size=500)` for the rules.

## Reference implementation
Mirror the entity-wiring in **`core/demo/seed_keystone.py`** — it already creates the same
kind of graph (orgs → affiliations → network participation → members → enrollments →
contract → scope) for the KEYSTONE NPIs. Follow its patterns for FK wiring and
`update_or_create` idempotency.

## Data files (all in `docs/`)
| File | Rows | Feeds |
|---|---|---|
| `provider_roster.csv` | 296 | `providers.Provider` + `providers.ProviderAffiliation` |
| `members.csv` | 252 | `members.Member` + `members.Enrollment` |
| `Exhibit_C_Fee_Schedule.csv` | 1,114 | `core.PricingRule` + `core.PricingRuleCondition` |
| `Sample_Managed_Care_Agreement.pdf` | — | human spec (Exhibits A/B/C); read for context |

## Models (confirmed)
- `core.ProviderOrganization` (billing org; has `organization_id`, `parent_org` self-FK, an NPI)
- `core.PayerNetwork` (legacy network the resolver uses)  •  `products.Network` (bridged, optional)
- `products.PayerOrganization`, `products.LineOfBusiness`, `products.Product`, `products.ProductNetworkConfig`
- `providers.Provider`, `providers.Facility`, `providers.ProviderAffiliation`,
  `providers.ProviderNetworkParticipation`, `providers.FacilityNetworkParticipation`
- `members.Member`, `members.Enrollment`
- `core.ProviderContract`, `core.ContractVersion`, `core.ContractScopeUnified`
  (and covered-entity model used by the resolver — inspect `core/services/contract_resolver.py`
  for `ContractCoveredEntity` / `ContractScopeUnified` and populate whatever it queries)
- `core.PricingRule`, `core.PricingRuleCondition`, `core.ContractBaseRate`

---

## Command 1 — `seed_agreement`
`python manage.py seed_agreement`

Creates (idempotent, `update_or_create` by natural key):

### Payer + network + product
- `PayerOrganization`: name "Highmark Health Plan, Inc.", `payer_id="HIGHMARK"`, type COMMERCIAL.
- `LineOfBusiness`: COMMERCIAL (reuse if exists).
- `Product`: name "Highmark Commercial PPO", `product_code="KHS-PPO"`, lob COMMERCIAL, effective 2025-01-01.
- `core.PayerNetwork`: a Commercial PPO network (reuse seed_keystone's pattern); link
  `products.Network` (PPO) → `legacy_payer_network` if you create the bridged row.
- `ProductNetworkConfig`: Product → Network, claim_type ALL, effective 2025-01-01.

### Provider organizations (Exhibit A roster) — set org NPI per this map
| org_key | ProviderOrganization name | organization NPI | parent |
|---|---|---|---|
| KHS-IDN   | Keystone Health System, Inc.   | KEYSTONE-NPI01 | (none — IDN parent) |
| KHS-GEN   | Keystone General Hospital      | KEYSTONE-NPI03 | KHS-IDN |
| KHS-CHILD | Keystone Children's Hospital   | KEYSTONE-NPI04 | KHS-IDN |
| KHS-CARD  | Keystone Cardiology Associates | KEYSTONE-NPI02 | KHS-IDN |
| KHS-IMG   | Keystone Imaging Center        | KEYSTONE-NPI06 | KHS-IDN |
| KHS-BH    | Keystone Behavioral Health     | KEYSTONE-NPI07 | KHS-IDN |

`update_or_create` by `organization_id`/NPI so existing KEYSTONE rows are reused, not duplicated.
Also create `Facility` rows for KHS-GEN (HOSPITAL_INPATIENT/OUTPATIENT), KHS-CHILD,
KHS-IMG (IMAGING), KHS-BH — NPIs per the roster; facility NPI for General = KEYSTONE-NPI03.

### Providers + affiliations (from provider_roster.csv)
For each row: `update_or_create` a `providers.Provider` by `npi` (names, credential,
`primary_specialty` = `RefSpecialty` matched by `specialty_code`, else null), then a
`ProviderAffiliation` (provider → the org named by `org_key`, role EMPLOYEE, `effective_date`).
Dr. Chen (`KEYSTONE-NPI05`) → KHS-CARD.

### Network participation (so claims resolve IN_NETWORK)
Create `ProviderNetworkParticipation` rows: **at the org level** for each of the 6 orgs
(status IN_NETWORK, effective 2025-01-01, network = the PPO PayerNetwork). Org-level
participation covers all affiliated providers — do NOT create one per provider.
Add `FacilityNetworkParticipation` for the facilities.

### Members + enrollments (from members.csv)
For each row: `update_or_create` a `Member` by `member_id`; if `product_key` is non-empty,
create an `Enrollment` (member → Product KHS-PPO, `effective_date`, `termination_date` if
present). The two edge members (`KHS-MEM-NOENROLL` = no enrollment; `KHS-MEM-TERMED` =
enrollment ended 2024-12-31) exercise the NO_CONTRACT coverage-gap path.

### The contract + version + scope
- `ProviderContract`: `contract_name="Highmark – Keystone Health System (Commercial PPO)"`,
  `legacy_contract_number="HM-KHS-2025-0417"`, `provider_org` = KHS-IDN, `payer_org` = Highmark,
  `network` = PPO PayerNetwork, `status="ACTIVE"`, `effective_start_date=2025-01-01`,
  `contract_origin_type="DIRECT"`, `resolution_priority=10`.
- `ContractVersion`: version_number 1, status ACTIVE, effective 2025-01-01.
- **Scope / covered entities**: populate whatever the resolver reads (`ContractScopeUnified`
  and/or `ContractCoveredEntity`) so the contract covers: the 6 orgs (Exhibit A), the PPO
  product/LOB/network (Exhibit B), and Dr. Chen as a provider-level covered entity (the
  carve-out). Inspect `contract_resolver.py` to see exactly which tables it queries and fill those.

Print the created `contract_id` and `version_id` at the end (needed for command 2).

---

## Command 2 — `import_fee_schedule`
`python manage.py import_fee_schedule --csv docs/Exhibit_C_Fee_Schedule.csv --contract <id> --version <vid> --year 2025`

Generalize the existing `core/services/bulk_rates.py::bulk_add_rate_basis` (which already
creates `PricingRule` + `PricingRuleCondition`). Steps:

1. Load contract + version. Build a `covered_entity` string → entity map ONCE from these CSV values:
   `"Keystone Cardiology (org)"`→KHS-CARD, `"Robert Chen, MD"`→provider NPI05,
   `"Keystone Imaging Center"`→KHS-IMG, `"Keystone General (OP)"`→KHS-GEN,
   `"Keystone General Hospital"`→KHS-GEN, `"Keystone Behavioral Health"`→KHS-BH.
2. Idempotency: delete existing `PricingRule`s for this version before load (or upsert by
   version+code+entity).
3. Pass 1 — build `PricingRule` objects: `methodology_code=row.methodology_code`,
   `flat_rate=Decimal(row["allowed_2025"])` (or `allowed_2026` when `--year 2026`),
   status ACTIVE, effective dates = contract's. `bulk_create(batch_size=500)`.
4. Pass 2 — build conditions with the now-assigned PKs:
   - always: `procedure_code EQ row.procedure_code`
   - if `setting` in (Inpatient, Outpatient, Facility per-diem): `claim_type EQ institutional`
     (professional is the default/wildcard — no condition needed)
   - for the `Robert Chen, MD` rows: add a provider/entity condition so the specificity
     ladder picks his line over the org line.
   `bulk_create(batch_size=500)`.
5. Optional: populate `ContractBaseRate` from `rate_basis`/`percentage`/`rvu`/`base_year`
   columns (the authoring formula behind the materialized rate).
6. Print counts: rules created, conditions created.

---

## Verification (run after both commands)
1. `ProviderContract.objects.filter(status='ACTIVE').count()` → **1**.
2. `PricingRule.objects.filter(version_id=<vid>).count()` → **1114**.
3. Reprice a professional office visit — should resolve to the new contract and price 99213:
   ```
   curl -s -X POST http://localhost:8000/api/reprice-claim/ -H "Content-Type: application/json" \
     -d '{"billing_npi":"KEYSTONE-NPI02","member_id":"KHS-MEM-0001","service_date":"2025-06-15","claim_type":"professional","lines":[{"procedure_code":"99213","billed_amount":"500.00","units":1}]}'
   ```
   Expect `status=SUCCESS`, the new `contract_id`, allowed ≈ `108.12` (Exhibit C.1).
4. Coverage-gap paths still work: `KHS-MEM-NOENROLL` → `NO_CONTRACT`; `KHS-MEM-TERMED` → `NO_CONTRACT`.
5. `python manage.py test --keepdb` → unchanged 8-failing baseline, no new failures.
