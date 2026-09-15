export const DAYS_OF_WEEK = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
] as const;

export const DAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'] as const;

export const SCHEDULE_TYPES = {
  lesson: 'Урок',
  meeting: 'Собрание',
  other: 'Прочее',
} as const;

/** Периоды задач: на какой срок ставится задача. */
export const TASK_SCOPES = {
  day: 'На день',
  month: 'На месяц',
  year: 'На год',
  none: 'Без срока',
} as const;

export const TASK_STATUSES = {
  pending: 'К выполнению',
  in_progress: 'В работе',
  done: 'Готово',
  overdue: 'Просрочено',
} as const;

/** Названия месяцев в предложном падеже для подписей. */
export const MONTHS_NOMINATIVE = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
] as const;

export const MONTHS_GENITIVE = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
] as const;

export const ROLES = {
  admin: 'Администратор',
  manager: 'Завуч',
  teacher: 'Учитель',
} as const;