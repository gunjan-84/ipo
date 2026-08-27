import { useEffect, useState } from 'react';
import { api } from './api';
import AccountsPage from './components/AccountsPage';
import UpisPage from './components/UpisPage';
import PansPage from './components/PansPage';
import IpoList from './components/IpoList';
import ApplicationsList from './components/ApplicationsList';
import AllotmentCheck from './components/AllotmentCheck';
import ThemeToggle from './components/ThemeToggle';
import LoginPage from './components/LoginPage';
import './App.css';

const TABS = [
  { key: 'ipos', label: 'IPOs' },
  { key: 'applications', label: 'Applications' },
  { key: 'allotment', label: 'Check Allotment' },
  { key: 'accounts', label: 'Accounts' },
  { key: 'upis', label: 'UPI IDs' },
  { key: 'pans', label: 'PAN Numbers' },
];

export default function App() {
  const [tab, setTab] = useState('ipos');
  const [auth, setAuth] = useState(null); // null while loading, else {configured, authenticated, username}

  useEffect(() => {
    api
      .authStatus()
      .then((res) => setAuth(res.data))
      .catch(() => setAuth({ configured: true, authenticated: false, username: null }));
  }, []);

  useEffect(() => {
    if (!auth?.authenticated) return;
    // Triggers the server's per-account token validation so any account whose
    // enctoken has expired is dropped back to "not connected" immediately,
    // rather than waiting for the user to open a page that hits Kite.
    api.getApplications().catch(() => {});
  }, [auth?.authenticated]);

  async function handleLogout() {
    await api.authLogout().catch(() => {});
    setAuth((a) => ({ ...a, authenticated: false, username: null }));
  }

  if (auth === null) return <div className="panel-loading">Loading…</div>;

  if (!auth.authenticated) {
    return (
      <LoginPage
        configured={auth.configured}
        onLoggedIn={(username) => setAuth({ configured: true, authenticated: true, username })}
      />
    );
  }

  return (
    <div className="page">
      <header className="app-header">
        <div className="brand">
          <span className="brand-ez">EZ</span> <span className="brand-ipo">IPO</span>
        </div>
        <nav className="main-tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab-btn ${tab === t.key ? 'active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="header-right">
          <ThemeToggle />
          <button className="secondary-btn" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <main className="content">
        {tab === 'ipos' && <IpoList onGoToAccounts={() => setTab('accounts')} />}
        {tab === 'applications' && <ApplicationsList onGoToAccounts={() => setTab('accounts')} />}
        {tab === 'allotment' && <AllotmentCheck onGoToPans={() => setTab('pans')} />}
        {tab === 'accounts' && <AccountsPage />}
        {tab === 'upis' && <UpisPage />}
        {tab === 'pans' && <PansPage />}
      </main>
    </div>
  );
}
