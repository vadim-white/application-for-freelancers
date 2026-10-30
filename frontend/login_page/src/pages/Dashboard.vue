<template>
  <n-layout>
    <n-layout-header class="dashboard-header">
      <div class="header-content">
        <div class="header-title">
          <h1 style="margin: 0; color: var(--color-text); font-size: 24px">Проекты</h1>
        </div>

        <div class="header-nav">
          <n-button-group>
            <n-button
              :type="currentTab === 'tasks' ? 'primary' : 'tertiary'"
              @click="currentTab = 'tasks'"
            >
              <template #icon><app-icon :icon="ListChecks" /></template>
              Задачи
            </n-button>
            <n-button
              v-if="isAdmin"
              :type="currentTab === 'statistics' ? 'primary' : 'tertiary'"
              @click="currentTab = 'statistics'"
            >
              <template #icon><app-icon :icon="ChartColumn" /></template>
              Статистика
            </n-button>
            <n-button v-if="isAdmin" type="tertiary" @click="router.push('/users')">
              <template #icon><app-icon :icon="Users" /></template>
              Пользователи
            </n-button>
          </n-button-group>
        </div>

        <div class="header-user">
          <div class="user-info">
            <n-avatar
              v-if="auth.user"
              round
              :style="{ background: 'var(--color-accent-soft)', color: 'var(--color-text)' }"
            >
              {{ (auth.user.full_name || auth.user.email).charAt(0).toUpperCase() }}
            </n-avatar>
            <div class="user-text">
              <div class="user-name">{{ auth.user?.full_name || auth.user?.email }}</div>
              <div v-if="isAdmin" class="user-role">
                <app-icon :icon="Crown" :size="14" /> Администратор
              </div>
              <div v-else class="user-role"><app-icon :icon="User" :size="14" /> Пользователь</div>
            </div>
          </div>
          <n-button-group>
            <n-button text style="color: var(--color-text-secondary)" @click="toProfile">
              <template #icon><app-icon :icon="User" /></template>
              Профиль
            </n-button>
            <n-button text style="color: var(--color-text-secondary)" @click="onLogout">
              <template #icon><app-icon :icon="LogOut" /></template>
              Выйти
            </n-button>
          </n-button-group>
        </div>
      </div>
    </n-layout-header>

    <n-layout-content class="dashboard-content">
      <!-- Идущий таймер -->
      <n-button v-if="timer.entry" type="warning" class="running-timer" @click="openRunningTimer">
        <template #icon><app-icon :icon="Timer" /></template>
        {{ timer.runningTitle }} · {{ timer.formatted }}
      </n-button>

      <!-- TAB: TASKS -->
      <div v-if="currentTab === 'tasks'" class="fade-in">
        <div class="section-header">
          <h2 style="margin: 0">Ваши проекты</h2>
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
          <NoProjectCard
            :total="noProjectTotal"
            :preview="noProjectPreview"
            @open="openNoProject"
          />
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

      <!-- TAB: STATISTICS -->
      <div v-if="currentTab === 'statistics' && isAdmin" class="fade-in">
        <div class="section-header">
          <h2 style="margin: 0">Статистика пользователей</h2>
          <p style="margin: 8px 0 0 0; color: var(--color-text-secondary)">
            Сводка по работе команды
          </p>
        </div>

        <n-card class="stats-table-card">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Записей</th>
                <th>Задач</th>
                <th>Всего (чч:мм)</th>
                <th>Среднее на задачу (чч:мм)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in usersStats" :key="row.user_id">
                <td>{{ userLabel(row.user_id) }}</td>
                <td class="text-center">{{ row.entries_count }}</td>
                <td class="text-center">
                  <n-tag type="info" round>{{ row.tasks_count }}</n-tag>
                </td>
                <td class="text-center">
                  <n-tag type="success" round>{{ formatHoursMinutes(row.total_seconds) }}</n-tag>
                </td>
                <td class="text-center">
                  <n-tag type="success" round>{{
                    formatHoursMinutes(row.avg_seconds_per_task)
                  }}</n-tag>
                </td>
              </tr>
            </tbody>
          </table>
        </n-card>

        <div v-if="usersStats.length === 0" class="empty-state">
          <div style="color: var(--color-text-secondary); margin-bottom: 12px">
            <app-icon :icon="ChartColumn" :size="40" />
          </div>
          <div style="font-weight: 600; margin-bottom: 4px">Нет данных</div>
          <div style="color: var(--color-text-secondary)">
            Статистика будет доступна после создания задач
          </div>
        </div>
      </div>
    </n-layout-content>

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
  </n-layout>
</template>

<script setup lang="ts">
import { ChartColumn, Crown, Inbox, ListChecks, LogOut, Timer, User, Users } from '@lucide/vue'
import AppIcon from '../components/AppIcon.vue'
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTimerStore, formatHoursMinutes } from '../stores/timer'
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
import {
  NAvatar,
  NButton,
  NButtonGroup,
  NCard,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NPagination,
  NSelect,
  NSwitch,
  NTag,
  useMessage
} from 'naive-ui'
import api from '../services/api'
import type { UserStatistics } from '../services/time'
import { listUsers, type UserItem } from '../services/users'

const router = useRouter()
const auth = useAuthStore()
const timer = useTimerStore()
const message = useMessage()

const isAdmin = computed(() => {
  return auth.user?.role === 'admin'
})

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
const usersStats = ref<UserStatistics[]>([])
const statsUsers = reactive<Record<number, UserItem>>({})

const currentTab = ref('tasks')

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

async function loadStatistics() {
  try {
    const stats = await api.get<UserStatistics[]>('/api/tasks/statistics/users')
    usersStats.value = stats.data
  } catch {
    message.error('Ошибка загрузки статистики')
    return
  }
  await loadStatsUsers(usersStats.value.map((row) => row.user_id))
}

// email и имя из auth порциями по 200 (лимит фильтра id); не нашёлся или auth ответил ошибкой — «#id».
// Об ошибке — одно предупреждение на всю загрузку, а не на каждую порцию
async function loadStatsUsers(ids: number[]) {
  let failed = false
  for (let i = 0; i < ids.length; i += 200) {
    try {
      const page = await listUsers({ id: ids.slice(i, i + 200), limit: 200 })
      for (const u of page.items) statsUsers[u.id] = u
    } catch {
      failed = true
    }
  }
  if (failed) message.warning('Не удалось загрузить email пользователей, показаны номера')
}

function userLabel(id: number) {
  const u = statsUsers[id]
  if (!u) return `#${id}`
  return u.full_name ? `${u.email} · ${u.full_name}` : u.email
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

function onLogout() {
  auth.logout()
  window.location.href = '/login'
}

function toProfile() {
  router.push('/profile')
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
  if (isAdmin.value) {
    await loadStatistics()
  }
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.dashboard-header {
  padding: 0;
  height: auto;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  gap: 24px;
}

.header-title {
  flex: 0 0 auto;
  min-width: 200px;
}

.header-nav {
  flex: 1;
  display: flex;
  justify-content: center;
}

.header-user {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--color-text);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-text {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: var(--weight-strong);
  font-size: 14px;
}

.user-role {
  font-size: 12px;
  opacity: 0.8;
}

.dashboard-content {
  padding: 32px 24px;
  background: var(--color-bg);
  min-height: calc(100vh - 80px);
}

.section-header {
  margin-bottom: 28px;
}

.running-timer {
  margin-bottom: 20px;
}

.section-header h2 {
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

.stats-table {
  width: 100%;
  border-collapse: collapse;
}

.stats-table thead tr {
  background: var(--color-surface-hover);
}

.stats-table th {
  padding: 14px 16px;
  text-align: left;
  font-weight: var(--weight-strong);
  color: var(--color-text);
  border-bottom: 2px solid var(--color-line);
}

.stats-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-line);
  color: var(--color-text);
}

.stats-table tbody tr:hover {
  background: var(--color-surface-hover);
}

.text-center {
  text-align: center;
}

.fade-in {
  animation: fadeIn 0.3s ease-out;
}

@media (max-width: 1024px) {
  .header-content {
    flex-wrap: wrap;
    padding: 12px 16px;
  }

  .header-title {
    flex: 1 1 100%;
    min-width: auto;
    margin-bottom: 8px;
  }

  .header-nav {
    flex: 1 1 auto;
  }

  .header-user {
    flex: 1 1 auto;
    justify-content: flex-end;
  }

  .projects-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 640px) {
  .dashboard-content {
    padding: 20px 16px;
  }

  .header-content {
    flex-direction: column;
    gap: 12px;
  }

  .header-user {
    flex: 1 1 100%;
    justify-content: space-between;
    order: -1;
  }

  .user-text {
    display: none;
  }

  .projects-grid {
    grid-template-columns: 1fr;
  }

  .stats-table {
    font-size: 12px;
  }

  .stats-table th,
  .stats-table td {
    padding: 8px 10px;
  }
}
</style>
