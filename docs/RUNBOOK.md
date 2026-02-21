# Runbook: Matrix Pricing Engine (PricingEngineDjango)

Quick reference for running the backend and frontend locally.

---

## Prerequisites

- Python 3.10+ with venv
- Node.js 18+ and npm (for React frontend)
- MySQL (or configured database per `config/settings.py`)

---

## Backend (Django)

### 1. Migrations

```bash
cd PricingEngineDjango
python manage.py migrate
```

### 2. Seed data (Matrix 2025 contract + RBRVS rule for 99213)

```bash
python manage.py seed_matrix
```

### 3. Load reference data (procedure codes, modifiers)

Procedure codes and modifiers can be loaded from CSV for demos and simulation.

**Data sources (examples; confirm licensing for your use):**

- **CPT/HCPCS and RVUs:** CMS publishes PFS (Physician Fee Schedule) and RBRVS data. Export or obtain CSV with columns: `code_id`, `code_type`, `description`, `work_rvu`, `pe_rvu`, `mp_rvu`.
- **Modifiers:** CMS and other sources publish modifier lists. CSV columns: `modifier_code`, `description`, `percentage_adjustment` (optional; default 100).

**Load steps:**

```bash
# Procedure codes only
python manage.py load_cms_codes --path /path/to/codes.csv

# Procedure codes + modifiers
python manage.py load_cms_codes --path /path/to/codes.csv --modifiers /path/to/modifiers.csv

# Preview without writing to DB
python manage.py load_cms_codes --path /path/to/codes.csv --dry-run
```

After loading, the API exposes:

- `GET /api/procedure-codes/?q=99213` — search by code or description; optional `?limit=20`
- `GET /api/modifiers/?q=26` — list modifiers; optional `?limit=20`

### 4. Run tests

```bash
python manage.py test tests
```

### 5. Start server

```bash
python manage.py runserver
```

- API base: `http://localhost:8000/api/`
- Django sandbox UI: `http://localhost:8000/sandbox/`

---

## Frontend (React)

### 1. Install and run

```bash
cd PricingEngineDjango/frontend
npm install
npm run dev
```

- App: `http://localhost:5173/`
- Set `VITE_API_BASE_URL=http://localhost:8000/api` in `.env.development` so the Pricing Sandbox calls the Django API.

### 2. Production build

```bash
cd PricingEngineDjango/frontend
npm run build
npm run preview   # optional: preview dist
```

---

## Quick smoke test

1. Start Django: `python manage.py runserver`
2. Start React: `cd frontend && npm run dev`
3. Open `http://localhost:5173/pricing-sandbox`, enter contract ID (e.g. `CONT-MATRIX-2026` or `1`) and procedure code `99213`, click "Price line" — expect a JSON response with `allowed_amount` and `status: "SUCCESS"`.
