// ── Stage 6D: Product catalog API ───────────────────────────────────────────

export interface ProductListParams {
  payer_id?: string
  lob?: string
  effective_date?: string
  page?: number
  page_size?: number
}

export interface ProductSummary {
  id: number
  name: string
  product_code: string | null
  payer_id: string
  payer_name: string
  lob: string | null
  effective_date: string
  termination_date: string | null
}

export interface ProductListResponse {
  count: number
  page: number
  page_size: number
  results: ProductSummary[]
}
