<template>
  <n-card class="project-card" @click="open">
    <template #header>
      <div class="card-header">
        <div class="card-title-section">
          <h3 class="card-title">{{ project.name }}</h3>
          <p class="card-description">{{ project.description }}</p>
        </div>
        <n-tag v-if="project.is_active" type="success" round size="small"> ✓ Активен </n-tag>
        <n-tag v-else type="warning" round size="small"> ⏸ Неактивен </n-tag>
      </div>
    </template>

    <div class="card-body">
      <div v-if="project.tasks_preview.length" class="tasks-list">
        <div class="tasks-label">
          📋 Задачи <span class="task-count">({{ project.tasks_count }})</span>
        </div>
        <div class="tasks-items">
          <div v-for="t in project.tasks_preview" :key="t.id" class="task-item">
            <div class="task-icon">
              <span v-if="t.status === 'done'" class="status-icon">✓</span>
              <span v-else-if="t.status === 'in_progress'" class="status-icon">⟳</span>
              <span v-else class="status-icon">○</span>
            </div>
            <div class="task-info">
              <div class="task-title">{{ t.title }}</div>
              <div class="task-status" :class="`status-${t.status}`">
                {{ formatStatus(t.status) }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-tasks">
        <div style="font-size: 24px; margin-bottom: 8px">📭</div>
        <div style="color: var(--color-text-secondary); font-size: 13px">Нет задач в проекте</div>
      </div>
    </div>

    <template #footer>
      <div class="card-footer">
        <n-button type="primary" text style="flex: 1; text-align: center"> Открыть → </n-button>
        <n-button size="small" :disabled="busy" @click.stop="emit('edit', project)">
          Изменить
        </n-button>
        <n-button size="small" :disabled="busy" @click.stop="emit('toggle-archive', project)">
          {{ project.is_active ? 'В архив' : 'Восстановить' }}
        </n-button>
      </div>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import { defineProps, defineEmits, type PropType } from 'vue'
import { NButton, NCard, NTag } from 'naive-ui'
import type { ProjectListItem } from '../services/tasks'

// tasks_preview — первые три активные задачи, tasks_count — число всех активных
const props = defineProps({
  project: { type: Object as PropType<ProjectListItem>, required: true },
  // идёт смена архивного флага этого проекта
  busy: { type: Boolean, default: false }
})
const emit = defineEmits(['open', 'toggle-archive', 'edit'])

function open() {
  emit('open', props.project)
}

function formatStatus(status: string): string {
  const statusMap: Record<string, string> = {
    todo: 'К выполнению',
    in_progress: 'В работе',
    done: 'Завершена',
    blocked: 'Заблокирована'
  }
  return statusMap[status] || status
}
</script>

<style scoped>
.project-card {
  cursor: pointer;
  transition:
    box-shadow var(--transition),
    transform var(--transition);
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.project-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--color-accent);
  transition: height var(--transition);
}

.project-card:hover {
  box-shadow: var(--shadow-overlay);
  transform: translateY(-4px);
}

.project-card:hover::before {
  height: 6px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid var(--color-line);
}

.card-title-section {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: var(--weight-strong);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-description {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-body {
  flex: 1;
  padding: 16px;
  min-height: 120px;
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tasks-label {
  font-weight: var(--weight-strong);
  color: var(--color-text);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.task-count {
  font-weight: var(--weight-text);
  color: var(--color-text-secondary);
}

.tasks-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px;
  border-radius: var(--radius-md);
  background: var(--color-surface-hover);
  transition: background var(--transition);
}

.task-item:hover {
  background: var(--color-accent-soft);
}

.task-icon {
  flex: 0 0 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: var(--weight-strong);
}

.status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-accent);
  color: var(--color-on-accent);
  font-size: 10px;
}

.task-info {
  flex: 1;
  min-width: 0;
}

.task-title {
  font-size: 13px;
  font-weight: var(--weight-text);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-status {
  font-size: 11px;
  margin-top: 2px;
  padding: 2px 6px;
  border-radius: 4px;
  width: fit-content;
}

.status-done {
  background: var(--color-status-done-soft);
  color: var(--color-text);
}

.status-in_progress {
  background: var(--color-status-in-progress-soft);
  color: var(--color-text);
}

.status-todo {
  background: var(--color-status-todo-soft);
  color: var(--color-text);
}

.status-blocked {
  background: var(--color-status-blocked-soft);
  color: var(--color-text);
}

.empty-tasks {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100px;
  text-align: center;
  color: var(--color-text-secondary);
}

.card-footer {
  display: flex;
  padding: 12px 16px;
  border-top: 1px solid var(--color-line);
  background: var(--color-surface-hover);
}

@media (max-width: 640px) {
  .project-card {
    min-height: auto;
  }

  .card-header {
    flex-direction: column;
    gap: 8px;
  }

  .card-title {
    font-size: 15px;
  }

  .card-body {
    min-height: auto;
  }
}
</style>
