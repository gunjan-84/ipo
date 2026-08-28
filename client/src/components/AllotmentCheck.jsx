import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import SearchableSelect from './SearchableSelect';

function StatusPill({ row }) {
  if (row.loading) {
    return (
      <span className="status-badge status-pill-checking">
        <span className="spinner" /> Checking…
      </span>
    );
  }
  if (row.error) {
    return <span className="status-badge status-pill-error">Error</span>;
  }
  if (row.not_applied || row.data.length === 0) {
    return <span className="status-badge status-pill-not-applied">− Not applied</span>;
  }
  const shares = Number(row.data[0].All_Shares || 0);
  if (shares > 0) {
    return <span className="status-badge status-pill-allotted">✓ {shares} shares</span>;
  }
  return <span className="status-badge status-pill-not-allotted">✕ Not allotted</span>;
}

// Lower rank sorts first: allotted, then not allotted, then not applied, errors last.
// Still-loading rows keep their original position instead of jumping around.
function statusRank(row) {
  if (row.loading) return -1;
  if (row.error) return 3;
  if (row.not_applied || row.data.length === 0) return 2;
  const shares = Number(row.data[0]?.All_Shares || 0);
  return shares > 0 ? 0 : 1;
}

// A single dropdown spans multiple registrars, so each option's value is a composite
// "registrar|client_id" key — split back apart before calling the allotment API.
function makeKey(ipo) {
  return `${ipo.registrar}|${ipo.value}`;
}

export default function AllotmentCheck({ onGoToPans }) {
  const [ipos, setIpos] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [selectedKey, setSelectedKey] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);

  useEffect(() => {
    api
      .listRegistryIpos()
      .then((res) => setIpos(res.data || []))
      .catch((err) => setLoadError(err.message));
  }, []);

  // Checks each saved PAN independently — the list of PANs to check resolves fast and
  // renders immediately with a per-PAN loader, then each PAN's allotment result fills in
  // as its own request completes, instead of waiting for the slowest PAN to check.
  async function handleCheck(e) {
    e.preventDefault();
    setError('');
    setResults(null);
    setChecking(true);
    try {
      const [registrar, clientId] = selectedKey.split('|');
      const pansRes = await api.listPans();
      const panList = pansRes.data || [];
      if (panList.length === 0) {
        throw new Error('No PAN numbers saved yet — add one under PAN Numbers');
      }

      setResults(
        panList.map((p) => ({
          pan_entry: { id: p.id, pan: p.pan, label: p.label || '' },
          data: [],
          not_applied: false,
          error: null,
          loading: true,
        }))
      );
      setChecking(false);

      panList.forEach(async (p) => {
        try {
          const res = await api.checkAllotmentForPan(p.id, clientId, registrar);
          const row = res.data;
          setResults((prev) => prev.map((r) => (r.pan_entry.id === p.id ? { ...row, loading: false } : r)));
        } catch (err) {
          setResults((prev) =>
            prev.map((r) => (r.pan_entry.id === p.id ? { ...r, error: err.message, loading: false } : r))
          );
        }
      });
    } catch (err) {
      setError(err.message);
      setChecking(false);
    }
  }

  const selectedIpo = ipos.find((i) => makeKey(i) === selectedKey);

  const ipoOptions = useMemo(
    () => ipos.map((ipo) => ({ value: makeKey(ipo), label: ipo.name })),
    [ipos]
  );

  const sortedResults = useMemo(
    () => (results ? [...results].sort((a, b) => statusRank(a) - statusRank(b)) : null),
    [results]
  );

  return (
    <div className="centered-panel">
      <div className="toolbar">
        <h2 className="panel-title">Check allotment</h2>
      </div>

      <p className="subtitle" style={{ textAlign: 'left', marginBottom: 16 }}>
        Pick an IPO and check every saved PAN against it in one go.
      </p>

      {loadError && <div className="error" style={{ marginBottom: 16 }}>{loadError}</div>}

      <form
        className="account-form"
        onSubmit={handleCheck}
        style={{ flexDirection: 'row', alignItems: 'flex-end', flexWrap: 'wrap', maxWidth: '100%' }}
      >
        <div className="field-label" style={{ flex: 1, minWidth: 260 }}>
          IPO
          <SearchableSelect
            options={ipoOptions}
            value={selectedKey}
            onChange={setSelectedKey}
            placeholder="Select an IPO"
          />
        </div>
        <button type="submit" disabled={checking || !selectedKey}>
          {checking ? 'Checking…' : 'Check allotment'}
        </button>
      </form>

      {error && (
        <div className="empty-state" style={{ marginTop: 16 }}>
          <div className="error" style={{ marginBottom: 12 }}>{error}</div>
          {error.includes('PAN') && (
            <button className="secondary-btn" onClick={onGoToPans}>
              Go to PAN Numbers
            </button>
          )}
        </div>
      )}

      {sortedResults && (
        <div style={{ marginTop: 24 }}>
          {selectedIpo && (
            <div className="cell-sub" style={{ marginBottom: 12 }}>
              Showing allotment for <strong>{selectedIpo.name}</strong>
            </div>
          )}

          <div className="account-list">
            {sortedResults.map((row) => (
              <div className="account-row" key={row.pan_entry.id}>
                <div>
                  <div className="cell-title">
                    {row.error ? row.error : row.data[0]?.Name || row.pan_entry.label || '—'}
                  </div>
                  <div className="cell-sub">{row.pan_entry.pan}</div>
                </div>
                <StatusPill row={row} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
