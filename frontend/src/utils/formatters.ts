import { format, parse, isToday, isTomorrow, isPast } from 'date-fns';
import { ru } from 'date-fns/locale';
import { DAYS_OF_WEEK, DAYS_SHORT, SCHEDULE_TYPES, TASK_STATUSES, TASK_SCOPES, ROLES } from './constants';

// ── Date & time formatters ──────────────────────────────────

/** Format a Date or ISO string to "dd.MM.yyyy" */
export const formatDate = (date: string | Date): string =>
  format(typeof date === 'string' ? new Date(date) : date, 'dd.MM.yyyy');

/** Format a Date or ISO string to "dd.MM.yyyy HH:mm" */
export const formatDateTime = (date: string | Date): string =>
  format(typeof date === 'string' ? new Date(date) : date, 'dd.MM.yyyy HH:mm', { locale: ru });

/** Extract "HH:mm" from a time string */
export const formatTime = (time: string): string => time.slice(0, 5);

/** Full weekday name from 0‑based index (0 = Понедельник) */
export const dayName = (index: number): string => DAYS_OF_WEEK[index] ?? '';

/** Short weekday name from 0‑based index (0 = ПН) */
export const dayNameShort = (index: number): string => DAYS_SHORT[index] ?? '';

// ── Color / style mappings ──────────────────────────────────

type ScheduleType = keyof typeof SCHEDULE_TYPES;
type Status = keyof typeof TASK_STATUSES;
type Scope = keyof typeof TASK_SCOPES;

/** Tailwind classes per schedule type */
export const scheduleTypeColor = (type: ScheduleType | string): string => {
  const map: Record<string, string> = {
    lesson: 'bg-blue-100 text-blue-800 border-blue-300',
    meeting: 'bg-red-100 text-red-800 border-red-300',
    other: 'bg-gray-100 text-gray-800 border-gray-300',
  };
  return map[type] ?? map.other;
};

/** Tailwind badge classes per task scope (период задачи) */
export const scopeColor = (scope: Scope | string): string => {
  const map: Record<string, string> = {
    day: 'bg-indigo-100 text-indigo-700',
    month: 'bg-violet-100 text-violet-700',
    year: 'bg-amber-100 text-amber-700',
    none: 'bg-gray-100 text-gray-600',
    week: 'bg-violet-100 text-violet-700',
  };
  return map[scope] ?? map.none;
};

/** Tailwind badge classes per task status */
export const statusColor = (status: Status | string): string => {
  const map: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-700',
    in_progress: 'bg-blue-100 text-blue-800',
    done: 'bg-green-100 text-green-800',
    overdue: 'bg-red-100 text-red-800',
  };
  return map[status] ?? map.pending;
};

/** Human‑readable label for a schedule type */
export const scheduleTypeLabel = (type: ScheduleType | string): string =>
  (SCHEDULE_TYPES as Record<string, string>)[type] ?? type;

/** Human‑readable label for a task scope (период) */
export const scopeLabel = (scope: Scope | string): string =>
  (TASK_SCOPES as Record<string, string>)[scope] ?? scope;

/** Human‑readable label for a task status */
export const statusLabel = (status: Status | string): string =>
  (TASK_STATUSES as Record<string, string>)[status] ?? status;

// ── Role helpers ─────────────────────────────────────────

/** Human-readable label for a role */
export const roleLabel = (role: string): string =>
  (ROLES as Record<string, string>)[role] ?? role;

/** Tailwind badge classes per role */
export const roleBadgeColor = (role: string): string => {
  const map: Record<string, string> = {
    admin: 'bg-purple-100 text-purple-800',
    manager: 'bg-blue-100 text-blue-800',
    teacher: 'bg-green-100 text-green-800',
  };
  return map[role] ?? 'bg-gray-100 text-gray-800';
};

// ── Misc helpers ────────────────────────────────────────────

/** Truncate a string with ellipsis */
export const truncate = (str: string, maxLen: number): string =>
  str.length <= maxLen ? str : str.slice(0, maxLen - 1) + '…';

/** Capitalise first letter */
export const capitalize = (str: string): string =>
  str.charAt(0).toUpperCase() + str.slice(1);