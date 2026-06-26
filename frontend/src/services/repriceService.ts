import { apiClient } from './apiClient'
import type {
  RepriceBatchRequest,
  RepriceBatchResponse,
  RepriceBatchResultRow,
  RepriceClaimRequest,
  RepriceClaimResponse,
  RepriceClaimResultLine,
  RepriceClaimSuccessResponse,
} from '@/types/reprice'
import { isRepriceResolutionFailure } from '@/types/reprice'

/** Raw line shape from API (_serialize_result_lines uses `notes` for engine details). */
interface RawRepriceResultLine {
  procedure_code?: string | null
  units?: string
  billed_amount?: string
  allowed_amount?: string
  payment_rate?: string
  modifier_1?: string
  status?: string
  notes?: string
  details?: string
}

function mapResultLine(raw: RawRepriceResultLine): RepriceClaimResultLine {
  return {
    procedure_code: raw.procedure_code ?? null,
    units: String(raw.units ?? ''),
    billed_amount: String(raw.billed_amount ?? ''),
    allowed_amount: String(raw.allowed_amount ?? ''),
    payment_rate: String(raw.payment_rate ?? ''),
    modifier_1: String(raw.modifier_1 ?? ''),
    status: String(raw.status ?? ''),
    details: String(raw.notes ?? raw.details ?? ''),
  }
}

function mapSuccessResponse(data: RepriceClaimSuccessResponse & { lines?: RawRepriceResultLine[] }): RepriceClaimSuccessResponse {
  return {
    ...data,
    lines: (data.lines ?? []).map(mapResultLine),
  }
}

function normalizeClaimPayload(claim: RepriceClaimRequest): RepriceClaimRequest {
  return {
    ...claim,
    rendering_npi: claim.rendering_npi?.trim() || undefined,
    lines: claim.lines.map((line) => ({
      ...line,
      billed_amount: line.billed_amount ?? undefined,
    })),
  }
}

export async function repriceClaim(payload: RepriceClaimRequest): Promise<RepriceClaimResponse> {
  const { data } = await apiClient.post<RepriceClaimResponse>(
    '/reprice-claim/',
    normalizeClaimPayload(payload),
  )
  if (isRepriceResolutionFailure(data)) {
    return data
  }
  return mapSuccessResponse(data as RepriceClaimSuccessResponse & { lines?: RawRepriceResultLine[] })
}

interface RawBatchResultRow {
  index: number
  status: string
  resolution_mode?: string
  contract_id?: number
  member_id: string
  lines?: RawRepriceResultLine[]
  trace_id?: string
  message?: string
}

function mapBatchResultRow(raw: RawBatchResultRow): RepriceBatchResultRow {
  if (
    raw.status === 'OON' ||
    raw.status === 'NO_CONTRACT' ||
    raw.status === 'ENGINE_ERROR'
  ) {
    return {
      index: raw.index,
      status: raw.status,
      member_id: raw.member_id,
      message: raw.message ?? '',
      lines: [],
    }
  }
  return {
    index: raw.index,
    status: raw.status,
    resolution_mode: raw.resolution_mode ?? 'RESOLVED',
    contract_id: raw.contract_id ?? 0,
    member_id: raw.member_id,
    lines: (raw.lines ?? []).map(mapResultLine),
    trace_id: raw.trace_id ?? '',
  }
}

/** POST /api/reprice-claim-batch/ — up to 50 claims, per-row isolation */
export async function repriceClaimBatch(
  payload: RepriceBatchRequest,
): Promise<RepriceBatchResponse> {
  const body: RepriceBatchRequest = {
    claims: payload.claims.map(normalizeClaimPayload),
  }
  const { data } = await apiClient.post<{ count: number; results: RawBatchResultRow[] }>(
    '/reprice-claim-batch/',
    body,
  )
  return {
    count: data.count,
    results: data.results.map(mapBatchResultRow),
  }
}
