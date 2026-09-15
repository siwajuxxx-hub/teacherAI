import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogIn, Eye, EyeOff, GraduationCap, Loader2 } from 'lucide-react';
import { useAuthStore } from '../store/auth';

const ROLE_REDIRECT: Record<string, string> = {
  teacher: '/teacher/chat',
  manager: '/manager',
  admin: '/admin/users',
};

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, isAuthenticated, isLoading: loading, login } = useAuthStore();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const passwordRef = useRef<HTMLInputElement>(null);

  // Если уже авторизован — сразу редирект
  useEffect(() => {
    if (isAuthenticated && user) {
      const target = ROLE_REDIRECT[user.role] ?? '/teacher/chat';
      navigate(target, { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError('');

    if (!username.trim() || !password.trim()) {
      setError('Введите имя пользователя и пароль');
      return;
    }

    try {
      await login(username.trim(), password);
      // useEffect выше обработает редирект при изменении isAuthenticated / user
    } catch (err: unknown) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось выполнить вход. Попробуйте позже.';
      setError(message);
      // Возвращаем фокус на пароль, чтобы удобно было исправить
      setPassword('');
      passwordRef.current?.focus();
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-600 via-indigo-700 to-purple-800 px-4 py-12 relative overflow-hidden">
      {/* Декоративные элементы */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-400 rounded-full mix-blend-multiply filter blur-3xl opacity-20" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-purple-400 rounded-full mix-blend-multiply filter blur-3xl opacity-20" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10" />
      </div>

      <div className="relative w-full max-w-md z-10">
        {/* Карточка */}
        <div className="bg-white rounded-2xl shadow-2xl p-8 sm:p-10">
          {/* Заголовок */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl shadow-lg mb-5">
              <GraduationCap className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              AI TEACHER (СФ МЭИ)
            </h1>
            <p className="mt-2 text-sm text-gray-500">
              Войдите в систему, чтобы продолжить работу
            </p>
          </div>

          {/* Форма */}
          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            {/* Логин */}
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Имя пользователя
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Введите имя пользователя"
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm text-gray-900 placeholder-gray-400
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                           transition-shadow duration-200"
              />
            </div>

            {/* Пароль */}
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Пароль
              </label>
              <div className="relative">
                <input
                  id="password"
                  ref={passwordRef}
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Введите пароль"
                  className="w-full px-4 py-2.5 pr-11 border border-gray-300 rounded-xl text-sm text-gray-900 placeholder-gray-400
                             focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                             transition-shadow duration-200"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                  tabIndex={-1}
                  aria-label={
                    showPassword ? 'Скрыть пароль' : 'Показать пароль'
                  }
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {/* Блок ошибки */}
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex items-start gap-2">
                <span className="text-red-500 mt-0.5 shrink-0">⚠</span>
                <span>{error}</span>
              </div>
            )}

            {/* Кнопка входа */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5
                         bg-gradient-to-r from-blue-600 to-indigo-600
                         text-white text-sm font-semibold rounded-xl shadow-md
                         hover:from-blue-700 hover:to-indigo-700
                         focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                         disabled:opacity-60 disabled:cursor-not-allowed
                         transition-all duration-200"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>Вход...</span>
                </>
              ) : (
                <>
                  <LogIn size={18} />
                  <span>Войти</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Футер */}
        <p className="mt-6 text-center text-xs text-white/60">
          © {new Date().getFullYear()} AI TEACHER (СФ МЭИ)
        </p>
      </div>
    </div>
  );
};

export default LoginPage;