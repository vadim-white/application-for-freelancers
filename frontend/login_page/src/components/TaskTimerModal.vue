<template>
  <n-modal
    :show="innerShow"
    :closable="true"
    preset="dialog"
    class="timer-modal"
    @update:show="updateShow"
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

        <!-- Таймер идёт на другой задаче -->
        <n-alert v-if="otherRunning" type="warning" class="other-timer">
          Идёт таймер на «{{ timer.runningTitle }}» — {{ timer.formatted }}. Старт остановит его и
          запустит эту задачу.
        </n-alert>

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
            :disabled="running || busy !== null"
            :loading="busy === 'start'"
            class="control-btn"
            @click="onStart"
          >
            {{ paused ? '▶ Продолжить' : '▶ Старт' }}
          </n-button>
          <n-button
            type="warning"
            :disabled="!running || busy !== null"
            :loading="busy === 'stop'"
            class="control-btn"
            @click="onPause"
          >
            ⏸ Пауза
          </n-button>
          <n-button
            type="success"
            :disabled="status === 'done' || busy !== null"
            :loading="busy === 'done'"
            class="control-btn"
            @click="onMarkDone"
          >
            ✓ Выполнена
          </n-button>
        </div>

        <!-- Заметка -->
        <div class="note-section">
          <label
            style="
              font-weight: 500;
              color: var(--color-text-primary);
              display: block;
              margin-bottom: 8px;
            "
          >
            📝 Заметка (опционально, сохраняется сама)
          </label>
          <n-input
            :value="note"
            type="textarea"
            placeholder="Добавьте описание работы..."
            rows="3"
            maxlength="200"
            show-count
            @update:value="onNoteInput"
          />
        </div>

        <!-- Информация -->
        <div class="task-info">
          <div class="info-item">
            <span class="info-label">Статус:</span>
            <n-tag type="info" round size="small" class="task-status">{{
              status || 'pending'
            }}</n-tag>
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
import { ref, watch, computed, type PropType } from 'vue'
import { isAxiosError } from 'axios'
import { updateTask, type Task } from '../services/tasks'
import { useTimerStore, formatDuration } from '../stores/timer'
import { NAlert, NButton, NInput, NModal, NSpace, NTag, useMessage } from 'naive-ui'

const props = defineProps({
  show: Boolean,
  task: { type: Object as PropType<Task | null>, default: null }
})
const emit = defineEmits(['update:show', 'changed'])

const message = useMessage()
const timer = useTimerStore()

const innerShow = ref(false)
watch(
  () => props.show,
  (v) => {
    innerShow.value = v
    // другая вкладка могла запустить или остановить таймер
    if (v) timer.refresh().catch(() => {})
  },
  { immediate: true }
)

function updateShow(v: boolean) {
  innerShow.value = v
  emit('update:show', v)
  if (!v) void flushNote()
}

const busy = ref<'start' | 'stop' | 'done' | null>(null)
const note = ref('')
const status = ref<string | null>(null)

// окно одно на дашборд: при смене задачи сбрасываем всё, что относилось к прежней
watch(
  () => props.task,
  (t) => {
    status.value = t?.status ?? null
  },
  { immediate: true }
)

const running = computed(() => !!props.task && timer.entry?.task_id === props.task.id)
const otherRunning = computed(() => !!timer.entry && !running.value)
const paused = computed(() => !!props.task && timer.lastStopped?.task_id === props.task.id)

// запись, к которой относится заметка: идущая, а после паузы — последняя закрытая
const noteEntry = computed(() =>
  running.value ? timer.entry : paused.value ? timer.lastStopped : null
)

// смена задачи или записи подставляет её заметку; пока записи нет, заметка уйдёт со стартом
watch(
  () => [props.task?.id, noteEntry.value?.id],
  () => {
    note.value = noteEntry.value?.description ?? ''
  },
  { immediate: true }
)

let noteTimer: number | null = null

function onNoteInput(v: string) {
  note.value = v
  if (noteTimer !== null) clearTimeout(noteTimer)
  if (noteEntry.value) noteTimer = window.setTimeout(flushNote, 600)
}

async function flushNote() {
  if (noteTimer !== null) clearTimeout(noteTimer)
  noteTimer = null
  const target = noteEntry.value
  if (!target || (target.description ?? '') === note.value) return
  try {
    await timer.updateNote(target.id, note.value || null)
  } catch {
    message.error('Не удалось сохранить заметку')
  }
}

const formattedElapsed = computed(() => {
  if (running.value) return timer.formatted
  if (paused.value) return formatDuration(timer.lastStopped?.duration_seconds ?? 0)
  return formatDuration(0)
})

function startErrorText(err: unknown): string {
  if (isAxiosError(err)) {
    const code = err.response?.status
    const detail = err.response?.data?.detail
    if (code === 404) return 'Задача не найдена — возможно, её удалили'
    if (code === 409 && detail === 'Task is archived')
      return 'Задача или проект в архиве — таймер не запустить'
    if (code === 409) return 'Таймер запустили одновременно в другом месте, попробуйте ещё раз'
    if (code === 503) return 'Сервис задач недоступен, попробуйте позже'
  }
  return 'Не удалось запустить таймер'
}

async function onStart() {
  const task = props.task
  if (!task || running.value) return
  const prevTitle = timer.runningTitle
  busy.value = 'start'
  try {
    const stopped = await timer.start(task, note.value || undefined)
    if (stopped && stopped.task_id !== task.id) {
      message.info(`Таймер на «${prevTitle}» остановлен`)
    }
  } catch (err) {
    message.error(startErrorText(err))
    timer.refresh().catch(() => {})
    return
  } finally {
    busy.value = null
  }

  if (status.value === 'todo') {
    try {
      const updated = await updateTask(task.id, { status: 'in_progress' })
      status.value = updated.status
      emit('changed')
    } catch {
      message.warning('Таймер идёт, но статус задачи не изменился')
    }
  }
}

async function onPause() {
  if (!running.value) return
  busy.value = 'stop'
  try {
    const stopped = await timer.stop()
    if (stopped) message.success(`Записано ${formatDuration(stopped.duration_seconds ?? 0)}`)
    await flushNote()
  } catch {
    message.error('Не удалось остановить таймер')
    timer.refresh().catch(() => {})
  } finally {
    busy.value = null
  }
}

async function onMarkDone() {
  const task = props.task
  if (!task) return
  busy.value = 'done'
  try {
    const updated = await updateTask(task.id, { status: 'done' })
    status.value = updated.status
    message.success('Задача выполнена')
    emit('changed')
  } catch {
    message.error('Не удалось завершить задачу')
  } finally {
    busy.value = null
  }
}

function onClose() {
  updateShow(false)
}
</script>

<style scoped>
.timer-modal :deep(.n-modal__header) {
  background: linear-gradient(135deg, #f7971e 0%, #ffd200 100%) !important;
  color: white !important;
}

.modal-content {
  padding: 24px 0;
}

.other-timer {
  margin-bottom: 24px;
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
