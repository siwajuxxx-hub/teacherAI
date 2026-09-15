import React, { useState, useEffect, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Plus, X, Trash2, Clock, MapPin, Users, Flag, AlertCircle } from 'lucide-react';
import * as api from '../../api/client';
import type { ScheduleItem, TaskItem, ScheduleCreatePayload } from '../../types';
import { DAYS_OF_WEEK, DAYS_SHORT, SCHEDULE_TYPES, TASK_STATUSES, TASK_SCOPES, MONTHS_NOMINATIVE } from '../../utils/constants';

const MONTH_NAMES = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];

function getMonthDays(year: number, month: number): (Date | null)[] {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startOffset = (firstDay.getDay() + 6) % 7;
  const days: (Date | null)[] = [];
  for (let i = 0; i < startOffset; i++) days.push(null);
  for (let d = 1; d <= lastDay.getDate(); d++) days.push(new Date(year, month, d));
  return days;
}

function fmtDate(d: Date | null): string {
  if (!d) return '';
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function sameDay(d1: Date, d2: Date): boolean {
  return d1.getFullYear() === d2.getFullYear() && d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate();
}

const TYPE_COLORS: Record<string, string> = {
  lesson: 'bg-blue-100 border-blue-300 text-blue-800',
  meeting: 'bg-red-100 border-red-300 text-red-800',
  other: 'bg-gray-100 border-gray-300 text-gray-800',
};

const SCOPE_CLASSES: Record<string, string> = {
  day: 'border-l-indigo-400',
  month: 'border-l-violet-500',
  year: 'border-l-amber-500',
  none: 'border-l-gray-300',
};

export default function CalendarTab() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState<Date>(today);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingItem, setEditingItem] = useState<ScheduleItem | null>(null);
  const [addTaskMode, setAddTaskMode] = useState(false);

  const [form, setForm] = useState({ title:'', start_time:'09:00', end_time:'10:30', group_name:'', room:'', type:'lesson' as 'lesson' | 'meeting' | 'other' });
  const [taskForm, setTaskForm] = useState({
    title: '', description: '', scope: 'day' as 'day' | 'month' | 'year',
    due_date: fmtDate(selectedDate) || '',
    due_month: (fmtDate(selectedDate) || '').slice(0, 7),
    due_year: String(today.getFullYear()),
  });

  useEffect(() => {
    loadData();
    // Обновляем при изменениях из чата AI
    const onChange = () => loadData();
    window.addEventListener('data-changed', onChange);
    window.addEventListener('focus', onChange);
    return () => {
      window.removeEventListener('data-changed', onChange);
      window.removeEventListener('focus', onChange);
    };
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [s, t] = await Promise.all([api.getMySchedule(), api.getMyTasks()]);
      setSchedule(s);
      setTasks(t);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }

  const days = useMemo(() => getMonthDays(year, month), [year, month]);

  // Расписание на выбранный день — сопоставляем день недели
  const selectedDayOfWeek = useMemo(() => {
    const d = selectedDate.getDay();
    return d === 0 ? 6 : d - 1;
  }, [selectedDate]);

  const daySchedule = useMemo(() => {
    return schedule.filter(s => s.day_of_week === selectedDayOfWeek);
  }, [schedule, selectedDayOfWeek]);

  const dayTasks = useMemo(() => {
    const iso = fmtDate(selectedDate);
    return tasks.filter(t => {
      if (t.due_date) return t.due_date === iso;
      // Задачи на месяц/год видны в каждом дне своего периода
      if (t.scope === 'month' && t.due_month) return iso.startsWith(t.due_month);
      if (t.scope === 'year' && t.due_year) return iso.startsWith(String(t.due_year));
      return false;
    });
  }, [tasks, selectedDate]);

  // События текущего месяца для точек
  const monthEvents = useMemo(() => {
    const map: Record<string, { sched: number; tasks: number }> = {};
    schedule.forEach(s => {
      const key = s.day_of_week;
      if (!map[String(key)]) map[String(key)] = { sched: 0, tasks: 0 };
      map[String(key)].sched++;
    });
    tasks.forEach(t => {
      if (t.due_date) {
        map[t.due_date] = map[t.due_date] || { sched: 0, tasks: 0 };
        map[t.due_date].tasks++;
      } else if (t.scope === 'month' && t.due_month) {
        // Отмечаем последний день месяца
        const [y, m] = t.due_month.split('-').map(Number)
        const last = new Date(y, m, 0)
        const key = fmtDate(last)
        map[key] = map[key] || { sched: 0, tasks: 0 }
        map[key].tasks++
      } else if (t.scope === 'year' && t.due_year) {
        const key = `${t.due_year}-12-31`
        map[key] = map[key] || { sched: 0, tasks: 0 }
        map[key].tasks++
      }
    });
    return map;
  }, [schedule, tasks]);

  function prevMonth() { if (month === 0) { setMonth(11); setYear(y => y - 1); } else setMonth(m => m - 1); }
  function nextMonth() { if (month === 11) { setMonth(0); setYear(y => y + 1); } else setMonth(m => m + 1); }

  async function handleSaveSchedule() {
    try {
      if (editingItem) {
        await api.updateSchedule(editingItem.id, form);
      } else {
        await api.createSchedule({ ...form, day_of_week: selectedDayOfWeek });
      }
      setShowAddModal(false);
      setEditingItem(null);
      await loadData();
    } catch (err: any) {
      alert('Ошибка: ' + (err.response?.data?.detail || err.message));
    }
  }

  async function handleDeleteSchedule(id: string) {
    if (!confirm('Удалить запись расписания?')) return;
    try { await api.deleteSchedule(id); await loadData(); } catch {} 
  }

  async function handleSaveTask() {
    try {
      await api.createTask({
        title: taskForm.title,
        description: taskForm.description,
        scope: taskForm.scope,
        due_date: taskForm.scope === 'day' ? (taskForm.due_date || null) : null,
        due_month: taskForm.scope === 'month' ? (taskForm.due_month || null) : null,
        due_year: taskForm.scope === 'year' ? (Number(taskForm.due_year) || null) : null,
      });
      setAddTaskMode(false);
      setTaskForm({
        title: '', description: '', scope: 'day',
        due_date: fmtDate(selectedDate) || '',
        due_month: (fmtDate(selectedDate) || '').slice(0, 7),
        due_year: String(today.getFullYear()),
      });
      await loadData();
      window.dispatchEvent(new CustomEvent('data-changed'));
    } catch (err: any) {
      alert('Ошибка: ' + (err.response?.data?.detail || err.message));
    }
  }

  async function handleTaskStatus(taskId: string, status: string) {
    try {
      await api.updateTaskStatus(taskId, status);
      await loadData();
    } catch {}
  }

  async function handleDeleteTask(id: string) {
    if (!confirm('Удалить задачу?')) return;
    try { await api.deleteTask(id); await loadData(); } catch {}
  }

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin h-8 w-8 border-2 border-indigo-600 border-t-transparent rounded-full" /></div>;

  return (
    <div className="max-w-6xl mx-auto flex flex-col lg:flex-row gap-4 lg:h-[calc(100dvh-12rem)]">
      {/* Левая часть — календарь месяц */}
      <div className="w-full lg:w-80 lg:flex-shrink-0 bg-white rounded-xl border border-gray-200 p-3 sm:p-4 lg:overflow-auto">
        <div className="flex items-center justify-between mb-3">
          <button onClick={prevMonth} className="p-1 hover:bg-gray-100 rounded"><ChevronLeft size={18} /></button>
          <h3 className="font-semibold text-gray-800">{MONTH_NAMES[month]} {year}</h3>
          <button onClick={nextMonth} className="p-1 hover:bg-gray-100 rounded"><ChevronRight size={18} /></button>
        </div>

        {/* Дни недели */}
        <div className="grid grid-cols-7 gap-1 mb-1">
          {DAYS_SHORT.map((d, i) => <div key={i} className="text-center text-xs font-medium text-gray-400 py-1">{d}</div>)}
        </div>

        {/* Дни месяца */}
        <div className="grid grid-cols-7 gap-1">
          {days.map((d, idx) => {
            if (!d) return <div key={`e${idx}`} className="aspect-square" />;
            const ds = fmtDate(d);
            const events = monthEvents[ds] || { sched: 0, tasks: 0 };
            const isToday = sameDay(d, today);
            const isSelected = sameDay(d, selectedDate);

            return (
              <button
                key={ds}
                onClick={() => setSelectedDate(d)}
                className={`aspect-square flex flex-col items-center justify-center rounded-lg text-sm relative transition ${
                  isSelected ? 'bg-indigo-600 text-white shadow-md' :
                  isToday ? 'bg-indigo-100 text-indigo-700 font-bold' :
                  'hover:bg-gray-100 text-gray-700'
                }`}
              >
                <span className="text-xs">{d.getDate()}</span>
                {/* Индикаторы */}
                <div className="flex gap-0.5 mt-0.5">
                  {events.sched > 0 && <span className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-white' : 'bg-blue-500'}`} />}
                  {events.tasks > 0 && <span className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-white' : 'bg-red-500'}`} />}
                </div>
              </button>
            );
          })}
        </div>

        {/* Легенда */}
        <div className="flex gap-3 mt-3 pt-3 border-t border-gray-100 text-xs text-gray-400">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500" /> Пары</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Задачи</span>
        </div>
      </div>

      {/* Правая часть — детали дня */}
      <div className="flex-1 min-h-0 bg-white rounded-xl border border-gray-200 p-4 sm:p-5 overflow-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-800">
            {selectedDate.toLocaleDateString('ru', { weekday: 'long', day: 'numeric', month: 'long' })}
          </h2>
          <div className="flex gap-2">
            <button onClick={() => setAddTaskMode(true)} className="flex items-center gap-1 px-3 py-1.5 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 transition">
              <Flag size={14} /> Задача
            </button>
            <button onClick={() => { setEditingItem(null); setForm({ title:'', start_time:'09:00', end_time:'10:30', group_name:'', room:'', type:'lesson' }); setShowAddModal(true); }}
              className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 transition">
              <Plus size={14} /> Занятие
            </button>
          </div>
        </div>

        {/* Секция: Расписание */}
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-gray-500 uppercase mb-3 flex items-center gap-2">
            <Clock size={14} /> Расписание
          </h3>
          {daySchedule.length === 0 ? (
            <p className="text-sm text-gray-400 py-3">Нет занятий на этот день</p>
          ) : (
            <div className="space-y-2">
              {daySchedule.sort((a,b) => a.start_time.localeCompare(b.start_time)).map(s => (
                <div key={s.id} className={`flex items-center gap-3 p-3 rounded-xl border ${TYPE_COLORS[s.type]} hover:shadow-sm transition cursor-pointer`}
                  onClick={() => { setEditingItem(s); setForm({title:s.title,start_time:s.start_time,end_time:s.end_time,group_name:s.group_name,room:s.room,type:s.type}); setShowAddModal(true); }}>
                  <div className="text-sm font-bold w-14 text-center">
                    {s.start_time} <br /> <span className="text-xs opacity-60">{s.end_time}</span>
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-sm">{s.title}</div>
                    <div className="flex gap-3 text-xs opacity-70 mt-0.5">
                      {s.group_name && <span className="flex items-center gap-1"><Users size={10} /> {s.group_name}</span>}
                      {s.room && <span className="flex items-center gap-1"><MapPin size={10} /> {s.room}</span>}
                    </div>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white/60">{SCHEDULE_TYPES[s.type]}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Секция: Задачи на день */}
        <div>
          <h3 className="text-sm font-semibold text-gray-500 uppercase mb-3 flex items-center gap-2">
            <Flag size={14} /> Задачи на этот день
          </h3>
          {dayTasks.length === 0 ? (
            <p className="text-sm text-gray-400 py-3">Нет задач на этот день</p>
          ) : (
            <div className="space-y-2">
              {dayTasks.map(t => {
                const isOverdue = t.status === 'overdue' || (t.status !== 'done' && t.due_date && t.due_date < new Date().toISOString().split('T')[0]);
                return (
                  <div key={t.id} className={`flex items-center gap-3 p-3 rounded-xl border-l-4 bg-white border border-gray-200 hover:shadow-sm transition ${SCOPE_CLASSES[t.scope] ?? SCOPE_CLASSES.none}`}>
                    <div className="flex-1">
                      <div className="font-medium text-sm">{t.title}</div>
                      {t.description && <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">{t.description}</div>}
                      <div className="flex gap-2 mt-1 flex-wrap">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                          t.scope === 'month' ? 'bg-violet-100 text-violet-700' :
                          t.scope === 'year' ? 'bg-amber-100 text-amber-700' :
                          t.scope === 'day' ? 'bg-indigo-100 text-indigo-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {t.scope === 'month' && t.due_month
                            ? `${MONTHS_NOMINATIVE[Number(t.due_month.slice(5, 7)) - 1]} ${t.due_month.slice(0, 4)}`
                            : t.scope === 'year' && t.due_year
                              ? `${t.due_year} год`
                              : TASK_SCOPES[t.scope] || 'Срок'}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                          t.status === 'done' ? 'bg-green-100 text-green-700' :
                          isOverdue ? 'bg-red-100 text-red-700' :
                          t.status === 'in_progress' ? 'bg-blue-100 text-blue-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>{t.status === 'overdue' || isOverdue ? 'Просрочено' : TASK_STATUSES[t.status] || t.status}</span>
                        {t.assigned_by && <span className="text-xs text-purple-500">От управляющего</span>}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      {t.status !== 'done' && (
                        <button onClick={() => handleTaskStatus(t.id, 'done')} className="text-xs px-2 py-1 bg-green-50 text-green-700 rounded hover:bg-green-100">Готово</button>
                      )}
                      <button onClick={() => handleDeleteTask(t.id)} className="text-xs px-2 py-1 bg-red-50 text-red-600 rounded hover:bg-red-100"><Trash2 size={12} /></button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Модальное окно добавления/редактирования занятия */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowAddModal(false)}>
          <div className="bg-white rounded-2xl p-4 sm:p-6 w-full max-w-md mx-4 max-h-[90dvh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">{editingItem ? 'Редактировать занятие' : 'Добавить занятие'}</h3>
              <button onClick={() => setShowAddModal(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            <div className="space-y-3">
              <input type="text" value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="Название" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500">Начало</label><input type="time" value={form.start_time} onChange={e => setForm({...form, start_time: e.target.value})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" /></div>
                <div><label className="text-xs text-gray-500">Конец</label><input type="time" value={form.end_time} onChange={e => setForm({...form, end_time: e.target.value})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" /></div>
              </div>
              <select value={form.type} onChange={e => setForm({...form, type: e.target.value as any})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="lesson">Занятие</option><option value="meeting">Собрание</option><option value="other">Прочее</option>
              </select>
              <input type="text" value={form.group_name} onChange={e => setForm({...form, group_name: e.target.value})} placeholder="Группа" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
              <input type="text" value={form.room} onChange={e => setForm({...form, room: e.target.value})} placeholder="Аудитория" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={handleSaveSchedule} className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">Сохранить</button>
              {editingItem && <button onClick={() => { handleDeleteSchedule(editingItem.id); setShowAddModal(false); }} className="py-2 px-3 bg-red-50 text-red-600 rounded-lg hover:bg-red-100"><Trash2 size={16} /></button>}
              <button onClick={() => setShowAddModal(false)} className="py-2 px-4 bg-gray-100 rounded-lg text-sm">Отмена</button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно добавления задачи */}
      {addTaskMode && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setAddTaskMode(false)}>
          <div className="bg-white rounded-2xl p-4 sm:p-6 w-full max-w-md mx-4 max-h-[90dvh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Новая задача на {fmtDate(selectedDate)}</h3>
              <button onClick={() => setAddTaskMode(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            <div className="space-y-3">
              <input type="text" value={taskForm.title} onChange={e => setTaskForm({...taskForm, title: e.target.value})} placeholder="Название задачи" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-purple-500" />
              <textarea value={taskForm.description} onChange={e => setTaskForm({...taskForm, description: e.target.value})} placeholder="Описание" rows={2} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-purple-500 resize-none" />
              <div className="grid grid-cols-2 gap-3">
                <select value={taskForm.scope} onChange={e => setTaskForm({...taskForm, scope: e.target.value as any})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-purple-500">
                  <option value="day">На конкретный день</option>
                  <option value="month">На месяц</option>
                  <option value="year">На год</option>
                </select>
                {taskForm.scope === 'day' ? (
                  <input type="date" value={taskForm.due_date} onChange={e => setTaskForm({...taskForm, due_date: e.target.value})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-purple-500" />
                ) : taskForm.scope === 'month' ? (
                  <input type="month" value={taskForm.due_month} onChange={e => setTaskForm({...taskForm, due_month: e.target.value})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-purple-500" />
                ) : (
                  <select value={taskForm.due_year} onChange={e => setTaskForm({...taskForm, due_year: e.target.value})} className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-purple-500">
                    {Array.from({ length: 8 }, (_, i) => today.getFullYear() - 2 + i).map(y => (
                      <option key={y} value={y}>{y} год</option>
                    ))}
                  </select>
                )}
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={handleSaveTask} className="flex-1 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700">Добавить</button>
              <button onClick={() => setAddTaskMode(false)} className="py-2 px-4 bg-gray-100 rounded-lg text-sm">Отмена</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}