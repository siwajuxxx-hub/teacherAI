import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import type {
  User, ScheduleItem, ScheduleCreatePayload, TaskItem, TaskCreatePayload,
  UserCreatePayload, UserUpdatePayload, AISettings, AISettingsUpdatePayload,
  ChatMessage, ParsedScheduleResponse, ChatAction, ExecuteActionsResponse,
} from '../types'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor — прикрепляем JWT access токен
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — при 401 пробуем обновить токен
let isRefreshing = false
let failedQueue: Array<{
  resolve: (value: unknown) => void
  reject: (reason?: unknown) => void
}> = []

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

// Мягкий выход: чистим токены и сообщаем приложению через событие.
// ВАЖНО: не используем window.location.href — жёсткая перезагрузка стирает
// сообщения об ошибках (например, на странице входа).
const softLogout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  window.dispatchEvent(new CustomEvent('auth-expired'))
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    // НЕ пытаемся обновить токен для login/refresh — это сами эндпоинты аутентификации
    const isAuthEndpoint =
      originalRequest?.url?.includes('/auth/login') ||
      originalRequest?.url?.includes('/auth/refresh');

    // Запросы входа не трогаем вообще — пусть ошибка дойдёт до формы
    if (isAuthEndpoint) {
      return Promise.reject(error)
    }

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`
          }
          return api(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        softLogout()
        return Promise.reject(error)
      }

      try {
        const response = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
        const { access_token, refresh_token } = response.data
        localStorage.setItem('access_token', access_token)
        localStorage.setItem('refresh_token', refresh_token)

        processQueue(null, access_token)

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${access_token}`
        }
        return api(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        softLogout()
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

// ── Auth API ──────────────────────────────────────────

export async function login(username: string, password: string) {
  const { data } = await api.post('/auth/login', { username, password })
  return data as { access_token: string; refresh_token: string; token_type: string }
}

export async function refreshToken(refresh_token: string) {
  const { data } = await api.post('/auth/refresh', { refresh_token })
  return data as { access_token: string; refresh_token: string; token_type: string }
}

export async function getMe() {
  const { data } = await api.get('/auth/me')
  return data as User
}

// ── Users API (admin) ─────────────────────────────────

export async function listUsers() {
  const { data } = await api.get('/users/')
  return data as User[]
}

export async function createUser(payload: UserCreatePayload) {
  const { data } = await api.post('/users/', payload)
  return data as User
}

export async function updateUser(id: string, payload: UserUpdatePayload) {
  const { data } = await api.put(`/users/${id}`, payload)
  return data as User
}

export async function deleteUser(id: string) {
  await api.delete(`/users/${id}`)
}

export async function changePassword(id: string, password: string) {
  await api.put(`/users/${id}/password`, { password })
}

// ── Schedule API ──────────────────────────────────────

export async function getMySchedule() {
  const { data } = await api.get('/schedule/my')
  return data as ScheduleItem[]
}

export async function getUserSchedule(userId: string) {
  const { data } = await api.get(`/schedule/user/${userId}`)
  return data as ScheduleItem[]
}

export async function createSchedule(payload: ScheduleCreatePayload) {
  const { data } = await api.post('/schedule/', payload)
  return data as ScheduleItem
}

export async function batchCreateSchedule(payload: { user_id?: string; items: ScheduleCreatePayload[] }) {
  const { data } = await api.post('/schedule/batch', payload)
  return data as ScheduleItem[]
}

export async function updateSchedule(id: string, payload: Partial<ScheduleCreatePayload>) {
  const { data } = await api.put(`/schedule/${id}`, payload)
  return data as ScheduleItem
}

export async function deleteSchedule(id: string) {
  await api.delete(`/schedule/${id}`)
}

// ── Tasks API ─────────────────────────────────────────

export async function getMyTasks() {
  const { data } = await api.get('/tasks/my')
  return data as TaskItem[]
}

export async function getUserTasks(userId: string) {
  const { data } = await api.get(`/tasks/user/${userId}`)
  return data as TaskItem[]
}

export async function createTask(payload: TaskCreatePayload) {
  const { data } = await api.post('/tasks/', payload)
  return data as TaskItem
}

export async function updateTask(id: string, payload: Partial<TaskCreatePayload>) {
  const { data } = await api.put(`/tasks/${id}`, payload)
  return data as TaskItem
}

export async function updateTaskStatus(id: string, status: string) {
  const { data } = await api.patch(`/tasks/${id}/status`, { status })
  return data as TaskItem
}

export async function deleteTask(id: string) {
  await api.delete(`/tasks/${id}`)
}

// ── Stats API (manager / admin) ───────────────────────

export interface TeacherStatsRow {
  id: string
  full_name: string
  username: string
  position: string
  role: string
  has_schedule: boolean
  teacher_id: string
  year: number
  month: number
  lessons_per_month: number
  lessons_per_week: number
  hours_per_month: number
  subjects_count: number
  groups_count: number
  tasks_total: number
  tasks_done: number
  tasks_completed_in_month: number
  tasks_overdue: number
  tasks_pending: number
  tasks_in_progress: number
  completion_rate: number
}

export interface OverviewResponse {
  year: number
  month: number
  totals: {
    teachers_total: number
    teachers_with_schedule: number
    lessons_per_month: number
    hours_per_month: number
    tasks_total: number
    tasks_done: number
    tasks_overdue: number
    completion_rate: number
  }
  teachers: TeacherStatsRow[]
}

export interface ManagerCalendarResponse {
  year: number
  month: number
  teachers: Array<{ id: string; full_name: string; position: string }>
  days: Array<{
    date: string
    lessons: Array<{
      id: string; teacher_id: string; teacher_name: string; title: string
      start_time: string; end_time: string; group_name: string; room: string; type: string
    }>
    tasks: Array<{
      id: string; teacher_id: string; teacher_name: string; title: string
      status: string; scope: string
      due_date: string | null; due_month: string | null; due_year: number | null
    }>
  }>
}

export async function getOverview(year?: number, month?: number) {
  const { data } = await api.get('/stats/overview', { params: { year, month } })
  return data as OverviewResponse
}

export async function getTeacherStats(teacherId: string, year?: number, month?: number) {
  const { data } = await api.get(`/stats/teacher/${teacherId}`, { params: { year, month } })
  return data
}

export async function getTeacherMonthly(teacherId: string, year?: number) {
  const { data } = await api.get(`/stats/teacher/${teacherId}/monthly`, { params: { year } })
  return data
}

export async function getManagerCalendar(year: number, month: number, teacherId?: string) {
  const { data } = await api.get('/stats/calendar', {
    params: { year, month, teacher_id: teacherId },
  })
  return data as ManagerCalendarResponse
}

// ── Chat API ──────────────────────────────────────────

export function sendChatMessage(message: string): Promise<Response> {
  return fetch('/api/chat/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('access_token')}`,
    },
    body: JSON.stringify({ message }),
  })
}

/** Выполняет подтверждённые действия из чата. */
export async function executeChatActions(actions: ChatAction[]): Promise<ExecuteActionsResponse> {
  const { data } = await api.post('/chat/execute-actions', { actions })
  return data as ExecuteActionsResponse
}

export async function uploadFile(file: File, message?: string): Promise<ParsedScheduleResponse> {
  const formData = new FormData()
  formData.append('file', file)
  // ВАЖНО: текст запроса нужен бэкенду, чтобы понять режим импорта
  // (свои пары / пары конкретного преподавателя / распределить всем)
  if (message && message.trim()) {
    formData.append('message', message.trim())
  }

  const response = await fetch('/api/chat/upload', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${localStorage.getItem('access_token')}`,
    },
    body: formData,
  })

  if (!response.ok) {
    let detail = 'Ошибка загрузки файла'
    try {
      const error = await response.json()
      detail = error.detail || detail
    } catch { /* not json */ }
    throw new Error(detail)
  }

  return response.json()
}

export async function getChatHistory(limit = 50) {
  const { data } = await api.get('/chat/history', { params: { limit } })
  return data as ChatMessage[]
}

// ── Settings API (admin) ──────────────────────────────

export async function getSettings() {
  const { data } = await api.get('/settings/')
  return data as AISettings
}

export async function updateAISettings(payload: AISettingsUpdatePayload) {
  const { data } = await api.put('/settings/ai', payload)
  return data as AISettings
}

export async function testAIConnection() {
  const { data } = await api.post('/settings/ai/test')
  return data as { status: string; response?: string; error?: string }
}

export default api