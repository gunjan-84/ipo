import { useEffect, useState } from 'react';
import { api } from '../api';

const emptyForm = { label: '', user_id: '', password: '', totp_secret: '' };

export default function AccountsPage() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.listAccounts();
      setAccounts(res.data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function openAddForm() {
    setEditingId(null);
    setForm(emptyForm);
    setReveal(false);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(emptyForm);
  }

  async function handleEdit(account) {
    setBusyId(account.id);
    setError('');
    try {
      const res = await api.revealAccount(account.id);
      setForm({
        label: account.label,
        user_id: res.data.user_id,
        password: res.data.password,
        totp_secret: res.data.totp_secret,
      });
      setEditingId(account.id);
      setReveal(true);
      setShowForm(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = {
        label: form.label.trim(),
        user_id: form.user_id.trim(),
        password: form.password,
        totp_secret: form.totp_secret.trim(),
      };
      if (editingId) {
        await api.updateAccount(editingId, payload);
      } else {
        await api.addAccount(payload);
      }
      closeForm();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleConnect(account) {
    setBusyId(account.id);
    setError('');
    try {
      await api.connectAccount(account.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDisconnect(account) {
    setBusyId(account.id);
    try {
      await api.disconnectAccount(account.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(account) {
    if (!confirm(`Remove saved account ${account.label}? This deletes the stored credentials.`)) return;
    setBusyId(account.id);
    try {
      await api.deleteAccount(account.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="panel-loading">Loading accounts…</div>;

  return (
    <div>
      <div className="toolbar">
        <h2 className="panel-title">Accounts</h2>
        <button onClick={showForm ? closeForm : openAddForm}>{showForm ? 'Cancel' : 'Add account'}</button>
      </div>

      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}

      {showForm && (
        <form className="account-form" onSubmit={handleSubmit}>
          <h3 style={{ marginBottom: 4 }}>{editingId ? 'Edit account' : 'Add account'}</h3>
          <label>
            Label (optional)
            <input
              type="text"
              placeholder="e.g. Dad's account"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </label>
          <label>
            User ID
            <input
              type="text"
              value={form.user_id}
              onChange={(e) => setForm({ ...form, user_id: e.target.value })}
              required
            />
          </label>
          <label>
            Password
            <input
              type={reveal ? 'text' : 'password'}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required={!editingId}
              placeholder={editingId ? 'Leave as-is to keep current password' : ''}
            />
          </label>
          <label>
            TOTP secret
            <input
              type={reveal ? 'text' : 'password'}
              placeholder={editingId ? 'Leave as-is to keep current secret' : 'Base32 secret from your authenticator setup'}
              value={form.totp_secret}
              onChange={(e) => setForm({ ...form, totp_secret: e.target.value })}
              required={!editingId}
            />
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} />
            Show password &amp; TOTP secret
          </label>
          <div className="modal-actions">
            <button type="submit" disabled={saving}>
              {saving ? 'Saving…' : editingId ? 'Save changes' : 'Save account'}
            </button>
          </div>
        </form>
      )}

      {accounts.length === 0 ? (
        <div className="empty-state">No accounts saved yet. Add one to get started.</div>
      ) : (
        <div className="account-list">
          {accounts.map((acc) => (
            <div className="account-row" key={acc.id}>
              <div>
                <div className="cell-title">{acc.label}</div>
                <div className="cell-sub">{acc.user_id}</div>
              </div>
              <span className={`status-badge ${acc.connected ? 'status-ongoing' : 'status-closed'}`}>
                {acc.connected ? 'Connected' : 'Not connected'}
              </span>
              <div className="account-actions">
                {acc.connected ? (
                  <button className="secondary-btn" disabled={busyId === acc.id} onClick={() => handleDisconnect(acc)}>
                    Disconnect
                  </button>
                ) : (
                  <button disabled={busyId === acc.id} onClick={() => handleConnect(acc)}>
                    {busyId === acc.id ? 'Connecting…' : 'Connect'}
                  </button>
                )}
                <button className="secondary-btn" disabled={busyId === acc.id} onClick={() => handleEdit(acc)}>
                  Edit
                </button>
                <button className="danger-btn" disabled={busyId === acc.id} onClick={() => handleDelete(acc)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
