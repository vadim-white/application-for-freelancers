<template>
  <div class="state-loading" role="status">
    <app-icon class="state-spinner" :icon="LoaderCircle" :size="28" />
    <span>{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { LoaderCircle } from '@lucide/vue'
import AppIcon from './AppIcon.vue'

// Ожидание списка: вращающийся значок с подписью. На дашборде вместо него серые заготовки карточек
defineProps({
  label: { type: String, default: 'Загружаем…' }
})
</script>

<style scoped>
.state-loading {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 48px 20px;
  color: var(--color-text-secondary);
}

.state-spinner {
  color: var(--color-accent);
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .state-spinner {
    animation: none;
  }
}
</style>
