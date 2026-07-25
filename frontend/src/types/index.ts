export type EnvKind = 'development' | 'production'

export interface Contract {
  contract_id: number
  contract_name: string
  status: string
  legacy_contract_number: string
  effective_start_date?: string
  effective_end_date?: string | null
  line_of_business?: string
  /** Step 12a: open conflict counts from ValidationResult */
  open_error_count?: number
  open_warning_count?: number
}

/** POST /api/contracts/ payload */
export interface ContractCreatePayload {
  contract_name: string
  legacy_contract_number: string
  payer_org: number
  provider_org: string
  network: string
  line_of_business: string
  effective_start_date: string
  effective_end_date?: string | null
  contract_origin_type: 'DIRECT' | 'LEASED' | 'DELEGATED'
  resolution_priority: number
}

/** POST /api/validate-contract/<id>/ response */
export interface ContractValidationResponse {
  contract_id: number
  error_count: number
  warning_count: number
  conflicts: BulkValidationConflict[]
}

/** Rate exhibit preview/commit (Exhibit C CSV) */
export interface RateExhibitPreviewSampleRow {
  change_type: 'added' | 'changed' | 'removed'
  procedure_code: string
  covered_entity: string
  setting?: string
  flat_rate?: string
  methodology_code?: string
  rule_id?: number
  previous_flat_rate?: string | null
  previous_methodology_code?: string
}

export interface RateExhibitPreview {
  contract_id: number
  version_id: number
  year: number
  counts: { added: number; changed: number; removed: number; skipped: number }
  added: RateExhibitPreviewSampleRow[]
  changed: RateExhibitPreviewSampleRow[]
  removed: RateExhibitPreviewSampleRow[]
  sample: RateExhibitPreviewSampleRow[]
  skipped: { row?: number; reason: string; procedure_code?: string }[]
}

export interface RateExhibitCommitResult {
  contract_id: number
  version_id: number
  year: number
  rules_created: number
  rules_updated: number
  rules_deleted: number
  rows_processed: number
  rate_bases_created: number
  rate_bases_updated: number
}

/** GET /api/contracts/<id>/covered-entities/ — Exhibit A roster row */
export interface ContractCoveredEntity {
  id: number
  entity_type: 'ORG' | 'FACILITY' | 'PROVIDER'
  name: string
  identifier: string
  organization_id?: string | null
  provider_id?: number | null
  facility_id?: number | null
  is_primary: boolean
  effective_start_date?: string | null
  effective_end_date?: string | null
}

export interface CoveredEntityCreatePayload {
  entity_type: 'ORG' | 'FACILITY' | 'PROVIDER'
  organization?: string
  provider?: number
  facility?: number
  is_primary?: boolean
  effective_start_date?: string | null
  effective_end_date?: string | null
}

/** GET /api/contracts/<id>/scope/ — Exhibit B product scope row */
export interface ContractProductScope {
  id: number
  product_id: number
  product_name: string | null
  product_code: string | null
  lob_code: string | null
  network_id: string | null
  effective_date: string | null
  termination_date: string | null
  priority: number
}

export interface ProductScopeCreatePayload {
  product_id: number
  lob_code?: string | null
  effective_date?: string | null
  termination_date?: string | null
}

/** Step 12d: one row from POST /api/validate-contracts/bulk/ */
export interface BulkValidationConflict {
  conflict_type: string
  severity: string
  message: string
  affected_objects: unknown[]
  suggested_action: string
}

export interface BulkValidationRow {
  contract_id: number
  error_count: number
  warning_count: number
  conflicts: BulkValidationConflict[]
  /** Present when validate_contract raised for this id */
  errors?: string
}

/** Step 12a: single conflict record from ValidationResult table */
export type ConflictSeverity = 'ERROR' | 'WARNING'

export interface ValidationResult {
  id: number
  conflict_type: string
  severity: ConflictSeverity
  message: string
  affected_objects: unknown[]
  suggested_action: string
  validated_at: string
  resolved: boolean
}

export interface PricingRuleCondition {
  condition_id: number
  attribute_name: string
  operator: string
  attribute_value: string
}

export type RuleStatus = 'DRAFT' | 'ACTIVE' | 'RETIRED'

export interface RuleHistory {
  id: number
  change_date: string
  previous_status: string
  new_status: string
  change_reason: string
}

export interface PricingRule {
  rule_id: number
  rule_name: string
  methodology_code: string
  rule_type: string
  contract_id: number
  status: RuleStatus
  specificity_score?: number
  effective_start_date?: string
  effective_end_date?: string | null
  /** Detail view only */
  multiplier?: number
  flat_rate?: string | number
  base_fee_schedule_id?: number | null
  conditions?: PricingRuleCondition[]
}

export interface PriceLineRequest {
  contract_id: string | number
  procedure_code: string
  billed_amount: string | number
  units?: number
  modifiers?: string[]
  service_date?: string
  pricing_date?: string
  claim_type?: string
}

export interface PriceLineResult {
  status: string
  allowed_amount: string | number
  methodology: string
  details: string
  contract_id: string
  rule_id: number
  trace_id?: string
  execution_time_ms?: number
  /** From simulate-line: log lines for "Why this amount?" */
  trace_logs?: string[]
}

/** Fee schedule option for rule parameter dropdown */
export interface FeeSchedule {
  fee_schedule_id: number
  name: string
  effective_date: string | null
  version: number
}

/** Single condition row for create/update (no condition_id) */
export interface RuleConditionRow {
  attribute_name: string
  operator: string
  attribute_value: string
}

/** POST /api/rules/check-conflicts/ item */
export interface RuleConflictItem {
  message: string
  rule_id: number
  rule_name?: string
  attribute_name?: string
  attribute_value?: string
}

/** Payload for creating a rule (POST) */
export interface RuleCreatePayload {
  rule_name?: string
  rule_type?: string
  methodology_code: string
  multiplier?: number
  flat_rate?: number | null
  base_fee_schedule_id?: number | null
  effective_start_date: string
  effective_end_date?: string | null
  conditions: RuleConditionRow[]
}

// ── Step 12f: Claim Simulation ───────────────────────────────────────────────

export interface ClaimSimulateLineInput {
  line_id?: string
  procedure_code: string
  billed_amount: string | number
  units?: number
  modifiers?: string[]
  cost_amount?: string | number
  revenue_code?: string
}

export interface ClaimSimulateClaimInput {
  service_date?: string
  pricing_date?: string
  claim_type?: string
  drg_code?: string
  facility_id?: number
  provider_id?: number
  lines: ClaimSimulateLineInput[]
}

export interface ClaimSimulateRequest {
  contract_id: number
  version_id: number
  claim: ClaimSimulateClaimInput
  /** Optional advisory validation — does not affect pricing */
  member_id?: string
  billing_npi?: string
  rendering_npi?: string
}

export interface ClaimSimulateValidationProvider {
  billing_org_id: string | null
  network_status: string
  network_tier: string | null
  affiliation_verified: boolean
}

export interface ClaimSimulateValidationMember {
  enrolled: boolean
  lob: string | null
  product_id: number | null
}

export interface ClaimSimulateValidation {
  ran: boolean
  resolution_mode?: 'RESOLVED' | 'OON' | 'NO_CONTRACT' | 'AMBIGUOUS' | null
  resolved_contract_id?: number | null
  selected_contract_id?: number
  matches_selected_contract?: boolean | null
  provider?: ClaimSimulateValidationProvider
  member?: ClaimSimulateValidationMember
  warnings?: string[]
}

export interface ClaimSimulateLineResult {
  status: string
  allowed_amount: string | number
  methodology: string
  details: string
  contract_id: string
  rule_id: number
  base_allowed_amount?: string | number | null
  blended_allowed_amount?: string | number | null
  carveout_applied?: boolean
  carveout_id?: number | null
}

export interface ExecutionTraceEntry {
  stage?: string
  phase?: string
  line_index?: number | null
  rule_id?: number | null
  methodology_code?: string
  message?: string
}

export interface ClaimPricingResult {
  claim_id: number
  contract_id: string
  total_allowed: string | number
  line_count: number
  lines: ClaimSimulateLineResult[]
  status: string
  claim_trace: string[]
  original_total_allowed?: string | number | null
  final_total_allowed?: string | number | null
  applied_outlier_rule_id?: number | null
  applied_stop_loss_rule_id?: number | null
  pre_cap_total_allowed?: string | number | null
  applied_cap_floor_id?: number | null
  blended_total_allowed?: string | number | null
  applied_blending_rule_ids?: number[]
  execution_trace?: ExecutionTraceEntry[]
}

export interface ClaimSimulateResponse {
  version_id: number
  simulation: boolean
  result: ClaimPricingResult
  /** Present when API includes timing metadata */
  request_time_ms?: number
  /** Advisory member/provider validation (optional inputs only) */
  validation?: ClaimSimulateValidation | { ran: false }
}

// ── Step 12e: Contract Explorer (GET /api/contracts/<id>/explorer/) ───────────

export interface ExplorerMethodology {
  id: number
  methodology_type: string
  version_id?: number | null
  effective_date?: string
  termination_date?: string | null
  priority?: number
  claim_type?: string | null
  site_of_service?: string | null
  base_percentage?: string | number | null
  conversion_factor?: string | number | null
  contract_term_id?: number | null
  fee_schedule_id?: number | null
  conditions?: unknown
}

export interface ExplorerPricingRule {
  rule_id: number
  rule_name: string
  methodology_code: string
  rule_type: string
  contract_id: number
  status: string
  version_id?: number | null
  specificity_score?: number | null
  effective_start_date?: string | null
  effective_end_date?: string | null
  multiplier?: number | null
  flat_rate?: string | number | null
  base_fee_schedule_id?: number | null
  conditions?: PricingRuleCondition[]
}

export interface ExplorerCarveout {
  carveout_id: number
  version_id: number
  code_type: string
  code_value: string
  carveout_methodology: string
  carveout_percentage?: string | number | null
  carveout_rate?: string | number | null
  status?: string
  conditions?: unknown
}

export interface ExplorerCapFloor {
  cap_floor_id: number
  version_id: number
  scope: string
  cap_type: string
  value?: string | number | null
  percentage?: string | number | null
  code_value?: string | null
  priority?: number
  effective_start_date?: string
  effective_end_date?: string | null
  status?: string
  conditions?: unknown
}

export interface ExplorerBlendingRule {
  blending_rule_id: number
  version_id: number
  blend_type: string
  scope: string
  primary_methodology: string
  secondary_methodology: string
  blend_percentage: string | number
  priority?: number
  effective_start_date?: string
  effective_end_date?: string | null
  status?: string
  conditions?: unknown
}

export interface ExplorerStopLossRule {
  id: number
  contract_id: number
  version_id?: number | null
  cost_threshold: string | number
  reimbursement_percentage: string | number
  priority?: number
  effective_start_date?: string
  effective_end_date?: string | null
}

export interface ExplorerOutlierRule {
  id: number
  contract_id: number
  version_id?: number | null
  threshold_amount: string | number
  threshold_scope: string
  reimbursement_percentage?: string | number | null
  cost_to_charge_ratio?: string | number | null
  priority?: number
  effective_start_date?: string
  effective_end_date?: string | null
}

export interface ExplorerVersion {
  version_id: number
  version_number: number
  effective_start_date: string
  effective_end_date?: string | null
  status: string
  notes?: string
  pricing_engine_mode?: string
  claim_level_drg_enabled?: boolean
  methodologies?: ExplorerMethodology[]
  /** Pricing rules (API key `rules` on GET …/explorer/) */
  rules?: ExplorerPricingRule[]
  carveouts?: ExplorerCarveout[]
  cap_floors?: ExplorerCapFloor[]
  blending_rules?: ExplorerBlendingRule[]
  stop_loss_rules?: ExplorerStopLossRule[]
  outlier_rules?: ExplorerOutlierRule[]
}

export interface ExplorerContractSummary {
  id: number
  legacy_contract_number?: string | null
  contract_name: string
}

export interface ExplorerOpenConflictCounts {
  errors: number
  warnings: number
}

export interface ContractExplorerResponse {
  contract: ExplorerContractSummary
  open_conflict_counts: ExplorerOpenConflictCounts
  versions: ExplorerVersion[]
}

export interface AmendmentWhatChanged {
  rules: { added: number; changed: number; removed: number }
  entities: { added: number; removed: number }
  scope: { added: number; changed: number; removed: number }
  prior_version_id?: number | null
  new_version_id?: number | null
}

export interface ContractAmendment {
  id: number
  contract: number
  version_id?: number | null
  version_number?: number | null
  version_status?: string | null
  amendment_number: string
  effective_date: string
  description: string
  what_changed?: AmendmentWhatChanged | null
  status: string
  created_at: string
}

export interface AmendmentCreatePayload {
  amendment_number: string
  effective_date: string
  description: string
}

export interface AmendmentCreateResponse {
  amendment: ContractAmendment
  version: { version_id: number; version_number: number; status: string }
}

export interface VersionDiffRateChange {
  code: string
  covered_entity?: string
  rule_name?: string | null
  old_rate?: string | null
  new_rate?: string | null
  pct_change?: number | null
}

export interface VersionDiffEntityRow {
  label: string
  entity_type?: string
  organization_id?: string | null
  facility_id?: number | null
  provider_id?: number | null
}

export interface VersionDiffScopeRow {
  label: string
  lob_code?: string | null
  product_id?: number | null
}

export interface VersionDiffHeaderChange {
  field: string
  old: unknown
  new: unknown
}

export interface ContractVersionDiff {
  version_id: number
  against_version_id: number
  headline: string
  summary: {
    rules: { added: number; changed: number; removed: number }
    entities: { added: number; removed: number }
    scope: { added: number; changed: number; removed: number }
    cap_floors: { changed: number }
    outlier_rules: { changed: number }
    stop_loss_rules: { changed: number }
    contract_header: { changed: number }
  }
  rates: {
    added: VersionDiffRateChange[]
    changed: VersionDiffRateChange[]
    removed: VersionDiffRateChange[]
  }
  covered_entities: {
    added: VersionDiffEntityRow[]
    removed: VersionDiffEntityRow[]
  }
  product_scope: {
    added: VersionDiffScopeRow[]
    removed: VersionDiffScopeRow[]
    changed: Array<{ label: string; old: unknown; new: unknown }>
  }
  cap_floors: { added: unknown[]; removed: unknown[]; changed: unknown[] }
  outlier_rules: { added: unknown[]; removed: unknown[]; changed: unknown[] }
  stop_loss_rules: { added: unknown[]; removed: unknown[]; changed: unknown[] }
  contract_header: VersionDiffHeaderChange[]
}
