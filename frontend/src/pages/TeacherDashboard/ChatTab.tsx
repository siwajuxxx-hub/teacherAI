import React, { useEffect, useRef, useState } from 'react';
import {
  Send, Paperclip, Loader2, Bot, User as UserIcon,
  CheckCircle, XCircle, FileText, Info, Sparkles, Trash2, Ban,
} from 'lucide-react';
import * as api from '../../api/client';
import type { ChatMessage, Proposal, QuestionEnvelope, ImportInfo } from '../../types';
import { useChatStore } from '../../store/chat';
import { useAuthStore } from '../../store/auth';

const ACCEPTED_FILE_TYPES = '.pdf,.docx,.doc,.txt,.xls,.xlsx';

let _seq = 0;
const nid = (p: string) => `${p}-${Date.now()}-${++_seq}`;

// ─── Карточка предложения (любые записи — только через неё) ──────
const ProposalCard: React.FC<{
  proposal: Proposal;
  onDone: (report: string, applied: boolean) => void;
}> = ({ proposal, onDone }) => {
  const [busy, setBusy] = useState(false);
  const total = proposal.total;
  const allShown = total <= proposal.items.length;
  const [checked, setChecked] = useState<Set<number>>(
    () => new Set(proposal.items.map((_i, idx) => idx)),
  );

  const meta = proposal.kind === 'CLEAR'
    ? { icon: <Trash2 size={18} className="text-red-600" />, title: 'Удаление из календаря', cls: 'bg-red-50 border-red-200', btn: 'bg-red-600 hover:bg-red-700 disabled:bg-red-300', applyLabel: 'Удалить' }
    : proposal.kind === 'IMPORT_PLAN'
    ? { icon: <FileText size={18} className="text-amber-600" />, title: 'Импорт расписания', cls: 'bg-amber-50 border-amber-200', btn: 'bg-green-600 hover:bg-green-700 disabled:bg-green-300', applyLabel: 'Добавить в календарь' }
    : { icon: <Sparkles size={18} className="text-indigo-600" />, title: 'Действия AI', cls: 'bg-indigo-50 border-indigo-200', btn: 'bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300', applyLabel: 'Применить' };

  const toggle = (i: number) => {
    if (!allShown) return;
    setChecked((prev) => {
      const n = new Set(prev);
      if (n.has(i)) n.delete(i); else n.add(i);
      return n;
    });
  };

  const apply = async () => {
    setBusy(true);
    try {
      const selected = allShown && checked.size < proposal.items.length
        ? [...checked].sort((a, b) => a - b)
        : undefined;
      const res = await api.confirmProposal(proposal.id, selected);
      onDone(res.report, !!res.ok);
    } catch (err: unknown) {
      onDone(`❌ Не удалось применить: ${err instanceof Error ? err.message : 'ошибка'}`, false);
    } finally { setBusy(false); }
  };

  const reject = async () => {
    setBusy(true);
    try { await api.rejectProposal(proposal.id); onDone('', false); }
    catch { /* карточка станет неактуальной при перезагрузке */ }
    finally { setBusy(false); }
  };

  return (
    <div className={`border rounded-2xl p-4 ${meta.cls}`}>
      <div className="flex items-center gap-2 mb-1">
        {meta.icon}
        <span className="font-semibold text-gray-800">{meta.title}</span>
        <span className="text-xs text-gray-500">({total} {total === 1 ? 'запись' : 'записе'}{total > 1 ? 'ей' : ''})</span>
      </div>
      {proposal.summary && (
        <p className="text-xs text-gray-600 mb-2">{proposal.summary}</p>
      )}
      <div className="space-y-1.5 max-h-64 overflow-y-auto">
        {proposal.items.map((it, i) => (
          <label key={i}
            className={`flex items-start gap-2 text-sm bg-white rounded-lg px-2.5 py-1.5 border border-black/5 ${allShown ? 'cursor-pointer' : ''}`}>
            {allShown && (
              <input type="checkbox" checked={checked.has(i)} onChange={() => toggle(i)}
                className="mt-1 accent-indigo-600" />
            )}
            <span className="min-w-0 break-words">{it.text}</span>
          </label>
        ))}
        {!allShown && (
          <p className="text-xs text-gray-500 px-1">
            Показаны первые {proposal.items.length} из {total} — выбор по строкам доступен, когда в карточке
            помещаются все записи. Применится всё предложение целиком.
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button onClick={apply} disabled={busy || (allShown && checked.size === 0)}
          className={`flex items-center gap-1.5 px-4 py-2 text-white rounded-xl text-sm font-medium transition ${meta.btn}`}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
          {meta.applyLabel}{allShown && checked.size < proposal.items.length ? ` (${checked.size})` : ''}
        </button>
        <button onClick={reject} disabled={busy}
          className="flex items-center gap-1.5 px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 rounded-xl text-sm transition">
          <XCircle size={16} /> Отмена
        </button>
      </div>
    </div>
  );
};

// ─── Вопрос системы с кнопками быстрого ответа ───────────────────
const QuestionCard: React.FC<{
  question: QuestionEnvelope;
  disabled?: boolean;
  onReply: (value: string) => void;
}> = ({ question, disabled, onReply }) => (
  <div className="bg-blue-50 border border-blue-200 rounded-2xl p-4">
    <div className="flex items-start gap-2">
      <Info size={16} className="text-blue-500 mt-0.5 shrink-0" />
      <p className="text-sm text-blue-900 whitespace-pre-wrap">{question.text}</p>
    </div>
    {question.replies?.length > 0 && (
      <div className="flex flex-wrap gap-2 mt-3">
        {question.replies.map((r) => (
          <button key={r.value} disabled={disabled} onClick={() => onReply(r.value)}
            className="px-3 py-1.5 bg-white border border-blue-300 hover:bg-blue-100 disabled:opacity-50 text-blue-700 rounded-lg text-sm font-medium transition">
            {r.label}
          </button>
        ))}
      </div>
    )}
  </div>
);

// ─── Индикатор «файл в памяти» ───────────────────────────────────
const ImportChip: React.FC<{ info: ImportInfo; onCancel: () => void; busy?: boolean }> =
  ({ info, onCancel, busy }) => {
    const stateLabel = info.state === 'ASK_PERIOD' ? 'ждёт ответа о периоде'
      : info.state === 'ASK_END' ? 'ждёт дату окончания семестра'
      : info.state === 'READY' ? 'развёрнут по датам'
      : info.state;
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-800 text-white rounded-xl text-xs">
        <FileText size={14} className="shrink-0" />
        <span className="truncate max-w-[12rem] sm:max-w-md">📄 {info.filename} · {stateLabel}</span>
        <button onClick={onCancel} disabled={busy} title="Отменить импорт"
          className="ml-auto flex items-center gap-1 px-2 py-0.5 bg-white/10 hover:bg-white/20 rounded-lg transition">
          <Ban size={12} /> отменить
        </button>
      </div>
    );
  };

// ─── Основной таб ────────────────────────────────────────────────
const ChatTab: React.FC = () => {
  const {
    messages, proposal, question, importInfo, isStreaming,
    appendMessages, replaceMessages, updateMessage,
    setProposal, setQuestion, setImportInfo, setIsStreaming,
  } = useChatStore();
  const user = useAuthStore((s) => s.user);
  const isManager = user?.role === 'manager' || user?.role === 'admin';

  const [input, setInput] = useState('');
  const [uploading, setUploading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const historyLoaded = useRef(false);

  // ── Восстановление истории и висящей карточки после F5 ─────
  useEffect(() => {
    if (historyLoaded.current) return;
    historyLoaded.current = true;
    api.getChatHistory(60)
      .then((h) => {
        replaceMessages(h.messages);
        if (h.pending_proposal) setProposal(h.pending_proposal);
        if (h.question) setQuestion(h.question);
        if (h.import) setImportInfo(h.import);
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming, proposal, question]);

  // ── Отправка сообщения (текст или быстрый ответ) ────────────
  const sendText = async (raw: string) => {
    const text = raw.trim();
    if (!text || isStreaming) return;

    appendMessages({ id: nid('usr'), role: 'user', content: text, created_at: new Date().toISOString() });
    setInput('');
    setQuestion(null);
    setIsStreaming(true);
    abortControllerRef.current = new AbortController();

    const assistantId = nid('ast');
    appendMessages({ id: assistantId, role: 'assistant', content: '', created_at: new Date().toISOString() });

    try {
      const response = await api.sendChatMessage(text, abortControllerRef.current.signal);
      if (!response.ok) {
        const errorText = await response.text().catch(() => '');
        throw new Error(errorText || `Ошибка сервера (${response.status})`);
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error('Поток ответа недоступен');

      const decoder = new TextDecoder();
      let buffer = '';
      let gotChunk = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) {
              if (!gotChunk && data.chunk !== '') gotChunk = true;
              const c = data.chunk;
              if (c) updateMessage(assistantId, (m) => ({ ...m, content: m.content + c }));
            }
            if (typeof data.final_text === 'string') {
              const t = data.final_text;
              updateMessage(assistantId, (m) => ({ ...m, content: t }));
            }
            if (data.error) {
              updateMessage(assistantId, (m) => ({ ...m, content: `❌ ${m.content || 'Ошибка'}` }));
            }
            if (data.proposal) setProposal(data.proposal as Proposal);
            if (data.question) setQuestion(data.question as QuestionEnvelope);
            // активный импорт мог измениться (отмена, развёртка) — обновим индикатор
            if (data.import) setImportInfo(data.import as ImportInfo);
          } catch { /* не JSON */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') return;
      const message = err instanceof Error ? err.message : 'Ошибка соединения';
      updateMessage(assistantId, (m) => ({ ...m, content: `❌ Ошибка: ${message}` }));
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(input); }
  };

  // ── Загрузка файла ──────────────────────────────────────────
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const instruction = input.trim();
      appendMessages({
        id: nid('fu'), role: 'user',
        content: `📎 Загружен файл: ${file.name}` + (instruction ? `\nЗапрос: ${instruction}` : ''),
        created_at: new Date().toISOString(),
      });
      setInput('');
      const result = await api.uploadFile(file, instruction || undefined);
      appendMessages({
        id: nid('fa'), role: 'assistant',
        content: result.message || 'Файл обработан.',
        created_at: new Date().toISOString(),
      });
      setProposal(result.proposal ?? null);
      setQuestion(result.question ?? null);
      setImportInfo(result.import ?? null);
    } catch (err: unknown) {
      appendMessages({
        id: nid('fe'), role: 'assistant',
        content: `❌ ${err instanceof Error ? err.message : 'Ошибка загрузки файла'}`,
        created_at: new Date().toISOString(),
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // ── После применения/отклонения карточки ────────────────────
  const onProposalDone = (report: string, applied: boolean) => {
    setProposal(null);
    if (report) {
      appendMessages({
        id: nid('rep'), role: 'assistant',
        content: report,
        created_at: new Date().toISOString(),
      });
    }
    if (applied) {
      setImportInfo(null);
      window.dispatchEvent(new CustomEvent('data-changed'));
    }
  };

  return (
    <div className="max-w-4xl mx-auto h-[calc(100dvh-14.5rem)] sm:h-[calc(100dvh-10rem)] flex flex-col">
      {/* Заголовок + индикатор файла */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Bot size={22} className="text-indigo-600" />
        <h2 className="text-xl font-bold text-gray-800">AI Чат</h2>
        <span className="hidden sm:inline text-xs text-gray-400">| История сохраняется</span>
        {importInfo && (
          <div className="ml-auto">
            <ImportChip info={importInfo} busy={isStreaming || uploading}
              onCancel={() => sendText('отмена')} />
          </div>
        )}
      </div>

      {/* Подсказка */}
      <div className="hidden sm:flex items-start gap-2 p-3 mb-3 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-800">
        <Info size={16} className="text-blue-500 mt-0.5 shrink-0" />
        <div>
          {isManager ? (
            <>
              <strong>Режим управляющего:</strong> перетащите файл расписания в чат — пары разложатся
              по датам; на вопрос о периоде ответьте кнопкой. Затем:
              <code className="text-xs bg-blue-100 px-1.5 py-0.5 rounded mx-1">распредели всем преподавателям</code>
              — записи получат только те, у кого есть учётка (дубли пропускаются);
              <code className="text-xs bg-blue-100 px-1.5 py-0.5 rounded mx-1">перенеси пары Федуловой к Шапуленковой</code>
              — занятия одного преподавателя из файла — в календарь другого. Можно править календарь
              любого преподавателя: «удали у ФИО все пары в среду».
            </>
          ) : (
            <>
              <strong>Что умеет чат:</strong> загрузить файл расписания (📎), добавить/удалить пары и задачи,
              перенести занятие, поставить задачу на день — и всегда спрашивает подтверждение карточкой.
              <br />
              <span className="text-xs text-blue-600">
                Примеры: «какие у меня пары завтра?», «поставь задачу на пятницу — сходить в деканат»,
                «добавь пары Федуловой А.С. ко мне», «очисти календарь полностью».
                После загрузки файл остаётся «в памяти» — недели раскладываются по вопросу о периоде.
              </span>
            </>
          )}
        </div>
      </div>

      {/* Сообщения */}
      <div className="flex-1 overflow-y-auto bg-white rounded-2xl border border-gray-200 p-3 sm:p-4 mb-3 space-y-3">
        {messages.length === 0 ? (
          <div className="text-center text-gray-400 mt-20">
            <div className="flex justify-center mb-3"><Bot size={48} className="opacity-30" /></div>
            <p>Загрузите файл с расписанием или попросите изменить календарь и заметки.</p>
            <p className="text-xs mt-2">Например: «перенеси пару на пятницу», «добавь задачу на завтра».</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`flex gap-3 ${msg.role === 'assistant' ? 'justify-start' : 'justify-end'}`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                msg.role === 'assistant'
                  ? msg.content.startsWith('❌') ? 'bg-red-50 text-red-800 border border-red-200'
                  : msg.content.startsWith('✅') || msg.content.startsWith('Выполнено') || msg.content.startsWith('Добавлено') ? 'bg-green-50 text-green-800 border border-green-200'
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
                    <UserIcon size={12} className="text-indigo-200" />
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {isStreaming && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl px-4 py-3 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" /> печатает…
            </div>
          </div>
        )}

        {question && !proposal && (
          <QuestionCard question={question} disabled={isStreaming} onReply={sendText} />
        )}
        {proposal && <ProposalCard proposal={proposal} onDone={onProposalDone} />}
        {proposal && question && (
          <QuestionCard question={question} disabled={isStreaming} onReply={sendText} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Ввод */}
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
        <button type="button" onClick={() => sendText(input)} disabled={!input.trim() || isStreaming}
          className="p-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white rounded-xl transition-colors shrink-0">
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default ChatTab;
