import React, { useEffect, useState, useCallback } from 'react';
import {
  Calendar,
  CheckSquare,
  User,
  Loader2,
  AlertCircle,
  Eye,
  MapPin,
  Clock,
} from 'lucide-react';
import * as api from '../../api/client';
import type { User as UserType, ScheduleItem, TaskItem } from '../../types';
import { DAYS_SHORT } from '../../utils/constants';
import {
  formatDate,
  formatTime,
  scopeColor,
  scopeLabel,
  statusColor,
  statusLabel,
  scheduleTypeColor,
  scheduleTypeLabel,
} from '../../utils/formatters';

// ─── helpers ─────────────────────────────────────────────────
const groupByDay = (entries: ScheduleItem[]) => {
  const groups: Record<number, ScheduleItem[]> = {};
  for (let i = 0; i < 7; i++) groups[i] = [];
  entries.forEach((e) => {
    const d = e.day_of_week;
    if (d >= 0 && d < 7) groups[d].push(e);
  });
  return groups;
};

const groupTasksByStatus = (tasks: TaskItem[]) => {
  const cols: Record<string, TaskItem[]> = { pending: [], in_progress: [], done: [] };
  tasks.forEach((t) => {
    const s = t.status || 'pending';
    if (cols[s]) cols[s].push(t);
    else cols.pending.push(t);
  });
  return cols;
};

// ─── Main component ──────────────────────────────────────────
const GlobalView: React.FC = () => {
  const [teachers, setTeachers] = useState<UserType[]>([]);
  const [teachersLoading, setTeachersLoading] = useState(true);
  const [teachersError, setTeachersError] = useState('');

  const [selectedTeacherId, setSelectedTeacherId] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState('');

  // ── fetch teachers ───────────────────────────────────────
  const fetchTeachers = useCallback(async () => {
    setTeachersLoading(true);
    setTeachersError('');
    try {
      const data = await api.listUsers();
      setTeachers(data.filter((u: UserType) => u.role === 'teacher'));
    } catch {
      setTeachersError('Ошибка загрузки списка учителей');
    } finally {
      setTeachersLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTeachers();
  }, [fetchTeachers]);

  // ── load data when teacher selected ──────────────────────
  useEffect(() => {
    if (!selectedTeacherId) {
      setSchedule([]);
      setTasks([]);
      setDataError('');
      return;
    }
    let cancelled = false;
    const load = async () => {
      setDataLoading(true);
      setDataError('');
      try {
        const [sched, t] = await Promise.all([
          api.getUserSchedule(selectedTeacherId),
          api.getUserTasks(selectedTeacherId),
        ]);
        if (cancelled) return;
        setSchedule(sched);
        setTasks(t);
      } catch {
        if (!cancelled) setDataError('Ошибка загрузки данных');
      } finally {
        if (!cancelled) setDataLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [selectedTeacherId]);

  const selectedTeacher = teachers.find((t) => t.id === selectedTeacherId);

  // ── render ────────────────────────────────────────────────
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Общий обзор</h1>
        <p className="text-sm text-gray-500 mt-1">
          Просмотр расписания и задач любого учителя (только чтение)
        </p>
      </div>

      {/* Teacher selector */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
          <Eye size={16} className="text-gray-400" />
          Выберите учителя для просмотра
        </label>
        {teachersLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
            <Loader2 size={16} className="animate-spin" /> Загрузка списка...
          </div>
        ) : teachersError ? (
          <div className="flex items-center gap-2 text-sm text-red-600">
            <AlertCircle size={16} />{teachersError}
          </div>
        ) : (
          <select
            value={selectedTeacherId ?? ''}
            onChange={(e) => setSelectedTeacherId(e.target.value || null)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">— Выберите учителя —</option>
            {teachers.map((t) => (
              <option key={t.id} value={t.id}>
                {t.full_name} {t.position ? `(${t.position})` : ''}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* No selection placeholder */}
      {!selectedTeacherId && (
        <div className="text-center py-20 text-gray-400">
          <User size={56} className="mx-auto mb-4 opacity-30" />
          <p className="text-lg">Выберите учителя, чтобы увидеть его расписание и задачи</p>
        </div>
      )}

      {/* Selected teacher info bar */}
      {selectedTeacher && (
        <div className="flex items-center gap-3 mb-6 px-5 py-3 bg-indigo-50 rounded-xl border border-indigo-100">
          <div className="w-10 h-10 rounded-full bg-indigo-200 flex items-center justify-center">
            <User size={20} className="text-indigo-600" />
          </div>
          <div>
            <p className="font-semibold text-gray-900">{selectedTeacher.full_name}</p>
            <p className="text-sm text-gray-500">{selectedTeacher.position || '—'}</p>
          </div>
        </div>
      )}

      {/* Loading */}
      {dataLoading && (
        <div className="flex justify-center py-16">
          <Loader2 size={28} className="animate-spin text-indigo-500" />
        </div>
      )}

      {/* Error */}
      {dataError && (
        <div className="flex items-center gap-2 p-4 mb-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          <AlertCircle size={18} />{dataError}
        </div>
      )}

      {/* Data panels */}
      {!dataLoading && selectedTeacherId && !dataError && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Schedule panel */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
              <Calendar size={18} className="text-blue-500" />
              <h2 className="font-semibold text-gray-800">Расписание на неделю</h2>
              {schedule.length > 0 && (
                <span className="ml-auto text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                  {schedule.length} зап.
                </span>
              )}
            </div>
            <div className="p-5">
              {schedule.length === 0 ? (
                <p className="text-sm text-gray-400 italic text-center py-8">Нет записей в расписании</p>
              ) : (
                <WeeklyScheduleGrid entries={schedule} />
              )}
            </div>
          </div>

          {/* Tasks panel (Kanban) */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
              <CheckSquare size={18} className="text-indigo-500" />
              <h2 className="font-semibold text-gray-800">Задачи</h2>
              {tasks.length > 0 && (
                <span className="ml-auto text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                  {tasks.length} зад.
                </span>
              )}
            </div>
            <div className="p-5">
              {tasks.length === 0 ? (
                <p className="text-sm text-gray-400 italic text-center py-8">Нет задач</p>
              ) : (
                <KanbanBoard tasks={tasks} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Weekly schedule grid ────────────────────────────────────
const WeeklyScheduleGrid: React.FC<{ entries: ScheduleItem[] }> = ({ entries }) => {
  const grouped = groupByDay(entries);
  return (
    <div className="grid grid-cols-7 gap-1.5">
      {DAYS_SHORT.map((day, idx) => (
        <div key={idx} className="flex flex-col">
          <div className="text-xs font-semibold text-gray-500 mb-2 text-center">{day}</div>
          <div className="space-y-1.5 min-h-[80px]">
            {grouped[idx].map((e) => (
              <div
                key={e.id}
                className={`text-xs p-2 rounded-lg border ${scheduleTypeColor(e.type)}`}
              >
                <div className="font-medium truncate mb-0.5">{e.title}</div>
                <div className="flex items-center gap-1 text-gray-600">
                  <Clock size={10} />
                  <span>{formatTime(e.start_time)} – {formatTime(e.end_time)}</span>
                </div>
                {e.room && (
                  <div className="flex items-center gap-1 text-gray-500 mt-0.5">
                    <MapPin size={10} />
                    <span className="truncate">{e.room}</span>
                  </div>
                )}
                <div className="text-[10px] text-gray-400 mt-0.5">{scheduleTypeLabel(e.type)}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

// ─── Kanban board ─────────────────────────────────────────────
const KanbanBoard: React.FC<{ tasks: TaskItem[] }> = ({ tasks }) => {
  const cols = groupTasksByStatus(tasks);
  const statuses = [
    { key: 'pending', label: 'К выполнению' },
    { key: 'in_progress', label: 'В работе' },
    { key: 'done', label: 'Готово' },
  ];

  return (
    <div className="grid grid-cols-3 gap-3">
      {statuses.map(({ key, label }) => (
        <div key={key} className="flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-500 uppercase">{label}</span>
            <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
              {cols[key].length}
            </span>
          </div>
          <div className="space-y-2">
            {cols[key].map((t) => (
              <div
                key={t.id}
                className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="font-medium text-sm text-gray-800 mb-1">{t.title}</div>
                {t.description && (
                  <p className="text-xs text-gray-500 mb-2 line-clamp-2">{t.description}</p>
                )}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${scopeColor(t.scope)}`}>
                    {scopeLabel(t.scope)}
                  </span>
                </div>
                {(t.due_date || t.due_month || t.due_year) && (
                  <div className="text-[10px] text-gray-400 mt-2 flex items-center gap-1">
                    <Clock size={10} />
                    {t.due_date ? formatDate(t.due_date) : t.due_month ? t.due_month : `${t.due_year} год`}
                  </div>
                )}
              </div>
            ))}
            {cols[key].length === 0 && (
              <div className="text-xs text-gray-300 italic text-center py-4">Пусто</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default GlobalView;