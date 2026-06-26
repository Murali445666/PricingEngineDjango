// ── Stage 6B: Provider directory API ─────────────────────────────────────────

export interface ProviderListParams {
  npi?: string
  name?: string
  specialty?: string
  status?: string
  page?: number
  page_size?: number
}

export interface ProviderSummary {
  id: number
  npi: string
  first_name: string
  last_name: string
  credential: string | null
  primary_specialty: string | null
  status: string
}

export interface ProviderListResponse {
  count: number
  page: number
  page_size: number
  results: ProviderSummary[]
}

export interface ProviderNetworkStatusParams {
  network_id?: number
  service_date?: string
}

export interface ProviderNetworkStatusResponse {
  provider_id: number
  npi: string
  network_status: string
  network_tier: string | null
  as_of_date: string
}
