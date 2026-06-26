# UI deliverables — Step 12f / 12a (status)

> **Canonical status:** [STATUS.md](../STATUS.md) · **Roadmap:** [ROADMAP.md](../ROADMAP.md)

**Updated:** `frontend/README.md` — routes table includes `/claim-simulation`, governance badges on `/contracts`, Conflicts panel on contract detail, tests TODO.

**Latest (Claim Simulation):** example payloads (DRG / RBRVS / APC), Load example buttons, `blended_total_allowed` + `applied_blending_rule_ids` in summary, empty state, `role="alert"` on API errors. **Conflicts:** panel title + `useState` import cleanup in `ConflictWarningsPanel.tsx`.

## Already implemented (no backend changes)

| Goal | Location |
|------|-----------|
| **Route `/claim-simulation`** | `frontend/src/routes/index.tsx`, `Sidebar.tsx` |
| **Simulate UI** (contract, version via explorer, JSON, Run, summary / lines / traces) | `ClaimSimulationPage.tsx` |
| **Contracts list badges** | `ContractsPage.tsx` — `open_error_count` / `open_warning_count` from `ContractSerializer` |
| **Conflicts panel** | `ContractDetailPage.tsx` + `ConflictWarningsPanel.tsx` — `GET /api/contracts/<id>/conflicts/` |

## Done in repo

- **`ClaimSimulationPage.tsx`** — examples + buttons + summary fields + empty state + alert role.
- **`ConflictWarningsPanel.tsx`** — title **Conflicts**, `useState` import, error copy.

Run `cd frontend && npm run build` after local edits.

## Step 12c (simulate + conflicts) — done

- **`RuleSimulateConflictPanel.tsx`** on **Rule create** and **Rule detail** — `POST /api/price-line/` (with `trace_logs`) or `POST /api/simulate-line/` with draft; `POST /api/rules/check-conflicts/` with optional `exclude_rule_id` on detail.
- Backend: `trace_logs` on `POST /api/price-line/`; `exclude_rule_id` on check-conflicts. Test: `tests.test_12c_price_line_trace_api`.

## Step 12e (Contract Explorer) — done

- **`ContractExplorerPanel.tsx`** — used on **contract detail** (Explorer tab) and **`/contract-explorer`**; conflict badges; accordions; conditions-by-rule; Download JSON + CSV (`GET …/explorer/?export=csv`).
- API: nested `contract` / `open_conflict_counts` / `versions[].rules[]`; tests: `core.tests.test_contract_explorer`.
