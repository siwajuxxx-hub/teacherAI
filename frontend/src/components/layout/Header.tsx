import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, Clock, Calendar } from 'lucide-react';
import { useAuthStore } from '../../store/auth';
import { ROLES } from '../../utils/constants';

const roleBadgeColor = (role: string): string => {
  const map: Record<string, string> = {
    admin: 'bg-purple-100 text-purple-800',
    manager: 'bg-blue-100 text-blue-800',
    teacher: 'bg-green-100 text-green-800',
  };
  return map[role] ?? 'bg-gray-100 text-gray-800';
};

const roleLabel = (role: string): string =>
  (ROLES as Record<string, string>)[role] ?? role;

const MONTHS = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

const WEEKDAYS = [
  'воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота',
];

function useDateTime() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const day = now.getDate();
  const month = MONTHS[now.getMonth()];
  const weekday = WEEKDAYS[now.getDay()];
  const time = now.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
  const dateStr = `${day} ${month}, ${weekday}`;

  return { dateStr, time, now };
}

const Header: React.FC = () => {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const { dateStr, time } = useDateTime();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="bg-white border-b border-gray-200 px-3 sm:px-6 py-2.5 sm:py-3 flex items-center justify-between gap-2 shadow-sm">
      {/* Left – app name */}
      <div className="flex items-center gap-2 sm:gap-3 min-w-0">
        <h1 className="text-base sm:text-xl font-bold text-gray-800 truncate">
          <span className="sm:hidden">ИИ Ассистент</span>
          <span className="hidden sm:inline">ИИ Ассистент Преподавателя</span>
        </h1>
      </div>

      {/* Center – date & time */}
      <div className="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm text-gray-600 shrink-0">
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-gray-50 rounded-xl">
          <Calendar size={16} className="text-indigo-500" />
          <span className="font-medium">{dateStr}</span>
        </div>
        <div className="flex items-center gap-2 px-2 sm:px-3 py-1 sm:py-1.5 bg-gray-50 rounded-xl">
          <Clock size={14} className="sm:hidden text-indigo-500" />
          <Clock size={16} className="hidden sm:block text-indigo-500" />
          <span className="font-medium tabular-nums">{time}</span>
        </div>
      </div>

      {/* Right – user info + logout */}
      <div className="flex items-center gap-2 sm:gap-4 shrink-0">
        {user && (
          <>
            <div className="flex flex-col items-end min-w-0">
              <span className="text-xs sm:text-sm font-medium text-gray-700 truncate max-w-[110px] sm:max-w-none">
                {user.full_name}
              </span>
              {user.position && (
                <span className="hidden sm:block text-xs text-gray-400">{user.position}</span>
              )}
            </div>
            <span
              className={`hidden sm:inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${roleBadgeColor(user.role)}`}
            >
              {roleLabel(user.role)}
            </span>
          </>
        )}

        <button
          onClick={handleLogout}
          className="flex items-center gap-1 p-1.5 sm:px-1 sm:py-0 text-sm text-gray-500 hover:text-red-600 transition-colors shrink-0"
          title="Выйти"
        >
          <LogOut size={18} />
          <span className="hidden sm:inline">Выйти</span>
        </button>
      </div>
    </header>
  );
};

export default Header;