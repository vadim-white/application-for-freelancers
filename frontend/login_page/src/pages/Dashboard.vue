<template>
  <n-layout>
    <!-- Header with gradient -->
    <n-layout-header class="dashboard-header">
      <div class="header-content">
        <div class="header-title">
          <h1 style="margin: 0; color: white; font-size: 24px">📊 Проекты</h1>
        </div>

        <div class="header-nav">
          <n-button-group>
            <n-button 
              :type="currentTab === 'tasks' ? 'primary' : 'tertiary'"
              @click="currentTab = 'tasks'"
            >
              📋 Задачи
            </n-button>
            <n-button 
              v-if="isAdmin"
              :type="currentTab === 'statistics' ? 'primary' : 'tertiary'"
              @click="currentTab = 'statistics'"
            >
              📈 Статистика
            </n-button>
            <n-button v-if="isAdmin" type="tertiary" @click="router.push('/users')">
              👥 Пользователи
            </n-button>
          </n-button-group>
        </div>

        <div class="header-user">
          <div class="user-info">
            <n-avatar 
              v-if="auth.user"
              round
              :style="{ background: 'rgba(255,255,255,0.3)' }"
            >
              {{ (auth.user.full_name || auth.user.email).charAt(0).toUpperCase() }}
            </n-avatar>
            <div class="user-text">
              <div class="user-name">{{ auth.user?.full_name || auth.user?.email }}</div>
              <div v-if="isAdmin" class="user-role">👑 Администратор</div>
              <div v-else class="user-role">👤 Пользователь</div>
            </div>
          </div>
          <n-button-group>
            <n-button text @click="toProfile" style="color: rgba(255,255,255,0.8)">
              👤 Профиль
            </n-button>
            <n-button text @click="onLogout" style="color: rgba(255,255,255,0.8)">
              🚪 Выйти
            </n-button>
          </n-button-group>
        </div>
      </div>
    </n-layout-header>

    <n-layout-content class="dashboard-content">
      <!-- Идущий таймер -->
      <n-button
        v-if="timer.entry"
        type="warning"
        class="running-timer"
        @click="openRunningTimer"
      >
        ⏱️ {{ timer.runningTitle }} · {{ timer.formatted }}
      </n-button>

      <!-- TAB: TASKS -->
      <div v-if="currentTab === 'tasks'" class="fade-in">
        <div class="section-header">
          <h2 style="margin: 0">Ваши проекты</h2>
        </div>

        <div class="projects-grid">
          <!-- Карточки проектов -->
          <ProjectCard
            v-for="p in projects"
            :key="p.id"
            :project="p"
            @open="openProject"
          />

          <!-- Карточка создания проекта (для всех) -->
          <div
            class="create-project-card"
            @click="createProjectOpen"
          >
            <div class="create-project-icon">+</div>
            <div class="create-project-text">
              <div class="create-project-title">Создать проект</div>
              <div class="create-project-desc">Новый проект</div>
            </div>
          </div>

          <!-- Пустое состояние -->
          <div v-if="projects.length === 0" class="empty-state">
            <div style="font-size: 48px; margin-bottom: 12px">📭</div>
            <div style="font-weight: 600; margin-bottom: 4px">Нет проектов</div>
            <div style="color: var(--color-text-secondary)">Создайте первый проект — нажмите «Создать проект»</div>
          </div>
        </div>
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
                <th>👤 Пользователь</th>
                <th>🧾 Записей</th>
                <th>📝 Задач</th>
                <th>⏱️ Всего (чч:мм)</th>
                <th>⏱️ Среднее на задачу (чч:мм)</th>
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
                  <n-tag type="success" round>{{ formatHoursMinutes(row.avg_seconds_per_task) }}</n-tag>
                </td>
              </tr>
            </tbody>
          </table>
        </n-card>

        <div v-if="usersStats.length === 0" class="empty-state">
          <div style="font-size: 48px; margin-bottom: 12px">📊</div>
          <div style="font-weight: 600; margin-bottom: 4px">Нет данных</div>
          <div style="color: var(--color-text-secondary)">Статистика будет доступна после создания задач</div>
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

    <!-- Модал создания проекта -->
    <CreateProjectModal
      :show="createProjectModal"
      @update:show="createProjectModal = $event"
      @created="onProjectCreated"
    />
  </n-layout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTimerStore, formatHoursMinutes } from '../stores/timer'
import { getProjects, type ProjectListItem } from '../services/tasks'
import ProjectCard from '../components/ProjectCard.vue'
import ProjectTasksDrawer from '../components/ProjectTasksDrawer.vue'
import TaskTimerModal from '../components/TaskTimerModal.vue'
import CreateProjectModal from '../components/CreateProjectModal.vue'
import { useMessage } from 'naive-ui'
import api from '../services/api'
import { listUsers, type UserItem } from '../services/users'

const router = useRouter()
const auth = useAuthStore()
const timer = useTimerStore()
const message = useMessage()

const isAdmin = computed(() => {
  return auth.user?.role === 'admin'
})

const projects = ref<ProjectListItem[]>([])
const usersStats = ref<any[]>([])
const statsUsers = reactive<Record<number, UserItem>>({})

const currentTab = ref('tasks')

const drawerShow = ref(false)
const tasksDrawer = ref<InstanceType<typeof ProjectTasksDrawer> | null>(null)
const activeProject = ref<any | null>(null)

const selectedTask = ref<any | null>(null)
const taskModalShow = ref(false)

const createProjectModal = ref(false)

async function loadStatistics() {
  try {
    const stats = await api.get('/api/tasks/statistics/users')
    usersStats.value = stats.data
  } catch (err) {
    console.error('Error loading statistics:', err)
    message.error('Ошибка загрузки статистики')
    return
  }
  await loadStatsUsers(usersStats.value.map((row) => row.user_id))
}

// email и имя из auth порциями по 200 (лимит фильтра id); не нашёлся или auth ответил ошибкой — «#id»
async function loadStatsUsers(ids: number[]) {
  for (let i = 0; i < ids.length; i += 200) {
    try {
      const page = await listUsers({ id: ids.slice(i, i + 200), limit: 200 })
      for (const u of page.items) statsUsers[u.id] = u
    } catch (err) {
      console.error('Error loading statistics users:', err)
    }
  }
}

function userLabel(id: number) {
  const u = statsUsers[id]
  if (!u) return `#${id}`
  return u.full_name ? `${u.email} · ${u.full_name}` : u.email
}

async function load() {
  try {
    // новые сверху (порядок API по умолчанию); страниц пока нет — до 200 проектов
    // превью задач и счётчик для карточек приходят в том же ответе
    projects.value = (await getProjects({ limit: 200 })).items
  } catch (err) {
    message.error('Ошибка загрузки проектов')
  }
}

function openProject(p: any) {
  activeProject.value = p
  drawerShow.value = true
}

function openTaskModal(task: any) {
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
      : { id: entry.task_id, title: timer.runningTitle, description: null, status: null }
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

function onProjectCreated(created: any) {
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
  background: var(--primary-gradient) !important;
  padding: 0 !important;
  height: auto !important;
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
  color: white;
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
  font-weight: 600;
  font-size: 14px;
}

.user-role {
  font-size: 12px;
  opacity: 0.8;
}

.dashboard-content {
  padding: 32px 24px !important;
  background: var(--color-bg-light);
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
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
  animation: slideInUp 0.4s ease-out;
}

.create-project-card {
  background: white;
  border: 2px dashed var(--color-primary);
  border-radius: 12px;
  padding: 24px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  transition: var(--transition-smooth);
  color: var(--color-primary);
}

.create-project-card:hover {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
  transform: translateY(-4px);
  box-shadow: 0 8px 20px rgba(102, 126, 234, 0.15);
}

.create-project-icon {
  font-size: 48px;
  margin-bottom: 12px;
  font-weight: 700;
}

.create-project-text {
  text-align: center;
}

.create-project-title {
  font-weight: 600;
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

.stats-table-card {
  border-radius: 12px !important;
}

.stats-table {
  width: 100%;
  border-collapse: collapse;
}

.stats-table thead tr {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
}

.stats-table th {
  padding: 14px 16px;
  text-align: left;
  font-weight: 600;
  color: var(--color-text-primary);
  border-bottom: 2px solid var(--color-border);
}

.stats-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-primary);
}

.stats-table tbody tr:hover {
  background: rgba(102, 126, 234, 0.05);
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
    padding: 20px 16px !important;
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
