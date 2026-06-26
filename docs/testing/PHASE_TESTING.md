# What Can Be Tested at Each Phase

This document lists concrete test scenarios for each phase of the Schema Upgrade for Enterprise Simulation plan (see `.cursor/plans/schema_upgrade_for_enterprise_simulation_6d0bd9b3.plan.md` in repo root). Use it for manual checks, automated tests, or handoff.

---

## Phase 1: Reference Table Split and Fee Schedule Versioning

**Deliverable:** New reference structure; FeeSchedule locality connected to geo for GPCI; fee schedule rates versioned.

### Models and migrations
- **RefCptHcpcsCode:** Create/read records with `code`, `code_type`, `description`, `status_indicator`, `effective_year`. PK is `code`.
- **RefMpfsRvu:** Create/read records with `code`, `year`, `work_rvu`, `pe_rvu`, `mp_rvu`, `total_rvu`, `status_indicator`. Unique on `(code, year)`.
- **FeeSchedule:** New fields present and nullable where specified: `effective_year`, `effective_start_date`, `effective_end_date`, `schedule_type`, `source`, `geo_id` (FK to RefGeoIndex). Existing behavior unchanged.
- **FeeScheduleRate:** New fields present and nullable: `effective_start_date`, `effective_end_date`, `year`. Existing `code_id` and `rate_amount` unchanged.
- **Migration:** Run `python manage.py migrate`; tables `ref_cpt_hcpcs_codes`, `ref_mpfs_rvu` exist; `fee_schedules` and `fee_schedule_rates` have new columns.

### API
- **GET /api/cpt-hcpcs-codes/** — Returns list; optional query params: `q` or `search`, `code_type`, `year`, `limit`.
- **GET /api/mpfs-rvu/** — Returns list; optional query params: `code`, `year`, `limit`.
- **GET /api/procedure-codes/** — Still works (unchanged).
- **GET /api/fee-schedules/** — Response includes `effective_year`, `effective_start_date`, `effective_end_date`, `schedule_type`, `source`, `geo_id`, `locality_code` (from linked RefGeoIndex when present).

### Loader and RBRVS
- **Fee schedule rate only (no RefMpfsRvu, no geo):** Price line uses `FeeScheduleRate.rate_amount` × rule multiplier × units (existing behavior).
- **RefMpfsRvu + FeeSchedule with geo (GPCI):** When rule is RBRVS, fee schedule has `effective_year` and a linked `geo`, and RefMpfsRvu has `(code, year)` and RefGeoIndex has GPCI values: loader fills `work_rvu`, `pe_rvu`, `mp_rvu`, `gpci_work`, `gpci_pe`, `gpci_mp`; RBRVS strategy computes `(work×gpci_work + pe×gpci_pe + mp×gpci_mp) × conversion_factor × units` and applies modifiers.
- **Locality metadata only:** Fee schedule has `geo` set but no RefMpfsRvu for (code, year): pricing falls back to `FeeScheduleRate.base_rate`; GPCI is not applied (no RVU components).
- **DRG:** Unchanged; still uses `RefProcedureCode.work_rvu` for weight and `FeeScheduleRate` not used for DRG base.

### Suggested test cases (Phase 1)
1. Create one `RefCptHcpcsCode`, one `RefMpfsRvu` (matching code/year), one `RefGeoIndex` with GPCI values, one `FeeSchedule` with `effective_year` and `geo` set, one `FeeScheduleRate` for that code; create a RBRVS rule using that fee schedule; POST to price-line or simulate-line and assert allowed amount matches `(work×gpci_work + pe×gpci_pe + mp×gpci_mp) × CF × units`.
2. Same setup but remove RefMpfsRvu row: assert pricing uses `FeeScheduleRate.rate_amount` × CF × units (no GPCI).
3. GET /api/cpt-hcpcs-codes/?code_type=CPT and GET /api/mpfs-rvu/?code=99213&year=2024; assert 200 and correct shape.
4. GET /api/fee-schedules/ and assert new fields and `locality_code` when `geo` is set.

---

## Phase 2: DRG and APC Reference Tables

**Deliverable:** DRG and APC reference data loadable and usable by the engine.

### What to test
- **RefDrg:** CRUD and unique `drg_code`; loader uses RefDrg for DRG weight when present, fallback to RefProcedureCode.work_rvu.
- **RefApc:** CRUD and read-only API; optional use in loader/strategies when APC methodology is introduced.
- **API:** GET endpoints for DRG and APC (list/filter by year, code).

---

## Phase 2B: Contract Methodology Layer and Claim-Type (Critical path)

**Deliverable:** Contract → Methodology → Rules override pattern; override rule documented; claim_type and line_of_business modelable.

### What to test
- **ContractMethodology:** Create per contract with methodology_type, effective_date, fee_schedule; unique `(contract_id, methodology_type, effective_date)` enforced.
- **Override rule:** Rule with `methodology_code` set overrides contract methodology; rule with null/blank `methodology_code` inherits from ContractMethodology for the date (and claim_type when present).
- **Resolver:** For a given contract + service_date (+ claim_type), correct methodology and fee_schedule resolved; rules filtered by claim_type when provided.
- **API:** GET/POST /api/contracts/<id>/methodologies/; contract detail shows methodology summary; simulation accepts claim_type / line_of_business filters.

---

## Phase 3: ICD-10 and ASP Reference Tables

**Deliverable:** ICD-10 and ASP reference data loadable and exposed; engine can use ASP when drug methodology is implemented.

### What to test
- **RefIcd10Cm, RefIcd10Pcs, RefAspPricing:** Create/read; APIs list/filter; loader optionally uses ASP for drug pricing when implemented.
- **Migrations:** New tables created.

---

## Phase 4: Revenue Codes and Provider Specialties

**Deliverable:** Revenue codes and specialties as first-class reference data; providers linkable to specialty.

### What to test
- **RefRevenueCode, RefSpecialty:** CRUD and read-only APIs.
- **ProviderOrganization:** Optional FK to RefSpecialty; serializer/API exposes primary_specialty.

---

## Phase 5: Effective Dating and Claim Context

**Deliverable:** Conditions inherit rule dates; resolver enforces rule effective dating; claim context (service_date, pricing_date) passed through all flows.

### What to test
- **Resolver:** Only rules where `effective_start_date <= service_date <= effective_end_date` are considered; conditions do not have independent dates.
- **Loader:** FeeScheduleRate lookup uses service_date (and year) when filtering by effective_start_date/effective_end_date; fallback when null.
- **API:** Price-line and simulate-line accept optional `service_date`, `pricing_date`; contract/rule serializers expose effective dates.
- **Determinism:** Same contract + line + service_date always yields same rule and result.

---

## Phase 5B: Claim Header and Claim Line

**Deliverable:** Persistent claim structure for bulk simulation; DRG and claim_type at header.

### What to test
- **ClaimHeader/ClaimLine:** Create claim with header (contract, service_date, claim_type, drg_code) and lines; GET /api/claims/<id>/price/ (or equivalent) runs pricing on stored claim.
- **Resolver:** Uses header’s claim_type and DRG when resolving methodology and rules.
- **Bulk:** Multiple claims can be priced in batch using stored ClaimHeader/ClaimLine.

---

## Phase 5C: Materialized Contract Snapshot (Optional)

**Deliverable:** Optional cache layer for contract configuration.

### What to test
- When enabled: first request (or after contract/rule change) builds cache; subsequent requests for same contract use cache; correctness matches non-cached resolver.

---

## Phase 6: Contract Outlier Rules and Stop-Loss Precedence

**Deliverable:** Outlier structure with explicit precedence; engine and docs aligned.

### What to test
- **ContractOutlierRule:** GET/POST /api/contracts/<id>/outlier-rules/; threshold_scope (PER_CLAIM, PER_LINE); PER_LINE rejected until implemented; priority ordering; DB constraint and index.
- **Engine:** Base rules → adjustments → outlier/stop-loss; multiple tiers by priority; per-claim vs per-line behavior.

---

## Phase 7: Indexes and Performance

**Deliverable:** Indexes in place; specificity precomputed on save; bulk simulation performant.

### What to test
- **PricingRule:** Composite index (contract_id, effective_start_date, effective_end_date); specificity_score updated on rule/condition save (no query-time computation).
- **fee_schedule_rates, ref_mpfs_rvu, ref_drg, etc.:** Indexes present (DB or migration inspection).
- **Bulk simulation:** No N+1; acceptable latency for 100s of contracts/lines.

---

## Phase 8: Deprecate RefProcedureCode for CPT/HCPCS/DRG (Optional)

**Deliverable:** Single source of truth; RefProcedureCode no longer used for CPT/HCPCS/DRG after migration.

### What to test
- **Loader:** RBRVS uses RefMpfsRvu (and RefCptHcpcsCode); DRG uses RefDrg only.
- **API:** procedure-codes deprecated or redirect; data migration script run; RefProcedureCode read-only or CPT/HCPCS/DRG rows removed.

---

## Summary

- **Phase 1:** Models (RefCptHcpcsCode, RefMpfsRvu, FeeSchedule/FeeScheduleRate changes), migrations, new APIs (cpt-hcpcs-codes, mpfs-rvu), FeeSchedule serializer, loader GPCI + optional RefMpfsRvu, RBRVS with GPCI formula.
- **Phases 2–8:** Use the “What to test” bullets above and the plan’s deliverables to design tests as each phase is implemented.
