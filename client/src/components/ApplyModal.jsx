import { useEffect, useState } from 'react';
import { api } from '../api';

function emptyBid(instrument, cutoffDisabled) {
  return {
    quantity: instrument.min_qty || instrument.lot_size,
    auto_cutoff: !cutoffDisabled,
    price: instrument.cutoff_price,
  };
}

export default function ApplyModal({ instrument, onClose, onApplied }) {
  const investorTypes = instrument.investor_types?.length
    ? instrument.investor_types
    : [{ code: instrument.series || 'IND', description: 'Individual investor' }];

  const [accounts, setAccounts] = useState([]);
  const [growwAccounts, setGrowwAccounts] = useState([]);
  const [upis, setUpis] = useState([]);
  const [applicationGroups, setApplicationGroups] = useState([]);
  const [loadingMeta, setLoadingMeta] = useState(true);

  const [selectedAccountIds, setSelectedAccountIds] = useState([]);
  const [selectedGrowwIds, setSelectedGrowwIds] = useState([]);
  const [investorType, setInvestorType] = useState(investorTypes[0].code);
  const [upiId, setUpiId] = useState('');
  const [bids, setBids] = useState([emptyBid(instrument, investorTypes[0].cutoff_disabled)]);
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    Promise.all([api.listAccounts(), api.listGrowwAccounts(), api.listUpis(), api.getApplications()])
      .then(([accRes, growwRes, upiRes, appsRes]) => {
        setAccounts(accRes.data || []);
        setGrowwAccounts(growwRes.data || []);
        setUpis(upiRes.data || []);
        setApplicationGroups(appsRes.data || []);
        if (upiRes.data?.length) setUpiId(upiRes.data[0].upi_id);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoadingMeta(false));
  }, []);

  const activeInvestor = investorTypes.find((t) => t.code === investorType) || investorTypes[0];
  const lotSize = instrument.lot_size || 1;
  const maxBids = instrument.max_bid_count || 1;
  const connectedAccounts = accounts.filter((a) => a.connected);
  const connectedGrowwAccounts = growwAccounts.filter((a) => a.connected);

  function existingApplication(accountId) {
    const group = applicationGroups.find((g) => g.account.id === accountId);
    return group?.applications.find(
      (a) => a.instrument_id === instrument.id && a.investor_type === investorType && a.status !== 'cancelled'
    );
  }

  useEffect(() => {
    setBids((prev) =>
      prev.map((b) =>
        activeInvestor.cutoff_disabled
          ? { ...b, auto_cutoff: false, price: b.price || instrument.cutoff_price }
          : b
      )
    );
  }, [activeInvestor.cutoff_disabled]);

  useEffect(() => {
    setSelectedAccountIds((prev) => prev.filter((id) => !existingApplication(id)));
  }, [investorType, applicationGroups]);

  function toggleAccount(id) {
    setSelectedAccountIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function toggleGrowwAccount(id) {
    setSelectedGrowwIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function updateBid(index, patch) {
    setBids((prev) => prev.map((b, i) => (i === index ? { ...b, ...patch } : b)));
  }

  function addBid() {
    if (bids.length < maxBids) setBids((prev) => [...prev, emptyBid(instrument, activeInvestor.cutoff_disabled)]);
  }

  function removeBid(index) {
    setBids((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setResults(null);

    if (selectedAccountIds.length === 0 && selectedGrowwIds.length === 0) {
      setError('Select at least one account to apply with');
      return;
    }
    if (!upiId) {
      setError('Select a UPI ID');
      return;
    }
    for (const b of bids) {
      if (!b.quantity || b.quantity % lotSize !== 0) {
        setError(`Quantity must be a multiple of lot size (${lotSize})`);
        return;
      }
    }

    setLoading(true);
    try {
      const kiteResultsPromise = selectedAccountIds.length
        ? api
            .apply({
              account_ids: selectedAccountIds,
              instrument_id: instrument.id,
              investor_type: investorType,
              upi_id: upiId,
              bids: bids.map((b) => {
                const bid = { quantity: Number(b.quantity), auto_cutoff: b.auto_cutoff };
                if (!b.auto_cutoff) bid.price = Number(b.price);
                return bid;
              }),
            })
            .then((res) => res.data || [])
        : Promise.resolve([]);

      // Groww's apply endpoint takes one account at a time and one bid — use the first bid.
      const firstBid = bids[0];
      const growwPrice = firstBid.auto_cutoff ? instrument.cutoff_price : firstBid.price;
      const growwResultsPromise = Promise.all(
        selectedGrowwIds.map((accountId) => {
          const account = growwAccounts.find((a) => a.id === accountId);
          return api
            .applyGrowwIpo(accountId, {
              symbol: instrument.symbol,
              isin: instrument.isin,
              quantity: Number(firstBid.quantity),
              price: Number(growwPrice),
              upi_id: upiId,
              cutoff: firstBid.auto_cutoff,
            })
            .then(() => ({ account, status: 'success', message: 'Applied' }))
            .catch((err) => ({ account, status: 'error', message: err.message }));
        })
      );

      const [kiteResults, growwResults] = await Promise.all([kiteResultsPromise, growwResultsPromise]);
      setResults([...kiteResults, ...growwResults]);
      onApplied?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{instrument.symbol}</h2>
            <div className="modal-subtitle">{instrument.name?.trim()}</div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <div className="price-band">
            Price band: ₹{instrument.min_price} – ₹{instrument.max_price} · Cutoff ₹{instrument.cutoff_price} · Lot
            size {lotSize}
          </div>

          {loadingMeta ? (
            <div className="panel-loading">Loading accounts…</div>
          ) : results ? (
            <div className="apply-results">
              {results.map((r) => (
                <div key={r.account.id} className={`apply-result ${r.status === 'success' ? 'success' : 'error'}`}>
                  <strong>{r.account.label || r.account.user_id}</strong>
                  <span>{r.message || (r.status === 'success' ? 'Applied' : 'Failed')}</span>
                </div>
              ))}
              <div className="modal-actions">
                <button type="button" onClick={onClose}>
                  Close
                </button>
              </div>
            </div>
          ) : connectedAccounts.length === 0 && connectedGrowwAccounts.length === 0 ? (
            <div className="empty-state">
              No connected accounts. Connect an account first from the Accounts tab.
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="accounts-picker">
                <span className="picker-label">Apply as</span>
                {connectedAccounts.map((acc) => {
                  const existing = existingApplication(acc.id);
                  return (
                    <label key={acc.id} className="checkbox-label account-pick">
                      <input
                        type="checkbox"
                        checked={selectedAccountIds.includes(acc.id)}
                        disabled={!!existing}
                        onChange={() => toggleAccount(acc.id)}
                      />
                      {acc.label} <span className="muted">({acc.user_id})</span>
                      {existing && <span className="muted"> — already applied ({existing.status})</span>}
                    </label>
                  );
                })}
                {connectedGrowwAccounts.map((acc) => (
                  <label key={`groww-${acc.id}`} className="checkbox-label account-pick">
                    <input
                      type="checkbox"
                      checked={selectedGrowwIds.includes(acc.id)}
                      onChange={() => toggleGrowwAccount(acc.id)}
                    />
                    {acc.label} <span className="muted">(Groww)</span>
                  </label>
                ))}
              </div>

              <label>
                Investor type
                <select value={investorType} onChange={(e) => setInvestorType(e.target.value)}>
                  {investorTypes.map((t) => (
                    <option key={t.code} value={t.code}>
                      {t.description} ({t.code})
                    </option>
                  ))}
                </select>
              </label>

              {upis.length === 0 ? (
                <div className="error">No UPI IDs saved. Add one from the UPI IDs tab first.</div>
              ) : (
                <label>
                  UPI ID
                  <select value={upiId} onChange={(e) => setUpiId(e.target.value)}>
                    {upis.map((u) => (
                      <option key={u.id} value={u.upi_id}>
                        {u.upi_id}
                        {u.label ? ` (${u.label})` : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <div className="bids-section">
                <div className="bids-header">
                  <span>Bids</span>
                  {bids.length < maxBids && (
                    <button type="button" className="link-btn" onClick={addBid}>
                      + Add bid
                    </button>
                  )}
                </div>
                {activeInvestor.cutoff_disabled && (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Cutoff bidding isn't available for this category — enter a price for each bid.
                  </div>
                )}
                {bids.map((bid, i) => (
                  <div className="bid-row" key={i}>
                    <div className="bid-row-fields">
                      <label>
                        Quantity
                        <input
                          type="number"
                          min={instrument.min_qty || lotSize}
                          step={lotSize}
                          value={bid.quantity}
                          onChange={(e) => updateBid(i, { quantity: e.target.value })}
                          required
                        />
                      </label>
                      <label>
                        Price
                        <input
                          type="number"
                          min={instrument.min_price}
                          max={instrument.max_price}
                          value={bid.auto_cutoff ? instrument.cutoff_price : bid.price}
                          disabled={bid.auto_cutoff}
                          onChange={(e) => updateBid(i, { price: e.target.value })}
                          required={!bid.auto_cutoff}
                        />
                      </label>
                    </div>
                    <div className="bid-row-footer">
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={bid.auto_cutoff}
                          disabled={activeInvestor.cutoff_disabled}
                          onChange={(e) => updateBid(i, { auto_cutoff: e.target.checked })}
                        />
                        Bid at cutoff price
                      </label>
                      {bids.length > 1 && (
                        <button type="button" className="icon-btn" onClick={() => removeBid(i)}>
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                <div className="bids-total">
                  <span>Amount payable</span>
                  <span className="bids-total-value">
                    ₹
                    {bids
                      .reduce((sum, b) => {
                        const qty = Number(b.quantity) || 0;
                        const price = Number(b.auto_cutoff ? instrument.cutoff_price : b.price) || 0;
                        return sum + qty * price;
                      }, 0)
                      .toLocaleString('en-IN')}
                  </span>
                </div>
              </div>

              {error && <div className="error">{error}</div>}

              <div className="modal-actions">
                <button type="button" className="secondary-btn" onClick={onClose}>
                  Cancel
                </button>
                <button type="submit" disabled={loading || upis.length === 0}>
                  {loading ? 'Submitting…' : `Apply (${selectedAccountIds.length + selectedGrowwIds.length})`}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
