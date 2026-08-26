import { useEffect, useState } from 'react';
import { api } from '../api';

export default function StatusCheck() {
  const [instruments, setInstruments] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [pan, setPan] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    api
      .getInstruments()
      .then((res) => setInstruments(res.data || []))
      .catch((err) => setLoadError(err.message));
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setResult(null);
    setChecking(true);
    try {
      const res = await api.checkIpoStatus({ name, pan: pan.trim().toUpperCase() });
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  }

  const rows = result?.data || [];

  return (
    <div>
      <div className="toolbar">
        <h2 className="panel-title">Check allotment status</h2>
      </div>

      <p className="subtitle" style={{ textAlign: 'left', marginBottom: 16 }}>
        Pick an IPO and enter a PAN to look up its allotment status directly from the registrar.
      </p>

      {loadError && <div className="error" style={{ marginBottom: 16 }}>{loadError}</div>}

      <form className="account-form" onSubmit={handleSubmit}>
        <label>
          IPO
          <select value={name} onChange={(e) => setName(e.target.value)} required>
            <option value="" disabled>
              Select an IPO
            </option>
            {instruments.map((ins) => (
              <option key={ins.id} value={ins.name?.trim() || ins.symbol}>
                {ins.symbol} — {ins.name?.trim()}
              </option>
            ))}
          </select>
        </label>
        <label>
          PAN
          <input
            type="text"
            placeholder="ABCDE1234F"
            value={pan}
            maxLength={10}
            onChange={(e) => setPan(e.target.value.toUpperCase())}
            required
          />
        </label>
        <div className="modal-actions">
          <button type="submit" disabled={checking}>
            {checking ? 'Checking…' : 'Check status'}
          </button>
        </div>
      </form>

      {error && <div className="error" style={{ marginTop: 16 }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 24 }}>
          {result.matched_name && (
            <div className="cell-sub" style={{ marginBottom: 12 }}>
              Matched as <strong>{result.matched_name}</strong>
              {typeof result.match_score === 'number' && ` (${Math.round(result.match_score * 100)}% match)`}
            </div>
          )}

          {rows.length === 0 ? (
            <div className="empty-state">
              {result.not_applied
                ? 'This PAN has not applied for this IPO.'
                : 'No application found for this PAN in this IPO.'}
            </div>
          ) : (
            <div className="applications-table-wrap">
              <table className="applications-table">
                <thead>
                  <tr>
                    <th>Applicant</th>
                    <th>PAN</th>
                    <th>Application No</th>
                    <th>DP Client ID</th>
                    <th>Applied shares</th>
                    <th>Allotted shares</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.Appln_No || i}>
                      <td className="cell-title">{r.Name}</td>
                      <td className="cell-sub">{r.Pan_No}</td>
                      <td className="cell-sub">{r.Appln_No}</td>
                      <td className="cell-sub">{r.DP_CLID}</td>
                      <td>{r.App_Shares}</td>
                      <td>{r.All_Shares}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
