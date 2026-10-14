<template>
  <n-card 
    class="project-card"
    @click="open"
  >
    <template #header>
      <div class="card-header">
        <div class="card-title-section">
          <h3 class="card-title">{{ project.name }}</h3>
          <p class="card-description">{{ project.description }}</p>
        </div>
        <n-tag 
          v-if="project.is_active"
          type="success"
          round
          size="small"
        >
          ✓ Активен
        </n-tag>
        <n-tag 
          v-else
          type="warning"
          round
          size="small"
        >
          ⏸ Неактивен
        </n-tag>
      </div>
    </template>

    <div class="card-body">
      <div v-if="tasks && tasks.length" class="tasks-list">
        <div class="tasks-label">
          📋 Задачи <span class="task-count">({{ tasks.length }})</span>
        </div>
        <div class="tasks-items">
          <div 
            v-for="(t, idx) in tasks.slice(0, 3)" 
            :key="t.id"
            class="task-item"
          >
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
        <div style="color: var(--color-text-secondary); font-size: 13px">
          Нет задач в проекте
        </div>
      </div>
    </div>

    <template #footer>
      <div class="card-footer">
        <n-button 
          type="primary" 
          text
          style="flex: 1; text-align: center"
        >
          Открыть → 
        </n-button>
      </div>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  project: { type: Object, required: true },
  tasks: { type: Array, default: () => [] }
})
const emit = defineEmits(['open'])

function open() {
  emit('open', props.project)
}

function formatStatus(status: string): string {
  const statusMap: Record<string, string> = {
    'todo': 'К выполнению',
    'in_progress': 'В работе',
    'done': 'Завершена',
    'blocked': 'Заблокирована'
  }
  return statusMap[status] || status
}
</script>

<style scoped>
.project-card {
  cursor: pointer;
  transition: var(--transition-smooth);
  display: flex;
  flex-direction: column;
  height: 100%;
  border: none !important;
  border-radius: 12px !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
  background: white !important;
  overflow: hidden;
}

.project-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--primary-gradient);
  transition: height 0.3s ease;
}

.project-card:hover {
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.2) !important;
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
  border-bottom: 1px solid var(--color-border);
}

.card-title-section {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
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
  font-weight: 600;
  color: var(--color-text-primary);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.task-count {
  font-weight: 500;
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
  border-radius: 6px;
  background: rgba(102, 126, 234, 0.04);
  transition: background 0.2s ease;
}

.task-item:hover {
  background: rgba(102, 126, 234, 0.08);
}

.task-icon {
  flex: 0 0 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-primary);
  color: white;
  font-size: 10px;
}

.task-info {
  flex: 1;
  min-width: 0;
}

.task-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
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
  background: rgba(86, 171, 47, 0.15);
  color: #56ab2f;
}

.status-in_progress {
  background: rgba(247, 151, 30, 0.15);
  color: #f7971e;
}

.status-todo {
  background: rgba(79, 172, 254, 0.15);
  color: #4facfe;
}

.status-blocked {
  background: rgba(235, 87, 87, 0.15);
  color: #eb5757;
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
  border-top: 1px solid var(--color-border);
  background: rgba(102, 126, 234, 0.02);
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
