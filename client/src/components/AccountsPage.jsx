import { Fragment, useEffect, useState } from 'react';
import { api } from '../api';

const emptyZerodhaForm = { label: '', user_id: '', password: '', totp_secret: '' };
const emptyGrowwForm = { label: '', email: '', password: '', pin: '' };
const emptyGrowwEditForm = { label: '', pin: '' };

export default function AccountsPage() {
  const [zerodhaAccounts, setZerodhaAccounts] = useState([]);
  const [growwAccounts, setGrowwAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [broker, setBroker] = useState('zerodha');
  const [editingId, setEditingId] = useState(null);
  const [editingBroker, setEditingBroker] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [zerodhaForm, setZerodhaForm] = useState(emptyZerodhaForm);
  const [growwForm, setGrowwForm] = useState(emptyGrowwForm);
  const [growwEditForm, setGrowwEditForm] = useState(emptyGrowwEditForm);
  const [growwOtpSession, setGrowwOtpSession] = useState(null); // { sessionId }
  const [growwOtp, setGrowwOtp] = useState('');
  const [saving, setSaving] = useState(false);

  const [busyId, setBusyId] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [accRes, growwRes] = await Promise.all([api.listAccounts(), api.listGrowwAccounts()]);
      setZerodhaAccounts(accRes.data || []);
      setGrowwAccounts(growwRes.data || []);
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
    setEditingBroker(null);
    setBroker('zerodha');
    setZerodhaForm(emptyZerodhaForm);
    setGrowwForm(emptyGrowwForm);
    setGrowwOtpSession(null);
    setGrowwOtp('');
    setReveal(false);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setEditingBroker(null);
    setZerodhaForm(emptyZerodhaForm);
    setGrowwForm(emptyGrowwForm);
    setGrowwEditForm(emptyGrowwEditForm);
    setGrowwOtpSession(null);
    setGrowwOtp('');
  }

  async function handleEditZerodha(account) {
    if (editingId === account.id) {
      closeForm();
      return;
    }
    setBusyId(account.id);
    setError('');
    try {
      const res = await api.revealAccount(account.id);
      setZerodhaForm({
        label: account.label,
        user_id: res.data.user_id,
        password: res.data.password,
        totp_secret: res.data.totp_secret,
      });
      setEditingBroker('zerodha');
      setEditingId(account.id);
      setReveal(false);
      setShowForm(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  function handleEditGroww(account) {
    if (editingId === account.id) {
      closeForm();
      return;
    }
    setGrowwEditForm({ label: account.label, pin: '' });
    setEditingBroker('groww');
    setEditingId(account.id);
    setShowForm(true);
  }

  async function handleZerodhaSubmit(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = {
        label: zerodhaForm.label.trim(),
        user_id: zerodhaForm.user_id.trim(),
        password: zerodhaForm.password,
        totp_secret: zerodhaForm.totp_secret.trim(),
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

  async function handleGrowwStart(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const res = await api.growwLoginStart({
        label: growwForm.label.trim(),
        email: growwForm.email.trim(),
        password: growwForm.password,
        pin: growwForm.pin.trim(),
      });
      if (res.data.otp_required) {
        setGrowwOtpSession({ sessionId: res.data.session_id });
      } else {
        closeForm();
        await load();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleGrowwOtpSubmit(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await api.growwLoginOtp({ session_id: growwOtpSession.sessionId, otp: growwOtp.trim() });
      closeForm();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleGrowwEditSubmit(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = { label: growwEditForm.label.trim() };
      if (growwEditForm.pin.trim()) payload.pin = growwEditForm.pin.trim();
      await api.updateGrowwAccount(editingId, payload);
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

  async function handleConnectGroww(account) {
    setBusyId(account.id);
    setError('');
    try {
      await api.connectGrowwAccount(account.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDisconnectGroww(account) {
    setBusyId(account.id);
    setError('');
    try {
      await api.disconnectGrowwAccount(account.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDeleteZerodha(account) {
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

  async function handleDeleteGroww(account) {
    if (!confirm(`Remove Groww account "${account.label}"? This deletes its stored session and PIN.`)) return;
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

  function renderZerodhaForm() {
    return (
      <form className="account-form" onSubmit={handleZerodhaSubmit} autoComplete="off" style={{ maxWidth: '100%' }}>
        <h3 style={{ marginBottom: 4 }}>{editingId ? 'Edit account' : 'Add account'}</h3>
        {!editingId && (
          <label>
            Broker
            <select value={broker} onChange={(e) => setBroker(e.target.value)}>
              <option value="zerodha">Zerodha</option>
              <option value="groww">Groww</option>
            </select>
          </label>
        )}
        <label>
          Label (optional)
          <input
            type="text"
            placeholder="e.g. Dad's account"
            value={zerodhaForm.label}
            onChange={(e) => setZerodhaForm({ ...zerodhaForm, label: e.target.value })}
            autoComplete="off"
          />
        </label>
        <label>
          User ID
          <input
            type="text"
            value={zerodhaForm.user_id}
            onChange={(e) => setZerodhaForm({ ...zerodhaForm, user_id: e.target.value })}
            required
            autoComplete="off"
            name="zerodha-user-id"
          />
        </label>
        <label>
          Password
          <input
            type={reveal ? 'text' : 'password'}
            value={zerodhaForm.password}
            onChange={(e) => setZerodhaForm({ ...zerodhaForm, password: e.target.value })}
            required={!editingId}
            placeholder={editingId ? 'Leave as-is to keep current password' : ''}
            autoComplete="new-password"
            name="zerodha-password"
          />
        </label>
        <label>
          TOTP secret
          <input
            type={reveal ? 'text' : 'password'}
            placeholder={editingId ? 'Leave as-is to keep current secret' : 'Base32 secret from your authenticator setup'}
            value={zerodhaForm.totp_secret}
            onChange={(e) => setZerodhaForm({ ...zerodhaForm, totp_secret: e.target.value })}
            required={!editingId}
            autoComplete="off"
            name="zerodha-totp-secret"
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

  function renderGrowwAddForm() {
    if (growwOtpSession) {
      return (
        <form className="account-form" onSubmit={handleGrowwOtpSubmit} style={{ maxWidth: '100%' }}>
          <h3 style={{ marginBottom: 4 }}>Enter the OTP Groww just sent you</h3>
          <p className="subtitle" style={{ textAlign: 'left', marginBottom: 8 }}>
            Check your phone/email for the 6-digit code from Groww and enter it below.
          </p>
          <label>
            OTP
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={growwOtp}
              onChange={(e) => setGrowwOtp(e.target.value.replace(/\D/g, ''))}
              required
              autoFocus
            />
          </label>
          <div className="modal-actions">
            <button type="button" className="secondary-btn" onClick={closeForm}>
              Cancel
            </button>
            <button type="submit" disabled={saving || growwOtp.length !== 6}>
              {saving ? 'Verifying…' : 'Verify & continue'}
            </button>
          </div>
        </form>
      );
    }

    return (
      <form className="account-form" onSubmit={handleGrowwStart} style={{ maxWidth: '100%' }}>
        <h3 style={{ marginBottom: 4 }}>Add Groww account</h3>
        <p className="subtitle" style={{ textAlign: 'left', marginBottom: 8 }}>
          Logs in through Groww's real login page on your behalf. If Groww sends you an OTP, you'll enter it
          on the next step — after that, this app renews access on its own.
        </p>
        <label>
          Broker
          <select value={broker} onChange={(e) => setBroker(e.target.value)}>
            <option value="zerodha">Zerodha</option>
            <option value="groww">Groww</option>
          </select>
        </label>
        <label>
          Label (optional)
          <input
            type="text"
            placeholder="e.g. My Groww"
            value={growwForm.label}
            onChange={(e) => setGrowwForm({ ...growwForm, label: e.target.value })}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={growwForm.email}
            onChange={(e) => setGrowwForm({ ...growwForm, email: e.target.value })}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={growwForm.password}
            onChange={(e) => setGrowwForm({ ...growwForm, password: e.target.value })}
            required
          />
        </label>
        <label>
          4-digit PIN
          <input
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={growwForm.pin}
            onChange={(e) => setGrowwForm({ ...growwForm, pin: e.target.value.replace(/\D/g, '') })}
            required
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-btn" onClick={closeForm}>
            Cancel
          </button>
          <button type="submit" disabled={saving}>
            {saving ? 'Logging in…' : 'Log in & continue'}
          </button>
        </div>
      </form>
    );
  }

  function renderGrowwEditForm() {
    return (
      <form className="account-form" onSubmit={handleGrowwEditSubmit} style={{ maxWidth: '100%' }}>
        <h3 style={{ marginBottom: 4 }}>Edit Groww account</h3>
        <label>
          Label
          <input
            type="text"
            value={growwEditForm.label}
            onChange={(e) => setGrowwEditForm({ ...growwEditForm, label: e.target.value })}
            required
          />
        </label>
        <label>
          4-digit PIN
          <input
            type="password"
            inputMode="numeric"
            maxLength={4}
            placeholder="Leave as-is to keep current PIN"
            value={growwEditForm.pin}
            onChange={(e) => setGrowwEditForm({ ...growwEditForm, pin: e.target.value.replace(/\D/g, '') })}
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-btn" onClick={closeForm}>
            Cancel
          </button>
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
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

      {addingNew && (broker === 'zerodha' ? renderZerodhaForm() : renderGrowwAddForm())}

      {zerodhaAccounts.length === 0 && growwAccounts.length === 0 ? (
        <div className="empty-state">No accounts saved yet. Add one to get started.</div>
      ) : (
        <div className="account-list">
          {zerodhaAccounts.map((acc) => (
            <Fragment key={`zerodha-${acc.id}`}>
              <div className="account-row">
                <div>
                  <div className="cell-title">
                    {acc.label} <span className="type-tag type-tag-zerodha">ZERODHA</span>
                  </div>
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
                  <button className="secondary-btn" disabled={busyId === acc.id} onClick={() => handleEditZerodha(acc)}>
                    <span className="btn-text">{editingId === acc.id ? 'Close' : 'Edit'}</span>
                    <span className="btn-icon" aria-hidden="true">{editingId === acc.id ? '✕' : '✎'}</span>
                  </button>
                  <button className="danger-btn" disabled={busyId === acc.id} onClick={() => handleDeleteZerodha(acc)}>
                    <span className="btn-text">Delete</span>
                    <span className="btn-icon" aria-hidden="true">🗑</span>
                  </button>
                </div>
              </div>
              {editingId === acc.id && editingBroker === 'zerodha' && renderZerodhaForm()}
            </Fragment>
          ))}

          {growwAccounts.map((acc) => (
            <Fragment key={`groww-${acc.id}`}>
              <div className="account-row">
                <div>
                  <div className="cell-title">
                    {acc.label} <span className="type-tag type-tag-groww">GROWW</span>
                  </div>
                </div>
                <span className={`status-badge ${acc.connected ? 'status-ongoing' : 'status-closed'}`}>
                  {acc.connected ? 'Connected' : 'Not connected'}
                </span>
                <div className="account-actions">
                  {acc.connected ? (
                    <button className="secondary-btn" disabled={busyId === acc.id} onClick={() => handleDisconnectGroww(acc)}>
                      Disconnect
                    </button>
                  ) : (
                    <button disabled={busyId === acc.id} onClick={() => handleConnectGroww(acc)}>
                      {busyId === acc.id ? 'Connecting…' : 'Connect'}
                    </button>
                  )}
                  <button className="secondary-btn" disabled={busyId === acc.id} onClick={() => handleEditGroww(acc)}>
                    <span className="btn-text">{editingId === acc.id ? 'Close' : 'Edit'}</span>
                    <span className="btn-icon" aria-hidden="true">{editingId === acc.id ? '✕' : '✎'}</span>
                  </button>
                  <button className="danger-btn" disabled={busyId === acc.id} onClick={() => handleDeleteGroww(acc)}>
                    <span className="btn-text">Delete</span>
                    <span className="btn-icon" aria-hidden="true">🗑</span>
                  </button>
                </div>
              </div>
              {editingId === acc.id && editingBroker === 'groww' && renderGrowwEditForm()}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
