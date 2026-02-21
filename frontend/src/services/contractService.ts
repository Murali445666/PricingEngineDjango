import { apiClient } from './apiClient'
import type { Contract, PricingRule } from '@/types'

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
