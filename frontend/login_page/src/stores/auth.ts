import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../services/api'

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
      const r = await api.get('/api/auth/me')
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
