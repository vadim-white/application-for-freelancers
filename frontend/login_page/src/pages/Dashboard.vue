<template>
  <div class="dashboard-content">
    <!-- Идущий таймер -->
    <n-button v-if="timer.entry" type="warning" class="running-timer" @click="openRunningTimer">
      <template #icon><app-icon :icon="Timer" /></template>
      {{ timer.runningTitle }} · {{ timer.formatted }}
    </n-button>

    <div class="fade-in">
      <div class="section-header">
        <h1>Ваши проекты</h1>
      </div>

      <div class="project-filters">
        <n-select
          v-model:value="sort"
          class="project-sort"
          :options="sortOptions"
          style="width: 200px"
          @update:value="onFilterChange"
        />
        <label class="archive-switch">
          <n-switch v-model:value="showArchive" @update:value="onFilterChange" />
          Показать архив
        </label>
      </div>

      <div class="projects-grid">
        <!-- Задачи вне проекта: всегда первая, не зависит от страницы, сортировки и архива -->
        <NoProjectCard :total="noProjectTotal" :preview="noProjectPreview" @open="openNoProject" />
        <!-- Карточки проектов -->
        <ProjectCard
          v-for="p in projects"
          :key="p.id"
          :project="p"
          :busy="busyId === p.id"
          @open="openProject"
          @toggle-archive="toggleArchive"
          @edit="openEditProject"
        />

        <!-- Карточка создания проекта (для всех) -->
        <div class="create-project-card" @click="createProjectOpen">
          <div class="create-project-icon">+</div>
          <div class="create-project-text">
            <div class="create-project-title">Создать проект</div>
            <div class="create-project-desc">Новый проект</div>
          </div>
        </div>

        <!-- Пустое состояние -->
        <div v-if="projects.length === 0" class="empty-state">
          <div style="color: var(--color-text-secondary); margin-bottom: 12px">
            <app-icon :icon="Inbox" :size="40" />
          </div>
          <div style="font-weight: 600; margin-bottom: 4px">Нет проектов</div>
          <div style="color: var(--color-text-secondary)">
            Создайте первый проект — нажмите «Создать проект»
          </div>
        </div>
      </div>

      <n-pagination
        v-if="total > PAGE_SIZE"
        class="projects-pagination"
        :page="page"
        :page-size="PAGE_SIZE"
        :item-count="total"
        @update:page="onPageChange"
      />
    </div>

    <!-- Drawer с задачами -->
    <ProjectTasksDrawer
      ref="tasksDrawer"
      :project="activeProject"
      :show="drawerShow"
      @update:show="drawerShow = $event"
      @open-task="openTaskModal"
      @changed="load"
    />

    <!-- Модал таймера -->
    <TaskTimerModal
      v-if="selectedTask"
      :task="selectedTask"
      :show="taskModalShow"
      @update:show="taskModalShow = $event"
      @changed="onTaskChanged"
    />

    <ProjectEditModal
      :show="editProjectShow"
      :project="editProject"
      @update:show="editProjectShow = $event"
      @saved="load"
    />

    <!-- Модал создания проекта -->
    <CreateProjectModal
      :show="createProjectModal"
      @update:show="createProjectModal = $event"
      @created="onProjectCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { Inbox, Timer } from '@lucide/vue'
import AppIcon from '../components/AppIcon.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useTimerStore } from '../stores/timer'
import {
  NO_PROJECT_ID,
  getProjects,
  getTasks,
  updateProject,
  type ProjectListItem,
  type ProjectRef,
  type Task
} from '../services/tasks'
import { errorText } from '../services/errors'
import ProjectCard from '../components/ProjectCard.vue'
import NoProjectCard from '../components/NoProjectCard.vue'
import ProjectTasksDrawer from '../components/ProjectTasksDrawer.vue'
import TaskTimerModal from '../components/TaskTimerModal.vue'
import CreateProjectModal from '../components/CreateProjectModal.vue'
import ProjectEditModal from '../components/ProjectEditModal.vue'
import { NButton, NPagination, NSelect, NSwitch, useMessage } from 'naive-ui'

const auth = useAuthStore()
const timer = useTimerStore()
const message = useMessage()

const PAGE_SIZE = 20

const sortOptions = [
  { label: 'Сначала новые', value: '-created_at' },
  { label: 'Сначала старые', value: 'created_at' },
  { label: 'Название А–Я', value: 'name' },
  { label: 'Название Я–А', value: '-name' }
]

const projects = ref<ProjectListItem[]>([])
const total = ref(0)
const page = ref(1)
const sort = ref<'created_at' | '-created_at' | 'name' | '-name'>('-created_at')
// выкл. — только активные, вкл. — только архивные
const showArchive = ref(false)
const busyId = ref<number | null>(null)
// карточка «Без проекта»: активные задачи вне проекта — число и первые три
const noProjectTotal = ref(0)
const noProjectPreview = ref<Task[]>([])
// ответ устаревшего запроса не должен затереть более новый
let requestSeq = 0
let noProjectSeq = 0

const drawerShow = ref(false)
const tasksDrawer = ref<InstanceType<typeof ProjectTasksDrawer> | null>(null)
const activeProject = ref<ProjectRef | null>(null)

const selectedTask = ref<Task | null>(null)
const taskModalShow = ref(false)

const createProjectModal = ref(false)

const editProject = ref<ProjectListItem | null>(null)
const editProjectShow = ref(false)

function openEditProject(p: ProjectListItem) {
  editProject.value = p
  editProjectShow.value = true
}

// список проектов и карточка «Без проекта» — два независимых запроса; ошибка одного не мешает другому
async function load() {
  await Promise.all([loadProjects(), loadNoProject()])
}

async function loadNoProject() {
  const seq = ++noProjectSeq
  try {
    const data = await getTasks({
      project_id: NO_PROJECT_ID,
      is_active: true,
      limit: 3,
      sort: 'created_at'
    })
    if (seq !== noProjectSeq) return
    noProjectTotal.value = data.total
    noProjectPreview.value = data.items
  } catch (err) {
    if (seq !== noProjectSeq) return
    message.error(errorText(err, 'Ошибка загрузки задач без проекта'))
  }
}

async function loadProjects() {
  const seq = ++requestSeq
  try {
    // превью задач и счётчик для карточек приходят в том же ответе
    const data = await getProjects({
      is_active: !showArchive.value,
      sort: sort.value,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE
    })
    if (seq !== requestSeq) return
    projects.value = data.items
    total.value = data.total
    // страницы, на которой мы стоим, больше нет (архивировали последний проект на ней)
    const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
    if (page.value > lastPage) {
      page.value = lastPage
      await loadProjects()
    }
  } catch (err) {
    if (seq !== requestSeq) return
    message.error(errorText(err, 'Ошибка загрузки проектов'))
  }
}

// страница и сортировка карточки «Без проекта» не касаются
function onFilterChange() {
  page.value = 1
  loadProjects()
}

function onPageChange(p: number) {
  page.value = p
  loadProjects()
}

async function toggleArchive(p: ProjectListItem) {
  busyId.value = p.id
  try {
    await updateProject(p.id, { is_active: !p.is_active })
    await loadProjects()
  } catch (err) {
    message.error(errorText(err, 'Не удалось изменить проект'))
  } finally {
    busyId.value = null
  }
}

function openNoProject() {
  // новый объект при каждом открытии: панель перечитывает списки
  activeProject.value = { id: NO_PROJECT_ID, name: 'Без проекта' }
  drawerShow.value = true
}

function openProject(p: ProjectListItem) {
  activeProject.value = p
  drawerShow.value = true
}

function openTaskModal(task: Task) {
  selectedTask.value = task
  taskModalShow.value = true
}

function openRunningTimer() {
  const entry = timer.entry
  if (!entry) return
  // задачу могли удалить: окно всё равно открывается, чтобы таймер можно было остановить
  selectedTask.value =
    timer.runningTask?.id === entry.task_id
      ? timer.runningTask
      : // заглушка: задачи нет в runningTask (удалена или ещё не загрузилась), у окна таймера есть
        // только id и название; остальные поля Task не заполнены, status — null, окно это терпит
        ({
          id: entry.task_id,
          title: timer.runningTitle,
          description: null,
          status: null
        } as unknown as Task)
  taskModalShow.value = true
}

function onTaskChanged() {
  load()
  tasksDrawer.value?.loadTasks()
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') timer.refresh().catch(() => {})
}

function createProjectOpen() {
  createProjectModal.value = true
}

function onProjectCreated() {
  load()
}

onMounted(async () => {
  if (!auth.user) {
    await auth.fetchMe()
  }
  document.addEventListener('visibilitychange', onVisibilityChange)
  timer.refresh().catch(() => message.error('Не удалось загрузить таймер'))
  await load()
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.dashboard-content {
  padding: 32px 24px;
}

.section-header {
  margin-bottom: 28px;
}

.running-timer {
  margin-bottom: 20px;
}

.section-header h1 {
  font-size: 28px;
  font-weight: var(--weight-heading);
  color: var(--color-text);
  margin: 0;
}

.project-filters {
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

.projects-pagination {
  margin-top: 20px;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
  animation: slideInUp 0.4s ease-out;
}

.create-project-card {
  background: var(--color-surface);
  border: 2px dashed var(--color-accent);
  border-radius: var(--radius-lg);
  padding: 24px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  transition:
    box-shadow var(--transition),
    transform var(--transition);
  color: var(--color-accent);
}

.create-project-card:hover {
  background: var(--color-accent-soft);
  transform: translateY(-4px);
  box-shadow: var(--shadow-overlay);
}

.create-project-icon {
  font-size: 48px;
  margin-bottom: 12px;
  font-weight: var(--weight-heading);
}

.create-project-text {
  text-align: center;
}

.create-project-title {
  font-weight: var(--weight-strong);
  font-size: 16px;
  margin-bottom: 4px;
}

.create-project-desc {
  font-size: 12px;
  opacity: 0.7;
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  color: var(--color-text-secondary);
}

.fade-in {
  animation: fadeIn 0.3s ease-out;
}

@media (max-width: 1024px) {
  .projects-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 640px) {
  .dashboard-content {
    padding: 20px 16px;
  }

  .projects-grid {
    grid-template-columns: 1fr;
  }
}
</style>
