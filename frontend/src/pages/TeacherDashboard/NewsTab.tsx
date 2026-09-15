import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Newspaper, Loader2, Image as ImageIcon, X, Pin, PinOff, Pencil, Trash2,
  Plus, Paperclip, Megaphone, Clock, User as UserIcon,
} from 'lucide-react';
import * as api from '../../api/client';
import type { NewsItem } from '../../types';
import { useAuthStore } from '../../store/auth';

const MAX_IMAGES = 5;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

const fmtDate = (iso: string) => {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  return isNaN(d.getTime()) ? '' : d.toLocaleString('ru-RU', {
    day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  });
};

// имена файлов из url /media/news/<id>/<name>
const nameOfUrl = (u: string) => u.split('/').pop() || '';

const LightBox: React.FC<{ images: string[]; index: number; onClose: () => void }> =
  ({ images, index, onClose }) => {
    const [i, setI] = useState(index);
    useEffect(() => {
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
        if (e.key === 'ArrowRight') setI((v) => (v + 1) % images.length);
        if (e.key === 'ArrowLeft') setI((v) => (v - 1 + images.length) % images.length);
      };
      window.addEventListener('keydown', onKey);
      return () => window.removeEventListener('keydown', onKey);
    }, [images.length, onClose]);
    return (
      <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={onClose}>
        <button className="absolute top-4 right-4 text-white/80 hover:text-white p-2" onClick={onClose}><X size={28} /></button>
        {images.length > 1 && (
          <button className="absolute left-3 text-white/70 hover:text-white p-2 text-3xl"
            onClick={(e) => { e.stopPropagation(); setI((v) => (v - 1 + images.length) % images.length); }}>‹</button>
        )}
        <img src={images[i]} alt="" className="max-h-[88vh] max-w-[92vw] rounded-xl object-contain"
          onClick={(e) => e.stopPropagation()} />
        {images.length > 1 && (
          <button className="absolute right-3 text-white/70 hover:text-white p-2 text-3xl"
            onClick={(e) => { e.stopPropagation(); setI((v) => (v + 1) % images.length); }}>›</button>
        )}
      </div>
    );
  };

// ─── Форма публикации / редактирования (только manager/admin) ────
const NewsForm: React.FC<{
  editing: NewsItem | null;
  onDone: () => void;
  onCancel: () => void;
}> = ({ editing, onDone, onCancel }) => {
  const [title, setTitle] = useState(editing?.title ?? '');
  const [body, setBody] = useState(editing?.body ?? '');
  const [pinned, setPinned] = useState(editing?.pinned ?? false);
  const [files, setFiles] = useState<File[]>([]);
  const [keep, setKeep] = useState<string[]>(editing ? editing.images.map(nameOfUrl) : []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  // превью: ещё не отправленные файлы + уже сохранённые картинки при правке
  const previews: Array<{ url: string; remove: () => void }> = [
    ...keep.map((n) => ({
      url: `${apiBaseUrl}/media/news/${editing!.id}/${n}`,
      remove: () => setKeep((k) => k.filter((x) => x !== n)),
    })),
    ...files.map((f, i) => ({
      url: URL.createObjectURL(f),
      remove: () => setFiles((fs) => fs.filter((_, j) => j !== i)),
    })),
  ];

  const addFiles = (list: FileList | null) => {
    setErr('');
    if (!list) return;
    const next: File[] = [];
    for (const f of Array.from(list)) {
      if (keep.length + files.length + next.length >= MAX_IMAGES) {
        setErr(`Максимум ${MAX_IMAGES} картинок`); break;
      }
      if (!IMAGE_TYPES.includes(f.type)) { setErr(`«${f.name}» — не картинка (PNG/JPG/WebP/GIF)`); continue; }
      if (f.size > MAX_IMAGE_BYTES) { setErr(`«${f.name}» больше 5 МБ`); continue; }
      next.push(f);
    }
    setFiles((cur) => [...cur, ...next]);
    if (fileRef.current) fileRef.current.value = '';
  };

  const submit = async () => {
    if (busy) return;
    if (!title.trim() && !body.trim()) { setErr('Заголовок или текст — обязательно'); return; }
    setBusy(true); setErr('');
    try {
      if (editing) {
        await api.updateNews(editing.id, { title: title.trim(), body: body.trim(), pinned }, keep, files);
      } else {
        await api.createNews(title.trim(), body.trim(), pinned, files);
      }
      window.dispatchEvent(new CustomEvent('data-changed'));
      onDone();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Не удалось сохранить');
    } finally { setBusy(false); }
  };

  return (
    <div className="bg-white border border-indigo-200 rounded-2xl p-4 space-y-2">
      <p className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
        <Megaphone size={15} className="text-indigo-500" />
        {editing ? 'Редактирование новости' : 'Новая новость'}
      </p>
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200}
        placeholder="Заголовок (необязательно)"
        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none" />
      <textarea value={body} onChange={(e) => setBody(e.target.value)} maxLength={20000} rows={4}
        placeholder="Текст новости…"
        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y" />
      {previews.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {previews.map((pv, i) => (
            <div key={i} className="relative">
              <img src={pv.url} alt="" className="h-16 w-16 object-cover rounded-lg border border-gray-200" />
              <button onClick={pv.remove}
                className="absolute -top-1.5 -right-1.5 bg-white border border-gray-300 rounded-full p-0.5 text-gray-600 hover:text-red-600">
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center gap-3 flex-wrap">
        <button type="button" onClick={() => fileRef.current?.click()}
          className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg transition"
          disabled={keep.length + files.length >= MAX_IMAGES}>
          <Paperclip size={14} /> Прикрепить картинку ({keep.length + files.length}/{MAX_IMAGES})
        </button>
        <input ref={fileRef} type="file" accept={IMAGE_TYPES.join(',')} multiple
          onChange={(e) => addFiles(e.target.files)} className="hidden" />
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer select-none">
          <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)}
            className="accent-indigo-600" /> 📌 закрепить как важную
        </label>
      </div>
      {err && <p className="text-xs text-red-600">{err}</p>}
      <div className="flex gap-2 pt-1">
        <button onClick={submit} disabled={busy}
          className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white rounded-xl text-sm font-medium transition">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          {editing ? 'Сохранить' : 'Опубликовать'}
        </button>
        <button onClick={onCancel} disabled={busy}
          className="px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 rounded-xl text-sm transition">
          Отмена
        </button>
      </div>
    </div>
  );
};

const apiBaseUrl = '' // SPA и API на одном origin

const NewsTab: React.FC = () => {
  const { user } = useAuthStore();
  const canPublish = user?.role === 'manager' || user?.role === 'admin';
  const [items, setItems] = useState<NewsItem[] | null>(null);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<NewsItem | null>(null);
  const [lightbox, setLightbox] = useState<{ images: string[]; index: number } | null>(null);
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    try {
      setItems(await api.listNews());
      setError('');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить новости');
    }
  }, []);

  useEffect(() => {
    load();
    // при любой правке из чата/другой вкладки — обновляем ленту
    const on = () => { load(); };
    window.addEventListener('data-changed', on);
    return () => window.removeEventListener('data-changed', on);
  }, [load]);

  // зашли во вкладку — сбрасываем бейдж «нового»
  useEffect(() => {
    api.markNewsRead()
      .then(() => window.dispatchEvent(new CustomEvent('news-read')))
      .catch(() => {});
  }, []);

  const act = async (id: string, fn: () => Promise<void>) => {
    setBusyId(id);
    try { await fn(); await load(); window.dispatchEvent(new CustomEvent('data-changed')); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : 'Действие не выполнено'); }
    finally { setBusyId(''); }
  };

  if (items === null && !error) {
    return <div className="flex justify-center py-24"><Loader2 className="animate-spin text-indigo-500" size={28} /></div>;
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <Newspaper size={22} className="text-indigo-600" />
        <h2 className="text-xl font-bold text-gray-800">Новости</h2>
        {canPublish && !formOpen && (
          <button onClick={() => { setEditing(null); setFormOpen(true); }}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-medium transition">
            <Plus size={15} /> Опубликовать
          </button>
        )}
      </div>
      {!canPublish && (
        <p className="text-xs text-gray-500 mb-3 -mt-2">
          Публиковать новости могут только административная и админ-учётная записи.
        </p>
      )}

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      {formOpen && (
        <div className="mb-4">
          <NewsForm editing={editing}
            onDone={() => { setFormOpen(false); setEditing(null); }}
            onCancel={() => { setFormOpen(false); setEditing(null); }} />
        </div>
      )}

      {items !== null && items.length === 0 && !formOpen && (
        <div className="text-center text-gray-400 py-20">
          <div className="flex justify-center mb-3"><Newspaper size={48} className="opacity-30" /></div>
          <p>Новостей пока нет.</p>
          {canPublish && <p className="text-xs mt-1">Опубликуйте первую — здесь или прямо из чата: «опубликуй новость — …».</p>}
        </div>
      )}

      <div className="space-y-3 pb-10">
        {items?.map((n) => (
          <article key={n.id}
            className={`bg-white rounded-2xl border p-4 sm:p-5 ${n.pinned ? 'border-amber-300 ring-1 ring-amber-200' : 'border-gray-200'}`}>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                {n.pinned && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-100 rounded-full px-2 py-0.5 mb-1.5">
                    <Pin size={11} /> Важно
                  </span>
                )}
                {n.title && <h3 className="text-base sm:text-lg font-semibold text-gray-900">{n.title}</h3>}
                <p className="text-sm text-gray-700 whitespace-pre-wrap mt-0.5">{n.body}</p>
                <p className="flex items-center gap-2 flex-wrap text-[11px] text-gray-400 mt-2">
                  <span className="inline-flex items-center gap-1"><UserIcon size={11} /> {n.author_name}</span>
                  <span className="inline-flex items-center gap-1"><Clock size={11} /> {fmtDate(n.created_at)}</span>
                  {n.updated_at && n.updated_at !== n.created_at && <span>(изменена)</span>}
                </p>
              </div>
              {canPublish && (
                <div className="flex gap-1 shrink-0">
                  <button title={n.pinned ? 'Открепить' : 'Закрепить'} disabled={busyId === n.id}
                    onClick={() => act(n.id, () => api.pinNews(n.id).then(() => undefined))}
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500">
                    {n.pinned ? <PinOff size={15} /> : <Pin size={15} />}
                  </button>
                  <button title="Редактировать" disabled={busyId === n.id}
                    onClick={() => { setEditing(n); setFormOpen(true); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"><Pencil size={15} /></button>
                  <button title="Удалить" disabled={busyId === n.id}
                    onClick={() => { if (confirm('Удалить новость?')) act(n.id, () => api.deleteNews(n.id)); }}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-red-500"><Trash2 size={15} /></button>
                </div>
              )}
            </div>
            {n.images.length > 0 && (
              <div className={`grid gap-2 mt-3 ${n.images.length === 1 ? 'grid-cols-1 max-w-md' : 'grid-cols-2 sm:grid-cols-3'}`}>
                {n.images.map((u, i) => (
                  <button key={u} onClick={() => setLightbox({ images: n.images, index: i })}
                    className="relative group rounded-xl overflow-hidden border border-gray-200">
                    <img src={u} alt="" loading="lazy"
                      className={`w-full object-cover ${n.images.length === 1 ? 'max-h-72' : 'h-28 sm:h-32'} group-hover:opacity-90 transition`} />
                    <span className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/20 transition">
                      <ImageIcon size={20} className="text-white" />
                    </span>
                  </button>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>

      {lightbox && <LightBox images={lightbox.images} index={lightbox.index} onClose={() => setLightbox(null)} />}
    </div>
  );
};

export default NewsTab;
