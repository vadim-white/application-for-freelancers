import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { refreshAccessToken } from '../services/api'

// role из тела access-токена; подпись проверяет сервер, здесь токен только читается
function tokenRole(token: string | null): string | null {
  try {
    const body = token?.split('.')[1]
    if (!body) return null
    const b64 = body.replace(/-/g, '+').replace(/_/g, '/')
    const json = new TextDecoder().decode(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)))
    const role = JSON.parse(json).role
    return typeof role === 'string' ? role : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<any | null>(null)

  const isAuthenticated = computed(() => !!accessToken.value)

  async function login(email: string, password: string) {
    const res = await api.post('/api/auth/login', { email, password })
    accessToken.value = res.data.access_token
    refreshToken.value = res.data.refresh_token
    localStorage.setItem('access_token', accessToken.value!)
    localStorage.setItem('refresh_token', refreshToken.value!)
    await fetchMe()
    return res.data
  }

  async function fetchMe() {
    if (!accessToken.value) {
      user.value = null
      return null
    }
    try {
      // токен (в т.ч. обновлённый после refresh) ставит интерцептор из localStorage
      let r = await api.get('/api/auth/me')
      // роль сменили при открытой сессии: токен несёт старую, /me — новую (D8). Один refresh и один
      // повторный /me, без цикла; не удался refresh — остаётся ответ первого /me
      const claim = tokenRole(localStorage.getItem('access_token'))
      if (claim !== null && claim !== r.data.role) {
        try {
          accessToken.value = await refreshAccessToken()
          r = await api.get('/api/auth/me')
        } catch {
          // старый токен ещё действует
        }
      }
      user.value = r.data
      return user.value
    } catch (err) {
      user.value = null
      return null
    }
  }

  async function register(payload: { email: string; password: string; full_name?: string }) {
    const res = await api.post('/api/auth/register', payload)
    return res.data
  }

  function logout() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  // auto-fetch user if token present on store init
  // Note: when using SSR or hydration, adjust accordingly.
  if (accessToken.value && !user.value) {
    // fire-and-forget
    fetchMe()
  }

  return { accessToken, refreshToken, user, isAuthenticated, login, register, logout, fetchMe }
})
