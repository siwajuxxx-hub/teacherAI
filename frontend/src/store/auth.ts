import { create } from 'zustand'
import * as api from '../api/client'
import type { User } from '../types'
import { useChatStore } from './chat'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,

  login: async (username, password) => {
    set({ isLoading: true })
    try {
      const data = await api.login(username, password)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)

      const me = await api.getMe()
      set({ user: me, isAuthenticated: true, isLoading: false })
      // Очищаем чат при входе нового пользователя
      useChatStore.getState().clearChat()
    } catch (err: any) {
      set({ isLoading: false })

      // Токены не должны остаться, если /me упал после успешного логина
      if (!useAuthStore.getState().isAuthenticated) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
      }

      const status = err?.response?.status
      const detail = err?.response?.data?.detail

      if (detail) {
        throw new Error(
          typeof detail === 'string' ? detail : 'Неверный логин или пароль',
        )
      }

      // Сеть недоступна / сервер не отвечает
      if (!err?.response) {
        throw new Error('Сервер недоступен. Проверьте подключение и повторите попытку.')
      }

      if (status === 401) {
        throw new Error('Неверный логин или пароль')
      }

      throw new Error(`Ошибка входа (код ${status ?? '—'}). Попробуйте позже.`)
    }
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ user: null, isAuthenticated: false })
    // Очищаем чат при выходе
    useChatStore.getState().clearChat()
  },

  checkAuth: async () => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      set({ user: null, isAuthenticated: false })
      return
    }

    set({ isLoading: true })
    try {
      const me = await api.getMe()
      set({ user: me, isAuthenticated: true, isLoading: false })
    } catch {
      // Try refresh
      const rt = localStorage.getItem('refresh_token')
      if (rt) {
        try {
          const data = await api.refreshToken(rt)
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          const me = await api.getMe()
          set({ user: me, isAuthenticated: true, isLoading: false })
          return
        } catch {
          // Refresh failed
        }
      }
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },
}))