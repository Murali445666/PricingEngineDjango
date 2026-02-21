# Matrix Pricing Platform — Frontend

React + TypeScript internal admin UI for the healthcare pricing engine.

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
| `/pricing-sandbox` | Single-line pricing form (live API) |
| `/contracts` | Contracts table (mock) |
| `/rules` | Rules table (mock) |
| `/rules/:id` | Rule detail (mock) |
| `/rule-simulator` | Placeholder |
| `/batch-monitor` | Placeholder |
| `/admin` | Placeholder |

Switch services to real API when backend endpoints are ready (e.g. `fetchContracts` instead of `fetchContractsMock`).
