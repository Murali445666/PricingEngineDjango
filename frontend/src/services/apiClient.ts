import axios, { AxiosError } from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

apiClient.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const message = error.response?.data && typeof error.response.data === 'object' && 'error' in error.response.data
      ? (error.response.data as { error: string }).error
      : error.message
    return Promise.reject(new Error(message))
  }
)
