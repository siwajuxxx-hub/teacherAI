// Shared types for Teacher AI Assistant

export interface User {
  id: string;        // UUID
  username: string;
  full_name: string;
  position: string;
  role: 'teacher' | 'manager' | 'admin';
  is_active: boolean;
  created_at: string;
}

export interface ScheduleItem {
  id: string;        // UUID
  user_id: string;
  title: string;
  day_of_week: number;      // 0=ПН … 6=ВС
  event_date: string | null;  // YYYY-MM-DD — конкретный день; null = недельный шаблон
  weeks: string | null;       // фильтр недель шаблона: "3,7", "2 по 12", "верх"/"низ"
  start_time: string;       // "HH:MM"
  end_time: string;         // "HH:MM"
  group_name: string;
  room: string;
  type: 'lesson' | 'meeting' | 'other';
  source: 'manual' | 'pdf_import' | 'manager';
  created_by: string;
  created_at: string;
}

export interface ScheduleCreatePayload {
  user_id?: string;
  title: string;
  day_of_week?: number;
  event_date?: string | null;
  weeks?: string | null;
  start_time: string;
  end_time: string;
  group_name?: string;
  room?: string;
  type?: 'lesson' | 'meeting' | 'other';
  source?: 'manual' | 'pdf_import' | 'manager';
}

/** Период, на который ставится задача. */
export type TaskScope = 'day' | 'month' | 'year' | 'none';

export interface TaskItem {
  id: string;        // UUID
  user_id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'done' | 'overdue';
  scope: TaskScope;
  due_date: string | null;   // YYYY-MM-DD — конкретный день
  due_month: string | null;  // YYYY-MM    — месяц
  due_year: number | null;   // YYYY       — год
  completed_at: string | null;
  assigned_by: string | null;
  created_at: string;
}

export interface TaskCreatePayload {
  user_id?: string;
  title: string;
  description?: string;
  status?: 'pending' | 'in_progress' | 'done' | 'overdue';
  scope?: TaskScope;
  due_date?: string | null;
  due_month?: string | null;
  due_year?: number | null;
}

export interface UserCreatePayload {
  username: string;
  password: string;
  full_name: string;
  position: string;
  role: 'teacher' | 'manager' | 'admin';
}

export interface UserUpdatePayload {
  username?: string;
  full_name?: string;
  position?: string;
  role?: 'teacher' | 'manager' | 'admin';
  is_active?: boolean;
}

export interface AISettings {
  provider: string;
  model: string;
  base_url: string | null;
  has_api_key: boolean;
}

export interface AISettingsUpdatePayload {
  provider: string;
  api_key: string;
  model: string;
  base_url?: string | null;
}

export interface ChatMessage {
  id: string;
  user_id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  context_type?: string | null;
  context_id?: string | null;
  created_at: string;
}

// ── Новый контракт чата: server-side Proposal ────────────────

export type ProposalKind = 'IMPORT_PLAN' | 'ACTIONS' | 'CLEAR';

export interface ProposalItem {
  text: string;
  kind?: string;
}

/** Карточка предложения (любые записи/удаления — только через неё). */
export interface Proposal {
  id: string;
  kind: ProposalKind;
  summary: string;
  items: ProposalItem[];   // максимум 30 публичных строк
  total: number;           // всего строк в предложении
}

export interface QuestionReply { label: string; value: string }

/** Вопрос системы с кнопками быстрого ответа. */
export interface QuestionEnvelope {
  text: string;
  replies: QuestionReply[];
}

export interface ImportInfo {
  id: string;
  filename: string;
  kind: 'WEEKLY' | 'DATED' | 'PDF_IMPORT' | string;
  state: 'ASK_PERIOD' | 'ASK_END' | 'READY' | 'APPLIED' | 'CANCELLED' | string;
  period_start: string | null;
  period_end: string | null;
}

/** Ответ POST /chat/upload. */
export interface UploadEnvelope {
  status: 'proposal' | 'question' | 'info';
  message: string;
  filename: string;
  question?: QuestionEnvelope | null;
  proposal?: Proposal | null;
  import?: ImportInfo | null;
}

/** Ответ GET /chat/history. */
export interface ChatHistoryEnvelope {
  messages: ChatMessage[];
  pending_proposal: Proposal | null;
  question: QuestionEnvelope | null;
  import: ImportInfo | null;
}

/** Кадр SSE от POST /chat/send. */
export interface SseFrame {
  chunk?: string;
  done?: boolean;
  final_text?: string;
  message_id?: string | null;
  proposal?: Proposal | null;
  question?: QuestionEnvelope | null;
  error?: boolean;
}

export interface ConfirmResult {
  ok: boolean;
  report: string;
  proposal_id?: string;
}