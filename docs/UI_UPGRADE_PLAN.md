# UI Upgrade Plan — Stage 6 (Context-Driven Flows)

**Status:** Planning only — no frontend implementation in this pass.  
**Backend reference:** Stages 1–5 complete (`docs/UPGRADE_PLAN.md`). All endpoints below already exist; **do not modify backend** for Stage 6 UI work.  
**Audience:** Frontend implementers and PM reviewers who need the contract-first → identity-first shift made visible in the admin UI.

---

## 1. Current-State Summary

### 1.1 Route table (`frontend/src/routes/index.tsx`)

All routes nest under `MainLayout` at `/`. Default redirect: `/` → `/pricing-sandbox`.

| Path | Page component | Domain |
|------|----------------|--------|
| `/pricing-sandbox` | `PricingSandboxPage` | Single-line pricing (contract-first) |
| `/contracts` | `ContractsPage` | Contract list + bulk validation |
| `/contracts/:id` | `ContractDetailPage` | Contract detail |
| `/contracts/:contractId/rules/new` | `RuleCreatePage` | Rule authoring |
| `/contract-explorer` | `ContractExplorerPage` | Contract tree explorer |
| `/rules` | `RulesPage` | Global rules list |
| `/rules/:id` | `RuleDetailPage` | Rule detail |
| `/claim-simulation` | `ClaimSimulationPage` | Version-scoped claim simulate |
| `/rule-simulator` | `RuleSimulatorPage` | Line-level rule simulation |
| `/run-scenario` | `RunScenarioPage` | Scenario runner |
| `/batch-monitor` | `BatchMonitorPage` | Batch job monitor |
| `/admin` | `AdminPage` | Admin utilities |

Catch-all `*` redirects to `/`.

### 1.2 Sidebar navigation (`frontend/src/app/Sidebar.tsx`)

Flat `navItems` array of `{ to, label }`. Active link styling via `NavLink` + Tailwind (`bg-primary-50 text-primary-700`). Mobile overlay drawer pattern (`isOpen` / `onClose`).

Current entries mirror the route table above. **New Stage 6 entries must be appended** to this array only — do not reorder or rename existing items.

### 1.3 Service layer (`frontend/src/services/`)

| Module | Responsibility | Pattern |
|--------|----------------|---------|
| `apiClient.ts` | Axios instance, 30s timeout, JSON headers | `baseURL` from `VITE_API_BASE_URL` (typically `http://localhost:8000/api` or `/api` via Vite proxy). Paths in service functions are **relative to baseURL** — e.g. `'/price-line/'` not `'/api/price-line/'`. Response interceptor wraps Axios errors as `Error` with human-readable message (`error`, `detail`, or field-level validation text). |
| `pricingService.ts` | `priceLine`, `simulateLine`, `priceClaim`, `priceClaimSimulate` | Async functions; request/response types co-located in service file or imported from `@/types`. |
| `contractService.ts` | Contracts, conflicts, explorer, bulk validation | Same pattern; uses `apiClient.get/post/patch`. |
| `ruleService.ts` | Rules CRUD, fee schedules, conflict check | Same pattern. |

**Convention:** One service module per backend domain. Export named async functions (not class instances). Optional `*Mock()` helpers for offline dev (see `priceLineMock`, `fetchContractsMock`).

### 1.4 Shared UI primitives (`frontend/src/shared/ui/`)

All re-exported from `@/shared/ui` via `index.ts`:

| Component | Role |
|-----------|------|
| `PageLayout` | Page title, description, optional metadata band, children |
| `FormPanel` | Bordered card with optional title/description header |
| `SectionHeader` | Standalone section heading |
| `Button` | `primary` / `secondary` / `danger` variants |
| `Input` | Label + error text; forwards ref |
| `Select` | Label + options dropdown |
| `TextArea` | Multi-line input with label/error |
| `StatusBadge` | Normalizes rule/pricing status strings to color variants |
| `LoadingSpinner` | Inline spinner (`size="sm"` in buttons) |
| `ErrorState` | Red panel + optional retry button |
| `Modal` / `ModalFooter` | Dialog shell |
| `DataTable` | Sortable columns, client-side pagination (`pageSize`), generic `Column<T>` type |

**Tailwind style:** Slate neutrals, `primary-*` blue accent, `rounded border border-slate-200`, `text-sm` body, `font-mono` for JSON/debug output.

### 1.5 Type conventions (`frontend/src/types/index.ts`)

- Central interfaces for API shapes used across features.
- Section comments with step/phase markers (e.g. `// ── Step 12f: Claim Simulation ──`).
- Money fields typed as `string | number` (DRF returns Decimal as string).
- Status fields typed as `string` (engine enums serialized as strings).
- New Stage 6 types should be **appended** in a `// ── Stage 6: Context-driven APIs ──` block.

### 1.6 Feature-page patterns (reference implementations)

**Data fetching:** TanStack Query v5 — `useQuery` for GET lists/detail, `useMutation` for POST actions. Query keys are string arrays (`['contracts']`, `['contract-explorer', contractId]`).

**Loading:** Centered `<LoadingSpinner />` or inline spinner inside `<Button>` while pending.

**Errors:**
- Query errors → `<ErrorState title="…" message={error.message} onRetry={refetch} />`
- Mutation errors → `window.alert(...)` and/or red `role="alert"` banner (see `ClaimSimulationPage`)
- Axios errors always arrive as `Error` with `.message` (interceptor)

**Layout:** `PageLayout` → one or more `FormPanel` sections → optional `DataTable` result panels.

**Forms:** Local `useState` for field values; submit via `mutation.mutate()`. No form library.

**Results:** `DataTable` with explicit `Column<T>` definitions and custom `render` cells; or raw JSON in `<pre>` (`PricingSandboxPage`).

**Contract-first assumption:** Every pricing flow today requires the user to know or select `contract_id` (and often `version_id`). Context resolution (member + provider → contract) is not surfaced.

---

## 2. The Gap

### 2.1 Architectural mismatch

| Today (UI) | Backend Stages 1–5 |
|------------|-------------------|
| User picks **contract_id** first | System resolves **member_id + billing_npi → enrollment → product → network → contract** |
| Pricing Sandbox / Claim Simulation / Bulk Monitor | `POST /api/reprice-claim/` and batch variant |
| No provider directory | `GET /api/providers/` + network-status |
| No member coverage lookup | `GET /api/members/<member_id>/enrollment/` |
| No product catalog | `GET /api/products/` |
| No resolution debug UI | `GET /api/resolve-context/` (Stage 4, API-only) |

The backend can price and resolve context without the analyst knowing `contract_id`. The frontend cannot.

### 2.2 Backend endpoints with **no UI today**

| Method | Path | Stage | Purpose |
|--------|------|-------|---------|
| `POST` | `/api/reprice-claim/` | 5 | Identity-first single-claim reprice |
| `POST` | `/api/reprice-claim-batch/` | 5 | Up to 50 claims, per-claim isolation |
| `GET` | `/api/providers/` | 5 | Paginated provider directory |
| `GET` | `/api/providers/<provider_id>/network-status/` | 5 | OON / tier check for a network |
| `GET` | `/api/members/<member_id>/enrollment/` | 5 | Active coverage on a date |
| `GET` | `/api/products/` | 5 | Paginated product catalog |
| `GET` | `/api/resolve-context/` | 4 | Resolve context without pricing (debug) |

**Related but already partially covered (contract-first — do not replace):**

| Method | Path | Existing UI |
|--------|------|-------------|
| `POST` | `/api/price-claim/` | No dedicated page (Pricing Sandbox is single-line only) |
| `POST` | `/api/price-claims-bulk/` | Batch Monitor (contract_id per claim) |
| `POST` | `/api/price-claim-simulate/` | Claim Simulation Workbench |

---

## 3. Staged UI Plan (6A–6E)

Each sub-stage is an independent, shippable PR. All changes are **additive**: new files + append-only edits to `routes/index.tsx`, `Sidebar.tsx`, and `types/index.ts`.

---

### 6A — Reprice Claim (flagship)

**Goal:** Analyst submits member + provider identity; UI shows resolution trace + priced lines without selecting a contract.

#### Route + nav

| Item | Value |
|------|-------|
| Route path | `/reprice-claim` |
| Sidebar label | `Reprice Claim` |
| Insert after | `Claim Simulation` (keeps pricing flows grouped) |

#### Page component

```
frontend/src/features/repricing/RepriceClaimPage.tsx
```

Optional co-located helpers (same folder):

```
frontend/src/features/repricing/ClaimLineEntryGrid.tsx   # shared form grid (see §4)
frontend/src/features/repricing/ResolutionTracePanel.tsx
```

#### Service module

```
frontend/src/services/contextPricingService.ts
```

```typescript
// Request shapes match RepriceClaimRequestSerializer
export interface RepriceClaimLineInput {
  procedure_code: string
  units?: number | string
  modifier_1?: string
  modifier_2?: string
  modifier_3?: string
  modifier_4?: string
  billed_amount?: number | string | null
  revenue_code?: string
  place_of_service?: string
  diagnosis_codes?: string[]
}

export interface RepriceClaimRequest {
  billing_npi: string
  rendering_npi?: string
  member_id: string
  service_date: string          // ISO date YYYY-MM-DD
  claim_type?: 'professional' | 'institutional'
  lines: RepriceClaimLineInput[]
}

// Success — HTTP 200, status is engine PricingStatus string (e.g. SUCCESS)
export interface RepriceClaimProviderContext {
  billing_org_id: string | null
  network_status: string | null   // IN_NETWORK | OUT_OF_NETWORK | UNKNOWN | …
  network_tier: string | null       // TIER_1 | TIER_2 | null
  affiliation_verified: boolean
}

export interface RepriceClaimMemberContext {
  member_id: string | null
  lob: string | null
  product_id: number | null
  enrollment_id: number | null
}

/** Line items from _serialize_result_lines — see §4.3 correlation note */
export interface RepriceClaimResultLine {
  procedure_code: string | null   // usually null — engine LineResult has no echo
  units: string
  billed_amount: string
  allowed_amount: string
  payment_rate: string            // usually empty
  modifier_1: string
  status: string
  notes: string                   // populated from engine `details`, not `notes`
}

export interface RepriceClaimSuccessResponse {
  status: string                  // SUCCESS | DENIED_* | …
  contract_id: number
  resolution_mode: string         // RESOLVED
  provider: RepriceClaimProviderContext
  member: RepriceClaimMemberContext
  lines: RepriceClaimResultLine[]
  trace_id: string
}

/** Resolution failure — still HTTP 200 */
export interface RepriceClaimResolutionFailureResponse {
  status: 'OON' | 'NO_CONTRACT'
  message: string
  contract_id: null
  lines: []
}

export type RepriceClaimResponse =
  | RepriceClaimSuccessResponse
  | RepriceClaimResolutionFailureResponse

export interface ResolveContextParams {
  billing_npi?: string
  rendering_npi?: string
  member_id?: string
  service_date?: string
  claim_type?: string
}

export interface ResolveContextSuccessResponse {
  resolution_mode: string
  contract_id: number | null
  version_id: number | null
  claim_type: string
  service_date: string
  provider: {
    billing_org_id: string | null
    rendering_provider_id: number | null
    rendering_provider_specialty: string | null
    network_status: string | null
    network_tier: string | null
    affiliation_verified: boolean
  }
  member: {
    member_id: string | null
    product_id: number | null
    lob: string | null
    network_id: number | null
    locality_zip: string | null
    enrollment_id: number | null
  }
}

export interface ResolveContextFailureResponse {
  resolution_mode: 'OON' | 'NO_CONTRACT'
  error: string
  contract_id: null
}

export type ResolveContextResponse =
  | ResolveContextSuccessResponse
  | ResolveContextFailureResponse

export async function repriceClaim(
  payload: RepriceClaimRequest,
): Promise<RepriceClaimResponse>

export async function resolveContext(
  params: ResolveContextParams,
): Promise<ResolveContextResponse>
```

Implementation notes:
- `repriceClaim` → `POST /reprice-claim/`; validation errors → HTTP **400** `{ errors: … }` (Axios throws).
- Resolution failure → HTTP **200** with `status: 'OON' | 'NO_CONTRACT'` — **not** an Axios error; page must branch on `response.status`.
- Engine failure → HTTP **500** `{ status: 'ENGINE_ERROR', message: string }` — Axios throws.
- `resolveContext` → `GET /resolve-context/` with query params; used by **Preview resolution** button feeding `ResolutionTracePanel` without running the engine.

#### TypeScript types location

Append interfaces above to `frontend/src/types/index.ts` (or re-export from service — prefer central `types/index.ts` for cross-feature use in 6E).

#### Shared UI reuse vs new

| Reuse | New (introduced in 6A) |
|-------|-------------------------|
| `PageLayout`, `FormPanel`, `Input`, `Select`, `Button`, `LoadingSpinner`, `ErrorState`, `DataTable`, `StatusBadge` | `ResolutionTracePanel` (§4.1) |
| | `NetworkStatusBadge` (§4.2) |
| | `ClaimLineEntryGrid` (§4.3) |

#### Page structure (wireframe)

1. **Identity panel** — `billing_npi`, `rendering_npi`, `member_id`, `service_date`, `claim_type` select.
2. **Claim lines panel** — `ClaimLineEntryGrid` (min 1 line).
3. **Actions** — `Preview resolution` (calls `resolveContext`) | `Reprice claim` (calls `repriceClaim`).
4. **ResolutionTracePanel** — shows resolve-context or reprice response context fields.
5. **Results panel** — merged input/output line table (index-correlated); summary row for `contract_id`, `status`, `trace_id`.

#### Demo script

1. Sidebar → **Reprice Claim**.
2. Enter seeded demo values: `billing_npi=BILLING-NPI-S4`, `member_id=MEM-S4-001`, `service_date=2025-06-15`, line `99213` / `$200`.
3. Click **Preview resolution** → trace shows `resolution_mode=RESOLVED`, `contract_id` populated, `network_status=IN_NETWORK`, `lob=COMMERCIAL`.
4. Click **Reprice claim** → `status=SUCCESS`, allowed amount on line 1, `ResolutionTracePanel` matches.

---

### 6B — Providers

**Goal:** Searchable provider directory + per-provider network status check.

#### Route + nav

| Item | Value |
|------|-------|
| Route path | `/providers` |
| Sidebar label | `Providers` |

#### Page component

```
frontend/src/features/providers/ProvidersPage.tsx
frontend/src/features/providers/ProviderNetworkStatusPanel.tsx   # optional drawer/modal
```

#### Service module

```
frontend/src/services/providerService.ts
```

```typescript
export interface ProviderListParams {
  npi?: string
  name?: string
  specialty?: string
  status?: string
  page?: number
  page_size?: number
}

export interface ProviderSummary {
  id: number
  npi: string
  first_name: string
  last_name: string
  credential: string | null
  primary_specialty: string | null
  status: string
}

export interface ProviderListResponse {
  count: number
  page: number
  page_size: number
  results: ProviderSummary[]
}

export interface ProviderNetworkStatusParams {
  providerId: number
  network_id?: number
  service_date?: string
}

export interface ProviderNetworkStatusResponse {
  provider_id: number
  npi: string
  network_status: string    // UNKNOWN | IN_NETWORK | OUT_OF_NETWORK | IN_NETWORK status passthrough
  network_tier: string | null
  as_of_date: string
}

export async function fetchProviders(
  params?: ProviderListParams,
): Promise<ProviderListResponse>

export async function fetchProviderNetworkStatus(
  params: ProviderNetworkStatusParams,
): Promise<ProviderNetworkStatusResponse>
```

- List → `GET /providers/?…`
- Network status → `GET /providers/${providerId}/network-status/?network_id=&service_date=`
- 404 → `{ error: 'Provider not found.' }` (Axios throws)
- Invalid date / network_id → 400 `{ error: string }`

#### Shared UI

| Reuse | New |
|-------|-----|
| `PageLayout`, `FormPanel`, `Input`, `Button`, `DataTable`, `LoadingSpinner`, `ErrorState`, `Modal` | Filter bar (inline in page — no new primitive) |
| `NetworkStatusBadge` (from 6A) | Row action opens network-status modal |

**Pagination:** Backend returns `count`, `page`, `page_size`. Current `DataTable` paginates client-side only — use **server-driven** prev/next buttons calling `fetchProviders` with `page` param (same pattern as backend API, not `DataTable` footer).

#### Demo script

1. Sidebar → **Providers**.
2. Filter NPI `RENDER-NPI-S4` → one row.
3. Click **Check network** → enter `network_id` from seeded data + date → badge shows `IN_NETWORK` or tier.

---

### 6C — Members

**Goal:** Coverage lookup by member ID and service date.

#### Route + nav

| Item | Value |
|------|-------|
| Route path | `/member-enrollment` |
| Sidebar label | `Member Enrollment` |

#### Page component

```
frontend/src/features/members/MemberEnrollmentPage.tsx
```

#### Service module

```
frontend/src/services/memberService.ts
```

```typescript
export interface MemberEnrollmentParams {
  memberId: string
  service_date?: string
}

export interface MemberEnrollmentResponse {
  member_id: string
  enrolled: boolean
  enrollment_id: number | null
  product_id: number | null
  product_name: string | null
  lob: string | null
  network_id: number | null
  effective_date: string | null
  termination_date: string | null
  as_of_date: string
}

export async function fetchMemberEnrollment(
  params: MemberEnrollmentParams,
): Promise<MemberEnrollmentResponse>
```

- `GET /members/${encodeURIComponent(memberId)}/enrollment/?service_date=`
- Invalid date → 400 `{ error: string }`

**Note:** `network_id` is only populated when a `ProductNetworkConfig` with `claim_type='ALL'` exists for the product. Seeded demo data uses `PROFESSIONAL` — UI should show `network_id` as `—` when null, not treat as error.

#### Shared UI

| Reuse | New |
|-------|-----|
| `PageLayout`, `FormPanel`, `Input`, `Button`, `LoadingSpinner`, `ErrorState`, `StatusBadge` | None — definition list (`<dl>`) for enrollment fields |

Optional cross-link: **Open in Reprice Claim** button pre-fills member_id on `/reprice-claim` via router state or query string.

#### Demo script

1. Sidebar → **Member Enrollment**.
2. Enter `MEM-S4-001`, date `2025-06-15`.
3. Submit → `enrolled=true`, `lob=COMMERCIAL`, product name shown.

---

### 6D — Products

**Goal:** Payer product catalog with filters.

#### Route + nav

| Item | Value |
|------|-------|
| Route path | `/products` |
| Sidebar label | `Products` |

#### Page component

```
frontend/src/features/products/ProductsPage.tsx
```

#### Service module

```
frontend/src/services/productService.ts
```

```typescript
export interface ProductListParams {
  payer_id?: string
  lob?: string
  effective_date?: string
  page?: number
  page_size?: number
}

export interface ProductSummary {
  id: number
  name: string
  product_code: string | null
  payer_id: string
  payer_name: string
  lob: string | null
  effective_date: string
  termination_date: string | null
}

export interface ProductListResponse {
  count: number
  page: number
  page_size: number
  results: ProductSummary[]
}

export async function fetchProducts(
  params?: ProductListParams,
): Promise<ProductListResponse>
```

- `GET /products/?…`
- Invalid `effective_date` → 400 `{ error: string }`

#### Shared UI

| Reuse | New |
|-------|-----|
| Same as 6B list page pattern | None |

#### Demo script

1. Sidebar → **Products**.
2. Filter `lob=COMMERCIAL` → seeded product row visible.
3. Optional filter `payer_id=PAYER-S4-01`.

---

### 6E — Batch Reprice

**Goal:** Submit multiple identity-first claims; show per-index results with isolated failures.

#### Route + nav

| Item | Value |
|------|-------|
| Route path | `/reprice-claim-batch` |
| Sidebar label | `Batch Reprice` |

#### Page component

```
frontend/src/features/repricing/RepriceClaimBatchPage.tsx
```

Reuse from 6A: `ClaimLineEntryGrid`, `ResolutionTracePanel` (compact per row), `NetworkStatusBadge`.

#### Service module

Extend `contextPricingService.ts`:

```typescript
export interface RepriceClaimBatchRequest {
  claims: RepriceClaimRequest[]
}

export interface RepriceClaimBatchSuccessItem {
  index: number
  status: string                    // engine status on success
  resolution_mode: string
  contract_id: number
  member_id: string
  lines: RepriceClaimResultLine[]
  trace_id: string
}

export interface RepriceClaimBatchFailureItem {
  index: number
  status: 'OON' | 'NO_CONTRACT' | 'ENGINE_ERROR'
  member_id: string
  message: string
  lines: []
}

export type RepriceClaimBatchResultItem =
  | RepriceClaimBatchSuccessItem
  | RepriceClaimBatchFailureItem

export interface RepriceClaimBatchResponse {
  count: number
  results: RepriceClaimBatchResultItem[]
}

export async function repriceClaimBatch(
  payload: RepriceClaimBatchRequest,
): Promise<RepriceClaimBatchResponse>
```

- `POST /reprice-claim-batch/` — max **50** claims; validation → 400 `{ errors: … }`
- Batch HTTP response is always **200** when the envelope validates; individual claim failures appear in `results[].status`.

#### Shared UI

| Reuse | New |
|-------|-----|
| All 6A components + `DataTable` | `BatchClaimCard` — collapsible claim editor (optional; can duplicate grid N times) |
| | Import JSON / add row / remove row controls |

#### Demo script

1. Sidebar → **Batch Reprice**.
2. Add two claims: both valid demo identities → `count=2`, both `SUCCESS`.
3. Add third claim with invalid `billing_npi` → that row `NO_CONTRACT`, others unaffected.

---

## 4. Cross-Cutting Components (built in 6A, reused in 6B–6E)

### 4.1 `ResolutionTracePanel`

**Path:** `frontend/src/features/repricing/ResolutionTracePanel.tsx`

**Purpose:** Make the resolution architecture visible — the centerpiece differentiator vs contract-first pages.

**Props (suggested):**

```typescript
interface ResolutionTracePanelProps {
  resolutionMode: string | null
  contractId: number | null
  provider: RepriceClaimProviderContext | ResolveContextSuccessResponse['provider'] | null
  member: RepriceClaimMemberContext | ResolveContextSuccessResponse['member'] | null
  message?: string | null          // OON / NO_CONTRACT message
  traceId?: string | null
}
```

**Visual flow (horizontal stepper or vertical timeline):**

```
member_id → enrollment / lob / product_id
     ↓
billing_npi → billing_org_id
     ↓
network_id (from member) → network_status / network_tier  [NetworkStatusBadge]
     ↓
resolution_mode → contract_id
```

**Data sources:**
- Preview: `GET /api/resolve-context/` (richer provider fields: `rendering_provider_id`, `locality_zip`)
- Post-reprice: fields embedded in `POST /api/reprice-claim/` success body (no `network_id` on member block — show `product_id` / `lob` only)

Use `FormPanel` wrapper + `dl` grid (same as Claim Simulation summary). Link `contract_id` to `/contracts/:id` when non-null.

### 4.2 `NetworkStatusBadge`

**Path:** `frontend/src/shared/ui/NetworkStatusBadge.tsx` — export from `shared/ui/index.ts`

Extends `StatusBadge` color mapping for network-specific values:

| Value | Display | Color intent |
|-------|---------|--------------|
| `IN_NETWORK` | IN NETWORK | green |
| `OUT_OF_NETWORK` | OUT OF NETWORK | red |
| `TIER_1`, `TIER_2` | show tier label | blue (tiered IN) |
| `UNKNOWN` | UNKNOWN | slate |
| Other passthrough | raw string | amber |

Accept optional `tier?: string | null` — when `network_status === 'IN_NETWORK'` and tier set, render `IN NETWORK (TIER_1)`.

### 4.3 Claim line entry grid + result correlation

**Path:** `frontend/src/features/repricing/ClaimLineEntryGrid.tsx`

**Input columns (match serializer):**

| Field | Required | Notes |
|-------|----------|-------|
| `procedure_code` | yes | max 10 |
| `units` | no (default 1) | |
| `modifier_1` … `modifier_4` | no | 2 chars each |
| `billed_amount` | no | Decimal |
| `revenue_code` | no | |
| `place_of_service` | no | |
| `diagnosis_codes` | no | comma-separated → string[] on submit |

Add/remove line buttons; minimum 1 line enforced client-side before submit.

**Output correlation (critical):**

`_serialize_result_lines()` reads `LineResult` from the engine. **`LineResult` does not echo input fields** — expect:

| Response field | Typical value |
|----------------|---------------|
| `procedure_code` | `null` |
| `units` | `""` |
| `billed_amount` | `""` |
| `payment_rate` | `""` |
| `modifier_1` | `""` |
| `allowed_amount` | priced value (string) |
| `status` | e.g. `SUCCESS`, `DENIED_NO_RULE` |
| `notes` | engine **`details`** text (field name is `notes` in JSON only) |

**UI rule:** Keep local input line array in component state. After reprice, render a **merged table** by **array index**:

```
| # | procedure_code (input) | billed (input) | allowed_amount (output) | status | notes |
```

Do not join on `procedure_code`. Optionally show raw output JSON in a collapsible debug section (`PricingSandboxPage` pattern).

---

## 5. Sequencing & Risk

### 5.1 Recommended build order

| Order | Stage | Rationale |
|-------|-------|-----------|
| 1 | **6A Reprice Claim** | Flagship; introduces `contextPricingService`, `ResolutionTracePanel`, `NetworkStatusBadge`, `ClaimLineEntryGrid`. Validates end-to-end identity-first story. |
| 2 | **6B Providers** | Read-only; low risk; reuses `NetworkStatusBadge`. |
| 3 | **6C Members** | Read-only; complements 6A member context. |
| 4 | **6D Products** | Read-only; same list pattern as 6B. |
| 5 | **6E Batch Reprice** | Reuses 6A form components + service types; highest UI complexity last. |

6B–6D can ship in parallel after 6A merges (no cross-dependencies except shared badges).

### 5.2 Risk register

| Risk | Mitigation |
|------|------------|
| Reprice returns HTTP 200 for OON/NO_CONTRACT | Branch on `data.status === 'OON' \|\| 'NO_CONTRACT'`; do not rely on Axios error handling. |
| Output lines lack procedure codes | Index-correlate with input state (§4.3). Document in page help text. |
| `billing_npi` max length 15 | Validate in UI; demo NPIs must fit (`BILLING-NPI-S4` = 14 chars). |
| `resolve-context` vs reprice provider shape differs | `ResolutionTracePanel` accepts union provider type; optional fields render as `—`. |
| Server pagination vs `DataTable` client pagination | 6B/6D use API `page`/`page_size` with external prev/next, not `DataTable` built-in footer. |
| No seeded providers/members in empty DB | Demo script references Stage 4/5 test fixtures; link to `python manage.py seed_demo` / test seed docs in page metadata. |

### 5.3 Explicit do-not-touch list

**Backend (frozen for Stage 6 UI):**
- No changes to `core/api/views.py`, `core/api/serializers.py`, `core/api/urls.py`
- No changes to `core/engine/`, models, or migrations
- No new API endpoints

**Frontend (append-only exceptions):**
- `frontend/src/routes/index.tsx` — add new `<Route>` entries only
- `frontend/src/app/Sidebar.tsx` — append `navItems` only
- `frontend/src/types/index.ts` — append Stage 6 types only
- `frontend/src/shared/ui/index.ts` — export new badges only

**Do not modify:**
- Existing feature pages (`PricingSandboxPage`, `ClaimSimulationPage`, `ContractsPage`, etc.)
- Existing services (`pricingService.ts`, `contractService.ts`, `ruleService.ts`)
- Existing shared UI component behavior (`StatusBadge.tsx`, etc.)
- `apiClient.ts` interceptor logic (unless a dedicated 400 `{ errors }` helper is needed — prefer parsing in page)

### 5.4 Route table after Stage 6 (target)

Append to existing routes:

```tsx
<Route path="reprice-claim" element={<RepriceClaimPage />} />
<Route path="providers" element={<ProvidersPage />} />
<Route path="member-enrollment" element={<MemberEnrollmentPage />} />
<Route path="products" element={<ProductsPage />} />
<Route path="reprice-claim-batch" element={<RepriceClaimBatchPage />} />
```

Append to `navItems`:

```typescript
{ to: '/reprice-claim', label: 'Reprice Claim' },
{ to: '/providers', label: 'Providers' },
{ to: '/member-enrollment', label: 'Member Enrollment' },
{ to: '/products', label: 'Products' },
{ to: '/reprice-claim-batch', label: 'Batch Reprice' },
```

---

## Appendix A — API quick reference (field-accurate)

### POST `/api/reprice-claim/`

**Request body:** `RepriceClaimRequest` (see 6A).

**Responses:**

| HTTP | Body |
|------|------|
| 200 | Success: `{ status, contract_id, resolution_mode, provider, member, lines, trace_id }` |
| 200 | Resolution fail: `{ status: 'OON'\|'NO_CONTRACT', message, contract_id: null, lines: [] }` |
| 400 | `{ errors: { field: string[] } }` |
| 500 | `{ status: 'ENGINE_ERROR', message }` |

### POST `/api/reprice-claim-batch/`

**Request:** `{ claims: RepriceClaimRequest[] }` (1–50).

**Response:** `{ count, results: [{ index, status, … }] }` — per-item shape per 6E types.

### GET `/api/resolve-context/`

**Query:** `billing_npi`, `rendering_npi`, `member_id`, `service_date`, `claim_type`.

**Response:** `{ resolution_mode, contract_id, version_id, claim_type, service_date, provider, member }` or failure `{ resolution_mode, error, contract_id: null }` — HTTP 200.

### GET `/api/providers/`

**Response:** `{ count, page, page_size, results: [{ id, npi, first_name, last_name, credential, primary_specialty, status }] }`.

### GET `/api/providers/:id/network-status/`

**Response:** `{ provider_id, npi, network_status, network_tier, as_of_date }`.

### GET `/api/members/:member_id/enrollment/`

**Response:** `{ member_id, enrolled, enrollment_id, product_id, product_name, lob, network_id, effective_date, termination_date, as_of_date }`.

### GET `/api/products/`

**Response:** `{ count, page, page_size, results: [{ id, name, product_code, payer_id, payer_name, lob, effective_date, termination_date }] }`.

---

## Appendix B — Relationship to existing pages

| Existing page | Relationship to Stage 6 |
|---------------|-------------------------|
| Pricing Sandbox | Keeps contract-first single-line pricing — complementary, not replaced |
| Claim Simulation | Version-scoped simulation — still needed for draft rules / version pinning |
| Batch Monitor | Contract-id bulk pricing — different API (`/price-claims-bulk/`) |
| Contract Explorer | Target for deep-link from `ResolutionTracePanel` when `contract_id` resolved |

Stage 6 UI completes the story begun in backend Stage 5: **the analyst no longer needs to know the contract before pricing a claim.**
