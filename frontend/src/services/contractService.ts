import { apiClient } from './apiClient'
import type {
  Contract,
  PricingRule,
  ValidationResult,
  ContractExplorerResponse,
  BulkValidationRow,
} from '@/types'

export async function fetchContracts(): Promise<Contract[]> {
  const { data } = await apiClient.get<Contract[]>('/contracts/')
  return data
}

export async function fetchContractById(id: number): Promise<Contract> {
  const { data } = await apiClient.get<Contract>(`/contracts/${id}/`)
  return data
}

export async function fetchContractRules(contractId: number): Promise<PricingRule[]> {
  const { data } = await apiClient.get<PricingRule[]>(`/contracts/${contractId}/rules/`)
  return data
}

// ── Step 12d: Bulk validation ────────────────────────────────────────────────

/** POST /api/validate-contracts/bulk/ — optional save persists ValidationResult per contract. */
export async function bulkValidateContracts(
  contractIds: number[],
  options?: { save?: boolean },
): Promise<BulkValidationRow[]> {
  const { data } = await apiClient.post<BulkValidationRow[]>(
    '/validate-contracts/bulk/',
    { contract_ids: contractIds },
    { params: options?.save ? { save: 1 } : undefined },
  )
  return data
}

// ── Step 12a: Conflict Warnings ──────────────────────────────────────────────

/**
 * Fetch open (unresolved) conflict records for a contract.
 * Pass includeAll=true to also return resolved records.
 */
export async function fetchContractConflicts(
  contractId: number,
  includeAll = false,
): Promise<ValidationResult[]> {
  const params = includeAll ? '?all=1' : ''
  const { data } = await apiClient.get<ValidationResult[]>(
    `/contracts/${contractId}/conflicts/${params}`,
  )
  return data
}

/**
 * Mark a single conflict as resolved (or un-resolved).
 */
export async function resolveContractConflict(
  contractId: number,
  resultId: number,
  resolved: boolean,
): Promise<ValidationResult> {
  const { data } = await apiClient.patch<ValidationResult>(
    `/contracts/${contractId}/conflicts/${resultId}/resolve/`,
    { resolved },
  )
  return data
}

// ── Step 12e: Contract Explorer ─────────────────────────────────────────────

/**
 * Fetch full contract tree for explorer: metadata, versions, methodologies,
 * pricing rules (with conditions), carve-outs, caps/floors, blending rules,
 * stop-loss, outlier, open conflict counts.
 * GET /api/contracts/<id>/explorer/
 */
export async function fetchContractExplorer(contractId: number): Promise<ContractExplorerResponse> {
  const { data } = await apiClient.get<ContractExplorerResponse>(`/contracts/${contractId}/explorer/`)
  return data
}

/** GET /api/contracts/<id>/explorer/?export=csv — flat rule rows (export= avoids DRF format= negotiation). */
export async function fetchContractExplorerCsv(contractId: number): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/contracts/${contractId}/explorer/`, {
    params: { export: 'csv' },
    responseType: 'blob',
  })
  return data
}

// ── Mock for development ──────────────────────────────────────────────────────
// Mock for development
export async function fetchContractsMock(): Promise<Contract[]> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve([
        {
          contract_id: 1,
          contract_name: 'Matrix 2025',
          status: 'ACTIVE',
          legacy_contract_number: 'CONT-MATRIX-2026',
        },
      ])
    }, 200)
  })
}
