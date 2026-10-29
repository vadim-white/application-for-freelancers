import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getTimer, startTimer, stopTimer, updateTimeEntry, type TimeEntry } from '../services/time'
import { getTask, type Task } from '../services/tasks'

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const hh = Math.floor(s / 3600)
    .toString()
    .padStart(2, '0')
  const mm = Math.floor((s % 3600) / 60)
    .toString()
    .padStart(2, '0')
  const ss = (s % 60).toString().padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

// чч:мм для итогов (статистика): до ближайшей минуты
export function formatHoursMinutes(seconds: number): string {
  const m = Math.round(Math.max(0, seconds) / 60)
  return `${Math.floor(m / 60)
    .toString()
    .padStart(2, '0')}:${(m % 60).toString().padStart(2, '0')}`
}

// Источник истины — сервер; здесь только его последнее состояние и счёт секунд для показа
export const useTimerStore = defineStore('timer', () => {
  const entry = ref<TimeEntry | null>(null)
  const lastStopped = ref<TimeEntry | null>(null)
  const runningTask = ref<Task | null>(null)
  const runningTaskMissing = ref(false)
  // server_time − часы браузера: время идёт от started_at сервера, а не от локальных часов
  const clockOffsetMs = ref(0)
  const now = ref(Date.now())
  let tickId: number | null = null
  // ответы, пришедшие после более нового запроса, не затирают состояние
  let seq = 0

  const elapsedSeconds = computed(() => {
    if (!entry.value) return 0
    return Math.max(
      0,
      (now.value + clockOffsetMs.value - Date.parse(entry.value.started_at)) / 1000
    )
  })
  const formatted = computed(() => formatDuration(elapsedSeconds.value))
  const runningTitle = computed(() => {
    if (!entry.value) return ''
    if (runningTask.value?.id === entry.value.task_id) return runningTask.value.title
    return runningTaskMissing.value ? 'задача удалена' : `задача #${entry.value.task_id}`
  })

  function setTicking(on: boolean) {
    if (on && tickId === null) {
      now.value = Date.now()
      tickId = window.setInterval(() => (now.value = Date.now()), 1000)
    } else if (!on && tickId !== null) {
      clearInterval(tickId)
      tickId = null
    }
  }

  async function loadRunningTask(taskId: number) {
    runningTaskMissing.value = false
    try {
      const t = await getTask(taskId)
      if (entry.value?.task_id === taskId) runningTask.value = t
    } catch {
      if (entry.value?.task_id === taskId) {
        runningTask.value = null
        runningTaskMissing.value = true
      }
    }
  }

  // задачу переименовали или изменили: индикатор берёт свежие данные; сбой оставляет прежние
  async function reloadRunningTask(taskId: number) {
    if (entry.value?.task_id !== taskId) return
    try {
      const t = await getTask(taskId)
      if (entry.value?.task_id === taskId) {
        runningTask.value = t
        runningTaskMissing.value = false
      }
    } catch {
      // прежнее название остаётся до следующего перечитывания
    }
  }

  function apply(next: TimeEntry | null, serverTime: string, task?: Task) {
    clockOffsetMs.value = Date.parse(serverTime) - Date.now()
    entry.value = next
    setTicking(next !== null)
    if (!next) return
    if (task && task.id === next.task_id) {
      runningTask.value = task
      runningTaskMissing.value = false
    } else if (runningTask.value?.id !== next.task_id) {
      runningTask.value = null
      void loadRunningTask(next.task_id)
    }
  }

  async function refresh() {
    const my = ++seq
    const r = await getTimer()
    if (my === seq) apply(r.entry, r.server_time)
  }

  async function start(task: Task, description?: string): Promise<TimeEntry | null> {
    const my = ++seq
    const r = await startTimer({ task_id: task.id, description })
    if (r.stopped) lastStopped.value = r.stopped
    if (my === seq) apply(r.entry, r.server_time, task)
    return r.stopped
  }

  async function stop(): Promise<TimeEntry | null> {
    const my = ++seq
    const r = await stopTimer()
    if (r.stopped) lastStopped.value = r.stopped
    if (my === seq) apply(null, r.server_time)
    return r.stopped
  }

  async function updateNote(id: number, description: string | null): Promise<void> {
    const updated = await updateTimeEntry(id, { description })
    if (entry.value?.id === id) entry.value = updated
    if (lastStopped.value?.id === id) lastStopped.value = updated
  }

  return {
    entry,
    lastStopped,
    runningTask,
    elapsedSeconds,
    formatted,
    runningTitle,
    refresh,
    reloadRunningTask,
    start,
    stop,
    updateNote
  }
})
