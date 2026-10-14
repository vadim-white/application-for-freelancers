import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

// по умолчанию тот же origin: /api проксирует nginx (Docker) или Vite (npm run dev)
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

// axios instance
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Attach token from localStorage to avoid Pinia circular import problems
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 401 на этих путях — ответ на сами учётные данные, refresh не поможет
const NO_REFRESH_PATHS = ['/api/auth/login', '/api/auth/register', '/api/auth/refresh']

// один общий запрос refresh на все параллельные 401
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) throw new Error('No refresh token')
  // голый axios, а не api: без интерцепторов и без рекурсии
  const r = await axios.post(`${API_BASE}/api/auth/refresh`, { refresh_token: refreshToken })
  const token = r.data.access_token as string
  localStorage.setItem('access_token', token)
  return token
}

function forceLogout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  // полная перезагрузка сбрасывает состояние Pinia
  if (window.location.pathname !== '/login') window.location.href = '/login'
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    if (
      error.response?.status !== 401 ||
      !config ||
      config._retry ||
      NO_REFRESH_PATHS.some((p) => config.url?.startsWith(p))
    ) {
      return Promise.reject(error)
    }
    config._retry = true
    try {
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null
      })
      await refreshPromise
    } catch {
      forceLogout()
      return Promise.reject(error)
    }
    // новый токен подставит request-интерцептор
    return api(config)
  }
)

export default api
