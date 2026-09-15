import React from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import { useAuthStore } from '../../store/auth';

/** Tab definitions keyed by role */
interface Tab {
  label: string;
  to: string;
}

const teacherTabs: Tab[] = [
  { label: 'Чат', to: '/teacher/chat' },
  { label: 'Календарь', to: '/teacher/calendar' },
  { label: 'Заметки', to: '/teacher/notes' },
];

const managerTabs: Tab[] = [
  { label: 'Обзор', to: '/manager/overview' },
  { label: 'Календарь', to: '/manager/calendar' },
  { label: 'Преподаватели', to: '/manager/teachers' },
  { label: 'AI Чат', to: '/manager/chat' },
];

const adminTabs: Tab[] = [
  { label: 'Пользователи', to: '/admin/users' },
  { label: 'Настройки', to: '/admin/settings' },
  { label: 'Обзор', to: '/admin/overview' },
];

const Layout: React.FC = () => {
  const { user } = useAuthStore();

  const tabs: Tab[] =
    user?.role === 'admin'
      ? adminTabs
      : user?.role === 'manager'
        ? managerTabs
        : teacherTabs;

  // Hide tabs for routes that don't need them (e.g. /login)
  const location = useLocation();
  const hideTabs = location.pathname === '/login';

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      {!hideTabs && tabs.length > 0 && (
        <nav className="bg-white border-b border-gray-200 px-6">
          <div className="flex gap-0">
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) =>
                  `px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                    isActive
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </div>
        </nav>
      )}

      {/* Main content rendered by child routes */}
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;