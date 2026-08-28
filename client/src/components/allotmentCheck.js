import { useState } from 'react';
import { api } from '../api';

// Lower rank sorts first: allotted, then not allotted, then not applied, errors last.
// Still-loading rows sort first too, so they don't jump around as results land.
export function statusRank(row) {
  if (row.loading) return -1;
  if (row.error) return 3;
  if (row.not_applied || row.data.length === 0) return 2;
  const shares = Number(row.data[0]?.All_Shares || 0);
  return shares > 0 ? 0 : 1;
}

// Checks every saved PAN against one registrar/client_id independently — the list of
// PANs to check resolves fast and renders immediately with a per-PAN loader, then each
// PAN's allotment result fills in as its own request completes, instead of waiting for
// the slowest PAN to check.
export function useAllotmentCheck() {
  const [results, setResults] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');

  async function run(clientId, registrar) {
    setError('');
    setResults(null);
    setChecking(true);
    try {
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
          setResults((prev) => prev && prev.map((r) => (r.pan_entry.id === p.id ? { ...row, loading: false } : r)));
        } catch (err) {
          setResults((prev) =>
            prev && prev.map((r) => (r.pan_entry.id === p.id ? { ...r, error: err.message, loading: false } : r))
          );
        }
      });
    } catch (err) {
      setError(err.message);
      setChecking(false);
    }
  }

  return { results, checking, error, run };
}
