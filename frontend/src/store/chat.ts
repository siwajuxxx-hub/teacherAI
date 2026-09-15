import { create } from 'zustand'
import type {
  ChatMessage, Proposal, QuestionEnvelope, ImportInfo,
} from '../types'

interface ChatState {
  messages: ChatMessage[]
  /** Карточка предложения — любые записи/удаления только через неё. */
  proposal: Proposal | null
  /** Вопрос системы с кнопками быстрого ответа (например, о периоде). */
  question: QuestionEnvelope | null
  /** Активный незавершённый импорт файла («в памяти»). */
  importInfo: ImportInfo | null
  isStreaming: boolean

  appendMessages: (...msgs: ChatMessage[]) => void
  replaceMessages: (msgs: ChatMessage[]) => void
  updateMessage: (id: string, fn: (msg: ChatMessage) => ChatMessage) => void
  setProposal: (p: Proposal | null) => void
  setQuestion: (q: QuestionEnvelope | null) => void
  setImportInfo: (i: ImportInfo | null) => void
  setIsStreaming: (v: boolean) => void
  clearChat: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  proposal: null,
  question: null,
  importInfo: null,
  isStreaming: false,

  appendMessages: (...msgs) => set((s) => ({ messages: [...s.messages, ...msgs] })),
  replaceMessages: (msgs) => set({ messages: msgs }),
  updateMessage: (id, fn) => set((s) => ({
    messages: s.messages.map((m) => m.id === id ? fn(m) : m),
  })),
  setProposal: (p) => set({ proposal: p }),
  setQuestion: (q) => set({ question: q }),
  setImportInfo: (i) => set({ importInfo: i }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  clearChat: () => set({
    messages: [], proposal: null, question: null, importInfo: null, isStreaming: false,
  }),
}))
