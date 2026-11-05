import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { ThemeName } from '../styles/tokens'

export type ThemeChoice = 'system' | ThemeName

// Тот же ключ и то же правило читает inline-скрипт в index.html: он ставит data-theme до загрузки
// JS, чтобы при открытии страницы не мелькала светлая тема
const STORAGE_KEY = 'theme'

const systemQuery = window.matchMedia('(prefers-color-scheme: dark)')

function isChoice(value: string | null): value is ThemeChoice {
  return value === 'system' || value === 'light' || value === 'dark'
}

// localStorage в приватном режиме или при запрете сайта бросает исключение — тогда выбор живёт
// до перезагрузки, тема по умолчанию — как в системе
function readChoice(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return isChoice(value) ? value : 'system'
  } catch {
    return 'system'
  }
}

function saveChoice(value: ThemeChoice) {
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // см. readChoice
  }
}

// I4: «Как в системе» (по умолчанию), «Светлая», «Тёмная»; выбор — удобство одного браузера
export const useThemeStore = defineStore('theme', () => {
  const choice = ref<ThemeChoice>(readChoice())
  const systemDark = ref(systemQuery.matches)

  // «Как в системе» меняется на лету, когда пользователь переключает тему ОС
  systemQuery.addEventListener('change', (event) => (systemDark.value = event.matches))

  const resolved = computed<ThemeName>(() =>
    choice.value === 'system' ? (systemDark.value ? 'dark' : 'light') : choice.value
  )

  // data-theme переключает CSS-переменные и color-scheme (tokensCss в tokens.ts)
  watch(resolved, (name) => (document.documentElement.dataset.theme = name), { immediate: true })

  function setChoice(value: ThemeChoice) {
    choice.value = value
    saveChoice(value)
  }

  return { choice, resolved, setChoice }
})
