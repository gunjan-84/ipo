function fmtDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function UpcomingIpoDetailsModal({ entry, onClose }) {
  const dateRange = entry.start_date && entry.end_date ? `${fmtDate(entry.start_date)} – ${fmtDate(entry.end_date)}` : null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{entry.name}</h2>
            <div className="modal-subtitle">
              {entry.symbol}
              {entry.board ? ` · ${entry.board}` : ''}
            </div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <div className="price-band">
            {dateRange || 'Dates to be announced'}
            {entry.listing_date && <> · Listing on {entry.listing_date}</>}
            {entry.price_range && <> · {entry.price_range}</>}
          </div>

          {entry.description ? (
            <p className="upcoming-ipo-description">{entry.description}</p>
          ) : (
            <div className="empty-state">No company description available yet for this IPO.</div>
          )}

          <div className="modal-actions">
            {entry.zerodha_url && (
              <a href={entry.zerodha_url} target="_blank" rel="noreferrer" className="secondary-btn">
                Open on Zerodha
              </a>
            )}
            <button type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
