import React, { useEffect, useState } from 'react';
import {
  Save, Wifi, Eye, EyeOff, Loader2, AlertCircle, CheckCircle,
  Info, ExternalLink, Zap, Globe, Settings2, Activity,
} from 'lucide-react';
import * as api from '../../api/client';
import type { AISettings, AISettingsUpdatePayload } from '../../types';

// Предустановленные популярные провайдеры
const POPULAR_PROVIDERS = [
  {
    id: 'openrouter',
    name: 'OpenRouter',
    description: 'Десятки бесплатных моделей через единый API',
    url: 'https://openrouter.ai/keys',
    baseUrl: 'https://openrouter.ai/api/v1',
    defaultModel: 'google/gemini-2.0-flash-001',
    color: 'amber',
    freeModels: ['Gemini 2.0 Flash', 'Llama 3.3 70B', 'Mistral Nemo', 'Qwen 2.5 72B'],
  },
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'Прямой доступ к GPT-4o, требуется платный аккаунт',
    url: 'https://platform.openai.com/api-keys',
    baseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o',
    color: 'green',
    freeModels: [],
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    description: 'Бесплатный доступ к Gemini Flash через Google AI',
    url: 'https://aistudio.google.com/apikey',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    defaultModel: 'gemini-2.0-flash',
    color: 'blue',
    freeModels: ['Gemini 2.0 Flash (бесплатно)'],
  },
];

const colorMap: Record<string, string> = {
  amber: 'border-amber-400 bg-amber-50 hover:border-amber-500',
  green: 'border-green-400 bg-green-50 hover:border-green-500',
  blue: 'border-blue-400 bg-blue-50 hover:border-blue-500',
};

const badgeMap: Record<string, string> = {
  amber: 'bg-amber-100 text-amber-800',
  green: 'bg-green-100 text-green-800',
  blue: 'bg-blue-100 text-blue-800',
};

const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Поля формы
  const [provider, setProvider] = useState('openrouter');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [hasApiKey, setHasApiKey] = useState(false);
  const [selectedPopular, setSelectedPopular] = useState<string | null>(null);

  const [showKey, setShowKey] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // ── Keepalive (пробуждение сервера) ────────────────────────
  const [ka, setKa] = useState<api.KeepaliveStatus | null>(null);
  const [kaBusy, setKaBusy] = useState(false);

  useEffect(() => {
    api.getKeepalive().then(setKa).catch(() => {});
  }, []);

  const toggleKeepalive = async () => {
    if (!ka || kaBusy) return;
    setKaBusy(true);
    try {
      setKa(await api.setKeepalive(!ka.enabled));
    } catch {
      /* оставили прежнее состояние */
    } finally {
      setKaBusy(false);
    }
  };

  // ── Загрузка текущих настроек ─────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data: AISettings = await api.getSettings();
        if (cancelled) return;
        setProvider(data.provider || 'openrouter');
        setModel(data.model || '');
        setBaseUrl(data.base_url || '');
        setHasApiKey(data.has_api_key);
        // Определяем, совпадает ли провайдер с популярным
        const popular = POPULAR_PROVIDERS.find(p => p.id === data.provider);
        setSelectedPopular(popular ? data.provider : null);
      } catch {
        if (!cancelled) setError('Ошибка загрузки настроек');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  // ── Выбор популярного провайдера ──────────────────────────
  const selectPopular = (p: typeof POPULAR_PROVIDERS[number]) => {
    setProvider(p.id);
    setModel(p.defaultModel);
    setBaseUrl(p.baseUrl);
    setSelectedPopular(p.id);
    setError('');
  };

  // ── Переключение на кастомный ввод ────────────────────────
  const selectCustom = () => {
    setProvider('openrouter');
    setModel('');
    setBaseUrl('');
    setSelectedPopular(null);
    setError('');
  };

  // ── Сохранение ────────────────────────────────────────────
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSaving(true);
    try {
      const payload: AISettingsUpdatePayload = {
        provider,
        api_key: apiKey,
        model,
        base_url: baseUrl || null,
      };
      await api.updateAISettings(payload);
      if (apiKey) setHasApiKey(true);
      setSuccess('✅ Настройки сохранены');
      setTimeout(() => setSuccess(''), 3000);
    } catch {
      setError('Ошибка при сохранении настроек');
    } finally {
      setSaving(false);
    }
  };

  // ── Проверка подключения ──────────────────────────────────
  const handleTest = async () => {
    setError('');
    setTestResult(null);
    setTesting(true);
    try {
      const data = await api.testAIConnection();
      setTestResult({
        ok: data.status === 'ok',
        message: data.response ?? data.error ?? 'Подключение успешно!',
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err as { message?: string })?.message ??
        'Ошибка подключения';
      setTestResult({ ok: false, message: msg });
    } finally {
      setTesting(false);
    }
  };

  // ── Загрузка ──────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex justify-center py-32">
        <Loader2 size={32} className="animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Настройки AI</h1>
        <p className="text-sm text-gray-500 mt-1">
          Настройка подключения нейросети для чата и парсинга расписания
        </p>
      </div>

      {/* Уведомления */}
      {error && (
        <div className="flex items-center gap-2 p-3 mb-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          <AlertCircle size={16} />{error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 p-3 mb-4 bg-green-50 border border-green-200 rounded-xl text-green-700 text-sm">
          <CheckCircle size={16} />{success}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── КОЛОНКА 1: Кастомный провайдер ────────────────── */}
        <div>
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-9 h-9 rounded-lg bg-gray-100 flex items-center justify-center">
                <Globe size={18} className="text-gray-600" />
              </div>
              <div>
                <h2 className="font-semibold text-gray-800">Кастомный провайдер</h2>
                <p className="text-xs text-gray-400">Любой OpenAI-совместимый API</p>
              </div>
            </div>

            <form onSubmit={handleSave} className="space-y-4">
              {/* Provider id */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">ID провайдера</label>
                <input
                  type="text"
                  value={provider}
                  onChange={(e) => { setProvider(e.target.value); setSelectedPopular(null); }}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                  placeholder="openrouter"
                />
                <p className="text-xs text-gray-400 mt-1">Технический идентификатор: openrouter, openai, gemini или свой</p>
              </div>

              {/* API Key */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  API Ключ {hasApiKey && <span className="text-green-500">(сохранён)</span>}
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                    placeholder={hasApiKey ? '•••••••• (оставьте пустым)' : 'sk-...'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-lg hover:bg-gray-100 text-gray-400"
                  >
                    {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {/* Model */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Модель</label>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => { setModel(e.target.value); setSelectedPopular(null); }}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                  placeholder="google/gemini-2.0-flash-001"
                />
              </div>

              {/* Base URL */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Базовый URL <span className="text-gray-400">(опционально)</span>
                </label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => { setBaseUrl(e.target.value); setSelectedPopular(null); }}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                  placeholder="https://api.openai.com/v1"
                />
                <p className="text-xs text-gray-400 mt-1">Для OpenAI-совместимых API. Оставьте пустым для автоподстановки.</p>
              </div>

              {/* Кнопки */}
              <div className="flex flex-wrap gap-3 pt-1">
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition disabled:opacity-50 shadow-sm text-sm"
                >
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                  {saving ? 'Сохранение...' : 'Сохранить'}
                </button>
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={testing}
                  className="flex items-center justify-center gap-2 px-4 py-2.5 bg-white text-gray-700 font-medium rounded-xl border border-gray-200 hover:bg-gray-50 transition disabled:opacity-50 text-sm"
                >
                  {testing ? <Loader2 size={16} className="animate-spin" /> : <Wifi size={16} />}
                  {testing ? '...' : 'Тест'}
                </button>
              </div>

              {/* Результат теста */}
              {testResult && (
                <div className={`flex items-center gap-2 p-3 rounded-xl text-sm ${
                  testResult.ok
                    ? 'bg-green-50 border border-green-200 text-green-700'
                    : 'bg-red-50 border border-red-200 text-red-700'
                }`}>
                  {testResult.ok ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                  {testResult.message}
                </div>
              )}
            </form>
          </div>
        </div>

        {/* ── КОЛОНКА 2: Популярные провайдеры ───────────────── */}
        <div>
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center">
                <Zap size={18} className="text-indigo-600" />
              </div>
              <div>
                <h2 className="font-semibold text-gray-800">Популярные провайдеры</h2>
                <p className="text-xs text-gray-400">Выберите — URL и модель подставятся сами</p>
              </div>
            </div>

            <div className="space-y-3">
              {POPULAR_PROVIDERS.map((p) => {
                const isActive = selectedPopular === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => selectPopular(p)}
                    className={`w-full text-left rounded-xl border-2 p-4 transition-all ${
                      isActive
                        ? `${colorMap[p.color]} ring-2 ring-offset-1 ring-${p.color}-400`
                        : 'border-gray-100 hover:border-gray-300 bg-white'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${badgeMap[p.color]}`}>
                            {p.name}
                          </span>
                          {p.freeModels.length > 0 && (
                            <span className="text-xs text-green-600 font-medium">✓ Бесплатные модели</span>
                          )}
                        </div>
                        <p className="text-sm text-gray-600 mt-1.5">{p.description}</p>

                        {isActive && (
                          <div className="mt-2 pt-2 border-t border-gray-100 space-y-1">
                            <div className="text-xs text-gray-500">
                              <span className="font-medium">Модель:</span>{' '}
                              <code className="bg-gray-100 px-1 py-0.5 rounded text-[11px]">{p.defaultModel}</code>
                            </div>
                            <div className="text-xs text-gray-500">
                              <span className="font-medium">URL:</span>{' '}
                              <code className="bg-gray-100 px-1 py-0.5 rounded text-[11px]">{p.baseUrl}</code>
                            </div>
                            {p.freeModels.length > 0 && (
                              <div className="text-xs text-gray-500">
                                <span className="font-medium">Доступные модели:</span>{' '}
                                {p.freeModels.join(', ')}
                              </div>
                            )}
                          </div>
                        )}

                        <a
                          href={p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800 mt-2"
                        >
                          <ExternalLink size={11} />
                          Получить API-ключ
                        </a>
                      </div>

                      {isActive && (
                        <CheckCircle size={20} className="text-indigo-600 shrink-0 mt-0.5" />
                      )}
                    </div>
                  </button>
                );
              })}

              {/* Кнопка сброса — кастомный ввод */}
              <button
                type="button"
                onClick={selectCustom}
                className={`w-full text-left rounded-xl border-2 p-4 transition-all ${
                  selectedPopular === null
                    ? 'border-dashed border-indigo-300 bg-indigo-50/50'
                    : 'border-dashed border-gray-200 hover:border-gray-400 bg-white'
                }`}
              >
                <div className="flex items-center gap-2">
                  <Settings2 size={18} className="text-gray-500" />
                  <span className="text-sm font-medium text-gray-700">Свой провайдер</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">Ручной ввод всех параметров</p>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Keepalive: против сна free-инстанса Render ───────────────── */}
      <div className="mt-6 bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-100 flex items-center justify-center shrink-0">
              <Activity size={18} className="text-emerald-600" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-800">Пробуждение сервера (keepalive)</h2>
              <p className="text-xs text-gray-500 mt-0.5 max-w-xl">
                Раз в {ka ? Math.round(ka.interval_sec / 60) : '…'} мин. приложение само обращается к своему
                публичному URL — этого достаточно, чтобы Render не усыплял бесплатный инстанс
                после 15 минут простоя. Выключайте, если приложение крутится на сервере 24/7
                (локально, VPS).
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={toggleKeepalive}
            disabled={!ka || kaBusy}
            className={`relative w-12 h-7 rounded-full transition-colors shrink-0 mt-1 ${
              ka?.enabled ? 'bg-emerald-500' : 'bg-gray-300'
            } disabled:opacity-50`}
            title={ka?.enabled ? 'Нажмите, чтобы выключить' : 'Нажмите, чтобы включить'}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                ka?.enabled ? 'translate-x-5' : ''
              }`}
            />
          </button>
        </div>

        {ka && (
          <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-xs text-gray-500">
            <div>
              <span className="font-medium text-gray-600">Цель:</span>{' '}
              <code className="bg-gray-100 px-1.5 py-0.5 rounded break-all">{ka.target}</code>
            </div>
            <div>
              {ka.external_url_mode ? (
                <span className="text-emerald-600 font-medium">
                  ✓ режим Render — пинг идёт через внешний URL и засчитывается как активность
                </span>
              ) : (
                <span className="text-gray-400">
                  локальный режим (нет RENDER_EXTERNAL_URL) — пинг в localhost, безопасная имитация
                </span>
              )}
            </div>
            <div>
              <span className="font-medium text-gray-600">Статус:</span>{' '}
              {ka.last_ok_at ? (
                <span className="text-emerald-600">
                  OK · успешных {ka.pings_ok} · последний{' '}
                  {new Date(ka.last_ok_at).toLocaleTimeString('ru-RU')}
                </span>
              ) : ka.last_error ? (
                <span className="text-red-500">ошибка: {ka.last_error}</span>
              ) : (
                <span>ожидаем первый пинг (до {ka.interval_sec} сек.)</span>
              )}
            </div>
            <div>
              <span className="font-medium text-gray-600">Функция:</span>{' '}
              {ka.enabled ? (
                <span className="text-emerald-600 font-semibold">включена</span>
              ) : (
                <span className="text-gray-400">выключена</span>
              )}
              {ka.pings_failed > 0 && <span className="text-red-400"> · сбоев: {ka.pings_failed}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPage;