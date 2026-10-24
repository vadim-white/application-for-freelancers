<template>
  <n-drawer
    :show="innerShow"
    @update:show="updateShow"
    size="640px"
    :show-mask="true"
    placement="right"
    class="tasks-drawer"
  >
    <template #header>
      <div style="font-weight: 600">📋 {{ project ? project.name : 'Проект' }}</div>
    </template>

    <div class="drawer-content">
      <div v-if="loading" class="loading-state">
        <n-spin />
        <p style="margin-top: 12px; color: var(--color-text-secondary)">Загрузка задач...</p>
      </div>

      <div v-else>
        <!-- Список задач -->
        <div v-if="tasks.length" class="tasks-section">
          <h3 class="section-title">📝 Текущие задачи</h3>
          <div v-if="!activeTasks.length" class="no-active-tasks">Нет текущих задач</div>
          <div class="tasks-list">
            <div 
              v-for="task in activeTasks" 
              :key="task.id"
              class="task-item"
            >
              <div class="task-main">
                <div class="task-header">
                  <div class="task-title-row">
                    <span class="task-status-badge" :class="`badge-${task.status}`">
                      {{ formatStatus(task.status) }}
                    </span>
                    <div class="task-title">{{ task.title }}</div>
                  </div>
                </div>
                <div v-if="task.description" class="task-desc">{{ task.description }}</div>
              </div>

              <div class="task-actions">
                <n-button 
                  size="small" 
                  type="primary"
                  text
                  @click="openTask(task)"
                >
                  ⏱️
                </n-button>
                <n-button 
                  size="small"
                  type="success"
                  text
                  @click="markDone(task)" 
                  :loading="task.isSaving"
                >
                  ✓
                </n-button>
              </div>
            </div>
          </div>
        </div>

        <!-- Выполненные задачи -->
        <div v-if="doneTasks.length" class="tasks-section">
          <h3 class="section-title section-toggle" @click="showDone = !showDone">
            {{ showDone ? '▾' : '▸' }} ✅ Выполненные ({{ doneTasks.length }})
          </h3>
          <div v-if="showDone" class="tasks-list">
            <div 
              v-for="task in doneTasks" 
              :key="task.id"
              class="task-item task-item-done"
            >
              <div class="task-main">
                <div class="task-header">
                  <div class="task-title-row">
                    <span class="task-status-badge" :class="`badge-${task.status}`">
                      {{ formatStatus(task.status) }}
                    </span>
                    <div class="task-title">{{ task.title }}</div>
                  </div>
                </div>
                <div v-if="task.description" class="task-desc">{{ task.description }}</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="!tasks.length" class="empty-tasks">
          <div style="font-size: 48px; margin-bottom: 12px">📭</div>
          <div style="font-weight: 600">Нет задач</div>
          <div style="color: var(--color-text-secondary); font-size: 13px">
            Создайте первую задачу ниже
          </div>
        </div>

        <!-- Форма добавления задачи -->
        <div class="add-task-section">
          <h3 class="section-title">➕ Добавить задачу</h3>
          <n-form :model="newTask" label-placement="top">
            <n-form-item label="Название задачи" path="title">
              <n-input 
                v-model:value="newTask.title"
                placeholder="Введите название задачи..."
                clearable
              />
            </n-form-item>
            <n-form-item label="Описание" path="description">
              <n-input 
                v-model:value="newTask.description"
                type="textarea"
                placeholder="Описание задачи (опционально)"
                rows="3"
              />
            </n-form-item>
            <div style="display: flex; gap: 8px">
              <n-button 
                type="primary" 
                @click="addTask" 
                :loading="adding"
                style="flex: 1"
              >
                ✓ Добавить задачу
              </n-button>
            </div>
          </n-form>
        </div>
      </div>
    </div>
  </n-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { getTasks, createTask, updateTask } from '../services/tasks'
import { useMessage } from 'naive-ui'

const props = defineProps({
  show: Boolean,
  project: Object
})
const emit = defineEmits(['update:show', 'open-task', 'changed'])

const innerShow = ref(props.show)
watch(() => props.show, (v) => (innerShow.value = v))

function updateShow(v: boolean) {
  innerShow.value = v
  emit('update:show', v)
}

const loading = ref(false)
const tasks = ref<any[]>([])
const activeTasks = computed(() => tasks.value.filter(t => t.status !== 'done'))
const doneTasks = computed(() => tasks.value.filter(t => t.status === 'done'))
const showDone = ref(true)
const message = useMessage()

watch(
  () => props.project,
  async (p) => {
    if (!p) {
      tasks.value = []
      return
    }
    await loadTasks()
  },
  { immediate: true }
)

async function loadTasks() {
  if (!props.project) return
  loading.value = true
  try {
    // страниц пока нет: больше 200 задач проекта панель не покажет
    const data = await getTasks({ project_id: props.project.id, limit: 200, sort: 'created_at' })
    tasks.value = data.items
  } catch (err) {
    console.error(err)
    message.error('Не удалось загрузить задачи')
    tasks.value = []
  } finally {
    loading.value = false
  }
}

defineExpose({ loadTasks })

function openTask(t: any) {
  emit('open-task', t)
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

async function markDone(t: any) {
  if (!t || !t.id) return
  t.isSaving = true
  try {
    const updated = await updateTask(t.id, { status: 'done' })
    tasks.value = tasks.value.map(task => (task.id === t.id ? updated : task))
    message.success('Задача выполнена')
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error('Не удалось завершить задачу')
  } finally {
    t.isSaving = false
  }
}

const newTask = ref({ title: '', description: '' })
const adding = ref(false)

async function addTask() {
  if (!props.project) {
    message.error('Нет проекта')
    return
  }
  if (!newTask.value.title) {
    message.error('Введите название')
    return
  }
  adding.value = true
  try {
    await createTask({
      title: newTask.value.title,
      description: newTask.value.description,
      project_id: props.project.id
    })
    message.success('Задача добавлена')
    newTask.value.title = ''
    newTask.value.description = ''
    await loadTasks()
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error('Ошибка при создании задачи')
  } finally {
    adding.value = false
  }
}
</script>

<style scoped>
.tasks-drawer :deep(.n-drawer__header) {
  background: var(--primary-gradient) !important;
  color: white !important;
}

.drawer-content {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 16px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tasks-section {
  margin-bottom: 32px;
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: rgba(102, 126, 234, 0.05);
  border-radius: 8px;
  border-left: 4px solid var(--color-primary);
  transition: var(--transition-smooth);
}

.task-item:hover {
  background: rgba(102, 126, 234, 0.1);
  transform: translateX(4px);
}

.task-main {
  flex: 1;
  min-width: 0;
}

.task-header {
  margin-bottom: 6px;
}

.task-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.task-status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

.badge-todo {
  background: rgba(79, 172, 254, 0.2);
  color: #4facfe;
}

.badge-in_progress {
  background: rgba(247, 151, 30, 0.2);
  color: #f7971e;
}

.badge-done {
  background: rgba(86, 171, 47, 0.2);
  color: #56ab2f;
}

.badge-blocked {
  background: rgba(235, 87, 87, 0.2);
  color: #eb5757;
}

.section-toggle {
  cursor: pointer;
  user-select: none;
}

.no-active-tasks {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}

.task-item-done {
  opacity: 0.7;
  border-left-color: #56ab2f;
}

.task-item-done .task-title {
  text-decoration: line-through;
}

.task-title {
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
}

.task-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 6px;
  line-height: 1.4;
}

.task-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.empty-tasks {
  text-align: center;
  padding: 40px 20px;
  color: var(--color-text-secondary);
}

.add-task-section {
  padding: 16px;
  background: rgba(102, 126, 234, 0.05);
  border-radius: 8px;
  border: 1px dashed var(--color-border);
}
</style>
