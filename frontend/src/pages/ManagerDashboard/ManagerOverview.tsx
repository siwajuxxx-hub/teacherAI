import React, { useState, useEffect, useMemo } from 'react'
import {
  Users, BookOpen, Clock, CheckSquare, AlertTriangle,
  TrendingUp, ChevronLeft, ChevronRight, Search, Award,
} from 'lucide-react'
import * as api from '../../api/client'
import type { TeacherStatsRow } from '../../api/client'
import { MONTHS_NOMINATIVE } from '../../utils/constants'

type SortKey = 'full_name' | 'hours_per_month' | 'lessons_per_month' | 'tasks_total' | 'completion_rate'

export default function ManagerOverview() {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)
  const [data, setData] = useState<api.OverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('hours_per_month')
  const [sortAsc, setSortAsc] = useState(false)

  useEffect(() => { load() }, [year, month])

  async function load() {
    setLoading(true); setError('')
    try {
      setData(await api.getOverview(year, month))
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки')
    } finally { setLoading(false) }
  }

  const rows = useMemo(() => {
    if (!data?.teachers) return []
    let list = data.teachers.filter(t =>
      !search || t.full_name.toLowerCase().includes(search.toLowerCase())
    )
    list = [...list].sort((a, b) => {
      const av = a[sortKey] as any, bv = b[sortKey] as any
      if (typeof av === 'string') return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av)
      return sortAsc ? av - bv : bv - av
    })
    return list
  }, [data, search, sortKey, sortAsc])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(false) }
  }

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1)
  }

  const maxHours = Math.max(1, ...rows.map(r => r.hours_per_month))

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin h-8 w-8 border-2 border-indigo-600 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
        Не удалось загрузить статистику: {error}
      </div>
    )
  }

  const t = data!.totals

  const cards = [
    { label: 'Преподавателей', value: t.teachers_total, sub: `${t.teachers_with_schedule} с расписанием`, icon: <Users size={18} />, cls: 'bg-indigo-50 text-indigo-600' },
    { label: 'Пар за месяц', value: t.lessons_per_month, sub: 'по расписанию', icon: <BookOpen size={18} />, cls: 'bg-blue-50 text-blue-600' },
    { label: 'Часов за месяц', value: t.hours_per_month, sub: 'учебная нагрузка', icon: <Clock size={18} />, cls: 'bg-violet-50 text-violet-600' },
    { label: 'Задач поставлено', value: t.tasks_total, sub: `${t.tasks_done} выполнено`, icon: <CheckSquare size={18} />, cls: 'bg-green-50 text-green-600' },
    { label: 'Просрочено', value: t.tasks_overdue, sub: 'требует внимания', icon: <AlertTriangle size={18} />, cls: 'bg-red-50 text-red-600' },
    { label: 'Выполнение', value: `${t.completion_rate}%`, sub: 'по задачам', icon: <TrendingUp size={18} />, cls: 'bg-amber-50 text-amber-600' },
  ]

  return (
    <div className="max-w-6xl mx-auto">
      {/* Заголовок */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Обзор</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Статистика преподавателей за {MONTHS_NOMINATIVE[month - 1].toLowerCase()} {year}
          </p>
        </div>
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
      </div>

      {/* Карточки итогов */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
        {cards.map(c => (
          <div key={c.label} className="bg-white rounded-xl border border-gray-200 p-3">
            <div className={`inline-flex p-2 rounded-lg mb-2 ${c.cls}`}>{c.icon}</div>
            <div className="text-xl font-bold text-gray-800">{c.value}</div>
            <div className="text-[11px] text-gray-500 mt-0.5 leading-tight">{c.label}</div>
            <div className="text-[10px] text-gray-400 mt-0.5">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Поиск */}
      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Поиск по ФИО преподавателя"
          className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      {/* Таблица */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr className="text-left text-xs text-gray-500 uppercase">
                <Th onClick={() => toggleSort('full_name')} active={sortKey === 'full_name'} asc={sortAsc}>Преподаватель</Th>
                <Th onClick={() => toggleSort('lessons_per_month')} active={sortKey === 'lessons_per_month'} asc={sortAsc}>Пар / мес</Th>
                <Th onClick={() => toggleSort('hours_per_month')} active={sortKey === 'hours_per_month'} asc={sortAsc}>Часов / мес</Th>
                <Th onClick={() => toggleSort('tasks_total')} active={sortKey === 'tasks_total'} asc={sortAsc}>Задач</Th>
                <Th>Выполнено</Th>
                <Th>Просрочено</Th>
                <Th onClick={() => toggleSort('completion_rate')} active={sortKey === 'completion_rate'} asc={sortAsc}>Выполнение</Th>
                <Th>Нагрузка</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 && (
                <tr><td colSpan={8} className="text-center text-gray-400 py-8 text-xs">Преподаватели не найдены</td></tr>
              )}
              {rows.map(r => (
                <tr key={r.id} className="hover:bg-gray-50 transition">
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-gray-800">{r.full_name}</div>
                    <div className="text-[10px] text-gray-400">{r.position || r.username}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    {r.has_schedule ? (
                      <span className="text-gray-800 font-medium">{r.lessons_per_month}</span>
                    ) : (
                      <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">нет расписания</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-gray-800">{r.hours_per_month}</td>
                  <td className="px-4 py-2.5 text-gray-600">{r.tasks_total}</td>
                  <td className="px-4 py-2.5 text-green-600">{r.tasks_done}</td>
                  <td className="px-4 py-2.5">
                    {r.tasks_overdue > 0
                      ? <span className="text-red-600 font-medium">{r.tasks_overdue}</span>
                      : <span className="text-gray-300">0</span>}
                  </td>
                  <td className="px-4 py-2.5">
                    {r.tasks_total > 0 ? (
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              r.completion_rate >= 70 ? 'bg-green-500' :
                              r.completion_rate >= 40 ? 'bg-amber-500' : 'bg-red-400'
                            }`}
                            style={{ width: `${r.completion_rate}%` }}
                          />
                        </div>
                        <span className="text-[11px] text-gray-500">{r.completion_rate}%</span>
                      </div>
                    ) : <span className="text-gray-300 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${(r.hours_per_month / maxHours) * 100}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Лучшие по нагрузке */}
      {rows.length > 1 && (
        <div className="mt-5 bg-white rounded-2xl border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <Award size={15} className="text-amber-500" /> Наибольшая нагрузка за месяц
          </h3>
          <div className="space-y-2">
            {[...rows].sort((a, b) => b.hours_per_month - a.hours_per_month).slice(0, 5).map((r, i) => (
              <div key={r.id} className="flex items-center gap-3 text-sm">
                <span className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center ${
                  i === 0 ? 'bg-amber-100 text-amber-700' :
                  i === 1 ? 'bg-gray-200 text-gray-600' :
                  i === 2 ? 'bg-orange-100 text-orange-700' : 'bg-gray-50 text-gray-400'
                }`}>{i + 1}</span>
                <span className="flex-1 text-gray-700">{r.full_name}</span>
                <span className="text-xs text-gray-500">{r.lessons_per_month} пар</span>
                <span className="text-xs font-medium text-indigo-600 w-16 text-right">{r.hours_per_month} ч</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const Th: React.FC<{
  children: React.ReactNode
  onClick?: () => void
  active?: boolean
  asc?: boolean
}> = ({ children, onClick, active, asc }) => (
  <th
    onClick={onClick}
    className={`px-4 py-2.5 font-semibold whitespace-nowrap ${onClick ? 'cursor-pointer hover:text-gray-700 select-none' : ''} ${active ? 'text-indigo-600' : ''}`}
  >
    <span className="flex items-center gap-1">
      {children}
      {active && <span className="text-[8px]">{asc ? '▲' : '▼'}</span>}
    </span>
  </th>
)