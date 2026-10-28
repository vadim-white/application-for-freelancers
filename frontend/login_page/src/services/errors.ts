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

// 429 по Retry-After (секунды): минуты с округлением вверх, секунды — если меньше минуты.
// Заголовка нет или он не число секунд (другой вход) — общий текст. Текст по коду и заголовку:
// у 429 входа (nginx, Envoy) тело не JSON, detail нет
function tooManyAttemptsText(err: unknown): string {
  const seconds = Number(isAxiosError(err) ? err.response?.headers?.['retry-after'] : NaN)
  if (!Number.isInteger(seconds) || seconds <= 0) {
    return 'Слишком много запросов, повторите через несколько секунд'
  }
  const wait = seconds < 60 ? `${seconds} с.` : `${Math.ceil(seconds / 60)} мин.`
  return `Слишком много попыток входа. Повторите через ${wait}`
}

// Текст ошибки входа и регистрации: 429 — по Retry-After, остальное — как errorText
export function authErrorText(err: unknown, fallback: string): string {
  if (isAxiosError(err) && err.response?.status === 429) return tooManyAttemptsText(err)
  return errorText(err, fallback)
}
