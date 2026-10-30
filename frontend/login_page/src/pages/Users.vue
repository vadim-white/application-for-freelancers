<template>
  <div class="users-page">
    <router-link to="/dashboard"><app-icon :icon="ArrowLeft" /> К проектам</router-link>
    <h1>Пользователи</h1>

    <div class="filters">
      <n-input
        v-model:value="search"
        clearable
        placeholder="Поиск по email или имени"
        @update:value="onSearchInput"
      />
      <n-select
        v-model:value="roleFilter"
        :options="roleOptions"
        style="width: 160px"
        @update:value="onFilterChange"
      />
      <n-select
        v-model:value="activeFilter"
        :options="activeOptions"
        style="width: 160px"
        @update:value="onFilterChange"
      />
    </div>

    <n-spin :show="loading">
      <table class="users-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Имя</th>
            <th>Роль</th>
            <th>Активен</th>
            <th>Дата регистрации</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in items" :key="u.id" class="user-row">
            <td>{{ u.email }}</td>
            <td>{{ u.full_name || '—' }}</td>
            <td>{{ u.role === 'admin' ? 'admin' : 'user' }}</td>
            <td>{{ u.is_active ? 'да' : 'нет' }}</td>
            <td>{{ formatDate(u.created_at) }}</td>
            <td>
              <template v-if="u.id !== auth.user?.id">
                <n-button
                  size="small"
                  :disabled="busyId === u.id"
                  @click="change(u, { role: u.role === 'admin' ? 'user' : 'admin' })"
                >
                  {{ u.role === 'admin' ? 'Сделать user' : 'Сделать admin' }}
                </n-button>
                <n-button
                  size="small"
                  :disabled="busyId === u.id"
                  @click="change(u, { is_active: !u.is_active })"
                >
                  {{ u.is_active ? 'Отключить' : 'Включить' }}
                </n-button>
              </template>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
            <td colspan="6">Никого не найдено</td>
          </tr>
        </tbody>
      </table>
    </n-spin>

    <n-pagination
      v-if="total > PAGE_SIZE"
      :page="page"
      :page-size="PAGE_SIZE"
      :item-count="total"
      @update:page="onPageChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import AppIcon from '../components/AppIcon.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { NButton, NInput, NPagination, NSelect, NSpin, useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { errorText } from '../services/errors'
import { listUsers, updateUser, type UserItem, type UserRole } from '../services/users'

const PAGE_SIZE = 20
const SEARCH_DELAY_MS = 300

const auth = useAuthStore()
const message = useMessage()

const roleOptions = [
  { label: 'Любая роль', value: 'all' },
  { label: 'admin', value: 'admin' },
  { label: 'user', value: 'user' }
]
const activeOptions = [
  { label: 'Любой статус', value: 'all' },
  { label: 'Активные', value: 'true' },
  { label: 'Отключённые', value: 'false' }
]

const items = ref<UserItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const busyId = ref<number | null>(null)

const search = ref('')
const roleFilter = ref('all')
const activeFilter = ref('all')

let searchTimer: ReturnType<typeof setTimeout> | undefined
// ответ устаревшего запроса не должен затереть более новый
let requestSeq = 0

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU')
}

async function load() {
  const seq = ++requestSeq
  loading.value = true
  try {
    const q = search.value.trim()
    const data = await listUsers({
      role: roleFilter.value === 'all' ? undefined : (roleFilter.value as UserRole),
      is_active: activeFilter.value === 'all' ? undefined : activeFilter.value === 'true',
      q: q || undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE
    })
    if (seq !== requestSeq) return
    items.value = data.items
    total.value = data.total
    // фильтры сузили выдачу: страницы, на которой мы стоим, больше нет
    const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
    if (page.value > lastPage) {
      page.value = lastPage
      await load()
    }
  } catch (err) {
    if (seq !== requestSeq) return
    message.error(errorText(err, 'Ошибка загрузки пользователей'))
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, SEARCH_DELAY_MS)
}

function onFilterChange() {
  page.value = 1
  load()
}

function onPageChange(p: number) {
  page.value = p
  load()
}

async function change(u: UserItem, patch: { role?: UserRole; is_active?: boolean }) {
  busyId.value = u.id
  try {
    const updated = await updateUser(u.id, patch)
    // строка из ответа сервера; список и total не перечитываем
    const i = items.value.findIndex((x) => x.id === updated.id)
    if (i !== -1) items.value[i] = updated
  } catch (err) {
    message.error(errorText(err, 'Не удалось изменить пользователя'))
  } finally {
    busyId.value = null
  }
}

onMounted(load)
onUnmounted(() => clearTimeout(searchTimer))
</script>
