import { useEffect, useState } from 'react';
import { api } from '../api';

export default function PansPage() {
  const [pans, setPans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ pan: '', label: '' });
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.listPans();
      setPans(res.data || []);
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
      await api.addPan({ pan: form.pan.trim().toUpperCase(), label: form.label.trim() });
      setForm({ pan: '', label: '' });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(entry) {
    if (!confirm(`Remove PAN ${entry.pan}?`)) return;
    setBusyId(entry.id);
    try {
      await api.deletePan(entry.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  function startRename(entry) {
    setRenamingId(entry.id);
    setRenameValue(entry.label === 'Unknown' ? '' : entry.label);
  }

  async function handleRename(e) {
    e.preventDefault();
    setBusyId(renamingId);
    try {
      await api.updatePan(renamingId, { label: renameValue.trim() });
      setRenamingId(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="panel-loading">Loading PAN numbers…</div>;

  return (
    <div className="centered-panel">
      <div className="toolbar">
        <h2 className="panel-title">PAN Numbers</h2>
        <button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Cancel' : 'Add PAN'}</button>
      </div>

      <p className="subtitle" style={{ textAlign: 'left', marginBottom: 16 }}>
        Any saved PAN can be checked against any IPO under Check Allotment — kept separate from accounts. Leave the
        name blank and it's saved as "Unknown" until an allotment check fills it in from the registrar's records.
      </p>

      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {showForm && (
        <form className="account-form" onSubmit={handleAdd}>
          <label>
            PAN
            <input
              type="text"
              placeholder="ABCDE1234F"
              value={form.pan}
              maxLength={10}
              onChange={(e) => setForm({ ...form, pan: e.target.value.toUpperCase() })}
              required
            />
          </label>
          <label>
            Name (optional)
            <input
              type="text"
              placeholder="Leave blank to fill in as Unknown"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </label>
          <div className="modal-actions">
            <button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save PAN'}
            </button>
          </div>
        </form>
      )}

      {pans.length === 0 ? (
        <div className="empty-state">No PAN numbers saved yet.</div>
      ) : (
        <div className="account-list">
          {pans.map((p) => (
            <div className="account-row" key={p.id}>
              {renamingId === p.id ? (
                <form onSubmit={handleRename} style={{ display: 'flex', gap: 8, flex: 1, alignItems: 'center' }}>
                  <div className="cell-title">{p.pan}</div>
                  <input
                    type="text"
                    autoFocus
                    placeholder="Name"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="submit" disabled={busyId === p.id}>
                    Save
                  </button>
                  <button type="button" className="secondary-btn" onClick={() => setRenamingId(null)}>
                    Cancel
                  </button>
                </form>
              ) : (
                <>
                  <div>
                    <div className="cell-title">{p.pan}</div>
                    <div className="cell-sub">{p.label || 'Unknown'}</div>
                  </div>
                  <div className="account-actions">
                    <button className="secondary-btn" disabled={busyId === p.id} onClick={() => startRename(p)}>
                      <span className="btn-text">Rename</span>
                      <span className="btn-icon" aria-hidden="true">✎</span>
                    </button>
                    <button className="danger-btn" disabled={busyId === p.id} onClick={() => handleDelete(p)}>
                      <span className="btn-text">Delete</span>
                      <span className="btn-icon" aria-hidden="true">🗑</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
