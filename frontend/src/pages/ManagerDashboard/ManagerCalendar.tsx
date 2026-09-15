import React, { useState, useEffect, useMemo } from 'react'
import {
  ChevronLeft, ChevronRight, Users, BookOpen, CheckSquare,
  Clock, MapPin, AlertCircle, CheckCircle2, Circle, X,
} from 'lucide-react'
import * as api from '../../api/client'
import type { ManagerCalendarResponse } from '../../api/client'
import { MONTHS_NOMINATIVE } from '../../utils/constants'

const pad = (n: number) => String(n).padStart(2, '0')

export default function ManagerCalendar() {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)
  const [teacherId, setTeacherId] = useState<string>('')
  const [data, setData] = useState<ManagerCalendarResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedDate, setSelectedDate] = useState<string>(
    `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
  )

  useEffect(() => { load() }, [year, month, teacherId])

  async function load() {
    setLoading(true)
    try {
      setData(await api.getManagerCalendar(year, month, teacherId || undefined))
    } catch (e) {
      console.error(e)
    } finally { setLoading(false) }
  }

  const dayMap = useMemo(() => {
    const m: Record<string, ManagerCalendarResponse['days'][0]> = {}
    data?.days.forEach(d => { m[d.date] = d })
    return m
  }, [data])

  const grid = useMemo(() => {
    const firstDay = new Date(year, month - 1, 1)
    const startOffset = (firstDay.getDay() + 6) % 7
    const daysInMonth = new Date(year, month, 0).getDate()
    const cells: Array<{ iso: string; day: number } | null> = []
    for (let i = 0; i < startOffset; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push({ iso: `${year}-${pad(month)}-${pad(d)}`, day: d })
    }
    while (cells.length % 7 !== 0) cells.push(null)
    return cells
  }, [year, month])

  const selected = dayMap[selectedDate]
  const todayISO = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1)
  }

  // Месячные итоги по выбранному фильтру
  const monthTotals = useMemo(() => {
    let lessons = 0
    const lessonsSeen = new Set<string>()
    const tasksSeen = new Set<string>()
    data?.days.forEach(d => {
      d.lessons.forEach(l => { if (!lessonsSeen.has(l.id)) { lessonsSeen.add(l.id); lessons++ } })
      d.tasks.forEach(t => tasksSeen.add(t.id))
    })
    return { lessons, tasks: tasksSeen.size }
  }, [data])

  if (loading && !data) {
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
          <h2 className="text-xl font-bold text-gray-800">Календарь преподавателей</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {teacherId
              ? `Пары и задачи: ${data?.teachers[0]?.full_name ?? ''}`
              : `Все преподаватели · ${monthTotals.lessons} пар, ${monthTotals.tasks} задач за месяц`}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Фильтр по преподавателю */}
          <div className="relative">
            <Users size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <select
              value={teacherId}
              onChange={e => setTeacherId(e.target.value)}
              className="pl-8 pr-8 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500 bg-white max-w-[240px]"
            >
              <option value="">Все преподаватели</option>
              {data?.teachers.map(t => (
                <option key={t.id} value={t.id}>{t.full_name}</option>
              ))}
            </select>
          </div>

          {/* Переключатель месяца */}
          <div className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg px-1 py-1">
            <button onClick={prevMonth} className="p-1.5 hover:bg-gray-100 rounded-md transition">
              <ChevronLeft size={16} className="text-gray-600" />
            </button>
            <span className="px-2 text-sm font-medium text-gray-700 min-w-[130px] text-center">
              {MONTHS_NOMINATIVE[month - 1]} {year}
            </span>
            <button onClick={nextMonth} className="p-1.5 hover:bg-gray-100 rounded-md transition">
              <ChevronRight size={16} className="text-gray-600" />
            </button>
          </div>

          <button
            onClick={() => {
              setYear(today.getFullYear()); setMonth(today.getMonth() + 1)
              setSelectedDate(todayISO)
            }}
            className="text-xs px-3 py-2 bg-indigo-50 text-indigo-600 rounded-lg hover:bg-indigo-100 transition"
          >
            Сегодня
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* Сетка календаря */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-200 p-4">
          <div className="grid grid-cols-7 gap-1 mb-2">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(d => (
              <div key={d} className="text-center text-xs font-semibold text-gray-400 py-1">{d}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {grid.map((cell, i) => {
              if (!cell) return <div key={`e${i}`} className="min-h-[68px]" />

              const entry = dayMap[cell.iso]
              const lessons = entry?.lessons.length ?? 0
              const tasks = entry?.tasks.length ?? 0
              const isToday = cell.iso === todayISO
              const isSelected = cell.iso === selectedDate
              const hasOverdue = entry?.tasks.some(t => t.status !== 'done' && t.due_date && t.due_date < todayISO) ?? false

              return (
                <button
                  key={cell.iso}
                  onClick={() => setSelectedDate(cell.iso)}
                  className={`min-h-[68px] rounded-lg p-1.5 text-left transition border flex flex-col ${
                    isSelected
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : isToday
                        ? 'bg-indigo-50 border-indigo-300'
                        : 'border-gray-100 hover:bg-gray-50'
                  }`}
                >
                  <span className={`text-xs font-medium ${
                    isSelected ? 'text-white' : isToday ? 'text-indigo-600' : 'text-gray-700'
                  }`}>{cell.day}</span>

                  {lessons > 0 && (
                    <span className={`text-[10px] mt-0.5 flex items-center gap-0.5 ${
                      isSelected ? 'text-indigo-100' : 'text-blue-600'
                    }`}>
                      <BookOpen size={9} /> {lessons}
                    </span>
                  )}
                  {tasks > 0 && (
                    <span className={`text-[10px] flex items-center gap-0.5 ${
                      isSelected ? 'text-indigo-100' : hasOverdue ? 'text-red-500' : 'text-green-600'
                    }`}>
                      <CheckSquare size={9} /> {tasks}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-4 mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
            <span className="flex items-center gap-1"><BookOpen size={11} className="text-blue-600" /> пары</span>
            <span className="flex items-center gap-1"><CheckSquare size={11} className="text-green-600" /> задачи</span>
            <span className="flex items-center gap-1"><AlertCircle size={11} className="text-red-500" /> просрочено</span>
          </div>
        </div>

        {/* Детали дня */}
        <div className="bg-white rounded-2xl border border-gray-200 p-4">
          <h3 className="font-semibold text-gray-800 text-sm mb-3">
            {(() => {
              const [y, m, d] = selectedDate.split('-').map(Number)
              return `${d} ${MONTHS_NOMINATIVE[m - 1].toLowerCase()} ${y}`
            })()}
          </h3>

          <div className="space-y-4 max-h-[520px] overflow-y-auto">
            {/* Пары */}
            <div>
              <h4 className="text-[11px] font-semibold text-gray-400 uppercase mb-2 flex items-center gap-1">
                <BookOpen size={11} /> Пары ({selected?.lessons.length ?? 0})
              </h4>
              {!selected?.lessons.length && (
                <p className="text-xs text-gray-400 py-2">Пар нет</p>
              )}
              <div className="space-y-1.5">
                {selected?.lessons.map(l => (
                  <div key={l.id + l.teacher_id} className="border-l-4 border-l-blue-400 bg-blue-50/40 rounded-lg p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-xs text-gray-800 truncate">{l.title || 'Пара'}</span>
                      <span className="text-[10px] text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded shrink-0">
                        {l.start_time}–{l.end_time}
                      </span>
                    </div>
                    <div className="text-[10px] text-indigo-600 mt-1 font-medium">{l.teacher_name}</div>
                    <div className="flex items-center gap-2 text-[10px] text-gray-500 mt-0.5 flex-wrap">
                      {l.group_name && <span className="flex items-center gap-0.5"><Users size={9} />{l.group_name}</span>}
                      {l.room && <span className="flex items-center gap-0.5"><MapPin size={9} />{l.room}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Задачи */}
            <div>
              <h4 className="text-[11px] font-semibold text-gray-400 uppercase mb-2 flex items-center gap-1">
                <CheckSquare size={11} /> Задачи ({selected?.tasks.length ?? 0})
              </h4>
              {!selected?.tasks.length && (
                <p className="text-xs text-gray-400 py-2">Задач нет</p>
              )}
              <div className="space-y-1.5">
                {selected?.tasks.map(t => {
                  const overdue = t.status !== 'done' && t.due_date && t.due_date < todayISO
                  return (
                    <div key={t.id + t.teacher_id} className={`border-l-4 rounded-lg p-2 ${
                      t.status === 'done' ? 'border-l-green-400 bg-green-50/40'
                      : overdue ? 'border-l-red-400 bg-red-50/40'
                      : 'border-l-amber-400 bg-amber-50/40'
                    }`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-xs text-gray-800 truncate">{t.title}</span>
                        <span className="shrink-0">
                          {t.status === 'done'
                            ? <CheckCircle2 size={12} className="text-green-500" />
                            : overdue
                              ? <AlertCircle size={12} className="text-red-500" />
                              : <Circle size={12} className="text-amber-500" />}
                        </span>
                      </div>
                      <div className="text-[10px] text-indigo-600 mt-1 font-medium">{t.teacher_name}</div>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        {t.scope === 'month' && t.due_month ? `Месяц ${t.due_month}` :
                         t.scope === 'year' && t.due_year ? `${t.due_year} год` :
                         t.due_date ? `до ${t.due_date.split('-').reverse().join('.')}` : 'Без срока'}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}