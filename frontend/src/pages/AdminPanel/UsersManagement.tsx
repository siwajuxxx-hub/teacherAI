import React, { useEffect, useState, useCallback } from 'react';
import {
  Plus,
  Pencil,
  Trash2,
  Key,
  Search,
  Loader2,
  AlertCircle,
  User,
  X,
  Check,
  Ban,
} from 'lucide-react';
import * as api from '../../api/client';
import { useAuthStore } from '../../store/auth';
import type { User as UserType, UserCreatePayload, UserUpdatePayload } from '../../types';
import {
  formatDate,
  roleLabel,
  roleBadgeColor,
} from '../../utils/formatters';

// ─── Modal shell ─────────────────────────────────────────────
const Modal: React.FC<{
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}> = ({ open, onClose, title, children }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 relative max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-800">{title}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 transition-colors">
            <X size={20} className="text-gray-500" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

// ─── Confirm dialog ──────────────────────────────────────────
const ConfirmDialog: React.FC<{
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  loading?: boolean;
}> = ({ open, onClose, onConfirm, title, message, loading }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 relative" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-800 mb-2">{title}</h2>
        <p className="text-sm text-gray-600 mb-6">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-xl hover:bg-gray-200 transition-colors">
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-xl hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {loading && <Loader2 size={14} className="animate-spin" />}
            {loading ? 'Удаление...' : 'Удалить'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Main component ──────────────────────────────────────────
const UsersManagement: React.FC = () => {
  const currentUser = useAuthStore((s) => s.user);

  const [users, setUsers] = useState<UserType[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserType | null>(null);

  const [createForm, setCreateForm] = useState({ username: '', password: '', full_name: '', position: '', role: 'teacher' as 'teacher' | 'manager' | 'admin' });
  const [editForm, setEditForm] = useState({ username: '', full_name: '', position: '', role: '', is_active: true });
  const [newPassword, setNewPassword] = useState('');
  const [formError, setFormError] = useState('');

  // ── fetch ─────────────────────────────────────────────────
  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch {
      setError('Ошибка загрузки пользователей');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // ── create ────────────────────────────────────────────────
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.username || !createForm.password || !createForm.full_name) {
      setFormError('Заполните обязательные поля');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      await api.createUser(createForm as UserCreatePayload);
      setShowCreate(false);
      resetCreateForm();
      fetchUsers();
    } catch {
      setFormError('Ошибка при создании пользователя');
    } finally {
      setSaving(false);
    }
  };

  const resetCreateForm = () => {
    setCreateForm({ username: '', password: '', full_name: '', position: '', role: 'teacher' });
    setFormError('');
  };

  // ── edit ──────────────────────────────────────────────────
  const openEdit = (u: UserType) => {
    setSelectedUser(u);
    setEditForm({ username: u.username, full_name: u.full_name, position: u.position || '', role: u.role, is_active: u.is_active });
    setFormError('');
    setShowEdit(true);
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    if (!editForm.username || !editForm.full_name) { setFormError('Заполните обязательные поля'); return; }
    setSaving(true);
    setFormError('');
    try {
      await api.updateUser(selectedUser.id, editForm as UserUpdatePayload);
      setShowEdit(false);
      setSelectedUser(null);
      fetchUsers();
    } catch {
      setFormError('Ошибка при обновлении пользователя');
    } finally {
      setSaving(false);
    }
  };

  // ── toggle active ────────────────────────────────────────
  const toggleActive = async (u: UserType) => {
    try {
      await api.updateUser(u.id, { is_active: !u.is_active });
      fetchUsers();
    } catch {
      setError('Ошибка при изменении статуса');
    }
  };

  // ── change password ──────────────────────────────────────
  const openPassword = (u: UserType) => {
    setSelectedUser(u);
    setNewPassword('');
    setFormError('');
    setShowPassword(true);
  };

  const handlePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser || !newPassword) { setFormError('Введите новый пароль'); return; }
    setSaving(true);
    setFormError('');
    try {
      await api.changePassword(selectedUser.id, newPassword);
      setShowPassword(false);
      setSelectedUser(null);
    } catch {
      setFormError('Ошибка при смене пароля');
    } finally {
      setSaving(false);
    }
  };

  // ── delete ────────────────────────────────────────────────
  const openDelete = (u: UserType) => { setSelectedUser(u); setShowDelete(true); };
  const handleDelete = async () => {
    if (!selectedUser) return;
    setSaving(true);
    try {
      await api.deleteUser(selectedUser.id);
      setShowDelete(false);
      setSelectedUser(null);
      fetchUsers();
    } catch {
      setFormError('Ошибка при удалении пользователя');
    } finally {
      setSaving(false);
    }
  };

  // ── filtered ──────────────────────────────────────────────
  const filtered = users.filter((u) =>
    u.full_name.toLowerCase().includes(search.toLowerCase()) ||
    u.username.toLowerCase().includes(search.toLowerCase()),
  );

  // ── render ────────────────────────────────────────────────
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Пользователи</h1>
          <p className="text-sm text-gray-500 mt-1">Управление учётными записями системы</p>
        </div>
        <button
          onClick={() => { resetCreateForm(); setShowCreate(true); }}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors shadow-sm"
        >
          <Plus size={16} /> Добавить пользователя
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Поиск по имени или логину..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 mb-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          <AlertCircle size={18} />{error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20"><Loader2 size={32} className="animate-spin text-indigo-500" /></div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 text-left">
                  <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Пользователь</th>
                  <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Должность</th>
                  <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Роль</th>
                  <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase text-center">Активен</th>
                  <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Создан</th>
                  <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase text-right">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((u) => (
                  <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center"><User size={16} className="text-gray-500" /></div>
                        <div>
                          <p className="font-medium text-gray-900 text-sm">{u.full_name}</p>
                          <p className="text-xs text-gray-400">{u.username}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-sm text-gray-600">{u.position || '—'}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${roleBadgeColor(u.role)}`}>
                        {roleLabel(u.role)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <button
                        onClick={() => toggleActive(u)}
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                          u.is_active ? 'bg-green-100 text-green-700 hover:bg-green-200' : 'bg-red-100 text-red-700 hover:bg-red-200'
                        }`}
                      >
                        {u.is_active ? <Check size={12} /> : <Ban size={12} />}
                        {u.is_active ? 'Активен' : 'Отключён'}
                      </button>
                    </td>
                    <td className="px-5 py-3.5 text-sm text-gray-400">{formatDate(u.created_at)}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => openEdit(u)} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-indigo-600 transition-colors" title="Редактировать"><Pencil size={16} /></button>
                        <button onClick={() => openPassword(u)} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-amber-600 transition-colors" title="Сменить пароль"><Key size={16} /></button>
                        {currentUser?.id !== u.id && (
                          <button onClick={() => openDelete(u)} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-red-600 transition-colors" title="Удалить"><Trash2 size={16} /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={6} className="px-5 py-10 text-center text-gray-400 text-sm">Пользователи не найдены</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {filtered.map((u) => (
              <div key={u.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center"><User size={20} className="text-gray-500" /></div>
                    <div>
                      <p className="font-semibold text-gray-900">{u.full_name}</p>
                      <p className="text-xs text-gray-400">{u.username}</p>
                    </div>
                  </div>
                  <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${roleBadgeColor(u.role)}`}>{roleLabel(u.role)}</span>
                </div>
                <p className="text-sm text-gray-600 mb-1">{u.position || '—'}</p>
                <div className="flex items-center justify-between text-xs text-gray-400 mb-3">
                  <button onClick={() => toggleActive(u)} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full font-medium ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {u.is_active ? <Check size={12} /> : <Ban size={12} />}{u.is_active ? 'Активен' : 'Отключён'}
                  </button>
                  <span>{formatDate(u.created_at)}</span>
                </div>
                <div className="flex gap-2 pt-2 border-t border-gray-100">
                  <button onClick={() => openEdit(u)} className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-sm text-gray-600 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors"><Pencil size={14} /> Ред.</button>
                  <button onClick={() => openPassword(u)} className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-sm text-amber-600 bg-amber-50 rounded-xl hover:bg-amber-100 transition-colors"><Key size={14} /> Пароль</button>
                  {currentUser?.id !== u.id && (
                    <button onClick={() => openDelete(u)} className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-sm text-red-600 bg-red-50 rounded-xl hover:bg-red-100 transition-colors"><Trash2 size={14} /> Удал.</button>
                  )}
                </div>
              </div>
            ))}
            {filtered.length === 0 && <div className="text-center py-10 text-gray-400 text-sm">Пользователи не найдены</div>}
          </div>
        </>
      )}

      {/* ── Create Modal ────────────────────────────────────── */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Добавить пользователя">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl"><AlertCircle size={16} /> {formError}</div>}
          <div><label className="block text-sm font-medium text-gray-700 mb-1">Логин *</label><input type="text" value={createForm.username} onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" required /></div>
          <div><label className="block text-sm font-medium text-gray-700 mb-1">Пароль *</label><input type="password" value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" required /></div>
          <div><label className="block text-sm font-medium text-gray-700 mb-1">ФИО *</label><input type="text" value={createForm.full_name} onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" required /></div>
          <div><label className="block text-sm font-medium text-gray-700 mb-1">Должность</label><input type="text" value={createForm.position} onChange={(e) => setCreateForm({ ...createForm, position: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Учитель математики" /></div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Роль</label>
            <select value={createForm.role} onChange={(e) => setCreateForm({ ...createForm, role: e.target.value as 'teacher' | 'manager' | 'admin' })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="admin">Администратор</option><option value="manager">Завуч</option><option value="teacher">Учитель</option>
            </select>
          </div>
          <button type="submit" disabled={saving} className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}{saving ? 'Сохранение...' : 'Добавить пользователя'}
          </button>
        </form>
      </Modal>

      {/* ── Edit Modal ──────────────────────────────────────── */}
      <Modal open={showEdit} onClose={() => setShowEdit(false)} title="Редактировать пользователя">
        <form onSubmit={handleEdit} className="space-y-4">
          {formError && <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl"><AlertCircle size={16} /> {formError}</div>}
          <div><label className="block text-sm font-medium text-gray-700 mb-1">Логин *</label><input type="text" value={editForm.username} onChange={(e) => setEditForm({ ...editForm, username: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" required /></div>
          <div><label className="block text-sm font-medium text-gray-700 mb-1">ФИО *</label><input type="text" value={editForm.full_name} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" required /></div>
          <div><label className="block text-sm font-medium text-gray-700 mb-1">Должность</label><input type="text" value={editForm.position} onChange={(e) => setEditForm({ ...editForm, position: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" /></div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Роль</label>
            <select value={editForm.role} onChange={(e) => setEditForm({ ...editForm, role: e.target.value })} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="admin">Администратор</option><option value="manager">Завуч</option><option value="teacher">Учитель</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700">Активен</label>
            <button type="button" onClick={() => setEditForm({ ...editForm, is_active: !editForm.is_active })} className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${editForm.is_active ? 'bg-green-500' : 'bg-gray-300'}`}>
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${editForm.is_active ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
            <span className="text-sm text-gray-500">{editForm.is_active ? 'Активен' : 'Отключён'}</span>
          </div>
          <button type="submit" disabled={saving} className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Pencil size={16} />}{saving ? 'Сохранение...' : 'Сохранить изменения'}
          </button>
        </form>
      </Modal>

      {/* ── Password Modal ──────────────────────────────────── */}
      <Modal open={showPassword} onClose={() => setShowPassword(false)} title="Сменить пароль">
        <form onSubmit={handlePassword} className="space-y-4">
          {formError && <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl"><AlertCircle size={16} /> {formError}</div>}
          {selectedUser && <p className="text-sm text-gray-600">Пользователь: <span className="font-medium text-gray-800">{selectedUser.full_name}</span></p>}
          <div><label className="block text-sm font-medium text-gray-700 mb-1">Новый пароль *</label><input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" required placeholder="Введите новый пароль" /></div>
          <button type="submit" disabled={saving} className="w-full flex items-center justify-center gap-2 py-2.5 bg-amber-600 text-white font-medium rounded-xl hover:bg-amber-700 transition-colors disabled:opacity-50">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Key size={16} />}{saving ? 'Сохранение...' : 'Сменить пароль'}
          </button>
        </form>
      </Modal>

      {/* ── Delete Confirmation ─────────────────────────────── */}
      <ConfirmDialog
        open={showDelete}
        onClose={() => setShowDelete(false)}
        onConfirm={handleDelete}
        title="Удалить пользователя"
        message={selectedUser ? `Вы уверены, что хотите удалить пользователя «${selectedUser.full_name}»? Это действие необратимо.` : ''}
        loading={saving}
      />
    </div>
  );
};

export default UsersManagement;