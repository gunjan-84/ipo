import { useEffect, useState } from 'react';
import { api } from '../api';
import ApplyModal from './ApplyModal';

const DAY_MS = 86400000;

function fmtDayMonth(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr.split(' ')[0]).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
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

function daysLeftInfo(endAt, today) {
  const days = Math.ceil((new Date(endAt.split(' ')[0]) - today) / DAY_MS);
  const label = days < 0 ? '' : days === 0 ? 'Last day' : days === 1 ? '1d left' : `${days}d left`;
  return { label, urgent: days <= 1 };
}

// Two-column vertical stepper: one dot+connector per milestone, "Today" called out inline.
function buildSteps(ins, today) {
  const d = (key) => (ins[key] ? new Date(ins[key].split(' ')[0]) : null);
  const sameDay = (a, b) => a && b && a.toDateString() === b.toDateString();
  const defs = [
    ['Offer opened', d('start_at')],
    ['Offer closes', d('end_at')],
    ['Allotment finalised', d('allotment_finalisation_date')],
    ['Refund initiated', d('refund_initiation_date')],
    ['Shares in demat', d('demat_transfer_date')],
    ['Lists · mandate ends', d('listing_date'), d('mandate_end_date')],
  ];
  if (defs.some(([, dt]) => !dt)) return null;

  return defs.map(([label, dt, dt2], i, arr) => ({
    label,
    date: dt2 ? `${fmtShort(dt)} · ${fmtShort(dt2)}` : fmtShort(dt),
    isToday: sameDay(dt, today),
    done: dt <= today,
    isLast: i === arr.length - 1,
  }));
}

function fmtShort(date) {
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function IpoTimeline({ instrument, today }) {
  const steps = buildSteps(instrument, today);
  if (!steps) return null;

  return (
    <div className="ipo-timeline">
      <div className="ipo-stepper-grid">
        {steps.map((st, i) => (
          <div className="ipo-step" key={i}>
            <div className="ipo-step-rail">
              <span className={`ipo-step-dot ${st.isToday ? 'today' : st.done ? 'done' : ''}`} />
              {!st.isLast && <span className="ipo-step-conn" data-done={st.done} />}
            </div>
            <div className="ipo-step-body">
              <div className="ipo-step-heading">
                <span className="ipo-step-label">{st.label}</span>
                {st.isToday && <span className="today-chip">Today</span>}
              </div>
              <div className="ipo-step-date">{st.date}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function IpoRow({ instrument: ins, closed, today, onApply }) {
  const [expanded, setExpanded] = useState(false);
  const days = closed ? null : daysLeftInfo(ins.end_at, today);

  return (
    <div className="ipo-row-wrap">
      <div className="ipo-row" onClick={() => setExpanded((e) => !e)}>
        <div className="ipo-row-col ipo-row-instrument">
          <div className="ipo-row-symbol">
            <span>{ins.symbol}</span>
            <span className={`type-tag ${ins.sub_type === 'SME' ? 'type-tag-sme' : 'type-tag-ipo'}`}>
              {ins.sub_type === 'SME' ? 'SME' : 'MAIN'}
            </span>
          </div>
          <div className="ipo-row-name">{ins.name?.trim()}</div>
        </div>

        <div className="ipo-row-col ipo-row-date">
          <span>
            {fmtDayMonth(ins.start_at)} – {fmtDayMonth(ins.end_at)}
          </span>
          {!closed && days?.label && (
            <span className={`days-pill ${days.urgent ? 'urgent' : ''}`}>{days.label}</span>
          )}
        </div>

        <div className="ipo-row-col ipo-row-price">
          ₹{ins.min_price} – {ins.max_price}
        </div>

        <div className="ipo-row-col ipo-row-amount">
          <div className="ipo-row-amount-value">₹{ins.min_investment_amount?.toLocaleString('en-IN')}</div>
          <div className="ipo-row-amount-qty">{ins.min_qty} qty</div>
        </div>

        <div className="ipo-row-col ipo-row-action" onClick={(e) => e.stopPropagation()}>
          {closed ? (
            <span className="closed-note">Listed {fmtDayMonth(ins.listing_date)}</span>
          ) : (
            <>
              <a href={ipojiLink(ins)} target="_blank" rel="noreferrer" className="ipo-row-details">
                Details
              </a>
              <button disabled={ins.status !== 'ongoing' || !ins.active} onClick={() => onApply(ins)}>
                Apply
              </button>
            </>
          )}
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
        </div>
      </div>

      {expanded && <IpoTimeline instrument={ins} today={today} />}
    </div>
  );
}

export default function IpoList({ onGoToAccounts }) {
  const [instruments, setInstruments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
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

  if (loading) return <div className="panel-loading">Loading IPOs…</div>;
  if (error) {
    return (
      <div className="empty-state">
        <div className="error" style={{ marginBottom: 12 }}>{error}</div>
        <button onClick={onGoToAccounts}>Go to Accounts</button>
      </div>
    );
  }

  const today = new Date();
  const pool = instruments.filter((i) => typeFilter === 'all' || i.sub_type === typeFilter);

  const bySort = (a, b) => {
    const diff = new Date(a.end_at) - new Date(b.end_at);
    return sortOrder === 'closing-soon' ? diff : -diff;
  };
  const open = pool.filter((i) => i.status === 'ongoing').sort(bySort);
  const closed = pool.filter((i) => i.status !== 'ongoing').sort((a, b) => new Date(b.end_at) - new Date(a.end_at));

  const soonest = open.length ? Math.ceil((new Date(open[0].end_at) - today) / DAY_MS) : null;
  const openSummary =
    open.length === 0
      ? 'No issues open right now'
      : `${open.length} ${open.length === 1 ? 'issue' : 'issues'} open` +
        (soonest === 0 ? ' · one closes today' : soonest === 1 ? ' · one closes tomorrow' : ` · next closes in ${soonest} days`);

  return (
    <div>
      <div className="ipo-page-header">
        <div>
          <h1>Public issues</h1>
          <p className="ipo-page-summary">{openSummary}</p>
        </div>
        <div className="filters-right">
          <div className="segment">
            {[
              { key: 'all', label: 'All' },
              { key: 'IPO', label: 'Mainboard' },
              { key: 'SME', label: 'SME' },
            ].map((t) => (
              <button
                key={t.key}
                className={`segment-btn ${typeFilter === t.key ? 'active' : ''}`}
                onClick={() => setTypeFilter(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
            <option value="closing-soon">Closing soon</option>
            <option value="closing-later">Closing later</option>
          </select>
          <button className="secondary-btn" onClick={load}>
            Refresh
          </button>
        </div>
      </div>

      <section className="ipo-section">
        <div className="ipo-section-heading">
          <h2>Open now</h2>
          <span className="ipo-section-count">{open.length}</span>
        </div>
        {open.length === 0 ? (
          <div className="empty-state">No open issues match this filter.</div>
        ) : (
          <div className="ipo-list">
            {open.map((ins) => (
              <IpoRow key={ins.id} instrument={ins} closed={false} today={today} onApply={setSelected} />
            ))}
          </div>
        )}
      </section>

      {closed.length > 0 && (
        <section className="ipo-section">
          <div className="ipo-section-heading">
            <h2 className="muted-heading">Closed</h2>
            <span className="ipo-section-count">{closed.length}</span>
          </div>
          <div className="ipo-list">
            {closed.map((ins) => (
              <IpoRow key={ins.id} instrument={ins} closed today={today} onApply={setSelected} />
            ))}
          </div>
        </section>
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
