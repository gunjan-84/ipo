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

// Brokers spell the same status differently (camelCase, SCREAMING_SNAKE, extra
// whitespace, ...). Canonicalize to "lowercase words separated by single spaces"
// so e.g. Kite's raw status and Groww's orderStatus land on the same string
// ("not allotted") and get grouped into the same section/tab/stat-tile instead
// of splitting into broker-specific duplicates.
// Some brokers also just spell a status differently outright (Groww sends the
// misspelled "Not Alloted"). Map known variants to one canonical spelling.
const STATUS_ALIASES = {
  'not alloted': 'not allotted',
  'payment pending': 'submitted',
};

function normalizeStatus(raw) {
  if (!raw) return '';
  const cleaned = String(raw)
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return STATUS_ALIASES[cleaned] || cleaned;
}

// Groww's order-list endpoint doesn't return bid qty/price/amount the way Kite's
// applications do — normalize what's available into the same shape so both brokers
// render through one table/filter/sort pipeline.
function normalizeGrowwOrder(o) {
  const status = normalizeStatus(o.orderStatus);
  return {
    id: o.growwOrderId,
    symbol: o.symbol,
    exchange: o.companyName,
    status,
    bids: o.bidQuantity && o.bidPrice ? [{ quantity: o.bidQuantity, price: o.bidPrice }] : null,
    amount_blocked: o.bidQuantity && o.bidPrice ? o.bidQuantity * o.bidPrice : null,
    payment_status: o.remark || null,
    created_at: o.orderTimeStamp,
    cancellable: !['cancelled', 'rejected', 'allotted', 'not allotted'].includes(status),
  };
}

function AccountApplications({ group, filtered, hasActiveFilter, onCancelled }) {
  const [cancellingId, setCancellingId] = useState(null);
  const [error, setError] = useState('');
  const isGroww = group.account.broker === 'groww';

  async function handleCancel(app) {
    if (!confirm(`Cancel ${group.account.label}'s application for ${app.symbol}?`)) return;
    setCancellingId(app.id);
    setError('');
    try {
      if (isGroww) {
        await api.cancelGrowwOrder(group.account.id, app.id);
      } else {
        await api.cancel(group.account.id, app.id);
      }
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
        {group.account.label} <span className="cell-sub">({isGroww ? 'Groww' : group.account.user_id})</span>
      </h3>

      {group.error && <div className="error">{group.error}</div>}
      {error && <div className="error">{error}</div>}

      {group.loading ? (
        <div className="inline-loader">
          <span className="spinner" /> Loading applications…
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          {hasActiveFilter ? 'No applications match the current filter.' : 'No applications for this account.'}
        </div>
      ) : (
        <div className="applications-table-wrap">
          <table className="applications-table">
            <colgroup>
              <col className="col-symbol" />
              <col className="col-status" />
              <col className="col-bid" />
              <col className="col-amount" />
              <col className="col-payment" />
              <col className="col-applied" />
              <col className="col-actions" />
            </colgroup>
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
                const cancellable = app.bids
                  ? !['cancelled', 'allotted', 'not allotted'].includes(app.status)
                  : app.cancellable;
                return (
                  <tr key={app.id}>
                    <td>
                      <div className="cell-title">{app.symbol}</div>
                      <div className="cell-sub">{app.exchange}</div>
                    </td>
                    <td>
                      <span className={`status-badge status-app-${app.status.replace(/ /g, '-')}`}>
                        {app.status}
                      </span>
                    </td>
                    <td>{bid ? `${bid.quantity} @ ₹${bid.price}` : '—'}</td>
                    <td>{app.amount_blocked ? `₹${app.amount_blocked.toLocaleString('en-IN')}` : '—'}</td>
                    <td className="cell-payment">{app.payment_status || '—'}</td>
                    <td className="cell-sub">{formatDateTime(app.created_at)}</td>
                    <td>
                      {cancellable && (
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

  // Fetches each account's applications independently — the account list resolves fast
  // and renders immediately with a per-account loader, then each account's applications
  // fill in as its own request completes, instead of the whole page waiting on whichever
  // account is slowest.
  function updateGroup(accountId, patch) {
    setGroups((prev) => prev.map((g) => (g.account.id === accountId ? { ...g, ...patch } : g)));
  }

  async function loadZerodhaAccount(account) {
    try {
      const res = await api.getApplicationsForAccount(account.id);
      const g = res.data;
      updateGroup(account.id, {
        applications: (g.applications || []).map((a) => ({ ...a, status: normalizeStatus(a.status) })),
        error: g.error,
        loading: false,
      });
    } catch (err) {
      updateGroup(account.id, { applications: [], error: err.message, loading: false });
    }
  }

  async function loadGrowwAccount(account) {
    try {
      const res = await api.getGrowwOrders(account.id);
      updateGroup(account.id, {
        applications: (res.data || []).map(normalizeGrowwOrder),
        error: null,
        loading: false,
      });
    } catch (err) {
      updateGroup(account.id, { applications: [], error: err.message, loading: false });
    }
  }

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [accountsRes, growwAccRes] = await Promise.all([api.listAccounts(), api.listGrowwAccounts()]);

      const zerodhaAccounts = (accountsRes.data || []).filter((a) => a.connected);
      const growwAccounts = growwAccRes.data || [];

      const initialGroups = [
        ...zerodhaAccounts.map((acc) => ({
          account: { ...acc, broker: 'zerodha' },
          applications: [],
          error: null,
          loading: true,
        })),
        ...growwAccounts.map((acc) => ({
          account: { ...acc, broker: 'groww' },
          applications: [],
          error: null,
          loading: true,
        })),
      ];

      setGroups(initialGroups);
      setLoading(false);

      zerodhaAccounts.forEach((acc) => loadZerodhaAccount(acc));
      growwAccounts.forEach((acc) => loadGrowwAccount(acc));
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  function refreshAccount(accountId) {
    const group = groups.find((g) => g.account.id === accountId);
    if (!group) return;
    updateGroup(accountId, { loading: true, error: null });
    if (group.account.broker === 'groww') {
      loadGrowwAccount(group.account);
    } else {
      loadZerodhaAccount(group.account);
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
                onCancelled={() => refreshAccount(group.account.id)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
