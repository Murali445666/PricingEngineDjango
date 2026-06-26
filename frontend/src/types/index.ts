export type EnvKind = 'development' | 'production'

export interface Contract {
  contract_id: number
  contract_name: string
  status: string
  legacy_contract_number: string
  effective_start_date?: string
  effective_end_date?: string | null
  /** Step 12a: open conflict counts from ValidationResult */
  open_error_count?: number
  open_warning_count?: number
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
