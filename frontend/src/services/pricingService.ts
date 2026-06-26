import { apiClient } from './apiClient'
import type {
  PriceLineRequest,
  PriceLineResult,
  ClaimSimulateRequest,
  ClaimSimulateResponse,
} from '@/types'

export interface SimulateLineRequest {
  contract_id: string | number
  line: {
    procedure_code: string
    billed_amount: string | number
    units?: number
    modifiers?: string[]
  }
  draft_rule?: Record<string, unknown>
}

export interface PriceClaimLine {
  line_id?: string
  procedure_code: string
  billed_amount: number
  units?: number
  modifiers?: string[]
}

export interface PriceClaimRequest {
  contract_id: string | number
  lines: PriceClaimLine[]
}

export interface PriceClaimResponse {
  contract_id: string
  total_allowed: number
  lines: PriceLineResult[]
  line_count: number
  request_time_ms?: number
}

export async function priceLine(payload: PriceLineRequest): Promise<PriceLineResult> {
  const { data } = await apiClient.post<PriceLineResult>('/price-line/', payload)
  return data
}

export async function simulateLine(payload: SimulateLineRequest): Promise<PriceLineResult> {
  const { data } = await apiClient.post<PriceLineResult>('/simulate-line/', payload)
  return data
}

export async function priceClaim(payload: PriceClaimRequest): Promise<PriceClaimResponse> {
  const { data } = await apiClient.post<PriceClaimResponse>('/price-claim/', payload)
  return data
}

/** Step 12f: POST /api/price-claim-simulate/ — price a claim against a specific contract version. */
export async function priceClaimSimulate(
  payload: ClaimSimulateRequest,
): Promise<ClaimSimulateResponse> {
  const { data } = await apiClient.post<ClaimSimulateResponse>('/price-claim-simulate/', payload)
  return data
}

// Mock for development when API not ready
export async function priceLineMock(): Promise<PriceLineResult> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        status: 'SUCCESS',
        allowed_amount: '150.00',
        methodology: 'RBRVS',
        details: '',
        contract_id: '1',
        rule_id: 1,
        execution_time_ms: 12.5,
      })
    }, 300)
  })
}
