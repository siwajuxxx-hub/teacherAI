import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import { useAuthStore } from '../../store/auth';
import * as api from '../../api/client';

/** Tab definitions keyed by role */
interface Tab {
  label: string;
  to: string;
  newsBadge?: boolean;
}

const teacherTabs: Tab[] = [
  { label: 'Чат', to: '/teacher/chat' },
  { label: 'Календарь', to: '/teacher/calendar' },
  { label: 'Заметки', to: '/teacher/notes' },
  { label: 'Новости', to: '/teacher/news', newsBadge: true },
];

const managerTabs: Tab[] = [
  { label: 'Обзор', to: '/manager/overview' },
  { label: 'Календарь', to: '/manager/calendar' },
  { label: 'Преподаватели', to: '/manager/teachers' },
  { label: 'AI Чат', to: '/manager/chat' },
  { label: 'Новости', to: '/manager/news', newsBadge: true },
];

const adminTabs: Tab[] = [
  { label: 'Пользователи', to: '/admin/users' },
  { label: 'Настройки', to: '/admin/settings' },
  { label: 'Обзор', to: '/admin/overview' },
  { label: 'Новости', to: '/admin/news', newsBadge: true },
];

const Layout: React.FC = () => {
  const { user } = useAuthStore();
  const [unread, setUnread] = useState(0);

  const tabs: Tab[] =
    user?.role === 'admin'
      ? adminTabs
      : user?.role === 'manager'
        ? managerTabs
        : teacherTabs;

  // Hide tabs for routes that don't need them (e.g. /login)
  const location = useLocation();
  const hideTabs = location.pathname === '/login';

  // счётчик непрочитанных новостей (обновляется при входах, правках и прочтении)
  useEffect(() => {
    let live = true;
    const refresh = () => api.newsUnreadCount().then((n) => { if (live) setUnread(n); }).catch(() => {});
    refresh();
    const on = () => refresh();
    window.addEventListener('data-changed', on);
    window.addEventListener('news-read', on);
    return () => {
      live = false;
      window.removeEventListener('data-changed', on);
      window.removeEventListener('news-read', on);
    };
  }, [location.pathname]);

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      {!hideTabs && tabs.length > 0 && (
        <nav className="bg-white border-b border-gray-200 px-2 sm:px-6">
          <div className="flex gap-0 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) =>
                  `px-3 sm:px-4 py-2.5 sm:py-3 text-sm font-medium border-b-2 shrink-0 whitespace-nowrap transition-colors ${
                    isActive
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`
                }
              >
                <span className="inline-flex items-center gap-1.5">
                  {tab.label}
                  {tab.newsBadge && unread > 0 && (
                    <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold leading-[18px] text-center">
                      {unread > 9 ? '9+' : unread}
                    </span>
                  )}
                </span>
              </NavLink>
            ))}
          </div>
        </nav>
      )}

      {/* Main content rendered by child routes */}
      <main className="flex-1 p-3 sm:p-6">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;