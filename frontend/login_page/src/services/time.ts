import api from './api'

export async function createTimeEntry(entry: {
  task_id: number
  user_id: number | null
  minutes: number
  description?: string
}) {
  // гарантируем числа
  entry.task_id = Number(entry.task_id)
  entry.user_id = entry.user_id !== null && entry.user_id !== undefined ? Number(entry.user_id) : null
  entry.minutes = Number(entry.minutes)
  
  console.log('createTimeEntry called with:', entry)
  
  try {
    const r = await api.post('/api/time/time-entries', entry)
    console.log('Time entry created successfully:', r.data)
    return r.data
  } catch (error: any) {
    console.error('Failed to create time entry:', error.response?.data || error.message)
    throw error
  }
}
