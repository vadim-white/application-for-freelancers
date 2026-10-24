import { isAxiosError } from 'axios'

// Текст ошибки для тоста: detail ответа API, иначе запасной
export function errorText(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    // 422: detail — список ошибок валидации
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join('; ')
  }
  return fallback
}
