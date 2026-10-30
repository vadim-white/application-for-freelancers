<template>
  <span class="status-shape" :style="{ color: shape.color }">
    <component
      :is="shape.icon"
      :size="STATUS_SIZE"
      :stroke-width="2"
      :fill="shape.filled ? 'currentColor' : 'none'"
      aria-hidden="true"
    />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Circle, CircleCheck, Square } from '@lucide/vue'

// I3: цвет и форма вместе, 14 px. К выполнению — пустое кольцо, в работе — залитый круг,
// выполнена — круг с галочкой, заблокирована — квадрат. Подписи статуса у значка нет: рядом
// всегда видна его текстовая форма (карточка проекта, бейдж в панели), скринридер читает её
const STATUS_SIZE = 14

const shapes = {
  todo: { icon: Circle, filled: false, color: 'var(--color-status-todo)' },
  in_progress: { icon: Circle, filled: true, color: 'var(--color-status-in-progress)' },
  done: { icon: CircleCheck, filled: false, color: 'var(--color-status-done)' },
  blocked: { icon: Square, filled: true, color: 'var(--color-status-blocked)' }
}

const props = defineProps({
  status: { type: String, required: true }
})

// неизвестный статус рисуется как «к выполнению»
const shape = computed(() => shapes[props.status as keyof typeof shapes] ?? shapes.todo)
</script>

<style scoped>
.status-shape {
  display: inline-flex;
  flex-shrink: 0;
}
</style>
