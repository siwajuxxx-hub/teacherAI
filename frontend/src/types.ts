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
  day_of_week: number;
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

export interface ParsedScheduleResponse {
  status: string;
  filename: string;
  items: ScheduleCreatePayload[];
  extracted_text: string;
  message: string;
}

/** Действие, предложенное AI в чате (требует подтверждения). */
export interface ChatAction {
  action: string;
  params: Record<string, unknown>;
  description: string;
}

/** Результат выполнения действия. */
export interface ActionResult {
  action: string;
  ok: boolean;
  message: string;
}

export interface ExecuteActionsResponse {
  results: ActionResult[];
  ok: boolean;
  report: string;
}