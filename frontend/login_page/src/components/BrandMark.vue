<template>
  <span class="brand-mark" :style="{ width: `${size}px`, height: `${size}px` }">
    <app-icon :icon="Timer" :size="Math.round(size * 0.625)" />
  </span>
</template>

<script setup lang="ts">
import { Timer } from '@lucide/vue'
import AppIcon from './AppIcon.vue'

// Знак J1: иконка timer в квадрате цвета акцента. В шапку встаёт в 3.2.4; тот же знак — public/favicon.svg
defineProps({
  size: { type: Number, default: 32 }
})
</script>

<style scoped>
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: var(--color-on-accent);
}
</style>
