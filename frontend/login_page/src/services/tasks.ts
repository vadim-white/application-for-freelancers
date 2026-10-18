// src/services/tasks.ts
import api from './api'

export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked'

// Задача из task-service (схема TaskRead, без вложенного project)
export interface Task {
  id: number
  title: string
  description: string | null
  status: TaskStatus
  deadline: string | null
  project_id: number | null
  is_active: boolean
  owner_id: number
  created_at: string | null
  updated_at: string | null
}

export async function getProjects() {
  const r = await api.get('/api/tasks/projects')
  return r.data
}

export async function getProject(id: number) {
  const r = await api.get(`/api/tasks/projects/${id}`)
  return r.data
}

export async function createProject(payload: { name: string; description?: string }) {
  const r = await api.post('/api/tasks/projects', payload)
  return r.data
}

export async function updateProject(projectId: number | string, payload: any) {
  const r = await api.put(`/api/tasks/projects/${projectId}`, payload)
  return r.data
}

export async function deleteProject(projectId: number | string) {
  const r = await api.delete(`/api/tasks/projects/${projectId}`)
  return r.data
}

/* Tasks */
export async function getTasks(params: { project_id?: number; status?: string } = {}) {
  const r = await api.get('/api/tasks/tasks', { params })
  return r.data
}

export async function getTask(taskId: number | string) {
  const r = await api.get(`/api/tasks/tasks/${taskId}`)
  return r.data
}

export async function createTask(payload: { title: string; description?: string; project_id: number }) {
  const r = await api.post('/api/tasks/tasks', payload)
  return r.data
}

export async function updateTask(taskId: number | string, payload: any) {
  const r = await api.put(`/api/tasks/tasks/${taskId}`, payload)
  return r.data
}

/* NOTE: path must match backend: /api/tasks/tasks/{id} */
export async function deleteTask(taskId: number | string) {
  const r = await api.delete(`/api/tasks/tasks/${taskId}`)
  return r.data
}
