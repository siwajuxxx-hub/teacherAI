import React, { useEffect, useState, useCallback } from 'react';
import {
  Search,
  ChevronDown,
  ChevronUp,
  Calendar,
  CheckSquare,
  User,
  Clock,
  MapPin,
  X,
  Loader2,
  AlertCircle,
  Trash2,
} from 'lucide-react';
import { useAuthStore } from '../../store/auth';
import * as api from '../../api/client';
import type { User as UserType, ScheduleItem, TaskItem } from '../../types';
import { DAYS_OF_WEEK, DAYS_SHORT } from '../../utils/constants';
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

// For kanban: group by status. Map the actual statuses from types.
const groupTasksByStatus = (tasks: TaskItem[]) => {
  const cols: Record<string, TaskItem[]> = { pending: [], in_progress: [], done: [] };
  tasks.forEach((t) => {
    const s = t.status || 'pending';
    if (cols[s]) cols[s].push(t);
    else cols.pending.push(t);
  });
  return cols;
};

// ─── Modal shell ─────────────────────────────────────────────
const Modal: React.FC<{
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}> = ({ open, onClose, title, children }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 relative max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-800">{title}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 transition-colors">
            <X size={20} className="text-gray-500" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

// ─── Main page ───────────────────────────────────────────────
const TeachersView: React.FC = () => {
  const user = useAuthStore((s) => s.user);

  const [teachers, setTeachers] = useState<UserType[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [expandLoading, setExpandLoading] = useState(false);

  const [showMeetingModal, setShowMeetingModal] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [editItem, setEditItem] = useState<ScheduleItem | null>(null);

  // ── fetch ────────────────────────────────────────────────
  const fetchTeachers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.listUsers();
      setTeachers(data.filter((u: UserType) => u.role === 'teacher'));
    } catch {
      setError('Ошибка загрузки списка учителей');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTeachers();
  }, [fetchTeachers]);

  // ── expand ───────────────────────────────────────────────
  const toggleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setSchedule([]);
      setTasks([]);
      return;
    }
    setExpandedId(id);
    setExpandLoading(true);
    try {
      const [sched, t] = await Promise.all([api.getUserSchedule(id), api.getUserTasks(id)]);
      setSchedule(sched);
      setTasks(t);
    } catch {
      setSchedule([]);
      setTasks([]);
    } finally {
      setExpandLoading(false);
    }
  };

  const refreshExpanded = async () => {
    if (expandedId) {
      try {
        const [sched, t] = await Promise.all([api.getUserSchedule(expandedId), api.getUserTasks(expandedId)]);
        setSchedule(sched);
        setTasks(t);
      } catch {
        /* ignore */
      }
    }
  };

  // ── менеджер правит чужой календарь вручную ──────────────
  const handleDeleteSchedule = async (id: string) => {
    if (!confirm('Удалить эту пару из расписания преподавателя?')) return;
    try { await api.deleteSchedule(id); await refreshExpanded(); window.dispatchEvent(new CustomEvent('data-changed')); }
    catch { alert('Не удалось удалить запись'); }
  };
  const handleDeleteTask = async (id: string) => {
    if (!confirm('Удалить эту задачу преподавателя?')) return;
    try { await api.deleteTask(id); await refreshExpanded(); window.dispatchEvent(new CustomEvent('data-changed')); }
    catch { alert('Не удалось удалить задачу'); }
  };

  // ── filtered ─────────────────────────────────────────────
  const filtered = teachers.filter((t) =>
    t.full_name.toLowerCase().includes(search.toLowerCase()),
  );

  // ── render ───────────────────────────────────────────────
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Учителя</h1>
          <p className="text-sm text-gray-500 mt-1">Управление расписанием и задачами преподавателей</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowMeetingModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 transition-colors shadow-sm"
          >
            <Calendar size={16} />
            Добавить собрание
          </button>
          <button
            onClick={() => setShowTaskModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <CheckSquare size={16} />
            Поставить задачу
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Поиск по имени..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 mb-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex justify-center py-20">
          <Loader2 size={32} className="animate-spin text-blue-500" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <User size={48} className="mx-auto mb-3 opacity-40" />
          <p>Учителя не найдены</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((teacher) => (
            <div
              key={teacher.id}
              className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden"
            >
              {/* Row */}
              <button
                onClick={() => toggleExpand(teacher.id)}
                className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors text-left"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                    <User size={20} className="text-blue-600" />
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">{teacher.full_name}</p>
                    <p className="text-sm text-gray-500">{teacher.position || '—'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-gray-400">
                  {expandedId === teacher.id ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                </div>
              </button>

              {/* Expanded */}
              {expandedId === teacher.id && (
                <div className="border-t border-gray-100">
                  {expandLoading ? (
                    <div className="flex justify-center py-10">
                      <Loader2 size={24} className="animate-spin text-blue-500" />
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-100">
                      {/* Mini schedule */}
                      <div className="p-5">
                        <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                          <Calendar size={16} className="text-blue-500" />
                          Расписание на неделю
                        </h3>
                        <MiniSchedule entries={schedule} onDelete={handleDeleteSchedule} onEdit={setEditItem} />
                      </div>
                      {/* Mini kanban */}
                      <div className="p-5">
                        <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                          <CheckSquare size={16} className="text-indigo-500" />
                          Задачи
                        </h3>
                        <MiniKanban tasks={tasks} onDelete={handleDeleteTask} />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <MeetingModal
        open={showMeetingModal}
        onClose={() => setShowMeetingModal(false)}
        teachers={teachers}
        onCreated={() => {
          setShowMeetingModal(false);
          refreshExpanded();
        }}
      />
      <TaskModal
        open={showTaskModal}
        onClose={() => setShowTaskModal(false)}
        teachers={teachers}
        currentUserId={user?.id ?? ''}
        onCreated={() => {
          setShowTaskModal(false);
          refreshExpanded();
        }}
      />
      <EditScheduleModal
        item={editItem}
        teachers={teachers}
        onClose={() => setEditItem(null)}
        onSaved={() => { setEditItem(null); refreshExpanded(); window.dispatchEvent(new CustomEvent('data-changed')); }}
      />
    </div>
  );
};

// ─── Mini schedule ───────────────────────────────────────────
const MiniSchedule: React.FC<{
  entries: ScheduleItem[];
  onDelete: (id: string) => void;
  onEdit: (item: ScheduleItem) => void;
}> = ({ entries, onDelete, onEdit }) => {
  const grouped = groupByDay(entries);
  if (entries.length === 0) {
    return <p className="text-sm text-gray-400 italic">Нет записей в расписании</p>;
  }
  return (
    <div className="grid grid-cols-7 gap-1">
      {DAYS_SHORT.map((day, idx) => (
        <div key={idx} className="text-center">
          <div className="text-[10px] font-semibold text-gray-500 mb-1">{day}</div>
          <div className="space-y-1 min-h-[60px]">
            {grouped[idx].map((e) => (
              <div
                key={e.id}
                onClick={() => onEdit(e)}
                className={`group relative cursor-pointer text-[10px] leading-tight px-1 py-0.5 rounded border ${scheduleTypeColor(e.type)}`}
                title={`${e.title} | ${formatTime(e.start_time)}–${formatTime(e.end_time)}${e.room ? ` | ${e.room}` : ''} — клик, чтобы изменить`}
              >
                <div className="font-medium truncate">{e.title}</div>
                <div>{formatTime(e.start_time)}</div>
                {e.event_date
                  ? <div className="text-[9px] text-gray-500">{e.event_date.split('-').reverse().slice(0, 2).join('.')}</div>
                  : e.weeks ? <div className="text-[9px] text-gray-500">нед. {e.weeks}</div> : null}
                {e.room && <div className="truncate text-gray-500">{e.room}</div>}
                <button
                  onClick={(ev) => { ev.stopPropagation(); onDelete(e.id); }}
                  className="hidden group-hover:flex absolute top-0 right-0 items-center justify-center w-4 h-4 rounded-full bg-red-100 text-red-600 hover:bg-red-200"
                  title="Удалить пару"
                >
                  <Trash2 size={9} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

// ─── Mini kanban ─────────────────────────────────────────────
const MiniKanban: React.FC<{ tasks: TaskItem[]; onDelete: (id: string) => void }> = ({ tasks, onDelete }) => {
  const cols = groupTasksByStatus(tasks);
  const statuses = ['pending', 'in_progress', 'done'];
  if (tasks.length === 0) {
    return <p className="text-sm text-gray-400 italic">Нет задач</p>;
  }
  return (
    <div className="grid grid-cols-3 gap-2">
      {statuses.map((s) => (
        <div key={s} className="flex flex-col gap-1.5">
          <div className="text-[10px] font-semibold text-gray-500 uppercase text-center">
            {statusLabel(s)}
          </div>
          {cols[s].slice(0, 4).map((t) => (
            <div key={t.id} className="group relative bg-white border border-gray-200 rounded-lg p-2 text-xs shadow-sm">
              <div className="font-medium text-gray-800 truncate">{t.title}</div>
              <span className={`inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${scopeColor(t.scope)}`}>
                {scopeLabel(t.scope)}
              </span>
              {(t.due_date || t.due_month || t.due_year) && (
                <div className="text-[10px] text-gray-400 mt-1">
                  {t.due_date ? formatDate(t.due_date)
                    : t.due_month ? t.due_month
                    : `${t.due_year} год`}
                </div>
              )}
              <button
                onClick={() => onDelete(t.id)}
                className="hidden group-hover:flex absolute top-1 right-1 items-center justify-center w-5 h-5 rounded-full bg-red-100 text-red-600 hover:bg-red-200"
                title="Удалить задачу"
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
          {cols[s].length > 4 && (
            <p className="text-[10px] text-gray-400 text-center">+{cols[s].length - 4} ещё</p>
          )}
        </div>
      ))}
    </div>
  );
};

// ─── Meeting modal ───────────────────────────────────────────
const MeetingModal: React.FC<{
  open: boolean;
  onClose: () => void;
  teachers: UserType[];
  onCreated: () => void;
}> = ({ open, onClose, teachers, onCreated }) => {
  const [teacherId, setTeacherId] = useState('');
  const [title, setTitle] = useState('');
  const [dayOfWeek, setDayOfWeek] = useState('0');
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('10:00');
  const [room, setRoom] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teacherId || !title) {
      setErr('Заполните обязательные поля');
      return;
    }
    setSaving(true);
    setErr('');
    try {
      await api.createSchedule({
        user_id: teacherId,
        title,
        day_of_week: Number(dayOfWeek),
        start_time: startTime,
        end_time: endTime,
        room: room || undefined,
        type: 'meeting',
        source: 'manager',
      });
      onCreated();
      reset();
    } catch {
      setErr('Ошибка при создании собрания');
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setTeacherId('');
    setTitle('');
    setDayOfWeek('0');
    setStartTime('09:00');
    setEndTime('10:00');
    setRoom('');
    setErr('');
  };

  return (
    <Modal open={open} onClose={onClose} title="Добавить собрание">
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl">
            <AlertCircle size={16} /> {err}
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Учитель *</label>
          <select
            value={teacherId}
            onChange={(e) => setTeacherId(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          >
            <option value="">Выберите учителя</option>
            {teachers.map((t) => (
              <option key={t.id} value={t.id}>{t.full_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Название *</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Педсовет, собрание кафедры..."
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">День недели</label>
          <select
            value={dayOfWeek}
            onChange={(e) => setDayOfWeek(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {DAYS_OF_WEEK.map((d, i) => (
              <option key={i} value={i}>{d}</option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Начало</label>
            <input
              type="time"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Конец</label>
            <input
              type="time"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Кабинет</label>
          <input
            type="text"
            value={room}
            onChange={(e) => setRoom(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="305"
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Calendar size={16} />}
          {saving ? 'Сохранение...' : 'Добавить собрание'}
        </button>
      </form>
    </Modal>
  );
};

// ─── Task modal ──────────────────────────────────────────────
const TaskModal: React.FC<{
  open: boolean;
  onClose: () => void;
  teachers: UserType[];
  currentUserId: string;
  onCreated: () => void;
}> = ({ open, onClose, teachers, currentUserId, onCreated }) => {
  const [teacherId, setTeacherId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('medium');
  const [dueDate, setDueDate] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teacherId || !title) {
      setErr('Заполните обязательные поля');
      return;
    }
    setSaving(true);
    setErr('');
    try {
      await api.createTask({
        user_id: teacherId,
        title,
        description: description || undefined,
        priority: priority as 'low' | 'medium' | 'high',
        due_date: dueDate || null,
        status: 'pending',
      } as Parameters<typeof api.createTask>[0] & { status?: string });
      onCreated();
      reset();
    } catch {
      setErr('Ошибка при создании задачи');
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setTeacherId('');
    setTitle('');
    setDescription('');
    setPriority('medium');
    setDueDate('');
    setErr('');
  };

  return (
    <Modal open={open} onClose={onClose} title="Поставить задачу">
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl">
            <AlertCircle size={16} /> {err}
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Учитель *</label>
          <select
            value={teacherId}
            onChange={(e) => setTeacherId(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          >
            <option value="">Выберите учителя</option>
            {teachers.map((t) => (
              <option key={t.id} value={t.id}>{t.full_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Название *</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Подготовить отчёт..."
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Описание</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            placeholder="Детали задачи..."
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Приоритет</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="low">Низкий</option>
            <option value="medium">Средний</option>
            <option value="high">Высокий</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Срок выполнения</label>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckSquare size={16} />}
          {saving ? 'Сохранение...' : 'Поставить задачу'}
        </button>
      </form>
    </Modal>
  );
};

// ─── Edit schedule item modal (ручная правка любой пары менеджером) ──
const EditScheduleModal: React.FC<{
  item: ScheduleItem | null;
  teachers: UserType[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ item, teachers, onClose, onSaved }) => {
  const [form, setForm] = useState({
    title: '', start_time: '09:00', end_time: '10:00', group_name: '', room: '',
    dateOnly: false, dateValue: '', weeks: '', owner: '',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!item) return;
    setForm({
      title: item.title, start_time: item.start_time, end_time: item.end_time,
      group_name: item.group_name, room: item.room,
      dateOnly: !!item.event_date, dateValue: item.event_date || '',
      weeks: item.weeks || '', owner: item.user_id,
    });
    setErr('');
  }, [item]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!item) return;
    if (form.dateOnly && !form.dateValue) { setErr('Укажите дату'); return; }
    setSaving(true);
    setErr('');
    try {
      const payload: Record<string, unknown> = {
        title: form.title,
        start_time: form.start_time, end_time: form.end_time,
        group_name: form.group_name, room: form.room,
        event_date: form.dateOnly ? form.dateValue : '',
        weeks: form.dateOnly ? '' : form.weeks.trim(),
      };
      if (!form.dateOnly) payload.day_of_week = item.day_of_week;
      if (form.owner && form.owner !== item.user_id) payload.user_id = form.owner;
      await api.updateSchedule(item.id, payload as Parameters<typeof api.updateSchedule>[1]);
      onSaved();
    } catch (ex: any) {
      setErr(ex?.response?.data?.detail || 'Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={!!item} onClose={onClose} title="Правка записи расписания">
      <form onSubmit={submit} className="space-y-3">
        {err && <div className="text-sm text-red-600 bg-red-50 p-2 rounded-lg">{err}</div>}
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required
          className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        <div className="grid grid-cols-2 gap-3">
          <input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })}
            className="border border-gray-200 rounded-xl px-3 py-2 text-sm" />
          <input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })}
            className="border border-gray-200 rounded-xl px-3 py-2 text-sm" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <input value={form.group_name} onChange={(e) => setForm({ ...form, group_name: e.target.value })} placeholder="Группа"
            className="border border-gray-200 rounded-xl px-3 py-2 text-sm" />
          <input value={form.room} onChange={(e) => setForm({ ...form, room: e.target.value })} placeholder="Кабинет"
            className="border border-gray-200 rounded-xl px-3 py-2 text-sm" />
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <button type="button" onClick={() => setForm({ ...form, dateOnly: false })}
            className={`px-2 py-1.5 rounded-lg text-xs font-medium border ${!form.dateOnly ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-200'}`}>
            Каждую неделю ({DAYS_SHORT[item?.day_of_week ?? 0]})
          </button>
          <button type="button" onClick={() => setForm({ ...form, dateOnly: true, dateValue: form.dateValue || item?.event_date || '' })}
            className={`px-2 py-1.5 rounded-lg text-xs font-medium border ${form.dateOnly ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-200'}`}>
            На конкретную дату
          </button>
        </div>
        {form.dateOnly ? (
          <input type="date" value={form.dateValue} onChange={(e) => setForm({ ...form, dateValue: e.target.value })}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm" />
        ) : (
          <input value={form.weeks} onChange={(e) => setForm({ ...form, weeks: e.target.value })}
            placeholder="Фильтр недель (пусто = все): 3,7 · 2 по 12 · верх/низ"
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-xs" />
        )}
        <div>
          <label className="block text-xs text-gray-500 mb-1">Преподаватель (перенос — если выбрать другого)</label>
          <select value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm">
            {teachers.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
          </select>
        </div>
        <div className="flex gap-2 pt-1">
          <button type="submit" disabled={saving}
            className="flex-1 py-2 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
          <button type="button" onClick={onClose} className="py-2 px-4 bg-gray-100 text-sm rounded-xl">Отмена</button>
        </div>
      </form>
    </Modal>
  );
};

export default TeachersView;