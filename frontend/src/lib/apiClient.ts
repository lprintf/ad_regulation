import axios from 'axios'

const serializeParams = (params?: Record<string, unknown>) => {
  const searchParams = new URLSearchParams()
  if (!params) {
    return searchParams.toString()
  }

  const appendValue = (key: string, value: unknown) => {
    if (value === null || value === undefined) {
      return
    }
    if (Array.isArray(value)) {
      value.forEach(item => appendValue(key, item))
      return
    }
    if (value instanceof Date) {
      searchParams.append(key, value.toISOString())
      return
    }
    searchParams.append(key, String(value))
  }

  Object.entries(params).forEach(([key, value]) => appendValue(key, value))
  return searchParams.toString()
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api'

const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'frontend-rule-engine'
  },
  timeout: 60000, // 60 seconds for API calls that may fetch from Facebook
  paramsSerializer: {
    serialize: serializeParams
  }
})

apiClient.interceptors.request.use(config => {
  const userId = import.meta.env.VITE_DEFAULT_USER_ID ?? 'dev-user'
  config.headers.set('X-User-Id', userId)
  return config
})

export default apiClient
