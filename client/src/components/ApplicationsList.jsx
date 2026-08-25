import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';

function titleCase(s) {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDateTime(d) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return d;
  }
}

function AccountApplications({ group, filtered, hasActiveFilter, onCancelled }) {
  const [cancellingId, setCancellingId] = useState(null);
  const [error, setError] = useState('');

  async function handleCancel(app) {
    if (!confirm(`Cancel ${group.account.label}'s application for ${app.symbol}?`)) return;
    setCancellingId(app.id);
    setError('');
    try {
      await api.cancel(group.account.id, app.id);
      onCancelled();
    } catch (err) {
      setError(err.message);
    } finally {
      setCancellingId(null);
    }
  }

  return (
    <div className="account-group">
      <h3 className="account-group-title">
        {group.account.label} <span className="cell-sub">({group.account.user_id})</span>
      </h3>

      {group.error && <div className="error">{group.error}</div>}
      {error && <div className="error">{error}</div>}

      {filtered.length === 0 ? (
        <div className="empty-state">
          {hasActiveFilter ? 'No applications match the current filter.' : 'No applications for this account.'}
        </div>
      ) : (
        <div className="applications-table-wrap">
          <table className="applications-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Status</th>
                <th>Bid qty / price</th>
                <th>Amount</th>
                <th>Payment</th>
                <th>Applied on</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((app) => {
                const bid = app.bids?.[0];
                return (
                  <tr key={app.id}>
                    <td>
                      <div className="cell-title">{app.symbol}</div>
                      <div className="cell-sub">{app.exchange}</div>
                    </td>
                    <td>
                      <span className={`status-badge status-app-${app.status.replace(' ', '-')}`}>
                        {app.status}
                      </span>
                    </td>
                    <td>{bid ? `${bid.quantity} @ ₹${bid.price}` : '—'}</td>
                    <td>{app.amount_blocked ? `₹${app.amount_blocked.toLocaleString('en-IN')}` : '—'}</td>
                    <td className="cell-sub">{app.payment_status || '—'}</td>
                    <td className="cell-sub">{formatDateTime(app.created_at)}</td>
                    <td>
                      {!['cancelled', 'allotted', 'not allotted'].includes(app.status) && (
                        <button
                          className="danger-btn"
                          disabled={cancellingId === app.id}
                          onClick={() => handleCancel(app)}
                        >
                          {cancellingId === app.id ? 'Cancelling…' : 'Cancel'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function ApplicationsList({ onGoToAccounts }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [accountFilter, setAccountFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('newest');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.getApplications();
      setGroups(res.data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const statuses = useMemo(() => {
    const set = new Set();
    groups.forEach((g) => g.applications.forEach((a) => set.add(a.status)));
    return Array.from(set);
  }, [groups]);

  const stats = useMemo(() => {
    const allApps = groups.flatMap((g) => g.applications);
    const amountBlocked = allApps
      .filter((a) => a.status === 'submitted' && a.amount_blocked > 0)
      .reduce((sum, a) => sum + a.amount_blocked, 0);
    const byStatus = {};
    for (const app of allApps) byStatus[app.status] = (byStatus[app.status] || 0) + 1;
    return { total: allApps.length, amountBlocked, byStatus };
  }, [groups]);

  const visibleGroups = groups.filter((g) => accountFilter === 'all' || g.account.id === accountFilter);
  const hasActiveFilter = statusFilter !== 'all';

  if (loading) return <div className="panel-loading">Loading applications…</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div>
      <div className="toolbar">
        <h2 className="panel-title">My applications</h2>
        <button className="secondary-btn" onClick={load}>
          Refresh
        </button>
      </div>

      {groups.length === 0 ? (
        <div className="empty-state">
          No connected accounts yet.{' '}
          <button className="link-btn" onClick={onGoToAccounts}>
            Connect one
          </button>
        </div>
      ) : (
        <>
          <div className="stat-tiles">
            <div className="stat-tile">
              <span className="stat-label">Applications</span>
              <span className="stat-value">{stats.total}</span>
            </div>
            <div className="stat-tile">
              <span className="stat-label">Amount blocked</span>
              <span className="stat-value accent-value">₹{stats.amountBlocked.toLocaleString('en-IN')}</span>
            </div>
            {statuses.map((s) => (
              <div className="stat-tile" key={s}>
                <span className="stat-label">{titleCase(s)}</span>
                <span className="stat-value">{stats.byStatus[s] || 0}</span>
              </div>
            ))}
          </div>

          <div className="filters-bar">
            <div className="segment">
              <button
                className={`segment-btn ${statusFilter === 'all' ? 'active' : ''}`}
                onClick={() => setStatusFilter('all')}
              >
                All
              </button>
              {statuses.map((s) => (
                <button
                  key={s}
                  className={`segment-btn ${statusFilter === s ? 'active' : ''}`}
                  onClick={() => setStatusFilter(s)}
                >
                  {titleCase(s)}
                </button>
              ))}
            </div>
            <div className="filters-right">
              <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
              </select>
              {groups.length > 1 && (
                <select value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)}>
                  <option value="all">All accounts</option>
                  {groups.map((g) => (
                    <option key={g.account.id} value={g.account.id}>
                      {g.account.label}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <div className="account-groups">
            {visibleGroups.map((group) => (
              <AccountApplications
                key={group.account.id}
                group={group}
                filtered={group.applications
                  .filter((a) => statusFilter === 'all' || a.status === statusFilter)
                  .sort((a, b) => {
                    const diff = new Date(a.created_at) - new Date(b.created_at);
                    return sortOrder === 'newest' ? -diff : diff;
                  })}
                hasActiveFilter={hasActiveFilter}
                onCancelled={load}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
