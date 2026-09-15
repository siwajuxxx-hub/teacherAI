import React, { lazy, Suspense, useEffect, useState } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useAuthStore } from './store/auth';
import Layout from './components/layout/Layout';
import ProtectedRoute from './components/layout/ProtectedRoute';
import LoginPage from './pages/LoginPage';

// Ленивая загрузка страниц
const ChatTab = lazy(() => import('./pages/TeacherDashboard/ChatTab'));
const CalendarTab = lazy(() => import('./pages/TeacherDashboard/CalendarTab'));
const NotesTab = lazy(() => import('./pages/TeacherDashboard/NotesTab'));
const TeachersView = lazy(() => import('./pages/ManagerDashboard/TeachersView'));
const ManagerOverview = lazy(() => import('./pages/ManagerDashboard/ManagerOverview'));
const ManagerCalendar = lazy(() => import('./pages/ManagerDashboard/ManagerCalendar'));
const UsersManagement = lazy(() => import('./pages/AdminPanel/UsersManagement'));
const SettingsPage = lazy(() => import('./pages/AdminPanel/SettingsPage'));
const GlobalView = lazy(() => import('./pages/AdminPanel/GlobalView'));

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-10 w-10 border-4 border-indigo-500 border-t-transparent mx-auto mb-3" />
        <p className="text-gray-500">Загрузка...</p>
      </div>
    </div>
  );
}

function roleHome(role: string): string {
  switch (role) {
    case 'admin': return '/admin/users';
    case 'manager': return '/manager';
    default: return '/teacher/chat';
  }
}

export default function App() {
  const { user, isAuthenticated, checkAuth, logout } = useAuthStore();
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    checkAuth().finally(() => setReady(true));
  }, []);

  // Токен истёк / невалиден — мягко выходим без перезагрузки страницы,
  // чтобы не терять сообщения об ошибках и введённые данные.
  useEffect(() => {
    const onExpired = () => {
      logout();
      navigate('/login', { replace: true });
    };
    window.addEventListener('auth-expired', onExpired);
    return () => window.removeEventListener('auth-expired', onExpired);
  }, [logout, navigate]);

  // Полноэкранный спиннер только на время первичной проверки токена.
  // ВАЖНО: isLoading во время входа/выхода НЕ должен размонтировать страницу,
  // иначе стирается сообщение об ошибке входа (выглядит как перезагрузка).
  if (!ready) {
    return <LoadingFallback />;
  }

  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        <Route path="/login" element={
          isAuthenticated ? <Navigate to={roleHome(user?.role ?? 'teacher')} replace /> : <LoginPage />
        } />

        {/* Защищённые маршруты */}
        <Route path="/teacher" element={
          <ProtectedRoute><Layout /></ProtectedRoute>
        }>
          <Route index element={<Navigate to="/teacher/chat" replace />} />
          <Route path="chat" element={<ChatTab />} />
          <Route path="calendar" element={<CalendarTab />} />
          <Route path="notes" element={<NotesTab />} />
        </Route>

        <Route path="/manager" element={
          <ProtectedRoute roles={['manager', 'admin']}><Layout /></ProtectedRoute>
        }>
          <Route index element={<Navigate to="/manager/overview" replace />} />
          <Route path="teachers" element={<TeachersView />} />
          <Route path="overview" element={<ManagerOverview />} />
          <Route path="calendar" element={<ManagerCalendar />} />
          <Route path="chat" element={<ChatTab />} />
        </Route>

        <Route path="/admin" element={
          <ProtectedRoute roles={['admin']}><Layout /></ProtectedRoute>
        }>
          <Route index element={<Navigate to="/admin/users" replace />} />
          <Route path="users" element={<UsersManagement />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="overview" element={<GlobalView />} />
        </Route>

        <Route path="/" element={
          isAuthenticated ? <Navigate to={roleHome(user?.role ?? 'teacher')} replace /> : <Navigate to="/login" replace />
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}