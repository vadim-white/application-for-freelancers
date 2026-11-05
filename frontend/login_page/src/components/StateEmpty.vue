<template>
  <div class="state-empty" :class="{ compact }">
    <app-icon :icon="icon" :size="compact ? 28 : 40" />
    <div class="state-title">{{ title }}</div>
    <div v-if="hint" class="state-hint">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Component, PropType } from 'vue'
import AppIcon from './AppIcon.vue'

// Пустой список: значок, заголовок и подсказка. Кнопок нет (выбор пользователя): рядом уже
// есть «Создать проект» и форма задачи. compact — для пустого раздела внутри панели
defineProps({
  icon: { type: [Object, Function] as PropType<Component>, required: true },
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  compact: Boolean
})
</script>

<style scoped>
.state-empty {
  display: grid;
  justify-items: center;
  gap: 4px;
  padding: 48px 20px;
  text-align: center;
  color: var(--color-text-secondary);
}

.state-empty.compact {
  padding: 16px 12px;
}

.state-title {
  margin-top: 8px;
  font-weight: var(--weight-strong);
  color: var(--color-text);
}

.state-hint {
  max-width: 36ch;
}
</style>
