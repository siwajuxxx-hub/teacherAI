import React, { useState, useEffect, useMemo } from 'react'
import {
  Plus, X, Trash2, Calendar, ChevronLeft, ChevronRight,
  AlertCircle, CheckCircle2, Circle, Clock, Briefcase,
} from 'lucide-react'
import * as api from '../../api/client'
import type { TaskItem, TaskCreatePayload, TaskScope } from '../../types'
import { TASK_SCOPES, MONTHS_NOMINATIVE } from '../../utils/constants'

// ─── Вспомогательные функции ─────────────────────────────────────

const pad = (n: number) => String(n).padStart(2, '0')
const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const todayISO = () => toISO(new Date())

/** Последний день срока задачи — для просрочки и сортировки. */
function effectiveDue(t: TaskItem): string | null {
  if (t.due_date) return t.due_date
  if (t.due_month) {
    const [y, m] = t.due_month.split('-').map(Number)
    const last = new Date(y, m, 0).getDate()
    return `${t.due_month}-${pad(last)}`
  }
  if (t.due_year) return `${t.due_year}-12-31`
  return null
}

function isOverdue(t: TaskItem): boolean {
  if (t.status === 'done') return false
  const due = effectiveDue(t)
  return !!due && due < todayISO()
}

/** Человекочитаемая подпись срока. */
function dueLabel(t: TaskItem): string {
  if (t.scope === 'month' && t.due_month) {
    const [y, m] = t.due_month.split('-').map(Number)
    return `${MONTHS_NOMINATIVE[m - 1]} ${y}`
  }
  if (t.scope === 'year' && t.due_year) return `${t.due_year} год`
  if (t.due_date) {
    const [y, m, d] = t.due_date.split('-').map(Number)
    return `${pad(d)}.${pad(m)}.${y}`
  }
  return 'Без срока'
}

/** Задача попадает в указанный день? */
function taskMatchesDay(t: TaskItem, iso: string): boolean {
  if (t.due_date) return t.due_date === iso
  // Задачи на месяц/год показываются в каждом дне соответствующего периода
  if (t.scope === 'month' && t.due_month) return iso.startsWith(t.due_month)
  if (t.scope === 'year' && t.due_year) return iso.startsWith(String(t.due_year))
  return false
}

const STATUS_META: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
  pending: { label: 'К выполнению', icon: <Circle size={13} />, cls: 'bg-gray-100 text-gray-600' },
  in_progress: { label: 'В работе', icon: <Clock size={13} />, cls: 'bg-blue-100 text-blue-700' },
  done: { label: 'Готово', icon: <CheckCircle2 size={13} />, cls: 'bg-green-100 text-green-700' },
  overdue: { label: 'Просрочено', icon: <AlertCircle size={13} />, cls: 'bg-red-100 text-red-700' },
}

type ViewMode = 'calendar' | 'list'

export default function NotesTab() {
  const today = new Date()

  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null)
  const [view, setView] = useState<ViewMode>('calendar')

  // Календарь
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [selectedDate, setSelectedDate] = useState<string>(todayISO())

  // Фильтр списка
  const [listFilter, setListFilter] = useState<'all' | 'past' | 'future' | 'overdue' | 'done'>('all')

  const [form, setForm] = useState<{
    title: string; description: string; scope: TaskScope;
    due_date: string; due_month: string; due_year: string;
  }>({
    title: '', description: '', scope: 'day',
    due_date: todayISO(), due_month: `${today.getFullYear()}-${pad(today.getMonth() + 1)}`,
    due_year: String(today.getFullYear()),
  })
  const [saving, setSaving] = useState(false)

  // ── Загрузка ──────────────────────────────────────────────
  useEffect(() => {
    loadTasks()
    const onChange = () => loadTasks()
    window.addEventListener('data-changed', onChange)
    window.addEventListener('focus', onChange)
    return () => {
      window.removeEventListener('data-changed', onChange)
      window.removeEventListener('focus', onChange)
    }
  }, [])

  async function loadTasks() {
    setLoading(true)
    try { setTasks(await api.getMyTasks()) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  // ── Модальное окно ────────────────────────────────────────
  function openAddModal(presetISO?: string) {
    const iso = presetISO || selectedDate || todayISO()
    setEditingTask(null)
    setForm({
      title: '', description: '', scope: 'day',
      due_date: iso,
      due_month: iso.slice(0, 7),
      due_year: iso.slice(0, 4),
    })
    setShowModal(true)
  }

  function openEditModal(task: TaskItem) {
    setEditingTask(task)
    const iso = task.due_date || selectedDate || todayISO()
    setForm({
      title: task.title,
      description: task.description,
      scope: task.scope || 'none',
      due_date: task.due_date || iso,
      due_month: task.due_month || iso.slice(0, 7),
      due_year: String(task.due_year || iso.slice(0, 4)),
    })
    setShowModal(true)
  }

  async function handleSave() {
    if (!form.title.trim()) return
    setSaving(true)
    try {
      const payload: TaskCreatePayload = {
        title: form.title.trim(),
        description: form.description,
        scope: form.scope,
        due_date: form.scope === 'day' ? form.due_date || null : null,
        due_month: form.scope === 'month' ? form.due_month || null : null,
        due_year: form.scope === 'year' ? Number(form.due_year) || null : null,
      }
      if (editingTask) {
        await api.updateTask(editingTask.id, payload)
      } else {
        await api.createTask(payload)
      }
      setShowModal(false)
      await loadTasks()
      window.dispatchEvent(new CustomEvent('data-changed'))
    } catch (err: any) {
      alert('Ошибка: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  async function handleStatusChange(taskId: string, newStatus: string) {
    try {
      await api.updateTaskStatus(taskId, newStatus)
      await loadTasks()
      window.dispatchEvent(new CustomEvent('data-changed'))
    } catch {}
  }

  async function handleDelete(id: string) {
    if (!confirm('Удалить задачу?')) return
    try {
      await api.deleteTask(id)
      await loadTasks()
      window.dispatchEvent(new CustomEvent('data-changed'))
    } catch {}
    setShowModal(false)
  }

  // ── Календарная сетка ─────────────────────────────────────
  const grid = useMemo(() => {
    const firstDay = new Date(year, month, 1)
    // Пн=0 … Вс=6
    const startOffset = (firstDay.getDay() + 6) % 7
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    const cells: Array<{ iso: string; day: number } | null> = []

    for (let i = 0; i < startOffset; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push({ iso: `${year}-${pad(month + 1)}-${pad(d)}`, day: d })
    }
    while (cells.length % 7 !== 0) cells.push(null)
    return cells
  }, [year, month])

  const tasksForDay = (iso: string) => tasks.filter(t => taskMatchesDay(t, iso))

  const selectedTasks = tasksForDay(selectedDate)

  // ── Списки прошлых / будущих ──────────────────────────────
  const filteredList = useMemo(() => {
    const t = todayISO()
    const list = tasks.filter(task => {
      const due = effectiveDue(task)
      switch (listFilter) {
        case 'overdue': return isOverdue(task)
        case 'done': return task.status === 'done'
        case 'past': return task.status !== 'done' && !!due && due < t
        case 'future': return !!due && due >= t
        default: return true
      }
    })
    return list.sort((a, b) => {
      // Незавершённые сначала, затем по сроку
      if ((a.status === 'done') !== (b.status === 'done')) return a.status === 'done' ? 1 : -1
      const da = effectiveDue(a) || '9999-99-99'
      const db = effectiveDue(b) || '9999-99-99'
      return da.localeCompare(db)
    })
  }, [tasks, listFilter])

  const stats = useMemo(() => ({
    total: tasks.length,
    overdue: tasks.filter(isOverdue).length,
    pending: tasks.filter(t => t.status === 'pending' || t.status === 'in_progress').length,
    done: tasks.filter(t => t.status === 'done').length,
  }), [tasks])

  const prevMonth = () => {
    if (month === 0) { setMonth(11); setYear(y => y - 1) } else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 11) { setMonth(0); setYear(y => y + 1) } else setMonth(m => m + 1)
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin h-8 w-8 border-2 border-indigo-600 border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Заголовок */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Заметки и задачи</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Всего {stats.total} · к выполнению {stats.pending} · просрочено {stats.overdue} · готово {stats.done}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Переключатель вида */}
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            <button
              onClick={() => setView('calendar')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                view === 'calendar' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Календарь
            </button>
            <button
              onClick={() => setView('list')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                view === 'list' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Список
            </button>
          </div>
          <button
            onClick={() => openAddModal()}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition text-sm"
          >
            <Plus size={16} /> Добавить задачу
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* ─── Календарь ─── */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-4">
            <button onClick={prevMonth} className="p-2 hover:bg-gray-100 rounded-lg transition">
              <ChevronLeft size={18} className="text-gray-600" />
            </button>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-gray-800">
                {MONTHS_NOMINATIVE[month]} {year}
              </h3>
              <button
                onClick={() => {
                  setYear(today.getFullYear())
                  setMonth(today.getMonth())
                  setSelectedDate(todayISO())
                }}
                className="text-xs px-2 py-1 bg-indigo-50 text-indigo-600 rounded-lg hover:bg-indigo-100 transition"
              >
                Сегодня
              </button>
            </div>
            <button onClick={nextMonth} className="p-2 hover:bg-gray-100 rounded-lg transition">
              <ChevronRight size={18} className="text-gray-600" />
            </button>
          </div>

          {/* Дни недели */}
          <div className="grid grid-cols-7 gap-1 mb-2">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(d => (
              <div key={d} className="text-center text-xs font-semibold text-gray-400 py-1">{d}</div>
            ))}
          </div>

          {/* Сетка */}
          <div className="grid grid-cols-7 gap-1">
            {grid.map((cell, i) => {
              if (!cell) return <div key={`e${i}`} className="aspect-square" />

              const dayTasks = tasksForDay(cell.iso)
              const isToday = cell.iso === todayISO()
              const isSelected = cell.iso === selectedDate
              const hasOverdue = dayTasks.some(isOverdue)
              const allDone = dayTasks.length > 0 && dayTasks.every(t => t.status === 'done')

              return (
                <button
                  key={cell.iso}
                  onClick={() => { setSelectedDate(cell.iso); setView('calendar') }}
                  className={`aspect-square rounded-lg p-1 flex flex-col items-center justify-start transition border ${
                    isSelected
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : isToday
                        ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
                        : 'border-transparent hover:bg-gray-50 text-gray-700'
                  }`}
                >
                  <span className={`text-xs font-medium ${isToday && !isSelected ? 'text-indigo-600' : ''}`}>
                    {cell.day}
                  </span>
                  {dayTasks.length > 0 && (
                    <span className="flex gap-0.5 mt-0.5 flex-wrap justify-center">
                      {hasOverdue && <span className="w-1.5 h-1.5 rounded-full bg-red-500" />}
                      {allDone && !hasOverdue && <span className="w-1.5 h-1.5 rounded-full bg-green-500" />}
                      {!hasOverdue && !allDone && <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-4 mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-indigo-400" /> есть задачи</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> просрочено</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> выполнено</span>
          </div>
        </div>

        {/* ─── Задачи выбранного дня ─── */}
        <div className="bg-white rounded-2xl border border-gray-200 p-4 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-800 text-sm">
              {(() => {
                const [y, m, d] = selectedDate.split('-').map(Number)
                return `${d} ${MONTHS_NOMINATIVE[m - 1].toLowerCase()} ${y}`
              })()}
            </h3>
            <button
              onClick={() => openAddModal(selectedDate)}
              className="p-1.5 hover:bg-indigo-50 rounded-lg transition text-indigo-600"
              title="Добавить задачу на этот день"
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto max-h-[420px]">
            {selectedTasks.length === 0 && (
              <p className="text-xs text-gray-400 text-center py-8">Задач на этот день нет</p>
            )}
            {selectedTasks.map(task => (
              <TaskCard
                key={task.id}
                task={task}
                onEdit={() => openEditModal(task)}
                onStatus={handleStatusChange}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ─── Список всех задач (прошлые/будущие) ─── */}
      {view === 'list' && (
        <div className="mt-4 bg-white rounded-2xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <Briefcase size={16} className="text-gray-400" />
            <h3 className="font-semibold text-gray-800 text-sm mr-2">Все задачи</h3>
            {([
              ['all', 'Все'],
              ['future', 'Будущие'],
              ['past', 'Прошедшие'],
              ['overdue', 'Просроченные'],
              ['done', 'Выполненные'],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setListFilter(key)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition ${
                  listFilter === key
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="space-y-2">
            {filteredList.length === 0 && (
              <p className="text-xs text-gray-400 text-center py-6">Задач нет</p>
            )}
            {filteredList.map(task => (
              <TaskCard
                key={task.id}
                task={task}
                showDue
                onEdit={() => openEditModal(task)}
                onStatus={handleStatusChange}
              />
            ))}
          </div>
        </div>
      )}

      {/* ─── Модальное окно ─── */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">{editingTask ? 'Редактировать задачу' : 'Новая задача'}</h3>
              <button onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Заголовок</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  placeholder="Что нужно сделать"
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Описание</label>
                <textarea
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  rows={3}
                  placeholder="Дополнительные детали (необязательно)"
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none resize-none"
                />
              </div>

              {/* Срок задачи */}
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Срок</label>
                <div className="grid grid-cols-4 gap-1.5 mb-2">
                  {(['day', 'month', 'year', 'none'] as TaskScope[]).map(s => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setForm({ ...form, scope: s })}
                      className={`px-2 py-1.5 rounded-lg text-xs font-medium transition ${
                        form.scope === s
                          ? 'bg-indigo-600 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {TASK_SCOPES[s]}
                    </button>
                  ))}
                </div>

                {form.scope === 'day' && (
                  <input
                    type="date"
                    value={form.due_date}
                    onChange={e => setForm({ ...form, due_date: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                )}

                {form.scope === 'month' && (
                  <input
                    type="month"
                    value={form.due_month}
                    onChange={e => setForm({ ...form, due_month: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                )}

                {form.scope === 'year' && (
                  <select
                    value={form.due_year}
                    onChange={e => setForm({ ...form, due_year: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  >
                    {Array.from({ length: 8 }, (_, i) => today.getFullYear() - 2 + i).map(y => (
                      <option key={y} value={y}>{y} год</option>
                    ))}
                  </select>
                )}

                {form.scope === 'none' && (
                  <p className="text-xs text-gray-400 px-1">Задача без срока — будет висеть в списке, пока не выполните.</p>
                )}
              </div>

              {editingTask?.assigned_by && (
                <div className="text-xs text-purple-600 bg-purple-50 p-2 rounded-lg">Задача от управляющего</div>
              )}
            </div>

            <div className="flex gap-2 mt-6">
              <button
                onClick={handleSave}
                disabled={saving || !form.title.trim()}
                className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:bg-indigo-300 transition"
              >
                {saving ? 'Сохранение…' : editingTask ? 'Сохранить' : 'Добавить'}
              </button>
              {editingTask && (
                <button
                  onClick={() => handleDelete(editingTask.id)}
                  className="py-2 px-3 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition"
                >
                  <Trash2 size={16} />
                </button>
              )}
              <button
                onClick={() => setShowModal(false)}
                className="py-2 px-4 bg-gray-100 text-gray-600 rounded-lg text-sm hover:bg-gray-200 transition"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Карточка задачи ─────────────────────────────────────────────
const TaskCard: React.FC<{
  task: TaskItem
  showDue?: boolean
  onEdit: () => void
  onStatus: (id: string, status: string) => void
}> = ({ task, showDue, onEdit, onStatus }) => {
  const overdue = isOverdue(task)
  const statusKey = overdue ? 'overdue' : task.status
  const meta = STATUS_META[statusKey] ?? STATUS_META.pending

  return (
    <div
      className={`bg-white rounded-lg p-3 border shadow-sm hover:shadow-md transition cursor-pointer ${
        overdue ? 'border-red-200 border-l-4 border-l-red-500' :
        task.status === 'done' ? 'border-green-200 border-l-4 border-l-green-500' :
        'border-gray-200 border-l-4 border-l-indigo-400'
      }`}
      onClick={onEdit}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className={`font-medium text-sm ${
          task.status === 'done' ? 'text-gray-400 line-through' : 'text-gray-800'
        }`}>
          {task.title}
        </h4>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium flex items-center gap-1 shrink-0 ${meta.cls}`}>
          {meta.icon}{meta.label}
        </span>
      </div>

      {task.description && (
        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{task.description}</p>
      )}

      <div className="flex items-center gap-2 mt-2 flex-wrap">
        <span className={`text-xs flex items-center gap-1 ${overdue ? 'text-red-500 font-medium' : 'text-gray-400'}`}>
          <Calendar size={11} /> {dueLabel(task)}
        </span>
        {task.assigned_by && (
          <span className="text-[10px] text-purple-500 bg-purple-50 px-1.5 py-0.5 rounded">
            От управляющего
          </span>
        )}
      </div>

      {task.status !== 'done' && (
        <div className="flex gap-1 mt-2 pt-2 border-t border-gray-100" onClick={e => e.stopPropagation()}>
          {task.status !== 'in_progress' && (
            <button
              onClick={() => onStatus(task.id, 'in_progress')}
              className="text-[11px] px-2 py-1 bg-blue-50 text-blue-600 hover:bg-blue-100 rounded transition"
            >
              В работу
            </button>
          )}
          <button
            onClick={() => onStatus(task.id, 'done')}
            className="text-[11px] px-2 py-1 bg-green-50 text-green-600 hover:bg-green-100 rounded transition"
          >
            Выполнено
          </button>
        </div>
      )}

      {task.status === 'done' && (
        <div className="flex gap-1 mt-2 pt-2 border-t border-gray-100" onClick={e => e.stopPropagation()}>
          <button
            onClick={() => onStatus(task.id, 'pending')}
            className="text-[11px] px-2 py-1 bg-gray-50 text-gray-500 hover:bg-gray-100 rounded transition"
          >
            Вернуть в работу
          </button>
        </div>
      )}
    </div>
  )
}
