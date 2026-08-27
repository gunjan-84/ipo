import { useEffect, useState } from 'react';
import { api } from '../api';

function parseMultiplier(value) {
  const n = parseFloat(String(value).replace(/x$/i, ''));
  return Number.isFinite(n) ? n : 0;
}

export default function SubscriptionModal({ instrument, slug, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    api
      .getIpoSubscriptionDetail(slug)
      .then((res) => {
        if (!cancelled) setDetail(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const maxMultiplier = detail ? Math.max(1, ...detail.categories.map((c) => parseMultiplier(c.value))) : 1;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>Live Subscription</h2>
            <div className="modal-subtitle">{instrument.name?.trim() || instrument.symbol}</div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="panel-loading">Loading subscription details…</div>
          ) : error ? (
            <div className="error">{error}</div>
          ) : (
            <div className="subscription-detail">
              {detail.categories.map((c, i) => (
                <div className={`subscription-row ${c.is_total ? 'total' : ''}`} key={i}>
                  <div className="subscription-row-label">
                    <span>{c.label}</span>
                    <span>{c.value}</span>
                  </div>
                  <div className="subscription-bar-track">
                    <div
                      className="subscription-bar-fill"
                      style={{ width: `${Math.min(100, (parseMultiplier(c.value) / maxMultiplier) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
              {detail.updated_at && <div className="subscription-updated">Last updated: {detail.updated_at}</div>}
              <a
                href={`https://www.ipoji.com/ipo/${slug}`}
                target="_blank"
                rel="noreferrer"
                className="secondary-btn"
                style={{ textAlign: 'center', marginTop: 4 }}
              >
                View full details on ipoji
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
