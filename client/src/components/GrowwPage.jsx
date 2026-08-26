import { Fragment, useEffect, useState } from 'react';
import { api } from '../api';

const emptyForm = { label: '', bearer_token: '', device_id: '', nkey: '', pin: '' };

function formatDateTime(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return '—';
  }
}

function OrdersPanel({ orders }) {
  if (!orders.length) return <div className="empty-state">No active IPO orders on this account.</div>;
  return (
    <div className="applications-table-wrap" style={{ marginTop: 12 }}>
      <table className="applications-table">
        <thead>
          <tr>
            <th>Company</th>
            <th>Status</th>
            <th>Application No</th>
            <th>Subscription</th>
            <th>Applied on</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.growwOrderId}>
              <td>
                <div className="cell-title">{o.companyName}</div>
                <div className="cell-sub">{o.symbol}</div>
              </td>
              <td className="cell-sub">{o.orderStatus}</td>
              <td className="cell-sub">{o.applicationNumber}</td>
              <td className="cell-sub">{o.overallSubscription ? `${o.overallSubscription}x` : '—'}</td>
              <td className="cell-sub">{formatDateTime(o.orderTimeStamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GrowwPage() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [ordersByAccount, setOrdersByAccount] = useState({});
  const [expandedId, setExpandedId] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.listGrowwAccounts();
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
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(emptyForm);
  }

  function startEdit(account) {
    if (editingId === account.id) {
      closeForm();
      return;
    }
    setEditingId(account.id);
    setForm({ label: account.label, bearer_token: '', device_id: '', nkey: '', pin: '' });
    setShowForm(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      if (editingId) {
        const payload = { label: form.label.trim() };
        if (form.bearer_token.trim()) payload.bearer_token = form.bearer_token.trim();
        if (form.device_id.trim()) payload.device_id = form.device_id.trim();
        if (form.nkey.trim()) payload.nkey = form.nkey.trim();
        if (form.pin.trim()) payload.pin = form.pin.trim();
        await api.updateGrowwAccount(editingId, payload);
      } else {
        await api.addGrowwAccount({
          label: form.label.trim(),
          bearer_token: form.bearer_token.trim(),
          device_id: form.device_id.trim(),
          nkey: form.nkey.trim(),
          pin: form.pin.trim(),
        });
      }
      closeForm();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(account) {
    if (!confirm(`Remove Groww account "${account.label}"? This deletes its stored tokens and PIN.`)) return;
    setBusyId(account.id);
    try {
      await api.deleteGrowwAccount(account.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleFetchOrders(account) {
    setBusyId(account.id);
    setError('');
    try {
      const res = await api.getGrowwOrders(account.id);
      setOrdersByAccount((prev) => ({ ...prev, [account.id]: res.data || [] }));
      setExpandedId(account.id);
      await load(); // pin_token may have just been silently refreshed — reflect "connected" state
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="panel-loading">Loading Groww accounts…</div>;

  const addingNew = showForm && !editingId;

  return (
    <div className="centered-panel">
      <div className="toolbar">
        <h2 className="panel-title">Groww</h2>
        <button onClick={addingNew ? closeForm : openAddForm}>{addingNew ? 'Cancel' : 'Add Groww account'}</button>
      </div>

      <p className="subtitle" style={{ textAlign: 'left', marginBottom: 16 }}>
        Groww doesn't offer a reverse-engineerable login API, so the one-time browser login has to happen
        outside this app — run the login script locally, then paste the captured Bearer Token, Device ID,
        NKey and your PIN below. After that, this app renews access on its own using just the PIN — no
        browser login needed again.
      </p>

      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}

      {addingNew && (
        <GrowwForm form={form} setForm={setForm} onSubmit={handleSubmit} onCancel={closeForm} saving={saving} isEdit={false} />
      )}

      {accounts.length === 0 ? (
        <div className="empty-state">No Groww accounts saved yet.</div>
      ) : (
        <div className="account-list">
          {accounts.map((acc) => (
            <Fragment key={acc.id}>
              <div className="account-row">
                <div>
                  <div className="cell-title">{acc.label}</div>
                </div>
                <span className={`status-badge ${acc.connected ? 'status-ongoing' : 'status-closed'}`}>
                  {acc.connected ? 'Unlocked' : 'Not unlocked yet'}
                </span>
                <div className="account-actions">
                  <button disabled={busyId === acc.id} onClick={() => handleFetchOrders(acc)}>
                    {busyId === acc.id ? 'Fetching…' : 'Fetch orders'}
                  </button>
                  <button className="secondary-btn" disabled={busyId === acc.id} onClick={() => startEdit(acc)}>
                    <span className="btn-text">{editingId === acc.id ? 'Close' : 'Edit'}</span>
                    <span className="btn-icon" aria-hidden="true">{editingId === acc.id ? '✕' : '✎'}</span>
                  </button>
                  <button className="danger-btn" disabled={busyId === acc.id} onClick={() => handleDelete(acc)}>
                    <span className="btn-text">Delete</span>
                    <span className="btn-icon" aria-hidden="true">🗑</span>
                  </button>
                </div>
              </div>
              {editingId === acc.id && (
                <GrowwForm form={form} setForm={setForm} onSubmit={handleSubmit} onCancel={closeForm} saving={saving} isEdit />
              )}
              {expandedId === acc.id && ordersByAccount[acc.id] && <OrdersPanel orders={ordersByAccount[acc.id]} />}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}

function GrowwForm({ form, setForm, onSubmit, onCancel, saving, isEdit }) {
  return (
    <form className="account-form" onSubmit={onSubmit} style={{ maxWidth: '100%' }}>
      <h3 style={{ marginBottom: 4 }}>{isEdit ? 'Edit Groww account' : 'Add Groww account'}</h3>
      <label>
        Label (optional)
        <input
          type="text"
          placeholder="e.g. My Groww"
          value={form.label}
          onChange={(e) => setForm({ ...form, label: e.target.value })}
        />
      </label>
      <label>
        Bearer Token
        <input
          type="text"
          placeholder={isEdit ? 'Leave blank to keep current token' : 'Captured via the login script'}
          value={form.bearer_token}
          onChange={(e) => setForm({ ...form, bearer_token: e.target.value })}
          required={!isEdit}
        />
      </label>
      <label>
        Device ID
        <input
          type="text"
          placeholder={isEdit ? 'Leave blank to keep current value' : 'Captured via the login script'}
          value={form.device_id}
          onChange={(e) => setForm({ ...form, device_id: e.target.value })}
          required={!isEdit}
        />
      </label>
      <label>
        NKey
        <input
          type="text"
          placeholder={isEdit ? 'Leave blank to keep current value' : 'Captured via the login script'}
          value={form.nkey}
          onChange={(e) => setForm({ ...form, nkey: e.target.value })}
          required={!isEdit}
        />
      </label>
      <label>
        PIN
        <input
          type="password"
          placeholder={isEdit ? 'Leave blank to keep current PIN' : 'Your Groww app PIN'}
          value={form.pin}
          onChange={(e) => setForm({ ...form, pin: e.target.value })}
          required={!isEdit}
        />
      </label>
      <div className="modal-actions">
        {isEdit && (
          <button type="button" className="secondary-btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button type="submit" disabled={saving}>
          {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Save account'}
        </button>
      </div>
    </form>
  );
}
