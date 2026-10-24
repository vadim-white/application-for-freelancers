<template>
  <n-card class="no-project-card" @click="emit('open')">
    <template #header>
      <h3 class="card-title">Без проекта</h3>
    </template>

    <div v-if="preview.length" class="tasks-items">
      <div class="tasks-label">
        📋 Задачи <span class="task-count">({{ total }})</span>
      </div>
      <div v-for="t in preview" :key="t.id" class="task-title">{{ t.title }}</div>
    </div>
    <div v-else class="empty-tasks">Нет задач вне проекта</div>

    <template #footer>
      <n-button type="primary" text>Открыть →</n-button>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { TaskPreview } from '../services/tasks'

// preview — первые три активные задачи вне проекта, total — число всех активных
defineProps({
  total: { type: Number, required: true },
  preview: { type: Array as PropType<TaskPreview[]>, required: true }
})
const emit = defineEmits(['open'])
</script>

<style scoped>
.no-project-card {
  cursor: pointer;
  height: 100%;
}
</style>
