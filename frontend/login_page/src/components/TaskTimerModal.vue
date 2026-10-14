<template>
  <n-modal
    :show="innerShow"
    @update:show="updateShow"
    :closable="true"
    preset="dialog"
    class="timer-modal"
  >
    <template #header>
      <div style="font-weight: 600; display: flex; align-items: center; gap: 8px">
        <span style="font-size: 20px">⏱️</span>
        <span>{{ task ? task.title : 'Таймер' }}</span>
      </div>
    </template>

    <template #default>
      <div v-if="!task" class="modal-content">
        <div style="text-align: center; color: var(--color-text-secondary)">Нет задачи</div>
      </div>

      <div v-else class="modal-content">
        <!-- Описание задачи -->
        <div v-if="task.description" class="task-description">
          {{ task.description }}
        </div>

        <!-- Таймер -->
        <div class="timer-display">
          <div class="timer-value">{{ formattedElapsed }}</div>
          <div class="timer-status">
            <n-tag :type="running ? 'warning' : 'default'" round>
              {{ running ? '▶ Идет отсчет' : '⏸ Остановлен' }}
            </n-tag>
          </div>
        </div>

        <!-- Кнопки управления -->
        <div class="timer-controls">
          <n-button 
            type="primary"
            @click="onStart" 
            :disabled="running"
            class="control-btn"
          >
            ▶ Старт
          </n-button>
          <n-button 
            type="warning"
            @click="onPause" 
            :disabled="!running"
            class="control-btn"
          >
            ⏸ Пауза
          </n-button>
          <n-button 
            type="error"
            @click="onStop" 
            :disabled="!hasRun || saving"
            :loading="saving"
            class="control-btn"
          >
            ⏹ Сохранить
          </n-button>
        </div>

        <!-- Заметка -->
        <div class="note-section">
          <label style="font-weight: 500; color: var(--color-text-primary); display: block; margin-bottom: 8px">
            📝 Заметка (опционально)
          </label>
          <n-input 
            v-model:value="note" 
            type="textarea"
            placeholder="Добавьте описание работы..."
            rows="3"
            maxlength="200"
            show-count
          />
        </div>

        <!-- Информация -->
        <div class="task-info">
          <div class="info-item">
            <span class="info-label">Статус:</span>
            <n-tag type="info" round size="small">{{ task.status || 'pending' }}</n-tag>
          </div>
        </div>
      </div>
    </template>

    <template #action>
      <n-space justify="end">
        <n-button @click="onClose">Закрыть</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { createTimeEntry } from '../services/time'
import { updateTask } from '../services/tasks'
import { useMessage } from 'naive-ui'

const props = defineProps({
  show: Boolean,
  task: Object
})
const emit = defineEmits(['update:show', 'stopped'])

const message = useMessage()

const innerShow = ref(props.show)
watch(() => props.show, (v) => (innerShow.value = v))

function updateShow(v: boolean) {
  innerShow.value = v
  emit('update:show', v)
}

/* timer state */
const running = ref(false)
const startTs = ref<number | null>(null)
const pausedAccum = ref(0) // seconds accumulated before current run
const elapsed = ref(0) // seconds total
let intervalId: number | null = null
const saving = ref(false)
const note = ref('')

const status = computed(() => props.task?.status ?? 'todo')
const hasRun = computed(() => elapsed.value > 0)

const formattedElapsed = computed(() => {
  const s = Math.floor(elapsed.value)
  const hh = Math.floor(s / 3600).toString().padStart(2, '0')
  const mm = Math.floor((s % 3600) / 60).toString().padStart(2, '0')
  const ss = (s % 60).toString().padStart(2, '0')
  return `${hh}:${mm}:${ss}`
})

function tick() {
  if (!startTs.value) return
  const now = Date.now()
  elapsed.value = pausedAccum.value + Math.floor((now - startTs.value) / 1000)
}

function onStart() {
  if (!props.task) return
  if (running.value) return
  // set backend status to in_progress
  updateTask(props.task.id, { status: 'in_progress' }).catch(() => {})
  startTs.value = Date.now()
  running.value = true
  intervalId = window.setInterval(tick, 500)
}

function onPause() {
  if (!running.value) return
  running.value = false
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
  // accumulate elapsed
  if (startTs.value) {
    pausedAccum.value = pausedAccum.value + Math.floor((Date.now() - startTs.value) / 1000)
  }
  startTs.value = null
  elapsed.value = pausedAccum.value
}

async function onStop() {
  if (!props.task) return
  // stop if running
  if (running.value) {
    onPause()
  }
  if (!hasRun.value) {
    message.warning('Таймер не запущен')
    return
  }

  // Конвертируем секунды в минуты
  const minutes = Math.round(elapsed.value / 60)
  const payload = {
    task_id: props.task.id,
    minutes,
    description: note.value || props.task.title
  }

  console.log('Time entry payload:', payload)
  console.log('Task ID:', payload.task_id, 'Type:', typeof payload.task_id)
  console.log('Minutes:', payload.minutes, 'Type:', typeof payload.minutes)

  saving.value = true
  try {
    await createTimeEntry(payload)
    // Optionally mark task done — here не навязываем, но можно:
    await updateTask(props.task.id, { status: 'done' })
    message.success('Время сохранено и задача помечена как выполненная')
    emit('stopped', payload)
    // reset timer state
    pausedAccum.value = 0
    elapsed.value = 0
    startTs.value = null
    note.value = ''
    innerShow.value = false
    emit('update:show', false)
  } catch (err) {
    console.error('Error creating time entry:', err)
    message.error('Ошибка при сохранении времени')
  } finally {
    saving.value = false
  }
}

function onClose() {
  // stop interval to avoid leaks
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
  innerShow.value = false
  emit('update:show', false)
}

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>

<style scoped>
.timer-modal :deep(.n-modal__header) {
  background: linear-gradient(135deg, #f7971e 0%, #ffd200 100%) !important;
  color: white !important;
}

.modal-content {
  padding: 24px 0;
}

.task-description {
  padding: 12px;
  background: rgba(102, 126, 234, 0.08);
  border-left: 4px solid var(--color-primary);
  border-radius: 4px;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
  font-size: 14px;
}

.timer-display {
  text-align: center;
  margin-bottom: 28px;
}

.timer-value {
  font-size: 64px;
  font-weight: 700;
  color: var(--color-primary);
  font-family: 'Courier New', monospace;
  margin-bottom: 12px;
  letter-spacing: 2px;
}

.timer-status {
  display: flex;
  justify-content: center;
}

.timer-controls {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 28px;
}

.control-btn {
  width: 100% !important;
}

.note-section {
  margin-bottom: 24px;
  padding: 16px;
  background: rgba(102, 126, 234, 0.05);
  border-radius: 8px;
  border: 1px dashed var(--color-border);
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: rgba(86, 171, 47, 0.08);
  border-radius: 6px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.info-label {
  color: var(--color-text-secondary);
  min-width: 70px;
}

@media (max-width: 480px) {
  .timer-value {
    font-size: 48px;
  }

  .timer-controls {
    grid-template-columns: 1fr;
  }
}
</style>