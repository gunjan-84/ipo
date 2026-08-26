import { useEffect, useState } from 'react';
import { api } from '../api';

export default function UpisPage() {
  const [upis, setUpis] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ upi_id: '', label: '' });
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.listUpis();
      setUpis(res.data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleAdd(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await api.addUpi({ upi_id: form.upi_id.trim(), label: form.label.trim() });
      setForm({ upi_id: '', label: '' });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(upi) {
    if (!confirm(`Remove UPI ID ${upi.upi_id}?`)) return;
    setBusyId(upi.id);
    try {
      await api.deleteUpi(upi.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="panel-loading">Loading UPI IDs…</div>;

  return (
    <div className="centered-panel">
      <div className="toolbar">
        <h2 className="panel-title">UPI IDs</h2>
        <button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Cancel' : 'Add UPI ID'}</button>
      </div>

      <p className="subtitle" style={{ textAlign: 'left', marginBottom: 16 }}>
        Any saved UPI ID can be used for any account's IPO application — pick it from a dropdown when applying.
      </p>

      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {showForm && (
        <form className="account-form" onSubmit={handleAdd}>
          <label>
            UPI ID
            <input
              type="text"
              placeholder="yourname@upi"
              value={form.upi_id}
              onChange={(e) => setForm({ ...form, upi_id: e.target.value })}
              required
            />
          </label>
          <label>
            Label (optional)
            <input
              type="text"
              placeholder="e.g. Primary bank"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </label>
          <div className="modal-actions">
            <button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save UPI ID'}
            </button>
          </div>
        </form>
      )}

      {upis.length === 0 ? (
        <div className="empty-state">No UPI IDs saved yet.</div>
      ) : (
        <div className="account-list">
          {upis.map((u) => (
            <div className="account-row" key={u.id}>
              <div>
                <div className="cell-title">{u.upi_id}</div>
                {u.label && <div className="cell-sub">{u.label}</div>}
              </div>
              <div className="account-actions">
                <button className="danger-btn" disabled={busyId === u.id} onClick={() => handleDelete(u)}>
                  <span className="btn-text">Delete</span>
                  <span className="btn-icon" aria-hidden="true">🗑</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
