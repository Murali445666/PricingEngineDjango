// ── Stage 6A: Context-driven reprice API ─────────────────────────────────────

/** Request line — matches ClaimLineInputSerializer */
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
  facility_npi?: string
  member_id: string
  service_date: string
  claim_type?: 'professional' | 'institutional'
  lines: RepriceClaimLineInput[]
}

export interface RepriceClaimProviderContext {
  billing_org_id: string | null
  network_status: string | null
  network_tier: string | null
  affiliation_verified: boolean
}

export interface RepriceClaimMemberContext {
  member_id: string | null
  lob: string | null
  product_id: number | null
  enrollment_id: number | null
}

/**
 * Priced line from engine LineResult (via _serialize_result_lines).
 * Input fields are usually empty — correlate to request lines by array index.
 * API JSON uses `notes`; mapped to `details` in repriceService.
 */
export interface RepriceClaimResultLine {
  procedure_code: string | null
  units: string
  billed_amount: string
  allowed_amount: string
  payment_rate: string
  modifier_1: string
  status: string
  details: string
}

export interface RepriceClaimSuccessResponse {
  status: string
  contract_id: number
  resolution_mode: string
  provider: RepriceClaimProviderContext
  member: RepriceClaimMemberContext
  lines: RepriceClaimResultLine[]
  trace_id: string
}

/** Resolution failure — HTTP 200, not an Axios error */
export interface RepriceClaimResolutionFailureResponse {
  status: 'OON' | 'NO_CONTRACT' | 'AMBIGUOUS'
  message: string
  contract_id: null
  lines: []
}

export type RepriceClaimResponse =
  | RepriceClaimSuccessResponse
  | RepriceClaimResolutionFailureResponse

export function isRepriceResolutionFailure(
  response: RepriceClaimResponse,
): response is RepriceClaimResolutionFailureResponse {
  return (
    response.status === 'OON' ||
    response.status === 'NO_CONTRACT' ||
    response.status === 'AMBIGUOUS'
  )
}

export function isRepriceSuccess(
  response: RepriceClaimResponse,
): response is RepriceClaimSuccessResponse {
  return !isRepriceResolutionFailure(response)
}

/** Context fields passed to ResolutionTracePanel after a successful reprice */
export interface RepriceTraceContext {
  resolutionMode: string | null
  contractId: number | null
  provider: RepriceClaimProviderContext | null
  member: RepriceClaimMemberContext | null
  traceId?: string | null
  message?: string | null
}

// ── Stage 6E: Batch reprice API ──────────────────────────────────────────────

export interface RepriceBatchRequest {
  claims: RepriceClaimRequest[]
}

export interface RepriceBatchSuccessItem {
  index: number
  status: string
  resolution_mode: string
  contract_id: number
  member_id: string
  lines: RepriceClaimResultLine[]
  trace_id: string
}

export interface RepriceBatchFailureItem {
  index: number
  status: 'OON' | 'NO_CONTRACT' | 'AMBIGUOUS' | 'ENGINE_ERROR'
  member_id: string
  message: string
  lines: []
}

export type RepriceBatchResultRow = RepriceBatchSuccessItem | RepriceBatchFailureItem

export interface RepriceBatchResponse {
  count: number
  results: RepriceBatchResultRow[]
}

export function isBatchResultFailure(
  row: RepriceBatchResultRow,
): row is RepriceBatchFailureItem {
  return (
    row.status === 'OON' ||
    row.status === 'NO_CONTRACT' ||
    row.status === 'AMBIGUOUS' ||
    row.status === 'ENGINE_ERROR'
  )
}

export function isBatchResultSuccess(
  row: RepriceBatchResultRow,
): row is RepriceBatchSuccessItem {
  return !isBatchResultFailure(row)
}
