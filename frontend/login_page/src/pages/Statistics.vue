<template>
  <div class="statistics-page fade-in">
    <div class="section-header">
      <h1>Статистика пользователей</h1>
      <p style="margin: 8px 0 0 0; color: var(--color-text-secondary)">Сводка по работе команды</p>
    </div>

    <StateLoading v-if="loading" label="Загружаем статистику…" />
    <StateError
      v-else-if="loadError !== null"
      title="Не удалось загрузить статистику"
      :text="loadError"
      @retry="loadStatistics"
    />
    <StateEmpty
      v-else-if="usersStats.length === 0"
      :icon="ChartColumn"
      title="Нет данных"
      hint="Статистика будет доступна после создания задач"
    />

    <n-card v-else class="stats-table-card">
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
              <n-tag type="success" round>{{ formatHoursMinutes(row.avg_seconds_per_task) }}</n-tag>
            </td>
          </tr>
        </tbody>
      </table>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ChartColumn } from '@lucide/vue'
import StateEmpty from '../components/StateEmpty.vue'
import StateError from '../components/StateError.vue'
import StateLoading from '../components/StateLoading.vue'
import { ref, reactive, onMounted } from 'vue'
import { NCard, NTag, useMessage } from 'naive-ui'
import { formatHoursMinutes } from '../stores/timer'
import { errorText } from '../services/errors'
import api from '../services/api'
import type { UserStatistics } from '../services/time'
import { listUsers, type UserItem } from '../services/users'

// Только admin: роль проверяет guard роутера (requiresAdmin), сервер отвечает 403 остальным
const message = useMessage()

const usersStats = ref<UserStatistics[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const statsUsers = reactive<Record<number, UserItem>>({})

async function loadStatistics() {
  loading.value = true
  loadError.value = null
  try {
    const stats = await api.get<UserStatistics[]>('/api/tasks/statistics/users')
    usersStats.value = stats.data
  } catch (err) {
    loadError.value = errorText(err, 'Ошибка загрузки статистики')
    loading.value = false
    return
  }
  await loadStatsUsers(usersStats.value.map((row) => row.user_id))
  loading.value = false
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

onMounted(loadStatistics)
</script>

<style scoped>
.statistics-page {
  padding: 32px 24px;
}

.section-header {
  margin-bottom: 28px;
}

.section-header h1 {
  font-size: 28px;
  font-weight: var(--weight-heading);
  color: var(--color-text);
  margin: 0;
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

@media (max-width: 640px) {
  .statistics-page {
    padding: 20px 16px;
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
