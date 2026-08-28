import { useEffect, useMemo } from 'react';
import AllotmentStatusPill from './AllotmentStatusPill';
import { statusRank, useAllotmentCheck } from './allotmentCheck';

export default function IpoAllotmentModal({ instrumentName, registrar, clientId, onClose }) {
  const { results, checking, error, run } = useAllotmentCheck();

  useEffect(() => {
    run(clientId, registrar);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, registrar]);

  const sortedResults = useMemo(
    () => (results ? [...results].sort((a, b) => statusRank(a) - statusRank(b)) : null),
    [results]
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>Check allotment</h2>
            <div className="modal-subtitle">{instrumentName}</div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          {checking && !sortedResults && <div className="panel-loading">Loading saved PANs…</div>}
          {error && <div className="error">{error}</div>}

          {sortedResults && (
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
          )}
        </div>
      </div>
    </div>
  );
}
