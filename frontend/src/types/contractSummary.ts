/** GET /api/contracts/<id>/summary/ — layered contract view (§15). */

export interface ContractSummaryHeader {
  contract_id: number
  contract_name: string | null
  legacy_contract_number: string | null
  status: string
  contract_origin_type: string
  effective_start_date: string
  effective_end_date: string | null
}

export interface ContractSummaryPayerOrg {
  id: number
  name: string
  payer_id: string
  payer_type: string
}

export interface ContractSummaryProviderOrg {
  organization_id: string
  name: string
  npi: string | null
  org_type: string | null
  parent_org_id: string | null
  parent_org_name: string | null
}

export interface ContractSummaryNetwork {
  network_id: string
  network_name: string | null
  line_of_business: string | null
  network_type: string | null
}

export interface ContractSummaryParties {
  payer_org: ContractSummaryPayerOrg | null
  provider_org: ContractSummaryProviderOrg
  network: ContractSummaryNetwork
}

export interface ContractSummaryCoveredEntity {
  id: number
  entity_type: 'ORG' | 'FACILITY' | 'PROVIDER'
  name: string
  detail: string
  is_primary: boolean
  effective_start_date: string | null
  effective_end_date: string | null
}

export interface ContractSummaryRule {
  rule_id: number
  rule_name: string | null
  rule_type: string
  methodology_code: string | null
  status: string
  claim_type: string | null
  codes: string[]
  rate: string | null
  rate_basis: string | null
  materialized_year: number | null
}

export interface ContractSummaryArrangement {
  id: number | null
  name: string
  arrangement_type: string | null
  claim_type: string | null
  status: string | null
  rules: ContractSummaryRule[]
}

export interface ContractSummaryAmendment {
  id: number
  amendment_number: number
  effective_date: string
  description: string
  status: string
}

export interface ContractSummaryDocument {
  id: number
  doc_type: string
  reference: string | null
  title: string
  notes: string | null
}

export interface ContractSummary {
  abstract: string
  header: ContractSummaryHeader
  contract_id: number
  contract_name: string | null
  legacy_contract_number: string | null
  status: string
  contract_origin_type: string
  line_of_business: string | null
  parties: ContractSummaryParties
  covered_entities: ContractSummaryCoveredEntity[]
  arrangements: ContractSummaryArrangement[]
  amendments: ContractSummaryAmendment[]
  terms: string[]
  documents: ContractSummaryDocument[]
  materialized_year?: number
}
