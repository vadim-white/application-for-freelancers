<template>
  <div class="profile-container">
    <!-- Header -->
    <div class="profile-header">
      <div class="header-content">
        <router-link to="/dashboard" class="back-link"> ← Вернуться </router-link>
        <h1>👤 Профиль</h1>
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
            <span v-if="isAdmin">👑 Администратор</span>
            <span v-else>👤 Пользователь</span>
          </div>
        </div>
      </div>

      <!-- Capabilities Grid -->
      <div class="capabilities-section">
        <h3 class="section-title">📋 Доступные возможности</h3>

        <!-- User Capabilities -->
        <div v-if="!isAdmin" class="capabilities-grid">
          <div class="capability-card">
            <div class="capability-icon">📝</div>
            <div class="capability-content">
              <div class="capability-title">Создание задач</div>
              <div class="capability-desc">Создавайте новые задачи в проектах</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">✓</div>
            <div class="capability-content">
              <div class="capability-title">Отметить выполненной</div>
              <div class="capability-desc">Отмечайте завершенные задачи</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">⏱️</div>
            <div class="capability-content">
              <div class="capability-title">Таймер для задач</div>
              <div class="capability-desc">Отслеживайте время на выполнение</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">📊</div>
            <div class="capability-content">
              <div class="capability-title">Просмотр проектов</div>
              <div class="capability-desc">Видите все доступные проекты</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card disabled">
            <div class="capability-icon">➕</div>
            <div class="capability-content">
              <div class="capability-title">Создание проектов</div>
              <div class="capability-desc">Только для администраторов</div>
            </div>
            <div class="capability-status">✗ Недоступно</div>
          </div>

          <div class="capability-card disabled">
            <div class="capability-icon">📈</div>
            <div class="capability-content">
              <div class="capability-title">Просмотр статистики</div>
              <div class="capability-desc">Только для администраторов</div>
            </div>
            <div class="capability-status">✗ Недоступно</div>
          </div>
        </div>

        <!-- Admin Capabilities -->
        <div v-else class="capabilities-grid">
          <div class="capability-card">
            <div class="capability-icon">➕</div>
            <div class="capability-content">
              <div class="capability-title">Создание проектов</div>
              <div class="capability-desc">Создавайте новые проекты для команды</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">📈</div>
            <div class="capability-content">
              <div class="capability-title">Просмотр статистики</div>
              <div class="capability-desc">Анализируйте работу команды</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">👥</div>
            <div class="capability-content">
              <div class="capability-title">Управление пользователями</div>
              <div class="capability-desc">Видите активность всех пользователей</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">📊</div>
            <div class="capability-content">
              <div class="capability-title">Просмотр всех проектов</div>
              <div class="capability-desc">Полный доступ ко всем проектам</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">⏱️</div>
            <div class="capability-content">
              <div class="capability-title">Таймер для задач</div>
              <div class="capability-desc">Отслеживайте время на выполнение</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>

          <div class="capability-card">
            <div class="capability-icon">✓</div>
            <div class="capability-content">
              <div class="capability-title">Редактирование задач</div>
              <div class="capability-desc">Управляйте всеми задачами проектов</div>
            </div>
            <div class="capability-status">✓ Доступно</div>
          </div>
        </div>
      </div>

      <!-- Info Section -->
      <div class="info-section">
        <h3 class="section-title">ℹ️ Информация</h3>
        <n-card class="info-card">
          <div class="info-row">
            <span class="info-label">Статус:</span>
            <span class="info-value">
              <n-tag type="success" round>🟢 В сети</n-tag>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">Роль:</span>
            <span class="info-value">
              <n-tag :type="isAdmin ? 'warning' : 'info'" round>
                {{ isAdmin ? '👑 Администратор' : '👤 Пользователь' }}
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
          🚪 Выйти из системы
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
  background: var(--color-bg-light);
  display: flex;
  flex-direction: column;
}

.profile-header {
  background: var(--primary-gradient);
  color: white;
  padding: 24px;
  box-shadow: 0 4px 12px var(--color-shadow);
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
  color: rgba(255, 255, 255, 0.8);
  text-decoration: none;
  margin-bottom: 12px;
  transition: color 0.3s ease;
  font-weight: 500;
}

.back-link:hover {
  color: white;
}

.header-content h1 {
  font-size: 32px;
  margin: 0;
  font-weight: 700;
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
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px var(--color-shadow);
  margin-bottom: 32px;
  animation: slideInUp 0.4s ease-out;
}

.user-avatar {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: var(--primary-gradient);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-info {
  flex: 1;
}

.user-name {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
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
  font-weight: 600;
  font-size: 13px;
}

.role-admin {
  background: linear-gradient(135deg, rgba(247, 151, 30, 0.2) 0%, rgba(255, 210, 0, 0.2) 100%);
  color: #f7971e;
}

.role-user {
  background: linear-gradient(135deg, rgba(79, 172, 254, 0.2) 0%, rgba(0, 242, 254, 0.2) 100%);
  color: #4facfe;
}

/* Capabilities Section */
.capabilities-section {
  margin-bottom: 32px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
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
  background: white;
  border-radius: 12px;
  border-left: 4px solid var(--color-primary);
  box-shadow: 0 4px 12px var(--color-shadow);
  transition: var(--transition-smooth);
}

.capability-card:hover:not(.disabled) {
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.2);
  transform: translateY(-4px);
}

.capability-card.disabled {
  border-left-color: var(--color-border);
  opacity: 0.7;
  background: rgba(0, 0, 0, 0.02);
}

.capability-icon {
  font-size: 28px;
  flex-shrink: 0;
}

.capability-content {
  flex: 1;
}

.capability-title {
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
  font-size: 14px;
}

.capability-desc {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.capability-status {
  color: #56ab2f;
  font-weight: 600;
  font-size: 12px;
  padding: 4px 8px;
  background: rgba(86, 171, 47, 0.1);
  border-radius: 4px;
  white-space: nowrap;
}

.capability-card.disabled .capability-status {
  color: #f5576c;
  background: rgba(245, 87, 108, 0.1);
}

/* Info Section */
.info-section {
  margin-bottom: 32px;
}

.info-card {
  background: white !important;
  border: none !important;
  border-radius: 12px !important;
  box-shadow: 0 4px 12px var(--color-shadow) !important;
  padding: 20px !important;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-weight: 600;
  color: var(--color-text-primary);
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
