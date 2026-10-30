<template>
  <component
    :is="icon"
    class="app-icon"
    :size="size"
    :stroke-width="ICON_STROKE"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import type { Component, PropType } from 'vue'

// Все иконки Lucide выводятся через эту обёртку: толщина линии и скрытие от скринридера заданы
// здесь один раз, размер — 16 px по умолчанию (в строке с текстом 14–16 px)
const ICON_STROKE = 2

defineProps({
  icon: { type: [Object, Function] as PropType<Component>, required: true },
  size: { type: Number, default: 16 }
})
</script>

<style scoped>
.app-icon {
  flex-shrink: 0;
  vertical-align: -0.2em;
}
</style>
