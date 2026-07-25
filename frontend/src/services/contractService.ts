import { apiClient } from './apiClient'
import type {
  Contract,
  ContractCreatePayload,
  ContractValidationResponse,
  PricingRule,
  ValidationResult,
  ContractExplorerResponse,
  BulkValidationRow,
  RateExhibitPreview,
  RateExhibitCommitResult,
  ContractCoveredEntity,
  CoveredEntityCreatePayload,
  ContractProductScope,
  ProductScopeCreatePayload,
  ContractAmendment,
  AmendmentCreatePayload,
  AmendmentCreateResponse,
  ContractVersionDiff,
} from '@/types'

export async function fetchContracts(options?: { includeDraft?: boolean }): Promise<Contract[]> {
  const params = options?.includeDraft ? { include_draft: 1 } : undefined
  const { data } = await apiClient.get<Contract[]>('/contracts/', { params })
  return data
}

export async function createContract(payload: ContractCreatePayload): Promise<Contract> {
  const { data } = await apiClient.post<Contract>('/contracts/', payload)
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

export async function fetchCoveredEntities(contractId: number): Promise<ContractCoveredEntity[]> {
  const { data } = await apiClient.get<ContractCoveredEntity[]>(`/contracts/${contractId}/covered-entities/`)
  return data
}

export async function addCoveredEntity(
  contractId: number,
  payload: CoveredEntityCreatePayload,
): Promise<ContractCoveredEntity> {
  const { data } = await apiClient.post<ContractCoveredEntity>(
    `/contracts/${contractId}/covered-entities/`,
    payload,
  )
  return data
}

export async function deleteCoveredEntity(contractId: number, entityId: number): Promise<void> {
  await apiClient.delete(`/contracts/${contractId}/covered-entities/${entityId}/`)
}

export async function fetchContractScope(contractId: number): Promise<ContractProductScope[]> {
  const { data } = await apiClient.get<ContractProductScope[]>(`/contracts/${contractId}/scope/`)
  return data
}

export async function addContractScope(
  contractId: number,
  payload: ProductScopeCreatePayload,
): Promise<ContractProductScope> {
  const { data } = await apiClient.post<ContractProductScope>(
    `/contracts/${contractId}/scope/`,
    payload,
  )
  return data
}

export async function deleteContractScope(contractId: number, scopeId: number): Promise<void> {
  await apiClient.delete(`/contracts/${contractId}/scope/${scopeId}/`)
}

/** POST /api/validate-contract/<id>/ — returns 422 when errors exist. */
export async function validateContract(
  contractId: number,
  options?: { save?: boolean },
): Promise<ContractValidationResponse> {
  const { data } = await apiClient.post<ContractValidationResponse>(
    `/validate-contract/${contractId}/`,
    {},
    { params: options?.save ? { save: 1 } : undefined, validateStatus: (s) => s === 200 || s === 422 },
  )
  return data
}

/** POST /api/contract-versions/<id>/activate/ — publish DRAFT version (+ contract ACTIVE). */
export async function activateContractVersion(versionId: number): Promise<{ version_id: number; new_status: string }> {
  const { data } = await apiClient.post<{ version_id: number; new_status: string }>(
    `/contract-versions/${versionId}/activate/`,
    {},
  )
  return data
}

/** POST /api/contract-versions/<id>/revert-to-draft/ — unlock ACTIVE version for editing. */
export async function revertContractVersionToDraft(
  versionId: number,
): Promise<{ version_id: number; new_status: string }> {
  const { data } = await apiClient.post<{ version_id: number; new_status: string }>(
    `/contract-versions/${versionId}/revert-to-draft/`,
    {},
  )
  return data
}

/** POST /api/contract-versions/<id>/discard/ — permanently delete a DRAFT version + amendment. */
export async function discardContractDraftVersion(
  versionId: number,
): Promise<{ contract_id: number; version_id: number; version_number: number }> {
  const { data } = await apiClient.post<{ contract_id: number; version_id: number; version_number: number }>(
    `/contract-versions/${versionId}/discard/`,
    {},
  )
  return data
}

export async function fetchContractAmendments(contractId: number): Promise<ContractAmendment[]> {
  const { data } = await apiClient.get<ContractAmendment[]>(`/contracts/${contractId}/amendments/`)
  return data
}

export async function createContractAmendment(
  contractId: number,
  payload: AmendmentCreatePayload,
): Promise<AmendmentCreateResponse> {
  const { data } = await apiClient.post<AmendmentCreateResponse>(
    `/contracts/${contractId}/amendments/`,
    payload,
  )
  return data
}

/** GET /api/contracts/<id>/versions/<version_id>/diff/ — semantic version diff. */
export async function fetchVersionDiff(
  contractId: number,
  versionId: number,
  options?: { against?: number; requireSnapshot?: boolean },
): Promise<ContractVersionDiff> {
  const params: Record<string, string | number> = {}
  if (options?.against != null) params.against = options.against
  if (options?.requireSnapshot) params.require_snapshot = 1
  const { data } = await apiClient.get<ContractVersionDiff>(
    `/contracts/${contractId}/versions/${versionId}/diff/`,
    { params },
  )
  return data
}

function rateExhibitFormData(file: File, options?: { year?: number; versionId?: number }): FormData {
  const form = new FormData()
  form.append('file', file)
  if (options?.year != null) form.append('year', String(options.year))
  if (options?.versionId != null) form.append('version_id', String(options.versionId))
  return form
}

export async function previewRateExhibit(
  contractId: number,
  file: File,
  options?: { year?: number; versionId?: number },
): Promise<RateExhibitPreview> {
  const { data } = await apiClient.post<RateExhibitPreview>(
    `/contracts/${contractId}/rate-exhibit/preview/`,
    rateExhibitFormData(file, options),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

export async function commitRateExhibit(
  contractId: number,
  file: File,
  options?: { year?: number; versionId?: number },
): Promise<RateExhibitCommitResult> {
  const { data } = await apiClient.post<RateExhibitCommitResult>(
    `/contracts/${contractId}/rate-exhibit/commit/`,
    rateExhibitFormData(file, options),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
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
