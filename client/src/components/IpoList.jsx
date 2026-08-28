import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import ApplyModal from './ApplyModal';
import SubscriptionModal from './SubscriptionModal';
import IpoAllotmentModal from './IpoAllotmentModal';

const DAY_MS = 86400000;
const PREMIUM_NOISE_WORDS = new Set(['LIMITED', 'LTD', 'IPO', 'SME', 'INDIA']);

function normalizeIpoName(name) {
  return (name || '')
    .toUpperCase()
    .replace(/\([^)]*\)/g, ' ')
    .replace(/[^A-Z0-9 ]/g, ' ')
    .split(/\s+/)
    .filter((t) => t && !PREMIUM_NOISE_WORDS.has(t))
    .join(' ');
}

// ipoji's card names don't always match our instrument names exactly (e.g. dropped
// suffixes), so match on normalized token overlap rather than requiring equality.
function findPremiumMatch(instrument, premiums) {
  const target = normalizeIpoName(instrument.name || instrument.symbol);
  if (!target) return null;
  const targetTokens = new Set(target.split(' '));

  let best = null;
  let bestScore = 0;
  for (const p of premiums) {
    const candidate = normalizeIpoName(p.name);
    if (!candidate) continue;
    if (candidate === target) return p;
    const candidateTokens = candidate.split(' ');
    const overlap = candidateTokens.filter((t) => targetTokens.has(t)).length;
    const score = overlap / Math.max(targetTokens.size, candidateTokens.length);
    if (score > bestScore) {
      bestScore = score;
      best = p;
    }
  }
  return bestScore >= 0.6 ? best : null;
}

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

function listingChangeLabel(premium) {
  const match = premium.listing_note?.match(/(\d+(\.\d+)?%)/);
  const pct = match ? match[1] : '';
  const word = premium.listing_direction === 'down' ? 'Discount' : 'Premium';
  return pct ? `${word} ${pct}` : word;
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

function IpoListHeader() {
  return (
    <div className="ipo-row ipo-row-header">
      <div className="ipo-row-col ipo-row-instrument">Instrument</div>
      <div className="ipo-row-col ipo-row-date">Closing</div>
      <div className="ipo-row-col ipo-row-price">Price</div>
      <div className="ipo-row-col ipo-row-gmp">GMP/Listing Price</div>
      <div className="ipo-row-col ipo-row-amount">Min. Amount</div>
      <div className="ipo-row-col ipo-row-action" />
    </div>
  );
}

function IpoRow({ instrument: ins, closed, today, onApply, onShowSubscription, onCheckAllotment, premium, registryMatch }) {
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

        <div className="ipo-row-col ipo-row-gmp">
          {closed && premium?.list_price ? (
            <>
              <div className={`ipo-row-gmp-value ${premium.listing_direction === 'down' ? 'down' : 'up'}`}>
                ₹{premium.list_price}
              </div>
              <div className="ipo-row-gmp-sub">{listingChangeLabel(premium)}</div>
            </>
          ) : premium?.exp_premium ? (
            <>
              <div className={`ipo-row-gmp-value ${premium.premium_direction === 'down' ? 'down' : 'up'}`}>
                {premium.exp_premium}
              </div>
              {premium.subscription && <div className="ipo-row-gmp-sub">{premium.subscription} sub</div>}
            </>
          ) : (
            <>
              <div className="ipo-row-gmp-value muted">—</div>
              {premium?.subscription && <div className="ipo-row-gmp-sub">{premium.subscription} sub</div>}
            </>
          )}
        </div>

        <div className="ipo-row-col ipo-row-amount">
          <div className="ipo-row-amount-value">₹{ins.min_investment_amount?.toLocaleString('en-IN')}</div>
          <div className="ipo-row-amount-qty">{ins.min_qty} qty</div>
        </div>

        <div className="ipo-row-col ipo-row-action" onClick={(e) => e.stopPropagation()}>
          {closed ? (
            <div className="closed-note-stack">
              {registryMatch && (
                <button type="button" onClick={() => onCheckAllotment(ins, registryMatch)}>
                  Check allotment
                </button>
              )}
              <span className="closed-note">
                {ins.listing_date && new Date(ins.listing_date.split(' ')[0]) > today ? 'Listing on' : 'Listed'}{' '}
                {fmtDayMonth(ins.listing_date)}
              </span>
            </div>
          ) : (
            <>
              {premium?.slug ? (
                <button
                  type="button"
                  className="ipo-row-details"
                  onClick={() => onShowSubscription(ins, premium.slug)}
                >
                  Details
                </button>
              ) : (
                <a href={ipojiLink(ins)} target="_blank" rel="noreferrer" className="ipo-row-details">
                  Details
                </a>
              )}
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
  const [premiums, setPremiums] = useState([]);
  const [registryIpos, setRegistryIpos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('closing-soon');
  const [selected, setSelected] = useState(null);
  const [subscriptionTarget, setSubscriptionTarget] = useState(null);
  const [allotmentTarget, setAllotmentTarget] = useState(null);

  useEffect(() => {
    // Best-effort — GMP/subscription figures are a nice-to-have, not worth failing the page over.
    api
      .getIpoPremiums()
      .then((res) => setPremiums(res.data || []))
      .catch(() => {});
    // Best-effort — lets closed issues show a "Check allotment" shortcut when a registrar match exists.
    api
      .listRegistryIpos()
      .then((res) => setRegistryIpos(res.data || []))
      .catch(() => {});
  }, []);

  const premiumByInstrumentId = useMemo(() => {
    const map = {};
    for (const ins of instruments) {
      const match = findPremiumMatch(ins, premiums);
      if (match) map[ins.id] = match;
    }
    return map;
  }, [instruments, premiums]);

  const registryMatchByInstrumentId = useMemo(() => {
    const map = {};
    for (const ins of instruments) {
      const match = findPremiumMatch(ins, registryIpos);
      if (match) map[ins.id] = match;
    }
    return map;
  }, [instruments, registryIpos]);

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

  const openSummary =
    open.length === 0 ? 'No issues open right now' : `${open.length} ${open.length === 1 ? 'issue' : 'issues'} open`;

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
            <IpoListHeader />
            {open.map((ins) => (
              <IpoRow
                key={ins.id}
                instrument={ins}
                closed={false}
                today={today}
                onApply={setSelected}
                onShowSubscription={(instrument, slug) => setSubscriptionTarget({ instrument, slug })}
                premium={premiumByInstrumentId[ins.id]}
              />
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
            <IpoListHeader />
            {closed.map((ins) => (
              <IpoRow
                key={ins.id}
                instrument={ins}
                closed
                today={today}
                onApply={setSelected}
                onCheckAllotment={(instrument, match) =>
                  setAllotmentTarget({
                    name: instrument.name?.trim() || instrument.symbol,
                    registrar: match.registrar,
                    clientId: match.value,
                  })
                }
                premium={premiumByInstrumentId[ins.id]}
                registryMatch={registryMatchByInstrumentId[ins.id]}
              />
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

      {subscriptionTarget && (
        <SubscriptionModal
          instrument={subscriptionTarget.instrument}
          slug={subscriptionTarget.slug}
          onClose={() => setSubscriptionTarget(null)}
        />
      )}

      {allotmentTarget && (
        <IpoAllotmentModal
          instrumentName={allotmentTarget.name}
          registrar={allotmentTarget.registrar}
          clientId={allotmentTarget.clientId}
          onClose={() => setAllotmentTarget(null)}
        />
      )}
    </div>
  );
}
