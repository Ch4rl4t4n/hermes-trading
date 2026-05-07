export default function PerformanceBadge({ label, icon }) {
  return (
    <span className="agent-badge">
      <span className="agent-badge-icon">{icon}</span>
      <span className="agent-badge-label">{label}</span>
    </span>
  );
}
