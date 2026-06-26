import axios, { AxiosError } from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

function formatAxiosErrorMessage(error: AxiosError): string {
  const status = error.response?.status
  const raw = error.response?.data

  if (raw != null && typeof raw === 'object' && !Array.isArray(raw)) {
    const obj = raw as Record<string, unknown>
    if (typeof obj.error === 'string') return obj.error
    if (typeof obj.detail === 'string') return obj.detail
    if (Array.isArray(obj.detail)) {
      return obj.detail.map(String).join('; ')
    }
    const parts: string[] = []
    for (const [key, val] of Object.entries(obj)) {
      if (key === 'detail') continue
      if (Array.isArray(val)) parts.push(`${key}: ${val.map(String).join(', ')}`)
      else if (typeof val === 'string') parts.push(`${key}: ${val}`)
      else if (val != null && typeof val === 'object') parts.push(`${key}: ${JSON.stringify(val)}`)
    }
    if (parts.length > 0) return parts.join(' ')
  }

  if (typeof raw === 'string' && raw.trim()) return raw

  if (status != null) {
    return `Request failed (HTTP ${status})${error.message ? `: ${error.message}` : ''}`
  }
  return error.message || 'Request failed'
}

apiClient.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    return Promise.reject(new Error(formatAxiosErrorMessage(error)))
  }
)
