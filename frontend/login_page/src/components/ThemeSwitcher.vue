<template>
  <div ref="root" class="theme-switcher" @focusout="onFocusout">
    <button
      ref="toggle"
      type="button"
      class="theme-toggle"
      aria-label="Тема"
      title="Тема"
      aria-controls="theme-options"
      :aria-expanded="open"
      @click="onToggle"
    >
      <app-icon :icon="current.icon" />
    </button>

    <div id="theme-options" class="theme-options" :class="{ open }" role="group" aria-label="Тема">
      <button
        v-for="option in OPTIONS"
        :key="option.value"
        type="button"
        class="theme-option"
        :title="option.label"
        :aria-pressed="theme.choice === option.value"
        @click="select(option.value)"
      >
        <app-icon :icon="option.icon" />
        <span class="option-label">{{ option.label }}</span>
        <app-icon v-if="theme.choice === option.value" :icon="Check" class="option-check" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, Monitor, Moon, Sun } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { useThemeStore, type ThemeChoice } from '../stores/theme'

// Переключатель темы в шапке (I4, вид выбран в 3.2.5): на компьютере — три кнопки в ряд;
// до 960 px (режим телефона шапки, AppLayout.vue) — значок текущего выбора, по нему те же три кнопки
// списком с подписями. Список закрывается выбором, Esc, щелчком мимо и уходом фокуса (Tab, меню
// разделов, открытое с клавиатуры)
const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Monitor }[] = [
  { value: 'system', label: 'Как в системе', icon: Monitor },
  { value: 'light', label: 'Светлая', icon: Sun },
  { value: 'dark', label: 'Тёмная', icon: Moon }
]

const emit = defineEmits<{ open: [] }>()

const theme = useThemeStore()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const toggle = ref<HTMLButtonElement | null>(null)

const current = computed(() => OPTIONS.find((o) => o.value === theme.choice) ?? OPTIONS[0]!)

function onToggle() {
  open.value = !open.value
  // меню разделов и список темы раскрываются под шапкой и закрыли бы друг друга
  if (open.value) emit('open')
}

function select(value: ThemeChoice) {
  theme.setChoice(value)
  open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !open.value) return
  open.value = false
  toggle.value?.focus()
}

function onFocusout(event: FocusEvent) {
  if (open.value && !root.value?.contains(event.relatedTarget as Node | null)) open.value = false
}

function onPointerdown(event: PointerEvent) {
  if (open.value && !root.value?.contains(event.target as Node)) open.value = false
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('pointerdown', onPointerdown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('pointerdown', onPointerdown)
})
</script>

<style scoped>
.theme-switcher {
  position: relative;
  display: flex;
}

.theme-toggle,
.theme-option {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    background var(--transition),
    color var(--transition);
}

.theme-toggle:hover,
.theme-option:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.theme-option[aria-pressed='true'] {
  background: var(--color-accent-soft);
  color: var(--color-text);
}

.theme-toggle:focus-visible,
.theme-option:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.theme-toggle {
  display: none;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
}

/* Компьютер: три кнопки в рамке, общая высота 36 px — как у кнопок шапки */
.theme-options {
  display: flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
}

.theme-option {
  width: 32px;
  height: 30px;
  border-radius: calc(var(--radius-md) - 2px);
}

/* подпись — для скринридера, зрячему — иконка и подсказка title */
.option-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.option-check {
  display: none;
}

/* Телефон (порог шапки — AppLayout.vue): значок в строке, кнопки — списком под ним */
@media (max-width: 960px) {
  .theme-toggle {
    display: inline-flex;
  }

  .theme-options {
    display: none;
    position: absolute;
    top: calc(100% + var(--space-3));
    right: 0;
    z-index: 11;
    flex-direction: column;
    min-width: 200px;
    padding: var(--space-2);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    box-shadow: var(--shadow-overlay);
  }

  .theme-options.open {
    display: flex;
  }

  .theme-option {
    width: auto;
    height: 44px;
    justify-content: flex-start;
    gap: var(--space-3);
    padding: 0 var(--space-3);
    border-radius: var(--radius-md);
    color: var(--color-text);
    font-size: 15px;
  }

  .option-label {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip-path: none;
  }

  .option-check {
    display: inline-block;
    margin-left: auto;
    color: var(--color-accent);
  }
}
</style>
