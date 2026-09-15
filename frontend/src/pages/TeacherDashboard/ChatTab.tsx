import React, { useEffect, useRef } from 'react';
import {
  Send, Paperclip, Loader2, Bot, User,
  CheckCircle, XCircle, FileText, Info, Sparkles,
} from 'lucide-react';
import * as api from '../../api/client';
import type { ChatMessage, ScheduleCreatePayload } from '../../types';
import { DAYS_SHORT, SCHEDULE_TYPES } from '../../utils/constants';
import { useChatStore } from '../../store/chat';
import { useAuthStore } from '../../store/auth';

const ACCEPTED_FILE_TYPES = '.pdf,.docx,.doc,.txt,.xls,.xlsx';

const ChatTab: React.FC = () => {
  const {
    messages, parsedItems, pendingActions, isStreaming,
    appendMessages, replaceMessages, updateMessage, setParsedItems,
    setPendingActions, setIsStreaming,
  } = useChatStore();
  const user = useAuthStore((s) => s.user);
  const isManager = user?.role === 'manager' || user?.role === 'admin';

  const [input, setInput] = React.useState('');
  const [uploading, setUploading] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // ── Загрузка истории при первом монтировании ──────────────
  const historyLoaded = useRef(false);

  useEffect(() => {
    if (historyLoaded.current) return;
    historyLoaded.current = true;

    if (messages.length === 0) {
      api.getChatHistory(50).then(replaceMessages).catch(() => {});
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Авто-скролл ───────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming, parsedItems]);

  // ── Отправка текстового сообщения ─────────────────────────
  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`, role: 'user', content: text, created_at: new Date().toISOString(),
    };

    appendMessages(userMsg);
    setInput('');
    setIsStreaming(true);

    abortControllerRef.current = new AbortController();

    try {
      const response = await api.sendChatMessage(text);
      if (!response.ok) {
        const errorText = await response.text().catch(() => '');
        throw new Error(errorText || `Ошибка сервера (${response.status})`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Поток ответа недоступен');

      const decoder = new TextDecoder();
      const assistantId = `ast-${Date.now()}`;

      appendMessages({ id: assistantId, role: 'assistant', content: '', created_at: new Date().toISOString() });

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.chunk) {
                updateMessage(assistantId, (m) => ({ ...m, content: m.content + data.chunk }));
              }
              if (data.final_text) {
                updateMessage(assistantId, (m) => ({ ...m, content: data.final_text }));
              }
              if (data.actions?.length) {
                setPendingActions(data.actions);
              }
            } catch { /* not JSON */ }
          }
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка соединения';
      appendMessages({
        id: `err-${Date.now()}`, role: 'assistant',
        content: `❌ Ошибка: ${message}`, created_at: new Date().toISOString(),
      });
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  // ── Enter для отправки ────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // ── Загрузка файла ────────────────────────────────────────
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setParsedItems(null);

    try {
      // Если пользователь что-то написал в поле — это указание к файлу
      // («добавь всем преподавателям их пары», «добавь пары Гаврилова»)
      const instruction = input.trim();
      const result = await api.uploadFile(file, instruction || undefined);

      appendMessages(
        {
          id: `fu-${Date.now()}`, role: 'user',
          content: `📎 Загружен файл: ${file.name}` + (instruction ? `\nЗапрос: ${instruction}` : ''),
          created_at: new Date().toISOString(),
        },
        { id: `fa-${Date.now()}`, role: 'assistant',
          content: result.message || `Файл обработан. Найдено ${result.items?.length ?? 0} записей.`,
          created_at: new Date().toISOString() },
      );

      if (instruction) setInput('');
      if (result.items?.length) setParsedItems(result);
      // Если парсер сразу разложил пары по преподавателям — обновляем вкладки
      if ((result as any).status === 'distributed') {
        window.dispatchEvent(new CustomEvent('data-changed'));
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка загрузки файла';
      appendMessages(
        { id: `fu-${Date.now()}`, role: 'user', content: `📎 Загружен файл: ${file.name}`, created_at: new Date().toISOString() },
        { id: `fe-${Date.now()}`, role: 'assistant', content: `❌ Ошибка: ${message}`, created_at: new Date().toISOString() },
      );
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // ── Подтверждение действий из чата ────────────────────────
  const handleConfirmActions = async () => {
    if (!pendingActions.length) return;
    setConfirming(true);
    try {
      const res = await api.executeChatActions(pendingActions);
      appendMessages({
        id: `act-${Date.now()}`, role: 'assistant',
        content: res.report || '✅ Действия выполнены',
        created_at: new Date().toISOString(),
      });
      setPendingActions([]);
      // Сообщаем вкладкам Календарь/Заметки, что данные изменились
      window.dispatchEvent(new CustomEvent('data-changed'));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка выполнения';
      appendMessages({
        id: `acterr-${Date.now()}`, role: 'assistant',
        content: `❌ Не удалось выполнить действия: ${message}`,
        created_at: new Date().toISOString(),
      });
    } finally {
      setConfirming(false);
    }
  };

  // ── Подтверждение расписания ──────────────────────────────
  const handleConfirmSchedule = async () => {
    if (!parsedItems?.items?.length) return;
    setConfirming(true);
    try {
      await api.batchCreateSchedule({ items: parsedItems.items as ScheduleCreatePayload[] });
      appendMessages({
        id: `ok-${Date.now()}`, role: 'assistant',
        content: `✅ ${parsedItems.items.length} записей добавлены в расписание! Проверьте календарь.`,
        created_at: new Date().toISOString(),
      });
      setParsedItems(null);
      window.dispatchEvent(new CustomEvent('data-changed'));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка сохранения';
      appendMessages({
        id: `err-${Date.now()}`, role: 'assistant',
        content: `❌ Не удалось добавить расписание: ${message}`, created_at: new Date().toISOString(),
      });
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-10rem)] flex flex-col">
      {/* Заголовок */}
      <div className="flex items-center gap-2 mb-4">
        <Bot size={22} className="text-indigo-600" />
        <h2 className="text-xl font-bold text-gray-800">AI Чат</h2>
        <span className="text-xs text-gray-400">| История сохраняется до выхода</span>
      </div>

      {/* Подсказка по возможностям */}
      <div className="flex items-start gap-2 p-3 mb-3 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-800">
        <Info size={16} className="text-blue-500 mt-0.5 shrink-0" />
        <div>
          {isManager ? (
            <>
              <strong>Режим управляющего:</strong> загрузите файл с расписанием и напишите
              <code className="text-xs bg-blue-100 px-1.5 py-0.5 rounded mx-1">добавь всем преподавателям их пары</code>
              — пары получат только те, у кого есть учётная запись; уже существующие пары будут пропущены.
            </>
          ) : (
            <>
              <strong>Что умеет чат:</strong> загрузить расписание из файла, добавить или удалить пары,
              перенести занятие, сменить аудиторию и группу, а также создавать задачи, менять их статус и удалять.
              <br />
              <span className="text-xs text-blue-600">
                Примеры: «перенеси пару по математике на среду», «добавь задачу проверить тетради на пятницу»,
                «отметь задачу как выполненную».
              </span>
            </>
          )}
        </div>
      </div>

      {/* Область сообщений */}
      <div className="flex-1 overflow-y-auto bg-white rounded-2xl border border-gray-200 p-4 mb-3 space-y-3">
        {messages.length === 0 ? (
          <div className="text-center text-gray-400 mt-20">
            <div className="flex justify-center mb-3"><Bot size={48} className="opacity-30" /></div>
            {isManager ? (
              <>
                <p>Загрузите файл с расписанием и напишите:</p>
                <p className="text-xs mt-2">
                  <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">добавь всем преподавателям их пары</code>
                </p>
                <p className="text-xs mt-2 text-gray-400">
                  Пары получат только зарегистрированные преподаватели. Дубли пропускаются.
                </p>
              </>
            ) : (
              <>
                <p>Загрузите файл с расписанием или попросите изменить календарь и заметки.</p>
                <p className="text-xs mt-2">Например: «перенеси пару на пятницу», «добавь задачу на завтра».</p>
              </>
            )}
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`flex gap-3 ${msg.role === 'assistant' ? 'justify-start' : 'justify-end'}`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                msg.role === 'assistant'
                  ? msg.content.startsWith('❌') ? 'bg-red-50 text-red-800 border border-red-200'
                  : msg.content.startsWith('✅') ? 'bg-green-50 text-green-800 border border-green-200'
                  : 'bg-gray-100 text-gray-800'
                  : 'bg-indigo-600 text-white'
              }`}>
                {msg.role === 'assistant' && !msg.content.startsWith('❌') && !msg.content.startsWith('✅') && (
                  <div className="flex items-center gap-1.5 mb-1">
                    <Bot size={14} className="text-indigo-500" />
                    <span className="text-xs font-semibold text-indigo-500">AI ассистент</span>
                  </div>
                )}
                {msg.content}
                {msg.role === 'user' && (
                  <div className="flex items-center justify-end gap-1.5 mt-1">
                    <span className="text-xs text-indigo-200">Вы</span>
                    <User size={12} className="text-indigo-200" />
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {/* Предложенные действия (требуют подтверждения) */}
        {pendingActions.length > 0 && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles size={18} className="text-indigo-600" />
              <span className="font-semibold text-indigo-800">
                AI предлагает {pendingActions.length} {pendingActions.length === 1 ? 'действие' : 'действий'}
              </span>
            </div>
            <div className="space-y-2">
              {pendingActions.map((a, i) => (
                <div key={i} className="text-sm bg-white rounded-lg px-3 py-2 border border-indigo-100 text-gray-800">
                  {a.description}
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-3">
              <button onClick={handleConfirmActions} disabled={confirming}
                className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-xl text-sm font-medium transition">
                {confirming ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                Применить
              </button>
              <button onClick={() => setPendingActions([])}
                className="flex items-center gap-1.5 px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 rounded-xl text-sm transition">
                <XCircle size={16} /> Отмена
              </button>
            </div>
          </div>
        )}

        {/* Превью расписания */}
        {parsedItems?.items?.length ? (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <FileText size={18} className="text-amber-600" />
              <span className="font-semibold text-amber-800">Найдено {parsedItems.items.length} записей</span>
            </div>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {parsedItems.items.map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-sm bg-white rounded-lg px-3 py-2 border border-amber-100">
                  <span className="font-medium text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full">
                    {(DAYS_SHORT as readonly string[])[item.day_of_week] ?? '?'}
                  </span>
                  <span className="font-mono text-xs text-gray-500">{item.start_time}-{item.end_time}</span>
                  <span className="font-medium text-gray-800">{item.title}</span>
                  <span className="text-xs text-gray-400 ml-auto">{(SCHEDULE_TYPES as Record<string,string>)[item.type as string] ?? item.type}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-3">
              <button onClick={handleConfirmSchedule} disabled={confirming}
                className="flex items-center gap-1.5 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-300 text-white rounded-xl text-sm font-medium transition">
                {confirming ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                Добавить в календарь
              </button>
              <button onClick={() => setParsedItems(null)}
                className="flex items-center gap-1.5 px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 rounded-xl text-sm transition">
                <XCircle size={16} /> Отмена
              </button>
            </div>
          </div>
        ) : null}

        <div ref={messagesEndRef} />
      </div>

      {/* Поле ввода */}
      <div className="flex items-end gap-2">
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading || isStreaming}
          className="p-3 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 rounded-xl transition-colors" title="Загрузить файл">
          {uploading ? <Loader2 size={20} className="animate-spin" /> : <Paperclip size={20} />}
        </button>
        <input ref={fileInputRef} type="file" accept={ACCEPTED_FILE_TYPES} onChange={handleFileUpload} className="hidden" />
        <div className="flex-1">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="Напишите сообщение… (Enter — отправить, Shift+Enter — новая строка)" disabled={isStreaming} rows={1}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow text-sm disabled:bg-gray-50 disabled:text-gray-400 resize-none" />
        </div>
        <button type="button" onClick={handleSend} disabled={!input.trim() || isStreaming}
          className="p-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white rounded-xl transition-colors shrink-0">
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default ChatTab;