import { createRouter, createWebHistory } from 'vue-router'
import LoginPage from '../pages/Login.vue'
import RegisterPage from '../pages/Register.vue'
import Dashboard from '../pages/Dashboard.vue'
import Profile from '../pages/Profile.vue'
import Users from '../pages/Users.vue'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: () => (useAuthStore().isAuthenticated ? '/dashboard' : '/login') },
  { path: '/login', component: LoginPage, meta: { guestOnly: true } },
  { path: '/register', component: RegisterPage, meta: { guestOnly: true } },
  { path: '/dashboard', component: Dashboard, meta: { requiresAuth: true } },
  { path: '/profile', component: Profile, meta: { requiresAuth: true } },
  { path: '/users', component: Users, meta: { requiresAuth: true, requiresAdmin: true } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// navigation guard
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/login'
  }
  if (to.meta.requiresAdmin) {
    // роль известна только из /me: при открытии страницы по прямой ссылке ждём ответ
    if (!auth.user) await auth.fetchMe()
    if (auth.user?.role !== 'admin') return '/dashboard'
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return '/dashboard'
  }
})

export default router
