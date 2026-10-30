<template>
  <div class="profile-container">
    <!-- Header -->
    <div class="profile-header">
      <div class="header-content">
        <router-link to="/dashboard" class="back-link">
          <app-icon :icon="ArrowLeft" /> Вернуться
        </router-link>
        <h1>Профиль</h1>
      </div>
    </div>

    <!-- Content -->
    <div class="profile-content">
      <!-- User Card -->
      <div class="user-card">
        <div class="user-avatar">
          {{ (auth.user?.full_name || auth.user?.email || '').charAt(0).toUpperCase() }}
        </div>
        <div class="user-info">
          <h2 class="user-name">{{ auth.user?.full_name || 'Пользователь' }}</h2>
          <p class="user-email">{{ auth.user?.email }}</p>
          <div class="user-role-badge" :class="`role-${auth.user?.role}`">
            <span v-if="isAdmin"><app-icon :icon="Crown" :size="14" /> Администратор</span>
            <span v-else><app-icon :icon="User" :size="14" /> Пользователь</span>
          </div>
        </div>
      </div>

      <!-- Capabilities Grid -->
      <div class="capabilities-section">
        <h3 class="section-title">Доступные возможности</h3>

        <!-- User Capabilities -->
        <div v-if="!isAdmin" class="capabilities-grid">
          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="ListPlus" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Создание задач</div>
              <div class="capability-desc">Создавайте новые задачи в проектах</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="CircleCheck" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Отметить выполненной</div>
              <div class="capability-desc">Отмечайте завершенные задачи</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="Timer" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Таймер для задач</div>
              <div class="capability-desc">Отслеживайте время на выполнение</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="FolderOpen" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Просмотр проектов</div>
              <div class="capability-desc">Видите все доступные проекты</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card disabled">
            <div class="capability-icon"><app-icon :icon="FolderPlus" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Создание проектов</div>
              <div class="capability-desc">Только для администраторов</div>
            </div>
            <div class="capability-status"><app-icon :icon="X" :size="14" /> Недоступно</div>
          </div>

          <div class="capability-card disabled">
            <div class="capability-icon"><app-icon :icon="ChartColumn" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Просмотр статистики</div>
              <div class="capability-desc">Только для администраторов</div>
            </div>
            <div class="capability-status"><app-icon :icon="X" :size="14" /> Недоступно</div>
          </div>
        </div>

        <!-- Admin Capabilities -->
        <div v-else class="capabilities-grid">
          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="FolderPlus" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Создание проектов</div>
              <div class="capability-desc">Создавайте новые проекты для команды</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="ChartColumn" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Просмотр статистики</div>
              <div class="capability-desc">Анализируйте работу команды</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="Users" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Управление пользователями</div>
              <div class="capability-desc">Видите активность всех пользователей</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="FolderOpen" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Просмотр всех проектов</div>
              <div class="capability-desc">Полный доступ ко всем проектам</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="Timer" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Таймер для задач</div>
              <div class="capability-desc">Отслеживайте время на выполнение</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon"><app-icon :icon="Pencil" :size="24" /></div>
            <div class="capability-content">
              <div class="capability-title">Редактирование задач</div>
              <div class="capability-desc">Управляйте всеми задачами проектов</div>
            </div>
            <div class="capability-status"><app-icon :icon="Check" :size="14" /> Доступно</div>
          </div>
        </div>
      </div>

      <!-- Info Section -->
      <div class="info-section">
        <h3 class="section-title">Информация</h3>
        <n-card class="info-card">
          <div class="info-row">
            <span class="info-label">Статус:</span>
            <span class="info-value">
              <n-tag type="success" round>В сети</n-tag>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">Роль:</span>
            <span class="info-value">
              <n-tag :type="isAdmin ? 'warning' : 'info'" round>
                <template #icon><app-icon :icon="isAdmin ? Crown : User" :size="14" /></template>
                {{ isAdmin ? 'Администратор' : 'Пользователь' }}
              </n-tag>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">Email:</span>
            <span class="info-value">{{ auth.user?.email }}</span>
          </div>
        </n-card>
      </div>

      <!-- Actions -->
      <div class="actions-section">
        <n-button type="error" style="width: 100%; padding: 12px" size="large" @click="onLogout">
          <template #icon><app-icon :icon="LogOut" /></template>
          Выйти из системы
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeft,
  Check,
  ChartColumn,
  CircleCheck,
  Crown,
  FolderOpen,
  FolderPlus,
  ListPlus,
  LogOut,
  Pencil,
  Timer,
  User,
  Users,
  X
} from '@lucide/vue'
import AppIcon from '../components/AppIcon.vue'
import { computed } from 'vue'
import { NButton, NCard, NTag } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const isAdmin = computed(() => {
  return auth.user?.role === 'admin'
})

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.profile-container {
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
}

.profile-header {
  background: var(--color-surface);
  color: var(--color-text);
  padding: 24px;
  border-bottom: 1px solid var(--color-line);
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  text-decoration: none;
  margin-bottom: 12px;
  transition: color var(--transition);
  font-weight: var(--weight-text);
}

.back-link:hover {
  color: var(--color-text);
}

.header-content h1 {
  font-size: 32px;
  margin: 0;
  font-weight: var(--weight-heading);
}

.profile-content {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  padding: 32px 24px;
}

/* User Card */
.user-card {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg);
  margin-bottom: 32px;
  animation: slideInUp 0.4s ease-out;
}

.user-avatar {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: var(--color-accent);
  color: var(--color-on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  font-weight: var(--weight-heading);
  flex-shrink: 0;
}

.user-info {
  flex: 1;
}

.user-name {
  font-size: 24px;
  font-weight: var(--weight-heading);
  color: var(--color-text);
  margin: 0 0 4px 0;
}

.user-email {
  color: var(--color-text-secondary);
  margin: 0 0 12px 0;
  font-size: 14px;
}

.user-role-badge {
  display: inline-block;
  padding: 8px 16px;
  border-radius: 20px;
  font-weight: var(--weight-strong);
  font-size: 13px;
}

.role-admin {
  background: var(--color-accent-soft);
  color: var(--color-text);
}

.role-user {
  background: var(--color-status-todo-soft);
  color: var(--color-text);
}

/* Capabilities Section */
.capabilities-section {
  margin-bottom: 32px;
}

.section-title {
  font-size: 18px;
  font-weight: var(--weight-heading);
  color: var(--color-text);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  animation: slideInUp 0.5s ease-out;
}

.capability-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--color-accent);
  transition:
    box-shadow var(--transition),
    transform var(--transition);
}

.capability-card:hover:not(.disabled) {
  box-shadow: var(--shadow-overlay);
  transform: translateY(-4px);
}

.capability-card.disabled {
  border-left-color: var(--color-line);
  opacity: 0.7;
  background: var(--color-surface-hover);
}

.capability-icon {
  font-size: 28px;
  flex-shrink: 0;
}

.capability-content {
  flex: 1;
}

.capability-title {
  font-weight: var(--weight-strong);
  color: var(--color-text);
  margin-bottom: 4px;
  font-size: 14px;
}

.capability-desc {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.capability-status {
  color: var(--color-text);
  font-weight: var(--weight-strong);
  font-size: 12px;
  padding: 4px 8px;
  background: var(--color-accent-soft);
  border-radius: 4px;
  white-space: nowrap;
}

.capability-card.disabled .capability-status {
  color: var(--color-text);
  background: var(--color-status-blocked-soft);
}

/* Info Section */
.info-section {
  margin-bottom: 32px;
}

.info-card {
  padding: 20px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-line);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-weight: var(--weight-strong);
  color: var(--color-text);
  font-size: 14px;
}

.info-value {
  color: var(--color-text-secondary);
  font-size: 14px;
}

/* Actions Section */
.actions-section {
  display: flex;
  gap: 12px;
  animation: slideInUp 0.6s ease-out;
}

@media (max-width: 768px) {
  .profile-header {
    padding: 16px;
  }

  .header-content h1 {
    font-size: 24px;
  }

  .profile-content {
    padding: 16px;
  }

  .user-card {
    flex-direction: column;
    text-align: center;
  }

  .user-avatar {
    width: 80px;
    height: 80px;
    font-size: 36px;
  }

  .capabilities-grid {
    grid-template-columns: 1fr;
  }

  .capability-card {
    flex-direction: column;
    text-align: center;
  }

  .capability-icon {
    font-size: 36px;
  }

  .info-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
