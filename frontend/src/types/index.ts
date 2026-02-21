export type EnvKind = 'development' | 'production'

export interface Contract {
  contract_id: number
  contract_name: string
  status: string
  legacy_contract_number: string
  effective_start_date?: string
  effective_end_date?: string | null
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
