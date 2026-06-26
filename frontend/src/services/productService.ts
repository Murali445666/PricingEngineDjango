import { apiClient } from './apiClient'
import type { ProductListParams, ProductListResponse } from '@/types/product'

function buildListParams(params?: ProductListParams): Record<string, string | number> {
  const query: Record<string, string | number> = {}
  if (!params) return query
  if (params.payer_id?.trim()) query.payer_id = params.payer_id.trim()
  if (params.lob?.trim()) query.lob = params.lob.trim()
  if (params.effective_date?.trim()) query.effective_date = params.effective_date.trim()
  if (params.page != null) query.page = params.page
  if (params.page_size != null) query.page_size = params.page_size
  return query
}

/** GET /api/products/ */
export async function listProducts(params?: ProductListParams): Promise<ProductListResponse> {
  const { data } = await apiClient.get<ProductListResponse>('/products/', {
    params: buildListParams(params),
  })
  return data
}
