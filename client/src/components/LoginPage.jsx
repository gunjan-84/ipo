import { useState } from 'react';
import { api } from '../api';

export default function LoginPage({ configured, onLoggedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!configured && password !== confirmPassword) {
      setError("Passwords don't match");
      return;
    }

    setSubmitting(true);
    try {
      const res = configured
        ? await api.authLogin({ username, password })
        : await api.authSetup({ username, password });
      onLoggedIn(res.data.username);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-card account-form" onSubmit={handleSubmit} style={{ maxWidth: 360, margin: '0 auto' }}>
        <div className="brand" style={{ justifyContent: 'center', marginBottom: 4 }}>
          <span className="brand-ez">EZ</span> <span className="brand-ipo">IPO</span>
        </div>
        <h3 style={{ textAlign: 'center', marginBottom: 4 }}>{configured ? 'Log in' : 'Create your login'}</h3>
        {!configured && (
          <p className="subtitle" style={{ textAlign: 'center', marginBottom: 8 }}>
            No login is set up yet — choose a username and password to protect this dashboard.
          </p>
        )}

        {error && <div className="error">{error}</div>}

        <label>
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={configured ? 'current-password' : 'new-password'}
            required
          />
        </label>
        {!configured && (
          <label>
            Confirm password
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
          </label>
        )}

        <div className="modal-actions" style={{ justifyContent: 'stretch' }}>
          <button type="submit" disabled={submitting} style={{ width: '100%' }}>
            {submitting ? 'Please wait…' : configured ? 'Log in' : 'Create login & continue'}
          </button>
        </div>
      </form>
    </div>
  );
}
