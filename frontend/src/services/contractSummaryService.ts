import { apiClient } from './apiClient'
import type { ContractSummary } from '@/types/contractSummary'

/** GET /api/contracts/<id>/summary/ — read-only layered contract summary. */
export async function getContractSummary(id: number): Promise<ContractSummary> {
  const { data } = await apiClient.get<ContractSummary>(`/contracts/${id}/summary/`)
  return data
}
