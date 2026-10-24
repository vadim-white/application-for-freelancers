import api from './api'

export type UserRole = 'user' | 'admin'

// Пользователь из auth (схема UserRead)
export interface UserItem {
  id: number
  email: string
  full_name: string | null
  role: UserRole
  is_active: boolean
  created_at: string
}

// Конверт списка: total — число подходящих под фильтры, не размер страницы
export interface UserList {
  items: UserItem[]
  total: number
  limit: number
  offset: number
}

export interface UserListParams {
  role?: UserRole
  is_active?: boolean
  q?: string
  id?: number[]
  sort?: 'created_at' | '-created_at' | 'email' | '-email'
  limit?: number
  offset?: number
}

export async function listUsers(params: UserListParams = {}): Promise<UserList> {
  // id повторяется (?id=1&id=2), а не id[]=1: так его ждёт FastAPI
  const r = await api.get('/api/auth/users', { params, paramsSerializer: { indexes: null } })
  return r.data
}

// merge-patch: что не передано, не меняется
export async function updateUser(
  id: number,
  patch: { role?: UserRole; is_active?: boolean }
): Promise<UserItem> {
  const r = await api.patch(`/api/auth/users/${id}`, patch)
  return r.data
}
