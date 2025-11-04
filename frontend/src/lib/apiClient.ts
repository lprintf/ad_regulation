import axios from 'axios'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'frontend-rule-engine'
  },
  timeout: 15000
})

apiClient.interceptors.request.use(config => {
  const userId = import.meta.env.VITE_DEFAULT_USER_ID ?? 'dev-user'
  config.headers.set('X-User-Id', userId)
  return config
})

export default apiClient
