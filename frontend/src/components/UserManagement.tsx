import React, { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Edit3,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  UserRound,
  UsersRound,
  X,
  XCircle,
} from 'lucide-react';
import { toast } from '../utils/toast';
import apiService, { ManagedUser } from '../services/apiService';
import { BUSINESS_UNITS, useAuth } from '../contexts/AuthContext';
import './UserManagement.css';

type ManagedRole = ManagedUser['role'];

const BU_ROLE_TO_UNIT: Partial<Record<ManagedRole, string>> = {
  GENAI: 'GenAI',
  DATABASE_MANAGEMENT: 'Database Management',
  DATA_ENGINEERING: 'Data Engineering',
  CLOUD: 'Cloud',
  MLOPS: 'MLOps',
};

const ROLE_OPTIONS: Array<{ value: ManagedRole; label: string }> = [
  { value: 'USER', label: 'User' },
  { value: 'GENAI', label: 'GenAI' },
  { value: 'DATABASE_MANAGEMENT', label: 'Database Management' },
  { value: 'DATA_ENGINEERING', label: 'Data Engineering' },
  { value: 'CLOUD', label: 'Cloud' },
  { value: 'MLOPS', label: 'MLOps' },
  { value: 'ADMIN', label: 'Administrator' },
];

const roleLabel = (role: ManagedRole) => (
  ROLE_OPTIONS.find(option => option.value === role)?.label || role
);

const displayEmployeeId = (employeeId?: number | null) => (
  employeeId ? `SK-${employeeId}` : '—'
);

interface UserFormState {
  email: string;
  name: string;
  roles: ManagedRole[];
  business_unit: string;
  employee_id: string;
  password: string;
  status: ManagedUser['status'];
}

const emptyForm: UserFormState = {
  email: '',
  name: '',
  roles: ['USER'] as ManagedRole[],
  business_unit: 'GenAI',
  employee_id: '',
  password: '',
  status: 'active' as 'active' | 'inactive',
};

const UserManagement: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState('');
  const [businessUnitFilter, setBusinessUnitFilter] = useState('all');
  const [roleFilter, setRoleFilter] = useState('all');
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ManagedUser | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await apiService.fetchManagedUsers();
      setUsers(response.users || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const openCreate = () => {
    setEditingUser(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEdit = (managedUser: ManagedUser) => {
    setEditingUser(managedUser);
    setForm({
      email: managedUser.email,
      name: managedUser.name,
      roles: managedUser.roles?.length ? managedUser.roles : [managedUser.role],
      business_unit: managedUser.business_unit || '',
      employee_id: managedUser.employee_id ? String(managedUser.employee_id) : '',
      password: '',
      status: managedUser.status,
    });
    setShowForm(true);
  };

  const toggleRole = (role: ManagedRole) => {
    setForm(current => {
      if (role === 'ADMIN') return { ...current, roles: ['ADMIN'], business_unit: '' };
      if (role === 'USER') return { ...current, roles: ['USER'], business_unit: current.business_unit || 'GenAI' };
      const withoutExclusive = current.roles.filter(value => value !== 'ADMIN' && value !== 'USER');
      const roles = withoutExclusive.includes(role)
        ? withoutExclusive.filter(value => value !== role)
        : [...withoutExclusive, role];
      const selected = roles.length ? roles : ['USER' as ManagedRole];
      return {
        ...current,
        roles: selected,
        business_unit: selected[0] === 'USER' ? current.business_unit || 'GenAI' : BU_ROLE_TO_UNIT[selected[0]] || '',
      };
    });
  };

  const saveUser = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      setSaving(true);
      if (editingUser) {
        const payload: Parameters<typeof apiService.updateManagedUser>[1] = {
          name: form.name,
          role: form.roles[0],
          roles: form.roles,
          business_unit: form.business_unit || null,
          status: form.status,
        };
        if (form.password) payload.password = form.password;
        await apiService.updateManagedUser(editingUser.email, payload);
        toast.success('User updated');
      } else {
        await apiService.createManagedUser({
          email: form.email,
          name: form.name,
          role: form.roles[0],
          roles: form.roles,
          business_unit: form.business_unit || null,
          password: form.password,
          employee_id: form.employee_id ? Number(form.employee_id) : undefined,
        });
        toast.success('User created');
      }
      setShowForm(false);
      await loadUsers();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to save user');
    } finally {
      setSaving(false);
    }
  };

  const toggleStatus = async (managedUser: ManagedUser) => {
    const nextStatus = managedUser.status === 'active' ? 'inactive' : 'active';
    try {
      await apiService.updateManagedUser(managedUser.email, { status: nextStatus });
      toast.success(nextStatus === 'active' ? 'User activated' : 'User deactivated');
      await loadUsers();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to update status');
    }
  };

  const deleteUser = async () => {
    if (!deleteTarget) return;
    try {
      setSaving(true);
      await apiService.deleteManagedUser(deleteTarget.email);
      toast.success('User deleted');
      setDeleteTarget(null);
      await loadUsers();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to delete user');
    } finally {
      setSaving(false);
    }
  };

  const filteredUsers = useMemo(() => users.filter(managedUser => {
    const search = query.toLowerCase();
    const matchesSearch = !search || [managedUser.name, managedUser.email, displayEmployeeId(managedUser.employee_id), ...(managedUser.business_units || [])]
      .some(value => value.toLowerCase().includes(search));
    const roles = managedUser.roles?.length ? managedUser.roles : [managedUser.role];
    const matchesBU = businessUnitFilter === 'all' || (managedUser.business_units || [managedUser.business_unit]).includes(businessUnitFilter);
    const roleGroup = roles.length === 1 && roles[0] === 'USER'
      ? 'USER'
      : roles.includes('ADMIN') ? 'ADMIN' : 'BU_HEAD';
    const matchesRole = roleFilter === 'all' || roleFilter === roleGroup;
    return matchesSearch && matchesBU && matchesRole;
  }), [users, query, businessUnitFilter, roleFilter]);

  const activeCount = users.filter(item => item.status === 'active').length;
  const userCount = users.filter(item => (item.roles || [item.role]).length === 1 && (item.roles || [item.role])[0] === 'USER').length;
  const buHeadCount = users.filter(item => !(item.roles || [item.role]).includes('USER') && !(item.roles || [item.role]).includes('ADMIN')).length;

  return (
    <div className="user-management-page">
      <header className="user-management-header">
        <div>
          <h1>User Management</h1>
          <p>Manage administrators, business-unit access, and individual users.</p>
        </div>
        <button className="primary-user-action" onClick={openCreate}>
          <Plus size={18} /> Add User
        </button>
      </header>

      <section className="user-summary-grid" aria-label="User database summary">
        <div className="user-summary-card"><UsersRound /><div><strong>{users.length}</strong><span>Total accounts</span></div></div>
        <div className="user-summary-card"><CheckCircle2 /><div><strong>{activeCount}</strong><span>Active accounts</span></div></div>
        <div className="user-summary-card"><ShieldCheck /><div><strong>{buHeadCount}</strong><span>BU role users</span></div></div>
        <div className="user-summary-card"><UserRound /><div><strong>{userCount}</strong><span>Individual users</span></div></div>
      </section>

      <section className="user-directory-panel">
        <div className="user-directory-toolbar">
          <div className="user-search-field">
            <Search size={17} />
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search users..." />
          </div>
          <select value={businessUnitFilter} onChange={event => setBusinessUnitFilter(event.target.value)} aria-label="Filter users by business unit">
            <option value="all">All Business Units</option>
            {BUSINESS_UNITS.map(unit => <option value={unit} key={unit}>{unit}</option>)}
          </select>
          <select value={roleFilter} onChange={event => setRoleFilter(event.target.value)} aria-label="Filter users by role">
            <option value="all">All Roles</option>
            <option value="ADMIN">Administrators</option>
            <option value="BU_HEAD">Business-unit roles</option>
            <option value="USER">Users</option>
          </select>
        </div>

        <div className="user-table-wrap">
          <table className="user-directory-table">
            <thead><tr><th>User</th><th>Employee ID</th><th>Roles</th><th>Business Units</th><th>Status</th><th className="user-actions-heading">Actions</th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="user-empty-state">Loading users…</td></tr>
              ) : filteredUsers.length === 0 ? (
                <tr><td colSpan={6} className="user-empty-state">No users match these filters.</td></tr>
              ) : filteredUsers.map(managedUser => {
                const isSelf = managedUser.email === currentUser?.email;
                return (
                  <tr key={managedUser.email}>
                    <td><div className="user-identity-cell"><span className="user-avatar">{managedUser.name.slice(0, 1).toUpperCase()}</span><div><strong>{managedUser.name}</strong><span>{managedUser.email}</span></div></div></td>
                    <td>{displayEmployeeId(managedUser.employee_id)}</td>
                    <td><div className="user-role-list">{(managedUser.roles || [managedUser.role]).map(role => <span key={role} className={`role-pill role-${role.toLowerCase()}`}>{roleLabel(role)}</span>)}</div></td>
                    <td>{(managedUser.business_units || [managedUser.business_unit]).filter(Boolean).join(', ') || 'All Business Units'}</td>
                    <td><span className={`user-status status-${managedUser.status}`}>{managedUser.status}</span></td>
                    <td><div className="user-row-actions">
                      <button title="Edit user" onClick={() => openEdit(managedUser)}><Edit3 size={16} /></button>
                      <button title={managedUser.status === 'active' ? 'Deactivate user' : 'Activate user'} disabled={isSelf} onClick={() => toggleStatus(managedUser)}>
                        {managedUser.status === 'active' ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
                      </button>
                      <button className="danger" title="Delete user" disabled={isSelf} onClick={() => setDeleteTarget(managedUser)}><Trash2 size={16} /></button>
                    </div></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {showForm && (
        <div className="user-modal-backdrop" role="presentation">
          <div className="user-modal" role="dialog" aria-modal="true" aria-labelledby="user-form-title">
            <div className="user-modal-header"><div><h2 id="user-form-title">{editingUser ? 'Edit User' : 'Add User'}</h2><p>{editingUser ? 'Update access, assignment, or credentials.' : 'Create an account with the appropriate access level.'}</p></div><button onClick={() => setShowForm(false)} aria-label="Close"><X size={20} /></button></div>
            <form onSubmit={saveUser}>
              <div className="user-form-grid">
                <label><span>Name</span><input required value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} /></label>
                <label><span>Email</span><input type="email" required disabled={Boolean(editingUser)} value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} /></label>
                {!editingUser && <label><span>Employee ID (optional)</span><input type="number" min="1" step="1" value={form.employee_id} onChange={event => setForm({ ...form, employee_id: event.target.value.replace(/\D/g, '') })} /></label>}
                <fieldset className="user-role-fieldset" disabled={editingUser?.email === currentUser?.email}><legend>Roles</legend>{ROLE_OPTIONS.map(option => <label key={option.value}><input type="checkbox" checked={form.roles.includes(option.value)} onChange={() => toggleRole(option.value)} /><span>{option.label}</span></label>)}</fieldset>
                {form.roles.length === 1 && form.roles[0] === 'USER' && <label><span>Business Unit</span><select value={form.business_unit} onChange={event => setForm({ ...form, business_unit: event.target.value })}>{BUSINESS_UNITS.map(unit => <option value={unit} key={unit}>{unit}</option>)}</select></label>}
                {editingUser && <label><span>Status</span><select value={form.status} onChange={event => setForm({ ...form, status: event.target.value as ManagedUser['status'] })} disabled={editingUser.email === currentUser?.email}>{form.status === 'pending_verification' && <option value="pending_verification">Pending verification</option>}<option value="active">Active</option><option value="inactive">Inactive</option></select></label>}
                <label className={editingUser ? '' : 'user-form-span'}><span>{editingUser ? 'New Password (optional)' : 'Temporary Password'}</span><input type="password" required={!editingUser} minLength={6} value={form.password} onChange={event => setForm({ ...form, password: event.target.value })} placeholder="At least 6 characters" /></label>
              </div>
              <div className="user-modal-actions"><button type="button" className="secondary-user-action" onClick={() => setShowForm(false)}>Cancel</button><button type="submit" className="primary-user-action" disabled={saving}>{saving ? 'Saving…' : editingUser ? 'Save Changes' : 'Create User'}</button></div>
            </form>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="user-modal-backdrop" role="presentation">
          <div className="user-modal user-delete-modal" role="alertdialog" aria-modal="true">
            <span className="delete-warning-icon"><Trash2 size={22} /></span>
            <h2>Delete {deleteTarget.name}?</h2>
            <p>This permanently removes the login account. Existing SOW records remain stored.</p>
            <div className="user-modal-actions"><button className="secondary-user-action" onClick={() => setDeleteTarget(null)}>Cancel</button><button className="danger-user-action" onClick={deleteUser} disabled={saving}>{saving ? 'Deleting…' : 'Delete User'}</button></div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserManagement;
