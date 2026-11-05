import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// Страницы — ленивые: каждая в своём чанке, грузится при первом переходе на неё
const LoginPage = () => import('../pages/Login.vue')
const RegisterPage = () => import('../pages/Register.vue')
const AppLayout = () => import('../layouts/AppLayout.vue')
const Dashboard = () => import('../pages/Dashboard.vue')
const Statistics = () => import('../pages/Statistics.vue')
const Profile = () => import('../pages/Profile.vue')
const Users = () => import('../pages/Users.vue')

const routes = [
  { path: '/login', component: LoginPage, meta: { guestOnly: true } },
  { path: '/register', component: RegisterPage, meta: { guestOnly: true } },
  // страницы после входа — внутри раздела с общей шапкой; redirect срабатывает только на самом «/»
  {
    path: '/',
    component: AppLayout,
    redirect: () => (useAuthStore().isAuthenticated ? '/dashboard' : '/login'),
    children: [
      { path: 'dashboard', component: Dashboard, meta: { requiresAuth: true } },
      {
        path: 'statistics',
        component: Statistics,
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      { path: 'profile', component: Profile, meta: { requiresAuth: true } },
      { path: 'users', component: Users, meta: { requiresAuth: true, requiresAdmin: true } }
    ]
  }
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
