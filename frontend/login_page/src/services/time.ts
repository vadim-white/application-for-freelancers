import api from './api'

// Запись времени из time-service; stopped_at = null — таймер идёт
export interface TimeEntry {
  id: number
  user_id: number
  task_id: number
  started_at: string
  stopped_at: string | null
  duration_seconds: number | null
  description: string | null
  created_at: string
  updated_at: string | null
}

// Строка статистики по пользователю (схема UserStatistics time-service; task-service проксирует)
export interface UserStatistics {
  user_id: number
  entries_count: number
  tasks_count: number
  total_seconds: number
  avg_seconds_per_task: number
}

export interface TimerState {
  entry: TimeEntry | null
  server_time: string
}

export interface TimerStarted {
  entry: TimeEntry
  // запись, закрытая автостопом, если таймер шёл на другой задаче
  stopped: TimeEntry | null
  server_time: string
}

export interface TimerStopped {
  stopped: TimeEntry | null
  server_time: string
}

export async function getTimer(): Promise<TimerState> {
  const r = await api.get('/api/time/timer')
  return r.data
}

export async function startTimer(payload: {
  task_id: number
  description?: string
}): Promise<TimerStarted> {
  const r = await api.post('/api/time/timer/start', payload)
  return r.data
}

export async function stopTimer(): Promise<TimerStopped> {
  const r = await api.post('/api/time/timer/stop')
  return r.data
}

// описание можно менять и у идущей записи, и у закрытой; null очищает
export async function updateTimeEntry(
  id: number,
  payload: { description: string | null }
): Promise<TimeEntry> {
  const r = await api.patch(`/api/time/time-entries/${id}`, payload)
  return r.data
}
