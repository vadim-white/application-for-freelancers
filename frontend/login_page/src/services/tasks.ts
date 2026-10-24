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

// Проект из task-service (схема ProjectRead)
export interface Project {
  id: number
  name: string
  description: string | null
  is_active: boolean
  owner_id: number
  created_at: string | null
}

// Задача в превью карточки проекта
export interface TaskPreview {
  id: number
  title: string
  status: TaskStatus
}

// Элемент списка проектов (схема ProjectListItem): активные задачи проекта —
// их число и первые три
export interface ProjectListItem extends Project {
  tasks_count: number
  tasks_preview: TaskPreview[]
}

// Конверт списка: total — число подходящих под фильтры, не размер страницы
export interface ProjectList {
  items: ProjectListItem[]
  total: number
  limit: number
  offset: number
}

export interface ProjectListParams {
  is_active?: boolean
  sort?: 'created_at' | '-created_at' | 'name' | '-name'
  limit?: number
  offset?: number
}

export async function getProjects(params: ProjectListParams = {}): Promise<ProjectList> {
  const r = await api.get('/api/tasks/projects', { params })
  return r.data
}

export async function getProject(id: number): Promise<Project> {
  const r = await api.get(`/api/tasks/projects/${id}`)
  return r.data
}

export async function createProject(payload: { name: string; description?: string }) {
  const r = await api.post('/api/tasks/projects', payload)
  return r.data
}

// PATCH — merge-patch: нет поля — не трогать, null — очистить; неизвестное поле — 422
export interface ProjectPatch {
  name?: string
  description?: string | null
  is_active?: boolean
}

export async function updateProject(projectId: number | string, payload: ProjectPatch): Promise<Project> {
  const r = await api.patch(`/api/tasks/projects/${projectId}`, payload)
  return r.data
}

export async function deleteProject(projectId: number | string) {
  const r = await api.delete(`/api/tasks/projects/${projectId}`)
  return r.data
}

/* Tasks */
export interface TaskList {
  items: Task[]
  total: number
  limit: number
  offset: number
}

type TaskSortField = 'created_at' | 'updated_at' | 'deadline' | 'title' | 'status'

export interface TaskListParams {
  project_id?: number | 'none'
  status?: TaskStatus[]
  is_active?: boolean
  sort?: TaskSortField | `-${TaskSortField}`
  limit?: number
  offset?: number
}

export async function getTasks(params: TaskListParams = {}): Promise<TaskList> {
  // status повторяется (?status=todo&status=done), а не status[]=…: так его ждёт FastAPI
  const r = await api.get('/api/tasks/tasks', { params, paramsSerializer: { indexes: null } })
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

// project_id: null — вынос задачи из проекта; deadline — с часовым поясом (toISOString)
export interface TaskPatch {
  title?: string
  description?: string | null
  status?: TaskStatus
  deadline?: string | null
  project_id?: number | null
  is_active?: boolean
}

export async function updateTask(taskId: number | string, payload: TaskPatch): Promise<Task> {
  const r = await api.patch(`/api/tasks/tasks/${taskId}`, payload)
  return r.data
}

/* NOTE: path must match backend: /api/tasks/tasks/{id} */
export async function deleteTask(taskId: number | string) {
  const r = await api.delete(`/api/tasks/tasks/${taskId}`)
  return r.data
}
