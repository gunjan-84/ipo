import { useEffect, useState } from 'react';
import { api } from './api';
import AccountsPage from './components/AccountsPage';
import UpisPage from './components/UpisPage';
import PansPage from './components/PansPage';
import IpoList from './components/IpoList';
import ApplicationsList from './components/ApplicationsList';
import AllotmentCheck from './components/AllotmentCheck';
import GrowwPage from './components/GrowwPage';
import ThemeToggle from './components/ThemeToggle';
import './App.css';

const TABS = [
  { key: 'ipos', label: 'IPOs' },
  { key: 'applications', label: 'Applications' },
  { key: 'allotment', label: 'Check Allotment' },
  { key: 'accounts', label: 'Accounts' },
  { key: 'upis', label: 'UPI IDs' },
  { key: 'pans', label: 'PAN Numbers' },
  { key: 'groww', label: 'Groww' },
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
        </div>
      </header>

      <main className="content">
        {tab === 'ipos' && <IpoList onGoToAccounts={() => setTab('accounts')} />}
        {tab === 'applications' && <ApplicationsList onGoToAccounts={() => setTab('accounts')} />}
        {tab === 'allotment' && <AllotmentCheck onGoToPans={() => setTab('pans')} />}
        {tab === 'accounts' && <AccountsPage />}
        {tab === 'upis' && <UpisPage />}
        {tab === 'pans' && <PansPage />}
        {tab === 'groww' && <GrowwPage />}
      </main>
    </div>
  );
}
