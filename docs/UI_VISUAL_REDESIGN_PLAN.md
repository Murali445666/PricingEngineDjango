# UI Visual Redesign Plan — Premium Healthcare-Finance Console

**Status:** Planning only — no implementation in this pass.
**Relationship to `docs/UI_UPGRADE_PLAN.md`:** That document plans new *functional* flows
(identity-first Reprice Claim, Providers, Members, Products, Batch Reprice — Stage 6). This
document is purely visual/presentational: a design-system pass over the existing app shell,
shared components, and the current contract-authoring pages. It does not add routes, pages, or
API calls, and should be read as complementary, not a replacement.

## Context

The app (`frontend/`, React + TS + Tailwind + React Query) currently uses a clean but generic
admin-panel look: flat white background, thin gray borders, a plain white top-nav-less sidebar,
and `window.alert`/`window.confirm` for feedback. The goal is a cohesive visual upgrade —
dark navy nav rail, glass/elevated surfaces, restrained gradients, better tables, badges, empty
states, toasts — **without changing any workflow, route, or API behavior**. This is a pure
presentation-layer pass on top of the existing component structure, not a rebuild.

Codebase exploration confirmed the shared component set already matches what the design brief
calls out (`Button`, `Input`, `Select`, `TextArea`, `DataTable`, `StatusBadge`,
`NetworkStatusBadge`, `Modal`, `FormPanel`, `PageLayout`, `SectionHeader`, `LoadingSpinner`,
`ErrorState` in `frontend/src/shared/ui/`), so the redesign is additive/restyling work on real
files, not new architecture. Notes from that exploration that shape the plan below:

- There's a lot of **uncommitted, in-progress work** already in the tree (contract
  amendment/versioning feature: `AmendmentPanel`, `VersionHistoryPanel`, `VersionDiffPanel`,
  `CoveredEntitiesPanel`, `ProductScopePanel`, `RateExhibitPanel`, `ContractCreatePage`, plus
  backend changes). None of this should be reverted or functionally altered when this plan is
  executed — only restyled.
- No icon library or toast/notification system exists anywhere in `frontend/src` today.
- All 20 `window.alert`/`window.confirm` call sites live inside the "Contracts" and "Claim
  Simulation" clusters — i.e. exactly the pages this redesign prioritizes — so migrating them to
  toast/confirm-dialog primitives is naturally in-scope for the priority-pages phase, not extra
  work.
- Pages compose from shared components for structure, but hand-roll real one-off UI per page:
  tab pills (`ContractDetailPage.tsx:169-191`), inline severity banners (multiple files,
  red/amber/green ternary `<div>`s), link-styled buttons (`<Link className="rounded
  bg-primary-600 ...">`), and raw `<table>` markup inside the bulk-validation modal
  (`ContractsPage.tsx:236-317`). These need real per-page touch-ups, not just a shared-component
  swap.
- `tailwind.config.js` currently forces global `borderRadius: { DEFAULT: '4px' }` — this should
  be removed so normal Tailwind radius utilities (`rounded-lg`, `rounded-xl`, etc.) behave as
  expected; components get updated to explicit radius classes so nothing shifts unintentionally.
- Font: keep the **system font stack** (no external Google Fonts network call) — `Inter` first,
  falling back to `ui-sans-serif`/`system-ui`. This matches the design brief's own fallback
  clause ("if adding a font dependency is undesirable, retain the system stack") and avoids
  introducing an external runtime dependency for a portfolio/demo app.
- Icons: add `lucide-react` as a new dependency (small, tree-shakeable, exactly matches the
  "Lucide-style line icons" requirement — not a "large component library").

## Scope decision

Given the size of the brief, work should be split into two passes:

- **First pass — Phases 0–3 below**: design tokens, the app shell (Sidebar/Header), the full
  shared `ui/` library upgrade + new primitives (Toast, ConfirmDialog, Tabs, EmptyState,
  Skeleton, ValueDiff, ReadinessBanner), and the 6 priority pages named in the design brief:
  Contracts list, Contract detail/authoring workspace (+ its child panels), Contract summary,
  Rate exhibit preview, Claim simulation, Resolution trace.
- **Follow-up pass — remaining pages**: Rules, Providers, Members, Products, Reprice, Batch,
  Admin, Pricing Sandbox, Rule Simulator, Run Scenario, Contract Explorer, Contract Create.
  These automatically pick up the shared-component visual upgrade (Phase 2) for free since they
  already import from `shared/ui`, but will retain their current hand-rolled bits (tab pills, ad
  hoc banners) until a dedicated follow-up pass. This matches the design brief's own "First Pages
  to Polish" phasing — intentionally deferred, not silently dropped.

## Phase 0 — Design tokens & foundation

- `frontend/src/index.css`: add the CSS custom properties from the design brief under `:root`
  (app background, surfaces, nav colors, text colors, accent/semantic colors, borders). Replace
  the flat `bg-slate-50` body with the layered radial-gradient background (kept subtle; the
  optional <3% opacity dot-grid texture is a judgment call to make visually once other changes
  are in place — skip if it risks table legibility).
- `frontend/tailwind.config.js`: remove the `borderRadius.DEFAULT: '4px'` override; extend
  `colors` with `navy`/`accent`/semantic tokens mapped to the CSS vars (or literal hexes) so
  Tailwind utility classes (`bg-nav-background`, `text-accent-primary`, etc.) are available;
  keep the existing `primary` scale (still referenced across ~30 files) untouched for
  compatibility.
- Add `lucide-react` to `frontend/package.json` dependencies, run install.
- This phase has no visible output on its own — it's plumbing for later phases.

## Phase 1 — App shell

- `frontend/src/app/Sidebar.tsx`: rebuild as a dark navy rail (`--nav-background` /
  `--nav-background-secondary`), grouped nav (`AUTHORING`, `PRICING`, `OPERATIONS`, `DIRECTORY`,
  `ADMINISTRATION`) with small uppercase group labels, a `lucide-react` icon per item,
  active-item soft blue background + left accent bar + white text + subtle glow, muted slate
  inactive text, subtle hover surface, small brand/logo area at top. Keep the same `navItems`
  destinations (no route changes) — just add `icon` + `group` fields to the existing config
  array. Keep the mobile slide-over behavior (`isOpen`/`onClose`) intact.
- `frontend/src/app/Header.tsx`: restyle as a translucent/backdrop-blur bar with bottom border,
  derive a simple breadcrumb/section label from the current route (via `useLocation` + a small
  path→label map built from the same nav config, so no per-page wiring is needed), keep the env
  badge (relabel to `DEMO`/`DEV` per the brief), add a decorative (non-functional) search input
  affordance, restyle the user menu as an avatar placeholder. Keep the `onMenuClick` prop
  contract unchanged so `MainLayout` doesn't need logic changes.
- `frontend/src/app/MainLayout.tsx`: adjust background to use the new app-background token; no
  structural changes.

## Phase 2 — Shared `ui/` library upgrade + new primitives

Restyle in place (props/behavior unchanged unless noted) — `frontend/src/shared/ui/`:

- `Button.tsx`: primary (blue, soft shadow), secondary (white/border), danger variants per spec;
  add an optional `premium` style path for gradient CTAs (used sparingly, e.g. Publish) — likely
  a new `variant: 'gradient'` option rather than a separate component, so existing call sites
  (`variant="primary"|"secondary"|"danger"`) keep working unchanged.
- `Input.tsx` / `Select.tsx` / `TextArea.tsx`: white bg, subtle shadow, blue focus ring w/ glow
  (`focus:ring-4 focus:ring-blue-500/10`), consistent heights, better label/description slot.
- `DataTable.tsx`: soft header background, sticky header, low-contrast zebra striping, row
  hover, tighter/consistent column padding, tabular-nums for numeric columns, rounded outer
  container, thin separators, refined sort indicator, refined pagination controls, better
  `emptyMessage` rendering (delegates to new `EmptyState` when no custom content given).
- `StatusBadge.tsx`: extend `normalizeStatus` mapping to cover `SUPERSEDED`, `ARCHIVED`,
  `WARNING`, `READY`, `AMBIGUOUS` (currently collapsed into Draft/Active/Retired/Error/Success),
  add small status dot, soft tinted bg, thin border — keep the `status: string` prop contract so
  no call site changes are needed.
- `NetworkStatusBadge.tsx`: same visual treatment (dot + tint), same prop contract.
- `Modal.tsx`: dark translucent overlay + backdrop blur, elevated white panel, sticky footer,
  fade + slight upward entrance transition (respect `prefers-reduced-motion`).
- `FormPanel.tsx`: `rounded-xl`, thin slate border, layered shadow, stronger header row,
  optional `icon`/`accent` props (new, optional, default off) for exhibit-specific identity
  color strips.
- `PageLayout.tsx`: extend (backward-compatible optional props) to support breadcrumb, status
  badges, and a right-aligned actions slot, per the brief's page-header example — existing
  callers passing only `title`/`description`/`metadata`/`children` keep working unchanged.
- `SectionHeader.tsx`: minor type/spacing polish only.
- `LoadingSpinner.tsx`: keep for button-level use; used by new `Skeleton` only where a spinner
  still makes sense (mutation-pending, not page load).
- `ErrorState.tsx`: add severity icon, keep retry action, add optional technical-details
  disclosure (new optional prop, default hidden).

New files to add to `shared/ui/` (and export from `index.ts`):

- `Toast.tsx` (+ `ToastProvider`/`useToast()` context): mounted once in `App.tsx`.
  Success/error/info variants, auto-dismiss, restrained entrance/exit transition.
- `ConfirmDialog.tsx`: thin wrapper over `Modal` (title, message, confirm/cancel labels, danger
  style) — replaces `window.confirm(...)` call sites via local `useState` per callsite.
- `Tabs.tsx`: extracted version of the pill-tab pattern already duplicated in
  `ContractDetailPage.tsx` — reusable `<Tabs items={[...]} value={} onChange={} />`.
- `EmptyState.tsx`: icon-in-soft-circle + heading + message + optional action, per the brief's
  example.
- `Skeleton.tsx`: `SkeletonRow`/`SkeletonCard` primitives for page-level loading states.
- `ValueDiff.tsx`: renders `$108.12 → $114.50` (muted old value, emphasized new value) — used in
  `VersionDiffPanel` and `RateExhibitPanel`'s preview table.
- `ReadinessBanner.tsx`: presentational progress bar + checklist rows (`✓`/`!`/`○` status
  lines) — contract-specific readiness *computation* stays in `ContractDetailPage`, this
  component just renders `{ percent, items: { label, state }[] }`.

## Phase 3 — Priority pages

1. **`ContractsPage.tsx`** — new page header (breadcrumb, title, description, "New agreement"
   as a proper `<Button as link>`), compact summary strip (Active/Draft/Need Attention counts
   derived from existing `data`), upgraded `DataTable` styling (inherits from Phase 2), replace
   the raw `<table>`s inside the bulk-validation `Modal` with `DataTable`, replace `window.alert`
   calls with `useToast()`.
2. **`ContractDetailPage.tsx`** (+ child panels `AmendmentPanel`, `VersionHistoryPanel`,
   `VersionDiffPanel`, `CoveredEntitiesPanel`, `ProductScopePanel`, `RateExhibitPanel`,
   `ConflictWarningsPanel`) — page header with breadcrumb/status badges/actions, replace the ad
   hoc tab buttons with `<Tabs>`, add `ReadinessBanner` (computed from covered-entities count,
   product-scope count, rate-row count, validation warning/error counts, "regression tests not
   run" placeholder), give Exhibit A/B/C panels (`CoveredEntitiesPanel`/`ProductScopePanel`/
   `RateExhibitPanel`) their violet/cyan/blue left-accent identity via `FormPanel`'s new
   `accent` prop, replace all `window.alert`/`window.confirm` in this cluster with
   `useToast()`/`ConfirmDialog`, restyle the validation result banner using semantic tokens, use
   `ValueDiff` in the diff/preview tables.
3. **`ContractSummaryPage.tsx`** — two-column layout with sticky right-side "Contract facts"
   panel on large screens (currently a single column of stacked `FormPanel`s — restructure
   layout only, same data/sections), polish entity chips and the arrangement blocks, replace the
   `📄` emoji with a `lucide-react` file icon.
4. **`RateExhibitPanel.tsx`** — covered under #2 (it's a child panel of Contract Detail).
5. **`ClaimSimulationPage.tsx`** — page header, replace its 6 `window.alert` calls with
   `useToast()`, polish forms/results tables with Phase 2 styling.
6. **`ResolutionTracePanel.tsx`** (used from `RepriceClaimPage.tsx`) — polish the existing
   numbered-step vertical layout (already close to a stepper) with refined dots/connector line
   and semantic-token severity banner; no structural change needed here, it's already
   well-formed.

## Verification (once implemented)

- `cd frontend && npm install && npm run build` — confirms TypeScript compiles and no import
  breaks across the ~30 files touched.
- `npm run lint`.
- Visually check, at minimum: Contracts list, Contract detail (all tabs/panels, readiness
  banner, publish flow up to the confirm dialog), Contract summary, Claim simulation, and one
  untouched page (e.g. Rules) to confirm the shared-component changes didn't break pages outside
  the priority list.
- Spot-check `prefers-reduced-motion` by toggling it in devtools and confirming modal/toast
  transitions are suppressed.
- Confirm no `window.alert`/`window.confirm` remain in the migrated files: `grep -rn
  "window.alert\|window.confirm" frontend/src/features/contracts frontend/src/features/simulation`.
