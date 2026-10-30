<template>
  <n-drawer
    :show="innerShow"
    size="640px"
    :show-mask="true"
    placement="right"
    class="tasks-drawer"
    @update:show="updateShow"
  >
    <!-- n-drawer сам слот header не выводит: заголовок — в n-drawer-content -->
    <n-drawer-content :native-scrollbar="false" closable>
      <template #header>
        <div class="drawer-title" style="font-weight: 600">
          {{ project ? project.name : 'Проект' }}
        </div>
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
            <h3 class="section-title">Текущие задачи ({{ currentTotal }})</h3>
            <div v-if="!currentTasks.length && !loading" class="no-active-tasks">
              {{ showArchive ? 'Нет архивных задач' : 'Нет текущих задач' }}
            </div>
            <div class="tasks-list">
              <div v-for="task in currentTasks" :key="task.id" class="task-item">
                <div class="task-main">
                  <div class="task-header">
                    <div class="task-title-row">
                      <span class="task-status-badge" :class="`badge-${task.status}`">
                        <status-icon :status="task.status" />
                        {{ formatStatus(task.status) }}
                      </span>
                      <div class="task-title">{{ task.title }}</div>
                    </div>
                  </div>
                  <div v-if="task.description" class="task-desc">{{ task.description }}</div>
                  <div v-if="task.deadline" class="task-deadline">
                    Срок: {{ formatDeadline(task.deadline) }}
                  </div>
                </div>

                <div class="task-actions">
                  <template v-if="task.is_active">
                    <n-button
                      size="small"
                      type="primary"
                      text
                      aria-label="Открыть таймер"
                      title="Открыть таймер"
                      @click="openTask(task)"
                    >
                      <app-icon :icon="Timer" />
                    </n-button>
                    <n-button
                      size="small"
                      type="success"
                      text
                      aria-label="Отметить выполненной"
                      title="Отметить выполненной"
                      :loading="task.isSaving"
                      @click="markDone(task)"
                    >
                      <app-icon :icon="Check" />
                    </n-button>
                  </template>
                  <n-button size="small" text :disabled="task.isSaving" @click="openEdit(task)">
                    Изменить
                  </n-button>
                  <n-button
                    size="small"
                    text
                    :disabled="task.isSaving"
                    @click="toggleArchive(task)"
                  >
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
              <app-icon :icon="showDone ? ChevronDown : ChevronRight" /> Выполненные ({{
                doneTotal
              }})
            </h3>
            <div v-if="showDone" class="tasks-list">
              <div v-for="task in doneTasks" :key="task.id" class="task-item task-item-done">
                <div class="task-main">
                  <div class="task-header">
                    <div class="task-title-row">
                      <span class="task-status-badge" :class="`badge-${task.status}`">
                        <status-icon :status="task.status" />
                        {{ formatStatus(task.status) }}
                      </span>
                      <div class="task-title">{{ task.title }}</div>
                    </div>
                  </div>
                  <div v-if="task.description" class="task-desc">{{ task.description }}</div>
                  <div v-if="task.deadline" class="task-deadline">
                    Срок: {{ formatDeadline(task.deadline) }}
                  </div>
                </div>

                <div class="task-actions">
                  <n-button size="small" text :disabled="task.isSaving" @click="openEdit(task)">
                    Изменить
                  </n-button>
                  <n-button
                    size="small"
                    text
                    :disabled="task.isSaving"
                    @click="toggleArchive(task)"
                  >
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
            <div style="color: var(--color-text-secondary); margin-bottom: 12px">
              <app-icon :icon="Inbox" :size="40" />
            </div>
            <div style="font-weight: 600">Нет задач</div>
            <div style="color: var(--color-text-secondary); font-size: 13px">
              Создайте первую задачу ниже
            </div>
          </div>
        </n-spin>

        <!-- Форма добавления задачи -->
        <div class="add-task-section">
          <h3 class="section-title">Добавить задачу</h3>
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
              <n-button type="primary" :loading="adding" style="flex: 1" @click="addTask">
                <template #icon><app-icon :icon="Check" /></template>
                Добавить задачу
              </n-button>
            </div>
          </n-form>
        </div>
      </div>
    </n-drawer-content>

    <TaskEditModal
      :show="editShow"
      :task="editTask"
      @update:show="editShow = $event"
      @saved="onTaskSaved"
    />
  </n-drawer>
</template>

<script setup lang="ts">
import { Check, ChevronDown, ChevronRight, Inbox, Timer } from '@lucide/vue'
import AppIcon from './AppIcon.vue'
import StatusIcon from './StatusIcon.vue'
import { ref, computed, watch, type PropType } from 'vue'
import {
  NO_PROJECT_ID,
  getTasks,
  createTask,
  updateTask,
  type ProjectRef,
  type Task,
  type TaskListParams,
  type TaskStatus
} from '../services/tasks'
import { errorText } from '../services/errors'
import { useTimerStore } from '../stores/timer'
import TaskEditModal from './TaskEditModal.vue'
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NPagination,
  NSelect,
  NSpin,
  NSwitch,
  useMessage
} from 'naive-ui'

// project — проект или { id: NO_PROJECT_ID, name: 'Без проекта' }: задачи вне проекта
const props = defineProps({
  show: Boolean,
  project: { type: Object as PropType<ProjectRef | null>, default: null }
})
const emit = defineEmits(['update:show', 'open-task', 'changed'])

// isSaving — клиентский флаг на время запроса (кнопки «Отметить выполненной» и архива), в API его нет
type DrawerTask = Task & { isSaving?: boolean }

const innerShow = ref(props.show)
watch(
  () => props.show,
  (v) => (innerShow.value = v)
)

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

const currentTasks = ref<DrawerTask[]>([])
const currentTotal = ref(0)
const currentPage = ref(1)
const doneTasks = ref<DrawerTask[]>([])
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
const timer = useTimerStore()

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

function openTask(t: DrawerTask) {
  emit('open-task', t)
}

function formatDeadline(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

const editTask = ref<Task | null>(null)
const editShow = ref(false)

function openEdit(t: Task) {
  editTask.value = t
  editShow.value = true
}

// задача, вынесенная в другой проект или из проекта, пропадает из этой панели
async function onTaskSaved(updated: Task) {
  await loadTasks()
  // счётчик и превью карточки; название идущей задачи — в индикаторе таймера
  emit('changed')
  void timer.reloadRunningTask(updated.id)
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

async function markDone(t: DrawerTask) {
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

async function toggleArchive(t: DrawerTask) {
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
      // вне проекта — без project_id
      project_id: props.project!.id === NO_PROJECT_ID ? undefined : props.project!.id
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
  font-weight: var(--weight-strong);
  color: var(--color-text);
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
  background: var(--color-surface-hover);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-accent);
  transition:
    background var(--transition),
    transform var(--transition);
}

.task-item:hover {
  background: var(--color-accent-soft);
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: var(--weight-strong);
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

.badge-todo {
  background: var(--color-status-todo-soft);
  color: var(--color-text);
}

.badge-in_progress {
  background: var(--color-status-in-progress-soft);
  color: var(--color-text);
}

.badge-done {
  background: var(--color-status-done-soft);
  color: var(--color-text);
}

.badge-blocked {
  background: var(--color-status-blocked-soft);
  color: var(--color-text);
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
  border-left-color: var(--color-status-done);
}

.task-item-done .task-title {
  text-decoration: line-through;
}

.task-title {
  font-weight: var(--weight-strong);
  color: var(--color-text);
  flex: 1;
}

.task-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 6px;
  line-height: 1.4;
}

.task-deadline {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 4px;
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
  background: var(--color-surface-hover);
  border-radius: var(--radius-md);
  border: 1px dashed var(--color-line);
}
</style>
