import { apiClient } from './apiClient'
import type {
  ProviderListParams,
  ProviderListResponse,
  ProviderNetworkStatusParams,
  ProviderNetworkStatusResponse,
} from '@/types/provider'

function buildListParams(params?: ProviderListParams): Record<string, string | number> {
  const query: Record<string, string | number> = {}
  if (!params) return query
  if (params.npi?.trim()) query.npi = params.npi.trim()
  if (params.name?.trim()) query.name = params.name.trim()
  if (params.specialty?.trim()) query.specialty = params.specialty.trim()
  if (params.status?.trim()) query.status = params.status.trim()
  if (params.page != null) query.page = params.page
  if (params.page_size != null) query.page_size = params.page_size
  return query
}

/** GET /api/providers/ */
export async function listProviders(params?: ProviderListParams): Promise<ProviderListResponse> {
  const { data } = await apiClient.get<ProviderListResponse>('/providers/', {
    params: buildListParams(params),
  })
  return data
}

/** GET /api/providers/<id>/network-status/ */
export async function getProviderNetworkStatus(
  providerId: number,
  params?: ProviderNetworkStatusParams,
): Promise<ProviderNetworkStatusResponse> {
  const query: Record<string, string | number> = {}
  if (params?.network_id != null) query.network_id = params.network_id
  if (params?.service_date?.trim()) query.service_date = params.service_date.trim()
  const { data } = await apiClient.get<ProviderNetworkStatusResponse>(
    `/providers/${providerId}/network-status/`,
    { params: query },
  )
  return data
}
