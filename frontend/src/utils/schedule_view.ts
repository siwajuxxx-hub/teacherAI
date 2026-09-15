// Порт серверной развёртки (import_expander.py) для отображения календаря:
// недельный ШАБЛОН (event_date=null) виден в те дни месяца, которым он
// соответствует по дню недели и фильтру недель ('3,7', '2 по 12', 'верх'/'низ').

export interface SchedLike {
  event_date: string | null;
  day_of_week: number;
  weeks?: string | null;
}

const pad = (n: number) => String(n).padStart(2, '0');

export const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export function mondayOf(d: Date): Date {
  const x = new Date(d);
  const dow = (x.getDay() + 6) % 7; // 0=Пн
  x.setDate(x.getDate() - dow);
  x.setHours(0, 0, 0, 0);
  return x;
}

/** Номер недели от «недели-1» (1-based). */
export function weekNumber(day: Date, firstMonday: Date): number {
  return Math.floor((mondayOf(day).getTime() - mondayOf(firstMonday).getTime()) / (7 * 86400000)) + 1;
}

/** Проходит ли шаблон с weeks=spec в неделю n (совместимо с weeks_match). */
export function weeksMatch(spec: string | null | undefined, n: number): boolean {
  if (!spec || !spec.trim()) return true;
  for (const token of spec.split(/[;,]/)) {
    const t = token.trim().toLowerCase();
    if (!t) continue;
    if (['верх', 'верхн', 'верхняя', 'чётн', 'четн', 'odd'].some((k) => t.startsWith(k))) {
      if (n % 2 === 0) return true;
      continue;
    }
    if (['низ', 'нижн', 'нижняя', 'нечётн', 'ечётн', 'even'].some((k) => t.startsWith(k))) {
      if (n % 2 === 1) return true;
      continue;
    }
    const nums = t.match(/\d+/g)?.map(Number) ?? [];
    if (!nums.length) continue; // нераспознанный маркер — любая неделя
    if (t.includes('по') && nums.length >= 2) {
      const [lo, hi] = [Math.min(nums[0], nums[1]), Math.max(nums[0], nums[1])];
      if (lo <= n && n <= hi) return true;
    } else if (nums.includes(n)) {
      return true;
    }
  }
  return false;
}

/** Применяется ли запись к дате d. weekAnchor — понедельник «недели-1». */
export function itemAppliesOn(s: SchedLike, d: Date, weekAnchor: Date): boolean {
  if (s.event_date) return s.event_date === toISO(d);
  const dow = (d.getDay() + 6) % 7;
  if (dow !== s.day_of_week) return false;
  const n = weekNumber(d, weekAnchor);
  return n >= 1 && weeksMatch(s.weeks, n);
}
