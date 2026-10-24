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
      <div class="task-filters">
        <n-select
          v-model:value="sort"
          class="task-sort"
          :options="sortOptions"
          style="width: 220px"
          @update:value="onFilterChange"
        />
        <label class="archive-switch">
          <n-switch v-model:value="showArchive" @update:value="onFilterChange" />
          Показать архив
        </label>
      </div>

      <n-spin :show="loading">
        <!-- Текущие задачи -->
        <div class="tasks-section tasks-current">
          <h3 class="section-title">📝 Текущие задачи ({{ currentTotal }})</h3>
          <div v-if="!currentTasks.length && !loading" class="no-active-tasks">
            {{ showArchive ? 'Нет архивных задач' : 'Нет текущих задач' }}
          </div>
          <div class="tasks-list">
            <div
              v-for="task in currentTasks"
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
                <template v-if="task.is_active">
                  <n-button size="small" type="primary" text @click="openTask(task)">
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
                </template>
                <n-button size="small" text :disabled="task.isSaving" @click="toggleArchive(task)">
                  {{ task.is_active ? 'В архив' : 'Восстановить' }}
                </n-button>
              </div>
            </div>
          </div>
          <n-pagination
            v-if="currentTotal > PAGE_SIZE"
            :page="currentPage"
            :page-size="PAGE_SIZE"
            :item-count="currentTotal"
            @update:page="onCurrentPage"
          />
        </div>

        <!-- Выполненные задачи -->
        <div v-if="doneTotal" class="tasks-section tasks-done">
          <h3 class="section-title section-toggle" @click="showDone = !showDone">
            {{ showDone ? '▾' : '▸' }} ✅ Выполненные ({{ doneTotal }})
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

              <div class="task-actions">
                <n-button size="small" text :disabled="task.isSaving" @click="toggleArchive(task)">
                  {{ task.is_active ? 'В архив' : 'Восстановить' }}
                </n-button>
              </div>
            </div>
          </div>
          <n-pagination
            v-if="showDone && doneTotal > PAGE_SIZE"
            :page="donePage"
            :page-size="PAGE_SIZE"
            :item-count="doneTotal"
            @update:page="onDonePage"
          />
        </div>

        <div v-if="!currentTotal && !doneTotal && !loading && !showArchive" class="empty-tasks">
          <div style="font-size: 48px; margin-bottom: 12px">📭</div>
          <div style="font-weight: 600">Нет задач</div>
          <div style="color: var(--color-text-secondary); font-size: 13px">
            Создайте первую задачу ниже
          </div>
        </div>
      </n-spin>

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
  </n-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  getTasks,
  createTask,
  updateTask,
  type TaskListParams,
  type TaskStatus
} from '../services/tasks'
import { errorText } from '../services/errors'
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

const PAGE_SIZE = 20
const CURRENT_STATUSES: TaskStatus[] = ['todo', 'in_progress', 'blocked']
const DEFAULT_SORT = 'created_at'

const sortOptions = [
  { label: 'Создана ↑ (старые сверху)', value: 'created_at' },
  { label: 'Создана ↓ (новые сверху)', value: '-created_at' },
  { label: 'Изменена ↑', value: 'updated_at' },
  { label: 'Изменена ↓', value: '-updated_at' },
  { label: 'Срок ↑', value: 'deadline' },
  { label: 'Срок ↓', value: '-deadline' },
  { label: 'Название А–Я', value: 'title' },
  { label: 'Название Я–А', value: '-title' },
  { label: 'Статус ↑', value: 'status' },
  { label: 'Статус ↓', value: '-status' }
]

const currentTasks = ref<any[]>([])
const currentTotal = ref(0)
const currentPage = ref(1)
const doneTasks = ref<any[]>([])
const doneTotal = ref(0)
const donePage = ref(1)
const sort = ref<TaskListParams['sort']>(DEFAULT_SORT)
// выкл. — только активные задачи, вкл. — только архивные
const showArchive = ref(false)
const showDone = ref(true)
const loadingCurrent = ref(false)
const loadingDone = ref(false)
const loading = computed(() => loadingCurrent.value || loadingDone.value)
const message = useMessage()

// ответ устаревшего запроса не должен затереть более новый (у каждого списка свой счётчик)
let currentSeq = 0
let doneSeq = 0

watch(
  () => props.project,
  async (p) => {
    // другой проект — списки с начала, с настройками по умолчанию
    sort.value = DEFAULT_SORT
    showArchive.value = false
    currentPage.value = 1
    donePage.value = 1
    if (!p) {
      currentSeq++
      doneSeq++
      currentTasks.value = []
      currentTotal.value = 0
      doneTasks.value = []
      doneTotal.value = 0
      loadingCurrent.value = false
      loadingDone.value = false
      return
    }
    await loadTasks()
  },
  { immediate: true }
)

async function fetchPage(statuses: TaskStatus[], page: number) {
  return getTasks({
    project_id: props.project!.id,
    status: statuses,
    is_active: !showArchive.value,
    sort: sort.value,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE
  })
}

async function loadCurrent() {
  if (!props.project) return
  const seq = ++currentSeq
  loadingCurrent.value = true
  try {
    const data = await fetchPage(CURRENT_STATUSES, currentPage.value)
    if (seq !== currentSeq) return
    currentTasks.value = data.items
    currentTotal.value = data.total
    // страницы, на которой мы стоим, больше нет (задачи ушли в архив или в «Выполненные»)
    const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
    if (currentPage.value > lastPage) {
      currentPage.value = lastPage
      await loadCurrent()
    }
  } catch (err) {
    if (seq !== currentSeq) return
    message.error(errorText(err, 'Не удалось загрузить задачи'))
    currentTasks.value = []
    currentTotal.value = 0
  } finally {
    if (seq === currentSeq) loadingCurrent.value = false
  }
}

async function loadDone() {
  if (!props.project) return
  const seq = ++doneSeq
  loadingDone.value = true
  try {
    const data = await fetchPage(['done'], donePage.value)
    if (seq !== doneSeq) return
    doneTasks.value = data.items
    doneTotal.value = data.total
    const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
    if (donePage.value > lastPage) {
      donePage.value = lastPage
      await loadDone()
    }
  } catch (err) {
    if (seq !== doneSeq) return
    message.error(errorText(err, 'Не удалось загрузить выполненные задачи'))
    doneTasks.value = []
    doneTotal.value = 0
  } finally {
    if (seq === doneSeq) loadingDone.value = false
  }
}

// «Текущие» и «Выполненные» — два запроса со своими страницами
async function loadTasks() {
  await Promise.all([loadCurrent(), loadDone()])
}

function onFilterChange() {
  currentPage.value = 1
  donePage.value = 1
  loadTasks()
}

function onCurrentPage(p: number) {
  currentPage.value = p
  loadCurrent()
}

function onDonePage(p: number) {
  donePage.value = p
  loadDone()
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
    await updateTask(t.id, { status: 'done' })
    message.success('Задача выполнена')
    await loadTasks()
    emit('changed')
  } catch (err) {
    message.error(errorText(err, 'Не удалось завершить задачу'))
  } finally {
    t.isSaving = false
  }
}

async function toggleArchive(t: any) {
  if (!t || !t.id) return
  t.isSaving = true
  try {
    await updateTask(t.id, { is_active: !t.is_active })
    await loadTasks()
    // счётчик и превью карточки считают только активные задачи
    emit('changed')
  } catch (err) {
    message.error(errorText(err, 'Не удалось изменить задачу'))
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
  // сервер обрезает пробелы: название из одних пробелов — 422
  if (!newTask.value.title.trim()) {
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
    message.error(errorText(err, 'Ошибка при создании задачи'))
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

.task-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.archive-switch {
  display: flex;
  align-items: center;
  gap: 8px;
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
