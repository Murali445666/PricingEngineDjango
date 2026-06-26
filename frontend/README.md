# Matrix Pricing Platform — Frontend

React + TypeScript internal admin UI for the healthcare pricing engine.

**Docs:** [ROADMAP.md](../docs/ROADMAP.md) · [STATUS.md](../docs/STATUS.md) · [TEST_PLAYBOOK.md](../docs/testing/TEST_PLAYBOOK.md)

## Stack

- **Vite** + **React 18** + **TypeScript**
- **React Router** — routing
- **TailwindCSS** — styling (neutral/slate, blue primary)
- **TanStack Query** — server state (no Redux)
- **Axios** — API client

## Scripts

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
npm run preview  # preview production build
```

## Environment

- `.env.development` — `VITE_API_BASE_URL`, `VITE_APP_VERSION`
- `.env.production` — production API base URL (e.g. `/api` with same-origin)

For local Django backend, use `VITE_API_BASE_URL=http://localhost:8000/api` or rely on the Vite proxy (see `vite.config.ts`: `/api` → `http://localhost:8000`).

## Structure

- `src/app/` — layout (Header, Sidebar, MainLayout)
- `src/features/` — pricing, contracts, rules, simulation, monitoring, admin
- `src/shared/ui/` — PageLayout, DataTable, FormPanel, Button, Input, etc.
- `src/services/` — apiClient, pricingService, contractService, ruleService
- `src/routes/` — route config

## Routes

| Path | Page |
|------|------|
| `/claim-simulation` | **Claim Simulation Workbench (Step 12f, first slice)** — `GET /api/contracts/` + explorer versions; claim JSON; **Load example:** DRG 470, RBRVS 99213, FLAT 00100, PCT 99213; `POST /api/price-claim-simulate/`; summary (badge, totals, applied_* IDs), line + execution trace + claim trace; Copy cURL / Download result JSON |
| `/pricing-sandbox` | Single-line pricing form (live API) |
| `/contracts` | Contracts list — live API; **governance:** `open_error_count` / `open_warning_count` badges; **Step 12d:** **Run bulk validation** → `POST /api/validate-contracts/bulk/` |
| `/contracts/:id` | Contract detail — **Overview** tab (rules, conflicts) and **Explorer** tab (`GET /api/contracts/<id>/explorer/`; Download JSON / **CSV** via `?export=csv`) |
| `/contract-explorer` | Standalone contract picker + same explorer panel |
| `/contracts/:id/rules/new` | Rule create wizard — **Step 12c:** Simulate line (draft via `POST /api/simulate-line/`), Check conflicts (`POST /api/rules/check-conflicts/`) |
| `/rules` | Rules list (live API) |
| `/rules/:id` | Rule detail — **Step 12c:** same panel; ACTIVE rules use `POST /api/price-line/` (response includes `trace_logs`); DRAFT uses simulate-line with draft; conflicts check passes `exclude_rule_id` |
| `/rule-simulator` | Placeholder |
| `/batch-monitor` | Placeholder |
| `/admin` | Placeholder |

API base: `fetchContracts`, `contractService`, `pricingService` — see `src/services/`.

## Tests

- No dedicated frontend unit tests for Step 12c yet (`TODO` in `RuleSimulateConflictPanel.tsx`); backend: `tests.test_12c_price_line_trace_api` asserts `trace_logs` on `POST /api/price-line/`.
- **Step 12d (bulk validation):** No Vitest/RTL in this package yet. **Manual QA:** open `/contracts`, click **Run bulk validation**, select contracts or “Validate all listed”, optional persist; confirm results table and list badges update after run. Backend: `tests/test_12d_bulk_validation.py`.
- **Step 12f (claim simulation):** No Vitest/RTL in this package; **manual QA:** open `/claim-simulation`, pick seeded DEMO_* contract + version, load each of the four examples and Run; confirm summary and tables; break JSON to see inline error; stop API to see alert.
- **Step 12e:** `TODO` in `ContractExplorerPanel.tsx`; backend: `core.tests.test_contract_explorer` (JSON shape, CSV, query budget).
