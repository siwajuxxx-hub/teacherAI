import { create } from 'zustand'
import type { ChatMessage, ParsedScheduleResponse, ChatAction } from '../types'

interface ChatState {
  messages: ChatMessage[]
  parsedItems: ParsedScheduleResponse | null
  pendingActions: ChatAction[]
  isStreaming: boolean

  appendMessages: (...msgs: ChatMessage[]) => void
  replaceMessages: (msgs: ChatMessage[]) => void
  updateMessage: (id: string, fn: (msg: ChatMessage) => ChatMessage) => void
  setParsedItems: (items: ParsedScheduleResponse | null) => void
  setPendingActions: (actions: ChatAction[]) => void
  setIsStreaming: (v: boolean) => void
  clearChat: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  parsedItems: null,
  pendingActions: [],
  isStreaming: false,

  appendMessages: (...msgs) => set((s) => ({ messages: [...s.messages, ...msgs] })),
  replaceMessages: (msgs) => set({ messages: msgs }),
  updateMessage: (id, fn) => set((s) => ({
    messages: s.messages.map((m) => m.id === id ? fn(m) : m),
  })),
  setParsedItems: (items) => set({ parsedItems: items }),
  setPendingActions: (actions) => set({ pendingActions: actions }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  clearChat: () => set({
    messages: [], parsedItems: null, pendingActions: [], isStreaming: false,
  }),
}))
