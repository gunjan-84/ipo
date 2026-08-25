import { useEffect, useState } from 'react';
import { api } from './api';
import AccountsPage from './components/AccountsPage';
import UpisPage from './components/UpisPage';
import IpoList from './components/IpoList';
import ApplicationsList from './components/ApplicationsList';
import './App.css';

const TABS = [
  { key: 'ipos', label: 'IPOs' },
  { key: 'applications', label: 'My Applications' },
  { key: 'accounts', label: 'Accounts' },
  { key: 'upis', label: 'UPI IDs' },
];

export default function App() {
  const [tab, setTab] = useState('ipos');

  useEffect(() => {
    // Triggers the server's per-account token validation so any account whose
    // enctoken has expired is dropped back to "not connected" immediately,
    // rather than waiting for the user to open a page that hits Kite.
    api.getApplications().catch(() => {});
  }, []);

  return (
    <div className="page">
      <header className="app-header">
        <div className="brand">Kite IPO</div>
      </header>

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

      <main className="content">
        {tab === 'ipos' && <IpoList onGoToAccounts={() => setTab('accounts')} />}
        {tab === 'applications' && <ApplicationsList onGoToAccounts={() => setTab('accounts')} />}
        {tab === 'accounts' && <AccountsPage />}
        {tab === 'upis' && <UpisPage />}
      </main>
    </div>
  );
}
