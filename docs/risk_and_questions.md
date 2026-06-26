# Pricing Engine – Risks and Open Questions

## Risks (likely bugs / ambiguity)
- **MPPR uses `base_allowed_amount` and ignores adjustments** — `_run_cross_line_phase` recalculates from `base_allowed_amount`; in legacy flow this is often `None`, so cross-line reductions can zero or ignore adjusted amounts (`core/engine/orchestrator.py`).
- **Outlier overwrites stop-loss every time both match** — claim orchestration runs stop-loss then outlier; outlier replaces totals/status without a guard, which may violate intended precedence (`core/engine/orchestrator.py`).
- **Carve-out lookup not version/effective scoped** — carve-outs are keyed only by `code_value` after config build; multiple carve-outs for the same code across versions or dates could collide if the config builder isn’t strict (`core/engine/orchestrator.py`).
- **Revenue code only affects resolver** — `revenue_code` flows into `PricingInput` and resolver conditions but loader/strategies ignore it, so pricing cannot vary by revenue code even if business expects it (`core/engine/config.py`, `core/engine/resolver.py`).
- **STAGED mode + carve-outs ordering** — Carve-outs and line caps run after staged BASE/ADJUSTMENT; if adjustment rules assume post–carve-out values the behavior can diverge from business intent (`core/engine/orchestrator.py`).
- **Batch/single-line rely on caller contract_id** — Only stored-claim pricing auto-resolves contracts; ad-hoc requests with wrong `contract_id` silently price against the wrong contract (`core/api/views.py`, `core/engine/service.py`).

## Unanswered questions
- Should MPPR apply to `current_allowed_amount` (post carve-out/line-cap) instead of `base_allowed_amount`? What is expected when `base_allowed_amount` is `None`?
- Should stop-loss and outlier be mutually exclusive, or is outlier meant to override stop-loss when both trigger?
- Must carve-outs be version/effective-dated in `ContractPricingConfig` to avoid same-code collisions?
- Is revenue code supposed to influence loader/rate selection, or only rule routing?
- In STAGED mode, should carve-outs/line caps be stage-aware (e.g., between BASE and ADJUSTMENT) rather than always after both stages?
- When should APIs favor snapshot-backed configs versus live DB, and how are version-specific snapshots produced?
- For claim-level DRG, which source of `drg_code` is authoritative (claim header vs first line), and how to prevent double-paying when line-level DRG rules also exist?
