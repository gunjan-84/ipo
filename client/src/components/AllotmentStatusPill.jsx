export default function AllotmentStatusPill({ row }) {
  if (row.loading) {
    return (
      <span className="status-badge status-pill-checking">
        <span className="spinner" /> Checking…
      </span>
    );
  }
  if (row.error) {
    return <span className="status-badge status-pill-error">Error</span>;
  }
  if (row.not_applied || row.data.length === 0) {
    return <span className="status-badge status-pill-not-applied">− Not applied</span>;
  }
  const shares = Number(row.data[0].All_Shares || 0);
  if (shares > 0) {
    return <span className="status-badge status-pill-allotted">✓ {shares} shares</span>;
  }
  return <span className="status-badge status-pill-not-allotted">✕ Not allotted</span>;
}
