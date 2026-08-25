import { useEffect, useState } from 'react';
import { api } from '../api';
import ApplyModal from './ApplyModal';

function ordinalSuffix(n) {
  const v = n % 100;
  if (v >= 11 && v <= 13) return 'th';
  switch (n % 10) {
    case 1:
      return 'st';
    case 2:
      return 'nd';
    case 3:
      return 'rd';
    default:
      return 'th';
  }
}

function ordinalDay(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr.split(' ')[0]);
  const day = d.getDate();
  return { day, suffix: ordinalSuffix(day), month: d.toLocaleDateString('en-US', { month: 'short' }) };
}

function formatDateRange(startStr, endStr) {
  const start = ordinalDay(startStr);
  const end = ordinalDay(endStr);
  if (!start || !end) return '—';
  return (
    <>
      {start.day}
      <sup>{start.suffix}</sup>
      {start.month !== end.month && ` ${start.month}`} — {end.day}
      <sup>{end.suffix}</sup> {end.month}
    </>
  );
}

function formatShortDate(dateStr) {
  if (!dateStr) return '—';
  return dateStr.split(' ')[0].split('T')[0];
}

function ipojiLink(instrument) {
  const name = (instrument.name || instrument.symbol || '').replace(/\([^)]*\)/g, '');
  const slug = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `https://www.ipoji.com/ipo/${slug}-ipo`;
}

function IpoTimeline({ instrument }) {
  const milestones = [
    { key: 'start_at', label: 'Offer start' },
    { key: 'end_at', label: 'Offer end' },
    { key: 'allotment_finalisation_date', label: 'Allotment' },
    { key: 'refund_initiation_date', label: 'Refund initiation' },
    { key: 'demat_transfer_date', label: 'Demat transfer' },
    { key: 'listing_date', label: 'Listing' },
    { key: 'mandate_end_date', label: 'Mandate end' },
  ]
    .map((m) => ({ ...m, date: instrument[m.key] ? new Date(instrument[m.key].split(' ')[0]) : null }))
    .filter((m) => m.date);

  if (milestones.length < 2) return null;

  const today = new Date();
  const first = milestones[0].date;
  const last = milestones[milestones.length - 1].date;
  const span = last - first;
  const fillPercent = span > 0 ? Math.min(100, Math.max(0, ((today - first) / span) * 100)) : 0;

  return (
    <div className="ipo-timeline">
      <div className="ipo-timeline-track">
        <div className="ipo-timeline-fill" style={{ width: `${fillPercent}%` }} />
        {milestones.map((m) => (
          <div className="ipo-timeline-point" key={m.key}>
            <span className={`ipo-timeline-dot ${m.date <= today ? 'reached' : ''}`} />
            <span className="ipo-timeline-label">{m.label}</span>
            <span className="ipo-timeline-date">{formatShortDate(instrument[m.key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function IpoRow({ instrument: ins, onApply }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="ipo-row-wrap">
      <div className="ipo-row" onClick={() => setExpanded((e) => !e)}>
        <div className="ipo-row-col ipo-row-instrument">
          <div className="ipo-row-symbol">
            {ins.symbol}
            <span className={`type-tag ${ins.sub_type === 'SME' ? 'type-tag-sme' : 'type-tag-ipo'}`}>
              {ins.sub_type === 'SME' ? 'SME IPO' : 'Normal IPO'}
            </span>
            {ins.status !== 'ongoing' && <span className="status-badge status-closed">{ins.status}</span>}
          </div>
          <div className="ipo-row-name">{ins.name?.trim()}</div>
        </div>

        <div className="ipo-row-col ipo-row-date">
          <button
            type="button"
            className={`ipo-expand-btn ${expanded ? 'expanded' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            aria-label="Toggle timeline"
          >
            ▾
          </button>
          <span>{formatDateRange(ins.start_at, ins.end_at)}</span>
        </div>

        <div className="ipo-row-col ipo-row-price">
          {ins.min_price} - {ins.max_price}
        </div>

        <div className="ipo-row-col ipo-row-amount">
          <div className="ipo-row-amount-value">{ins.min_investment_amount?.toLocaleString('en-IN')}</div>
          <div className="ipo-row-amount-qty">{ins.min_qty} Qty.</div>
        </div>

        <div className="ipo-row-col ipo-row-action" onClick={(e) => e.stopPropagation()}>
          <a href={ipojiLink(ins)} target="_blank" rel="noreferrer" className="ipo-row-details">
            Details
          </a>
          <button disabled={ins.status !== 'ongoing' || !ins.active} onClick={() => onApply(ins)}>
            Apply
          </button>
        </div>
      </div>

      {expanded && <IpoTimeline instrument={ins} />}
    </div>
  );
}

export default function IpoList({ onGoToAccounts }) {
  const [instruments, setInstruments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('ongoing');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('closing-soon');
  const [selected, setSelected] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.getInstruments();
      setInstruments(res.data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = instruments
    .filter((i) => {
      if (filter !== 'all' && i.status !== filter) return false;
      if (typeFilter !== 'all' && i.sub_type !== typeFilter) return false;
      return true;
    })
    .sort((a, b) => {
      const diff = new Date(a.end_at) - new Date(b.end_at);
      return sortOrder === 'closing-soon' ? diff : -diff;
    });

  if (loading) return <div className="panel-loading">Loading IPOs…</div>;
  if (error) {
    return (
      <div className="empty-state">
        <div className="error" style={{ marginBottom: 12 }}>{error}</div>
        <button onClick={onGoToAccounts}>Go to Accounts</button>
      </div>
    );
  }

  return (
    <div>
      <div className="filters-bar">
        <div className="tabs">
          {['ongoing', 'closed', 'all'].map((f) => (
            <button
              key={f}
              className={`tab-btn ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f[0].toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
        <div className="tabs">
          {[
            { key: 'all', label: 'All IPO types' },
            { key: 'IPO', label: 'Normal IPO' },
            { key: 'SME', label: 'SME IPO' },
          ].map((t) => (
            <button
              key={t.key}
              className={`tab-btn ${typeFilter === t.key ? 'active' : ''}`}
              onClick={() => setTypeFilter(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="filters-right">
          <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
            <option value="closing-soon">Closing soon first</option>
            <option value="closing-later">Closing later first</option>
          </select>
          <button className="secondary-btn" onClick={load}>
            Refresh
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">No IPOs in this category.</div>
      ) : (
        <div className="ipo-list">
          <div className="ipo-row ipo-row-header">
            <div className="ipo-row-col ipo-row-instrument">Instrument</div>
            <div className="ipo-row-col ipo-row-date">Date</div>
            <div className="ipo-row-col ipo-row-price">Price (₹)</div>
            <div className="ipo-row-col ipo-row-amount">Min. amount (₹)</div>
            <div className="ipo-row-col ipo-row-action"></div>
          </div>
          {filtered.map((ins) => (
            <IpoRow key={ins.id} instrument={ins} onApply={setSelected} />
          ))}
        </div>
      )}

      {selected && (
        <ApplyModal
          instrument={selected}
          onClose={() => setSelected(null)}
          onApplied={() => {
            // keep modal open to show per-account results; user closes manually
          }}
        />
      )}
    </div>
  );
}
