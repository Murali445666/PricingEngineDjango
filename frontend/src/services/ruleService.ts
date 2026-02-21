import { apiClient } from './apiClient'
import type {
  PricingRule,
  RuleHistory,
  RuleStatus,
  FeeSchedule,
  RuleCreatePayload,
} from '@/types'

export async function fetchRules(status?: RuleStatus): Promise<PricingRule[]> {
  const params = status ? { status } : {}
  const { data } = await apiClient.get<PricingRule[]>('/rules/', { params })
  return data
}

export async function fetchRuleById(id: string): Promise<PricingRule | null> {
  const { data } = await apiClient.get<PricingRule>(`/rules/${id}/`)
  return data
}

export async function fetchRuleHistory(ruleId: number | string): Promise<RuleHistory[]> {
  const { data } = await apiClient.get<RuleHistory[]>(`/rules/${ruleId}/history/`)
  return data
}

export async function fetchFeeSchedules(): Promise<FeeSchedule[]> {
  const { data } = await apiClient.get<FeeSchedule[]>('/fee-schedules/')
  return data
}

export async function createRule(
  contractId: number,
  payload: RuleCreatePayload
): Promise<PricingRule> {
  const { data } = await apiClient.post<PricingRule>(
    `/contracts/${contractId}/rules/`,
    payload
  )
  return data
}

export async function updateRuleStatus(
  ruleId: number,
  status: RuleStatus
): Promise<PricingRule> {
  const { data } = await apiClient.patch<PricingRule>(`/rules/${ruleId}/`, { status })
  return data
}

// Mock for development
export async function fetchRulesMock(): Promise<PricingRule[]> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve([
        {
          rule_id: 1,
          rule_name: 'RBRVS Standard',
          methodology_code: 'RBRVS',
          rule_type: 'BASE',
          status: 'ACTIVE',
          contract_id: 1,
        },
      ])
    }, 200)
  })
}

export async function fetchRuleByIdMock(id: string): Promise<PricingRule | null> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        rule_id: Number(id) || 1,
        rule_name: 'RBRVS Standard',
        methodology_code: 'RBRVS',
        rule_type: 'BASE',
        status: 'ACTIVE',
        contract_id: 1,
      })
    }, 200)
  })
}
