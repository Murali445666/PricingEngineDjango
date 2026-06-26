# Project handoff — Matrix Pricing Engine (PricingEngineDjango)

Concise reference for engineers or new sessions. **Status:** [STATUS.md](STATUS.md). **Roadmap:** [ROADMAP.md](ROADMAP.md) (Stages 0–6). **Upgrade plan (full specs):** [UPGRADE_PLAN.md](UPGRADE_PLAN.md). Deep detail: [`pricing_execution_flow.md`](pricing_execution_flow.md), [`system_overview_pricing_engine.md`](system_overview_pricing_engine.md).

---

## 1. Project overview

- **Purpose:** Backend pricing engine for **healthcare claims**: given a **contract** (and usually a **contract version**), **reference data**, and **claim lines**, compute **allowed amounts** per line and claim-level totals, with optional carve-outs, stop-loss, outlier, blending, and caps/floors.
- **Core capabilities (methodologies / behaviors):**
  - **RBRVS** — Fee schedule + conversion factor; optional MPFS RVU + GPCI when reference data and fee schedule year/locality are set (`core/engine/strategies/rbrvs.py`, loader).
  - **DRG** — Line-level DRG via `procedure_code` (DRG code on line) + weights from `ref_drg`; optional **claim-level DRG** when `contract_versions.claim_level_drg_enabled` (`CLAIM_METHODOLOGY_REGISTRY`).
  - **APC / OPPS** — APC-style strategies where configured.
  - **FLAT_RATE**, **PER_DIEM**, **CASE_RATE**-related paths, **ANESTHESIA**, **ASP**, etc. — see `core/engine/strategies/`.
  - **PCT_BILLED / PERCENT_BILLED** — Percent of line billed (`PercentBilledMethod`).
  - **Carve-outs**, **stop-loss**, **outlier**, **blending**, **contract caps/floors** (claim- and line-scoped) — orchestrator.

---

## 2. Current architecture (high level)

- **API layer:** Django REST Framework in `core/api/` — views, serializers, URLs (`core/api/urls.py`). Prefix: **`/api/`** (see project `urls.py`).
- **Service entry:** `ClaimPricingService` in `core/engine/service.py` — `price_line`, `price_claim`, `price_claim_with_version` (simulation), `price_stored_claim`, `price_claims_bulk`.
- **Orchestration:** `ClaimOrchestrator.run()` in `core/engine/orchestrator.py` — builds or accepts `ContractPricingConfig`, loops lines, claim-level steps.
- **Line pricing:** `LineOrchestrator.run()` — **StrictRuleResolver** → **PricingDataLoader.load_context** → **strategy** `calculate()`.
- **Resolver:** `core/engine/resolver.py` — `StrictRuleResolver`: ACTIVE rules, effective dates, version match (`version_id` or null), `claim_type` alignment, **`PricingRuleCondition`** (AND). Rules with **no conditions do not match**. Supports `procedure_code`, `code` alias, `code_group`, `revenue_code`, etc.
- **Loader:** `core/engine/loader.py` — `PricingDataLoader`: resolves effective methodology, fee schedules, RVU/GPCI, DRG weight, modifiers, base rates from version, etc.
- **Strategy pattern:** `get_methodology(code)` in `core/engine/strategies/__init__.py`; implementations in `core/engine/strategies/*.py`.
- **Contract model:** `ProviderContract` → **`ContractVersion`** (version row PK = **`version_id`**, not `version_number`) → **`PricingRule`** + conditions; version-scoped **methodologies**, **base rates**, **cap/floors**, **carveouts**, **blending**, etc.
- **ContractPricingConfig:** Immutable snapshot for one pricing run: rules, `rules_by_stage`, methodologies, stop-loss, outlier, carveouts, cap_floors, **line_cap_floors**, blending, MPPR, base_rates, etc. Built via `build_contract_pricing_config_from_db` or `build_contract_pricing_config_from_version` (`loader.py`). Optional **contract snapshot** API for reproducible configs (`ContractSnapshotView`, `core/services/contract_snapshot.py`).

---

## 3. Canonical pricing flow (execution order)

**Per line (inside `ClaimOrchestrator` loop):**

1. Build `PricingInput` from claim line.
2. **`LineOrchestrator.run`** — resolve rule (LEGACY: single rule; STAGED: BASE then ADJUSTMENT stages), load context, run strategy.
3. **`_apply_carveout`** — may zero or reprice line (`ContractCarveout`).
4. **`_apply_line_cap_floor`** — **LINE**-scoped `ContractCapFloor` (e.g. **`PCT_BILLED_CAP`** = min calculated vs % of billed). **First matching cap wins.**

**After all lines:**

5. Sum line allowables into `total_allowed` (see **Known limitations** for status filtering).
6. **Claim-level DRG** (optional) — if `version.claim_level_drg_enabled`, DRG plugin may replace claim total.
7. **Stop-loss** — cost-based; first matching rule (`config.stop_loss_rules`).
8. **Outlier** — charge-based; **PER_CLAIM** only (**PER_LINE** not implemented).
9. **Cross-line MPPR** — `_run_cross_line_phase` when MPPR defs exist; may sync line amounts and total.
10. **Blending** — `_apply_blending` (claim- and line-level rules).
11. **Claim-level caps/floors** — `_apply_cap_floor` with **CLAIM** / DRG / APC scope (**LINE** scope rows are skipped here; already applied per line).

Modifiers are applied **inside** strategies (`apply_modifiers`), not as a separate orchestrator step.

---

## 4. Current state (what is done)

- **Engine:** End-to-end claim pricing with config preload, trace hooks, STAGED vs LEGACY line mode (`pricing_engine_mode` on `ContractVersion`).
- **Version resolution:** Active version by service date for `price-claim`; **simulation** uses explicit **`version_id`** (`price_claim_with_version`); DRAFT/ACTIVE/SUPERSEDED allowed for simulate, **ARCHIVED** rejected.
- **APIs:** `price-line`, `price-claim`, **`price-claim-simulate`**, `price-claims-bulk`, stored claim price, rules/contracts CRUD, explorer, snapshot, reference data list endpoints — see `core/api/urls.py`.
- **React UI:** Vite + React + TS; **Claim Simulation** (`/claim-simulation`), contracts/rules pages, **Contract Explorer**, rule create wizard, sandbox/scenario pages — see section 5.
- **Bulk pricing** with config cache per `(contract, version, service_date)`.
- **Snapshot** endpoint for contract config capture.
- **Performance:** Loader caches (RVU, fee schedule rates, code groups, etc.), prefetch in config build, documented in roadmap/status docs.

---

## 5. What UI exists today

| Area | Route / feature | Notes |
|------|-----------------|--------|
| **Claim Simulation** | `/claim-simulation` | Contract + version, claim JSON, `POST /api/price-claim-simulate/` |
| **Contract Explorer** | Contract explorer page + `GET /api/contracts/<id>/explorer/` | Version/context for UI |
| **Contracts / rules** | List/detail, rule create (`RuleCreatePage`) | Wired to APIs |
| **Run scenario / sandbox** | `RunScenarioPage`, etc. | Varies |

**Missing / thin:**

- Full **contract authoring** wizard (create contract + version + all terms in one flow).
- **Rule simulator** page may be placeholder vs `simulate-line` API (check [STATUS.md](STATUS.md) Phase 4).
- **Admin:** Many models may be **unregistered**; ops often use Django admin selectively, SQL, or shell.
- **Code group** maintenance UI may be limited; engine supports `code_group` conditions when data exists.

---

## 6. How to run the system

**Backend** (from repo `PricingEngineDjango/`):

```bash
python manage.py migrate
python manage.py seed_matrix    # optional demo contract
python manage.py runserver
```

Reference data (optional): `python manage.py load_reference_data` — see [`RUNBOOK.md`](RUNBOOK.md).

**Frontend** (from `PricingEngineDjango/frontend/`):

```bash
npm install
npm run dev      # Vite dev server (often :5173)
npm run build
```

Ensure CORS/settings allow the Vite origin if API is on another port.

**Key HTTP endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `POST /api/price-line/` | Single line |
| `POST /api/price-claim/` | Multi-line; resolves **active** version |
| `POST /api/price-claim-simulate/` | Multi-line; explicit **`contract_id` + `version_id` + `claim`** |
| `POST /api/price-claims-bulk/` | Batch claims |
| `GET/POST /api/claims/<pk>/price/` | Price stored claim |
| `GET /api/contracts/<pk>/explorer/` | Explorer payload |
| `GET /api/contracts/<pk>/snapshot/` | Config snapshot |

---

## 7. Example working payloads

**Simulate request wrapper** (all examples use this shape):

```json
{
  "contract_id": 1,
  "version_id": 8,
  "claim": { }
}
```

### RBRVS (professional line)

```json
{
  "contract_id": 1,
  "version_id": 8,
  "claim": {
    "service_date": "2026-06-01",
    "claim_type": "PROFESSIONAL",
    "lines": [
      {
        "line_id": "L1",
        "procedure_code": "99213",
        "billed_amount": "150.00",
        "units": 1,
        "modifiers": []
      }
    ]
  }
}
```

*Requires: ACTIVE RBRVS rule, fee schedule rate for `99213`, matching **`version_id`**, at least one condition (e.g. `procedure_code` EQ `99213`).*

### DRG (inpatient line; DRG code on line)

```json
{
  "contract_id": 1,
  "version_id": 8,
  "claim": {
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
}
```

*Requires: DRG rule + valid **`ref_drg.relative_weight`** (not the DRG code duplicated as weight), version-scoped DRG base rate as configured; **procedure_code** on line = DRG code for line-level DRG path.*

### Percent of billed

```json
{
  "contract_id": 1,
  "version_id": 8,
  "claim": {
    "service_date": "2026-06-01",
    "claim_type": "OUTPATIENT",
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
}
```

*Requires: Rule with **`methodology_code`** `PCT_BILLED` / `PERCENT_BILLED`, multiplier = desired decimal factor (e.g. `0.75` for 75%), conditions as needed.*

**“Lesser of fee and billed”** is not automatic for RBRVS: add **`ContractCapFloor`** with **`scope=LINE`**, **`cap_type=PCT_BILLED_CAP`**, **`percentage=100`** on the same **version**.

---

## 8. Known limitations

- **Claim total rollup:** Lines whose status becomes **`CAP_APPLIED`** / **`FLOOR_APPLIED`** after line-level cap/floor may be **omitted** from the initial `total_allowed` sum in `ClaimOrchestrator` (only certain statuses are added). Verify claim totals vs line results if you use line caps heavily.
- **Outlier:** **`PER_LINE`** outlier raises `NotImplementedError`.
- **RBRVS vs billed:** Base methodologies do not default to **min(fee, charge)**; use **LINE `PCT_BILLED_CAP`** or product change.
- **DRG on line:** Line-level path expects **DRG code in `procedure_code`** (not a separate `drg_code` on the line for resolver matching); claim header may carry `drg_code` for claim-level flows.
- **Code groups:** Resolver supports **`code_group`** conditions; **UI/admin** may not expose full lifecycle for **CodeGroup** / members — often **per-code rules** or DB maintenance.
- **Contract creation:** No polished end-user **“new contract”** wizard in React; typical path: Django admin / API / seeds (`seed_matrix`, `seed_demo`).
- **Single pricing engine folder:** Handoff scope is **`PricingEngineDjango/`** only unless noted.

---

## 9. Next recommended steps

1. Maintain **small learning contracts** (one DRG version, one RBRVS version) with correct **`version_id`** linkage on rules and cap/floors.
2. Use **Claim Simulation** + **`price-claim-simulate`** for regression tests whenever rules or loader change.
3. Align **reference data** (DRG weights, MPFS RVU) with real CMS/vendor files; avoid placeholder numbers (e.g. weight = DRG code).
4. Later: **contract creation / amendment UI**, richer **rule builder** (conflicts, simulate-line in UI), register missing models in admin as needed.

---

## 10. Key files and folders

| Path | Role |
|------|------|
| `core/engine/orchestrator.py` | `ClaimOrchestrator`, `LineOrchestrator`, carve-out, line cap, blending, claim cap |
| `core/engine/resolver.py` | `StrictRuleResolver`, conditions |
| `core/engine/loader.py` | `build_contract_pricing_config_*`, `PricingDataLoader`, version resolution helpers |
| `core/engine/service.py` | `ClaimPricingService` |
| `core/engine/config.py` | `ContractPricingConfig` dataclass |
| `core/engine/strategies/` | Methodology implementations |
| `core/engine/types.py` | `PricingInput`, `ClaimPricingInput`, `LineResult`, … |
| `core/models.py` | Domain models (contracts, versions, rules, cap/floors, ref tables) |
| `core/api/views.py` | DRF views |
| `core/api/serializers.py` | Request/response validation |
| `core/api/urls.py` | API routes |
| `frontend/src/features/simulation/ClaimSimulationPage.tsx` | Simulation UI |
| `frontend/src/features/contracts/ContractExplorerPage.tsx` | Explorer UI |
| `frontend/src/services/apiClient.ts` | HTTP client / errors |
| `docs/DEMO_TEST_CASES.md` | Deterministic `seed_demo` scenarios, claim JSON, expected results |
| `docs/DATA_MODEL.md` | MySQL tables and API data usage |
| `docs/RUNBOOK.md` | Local run + seed commands |

---

*Last updated: handoff doc generation (internal). Update this file when major behavior or UI ships.*
