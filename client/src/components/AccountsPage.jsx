import { Fragment, useEffect, useState } from 'react';
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
    if (editingId === account.id) {
      closeForm();
      return;
    }
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
      setReveal(false);
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

  function renderForm() {
    return (
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
          {editingId && (
            <button type="button" className="secondary-btn" onClick={closeForm}>
              Cancel
            </button>
          )}
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : editingId ? 'Save changes' : 'Save account'}
          </button>
        </div>
      </form>
    );
  }

  if (loading) return <div className="panel-loading">Loading accounts…</div>;

  const addingNew = showForm && !editingId;

  return (
    <div className="centered-panel">
      <div className="toolbar">
        <h2 className="panel-title">Accounts</h2>
        <button onClick={addingNew ? closeForm : openAddForm}>{addingNew ? 'Cancel' : 'Add account'}</button>
      </div>

      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}

      {addingNew && renderForm()}

      {accounts.length === 0 ? (
        <div className="empty-state">No accounts saved yet. Add one to get started.</div>
      ) : (
        <div className="account-list">
          {accounts.map((acc) => (
            <Fragment key={acc.id}>
              <div className="account-row">
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
                    <span className="btn-text">{editingId === acc.id ? 'Close' : 'Edit'}</span>
                    <span className="btn-icon" aria-hidden="true">{editingId === acc.id ? '✕' : '✎'}</span>
                  </button>
                  <button className="danger-btn" disabled={busyId === acc.id} onClick={() => handleDelete(acc)}>
                    <span className="btn-text">Delete</span>
                    <span className="btn-icon" aria-hidden="true">🗑</span>
                  </button>
                </div>
              </div>
              {editingId === acc.id && renderForm()}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
