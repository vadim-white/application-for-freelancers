<template>
  <div class="state-error" role="alert">
    <app-icon class="state-icon" :icon="TriangleAlert" :size="36" />
    <div class="state-title">{{ title }}</div>
    <div class="state-hint">{{ text }}</div>
    <div class="state-action">
      <button type="button" class="state-retry" @click="emit('retry')">
        <app-icon :icon="RotateCw" />
        Повторить
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RotateCw, TriangleAlert } from '@lucide/vue'
import AppIcon from './AppIcon.vue'

// Ошибка загрузки на месте списка: заголовок, текст из errorText и «Повторить» (то же действие загрузки).
// Тост остаётся для действий пользователя, не для загрузки. Кнопка обычная, не NButton: компонент
// показывается из App.vue и попадает в стартовый чанк, а NButton тянул бы за собой ~20 kB
defineProps({
  title: { type: String, required: true },
  text: { type: String, default: '' }
})
const emit = defineEmits(['retry'])
</script>

<style scoped>
.state-error {
  display: grid;
  justify-items: center;
  gap: 4px;
  padding: 48px 20px;
  text-align: center;
  color: var(--color-text-secondary);
}

.state-icon {
  color: var(--color-status-blocked);
}

.state-title {
  margin-top: 4px;
  font-weight: var(--weight-strong);
  color: var(--color-text);
}

.state-hint {
  max-width: 44ch;
}

.state-action {
  margin-top: 12px;
}

.state-retry {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--color-button);
  color: var(--color-on-button);
  font: inherit;
  font-weight: var(--weight-strong);
  cursor: pointer;
  transition: opacity var(--transition);
}

.state-retry:hover {
  opacity: 0.88;
}

.state-retry:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
</style>
