import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import SearchableSelect from './SearchableSelect';
import AllotmentStatusPill from './AllotmentStatusPill';
import { statusRank, useAllotmentCheck } from './allotmentCheck';

// A single dropdown spans multiple registrars, so each option's value is a composite
// "registrar|client_id" key — split back apart before calling the allotment API.
function makeKey(ipo) {
  return `${ipo.registrar}|${ipo.value}`;
}

export default function AllotmentCheck({ onGoToPans }) {
  const [ipos, setIpos] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [selectedKey, setSelectedKey] = useState('');
  const { results, checking, error, run } = useAllotmentCheck();

  useEffect(() => {
    api
      .listRegistryIpos()
      .then((res) => setIpos(res.data || []))
      .catch((err) => setLoadError(err.message));
  }, []);

  function handleCheck(e) {
    e.preventDefault();
    const [registrar, clientId] = selectedKey.split('|');
    run(clientId, registrar);
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
                <AllotmentStatusPill row={row} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
