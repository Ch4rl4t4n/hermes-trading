import { memo, useEffect, useRef, useState } from "react";
import { useCurrency } from "../../contexts/CurrencyContext";
import SparkLine from "../ui/SparkLine";

/**
 * Compact agent card — entire body is the click target that opens a detail
 * modal (chart, recent trades, win/loss, share/export). Action pills:
 *   PAUSE / START — primary inline toggle
 *   CHART         — opens detail modal at the chart tab
 *   ⋯ (kebab)     — menu with Export, Share and Remove (destructive)
 *
 * The card is also draggable: parent attaches `onDragStart`/`onDragOver`/
 * `onDrop` for HTML5 drag and drop reordering. The drag handle is a small
 * grip icon at the very top-right (next to status dot) so the rest of the
 * card stays clickable.
 */

function tierStrategy(agent) {
  return agent.strategy || agent.strategyLabel || agent.strategy_type || agent.name || "Strategy";
}

function symbolLabel(agent) {
  const s = String(agent.symbol || agent.ticker || "").toUpperCase();
  if (!s) return "—";
  return s;
}

function ActionIcon({ name }) {
  const c = "currentColor";
  switch (name) {
    case "pause":
      return (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <rect x="6" y="5" width="4" height="14" />
          <rect x="14" y="5" width="4" height="14" />
        </svg>
      );
    case "start":
      return (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="6 4 20 12 6 20 6 4" />
        </svg>
      );
    case "chart":
      return (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 3v18h18" />
          <path d="m7 14 4-4 3 3 5-6" />
        </svg>
      );
    case "share":
      return (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" />
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="19" r="3" />
          <path d="m8.6 13.5 6.8 4M15.4 6.5 8.6 10.5" />
        </svg>
      );
    case "export":
      return (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      );
    case "trash":
      return (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
          <path d="M10 11v6M14 11v6" />
          <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
        </svg>
      );
    case "grip":
      return (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <circle cx="5.5" cy="3" r="1.1" />
          <circle cx="10.5" cy="3" r="1.1" />
          <circle cx="5.5" cy="8" r="1.1" />
          <circle cx="10.5" cy="8" r="1.1" />
          <circle cx="5.5" cy="13" r="1.1" />
          <circle cx="10.5" cy="13" r="1.1" />
        </svg>
      );
    case "kebab":
      return (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <circle cx="8" cy="3" r="1.2" />
          <circle cx="8" cy="8" r="1.2" />
          <circle cx="8" cy="13" r="1.2" />
        </svg>
      );
    default:
      return null;
  }
}

function AgentCardCompact({
  agent,
  onToggle,
  onShare,
  onDetails,
  onExport,
  onRemove,
  draggable = false,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDragLeave,
  onDrop,
  isDragging = false,
  isDragOver = false,
}) {
  const { format } = useCurrency();
  const positive = Number(agent.pnlUsd || 0) >= 0;
  const isLive = agent.status === "live";
  const isPaper = !agent.realMoney;
  const winPct = Math.round(Number(agent.winRate || 0));

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDocClick = (ev) => {
      if (menuRef.current && !menuRef.current.contains(ev.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menuOpen]);

  const cardClass = [
    "hermes-agent-card",
    "glass",
    isDragging ? "is-dragging" : "",
    isDragOver ? "is-drag-over" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={cardClass}
      onClick={() => onDetails?.(agent)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onDetails?.(agent);
      }}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <header className="hermes-agent-card-head">
        <div className="hermes-agent-card-symbol-block">
          <strong className="hermes-agent-card-symbol">{symbolLabel(agent)}</strong>
          <span className="hermes-agent-card-strategy text-3 fs-12">{tierStrategy(agent)}</span>
        </div>

        <div className="hermes-agent-card-head-actions">
          <span
            className={`hermes-agent-card-status${isLive ? " is-live" : " is-paused"}`}
            aria-label={isLive ? "Active agent" : "Paused agent"}
          />
          {draggable ? (
            <button
              type="button"
              className="hermes-agent-card-icon-btn hermes-agent-card-grip"
              aria-label="Drag to reorder"
              title="Drag to reorder"
              onClick={(e) => e.stopPropagation()}
            >
              <ActionIcon name="grip" />
            </button>
          ) : null}
          <div className="hermes-agent-card-menu" ref={menuRef}>
            <button
              type="button"
              className="hermes-agent-card-icon-btn hermes-agent-card-kebab"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="Card actions"
              title="More actions"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((o) => !o);
              }}
            >
              <ActionIcon name="kebab" />
            </button>
            {menuOpen ? (
              <div
                className="hermes-agent-card-menu-popover"
                role="menu"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    onExport?.(agent);
                  }}
                >
                  <ActionIcon name="export" /> Export CSV
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    onShare?.(agent);
                  }}
                >
                  <ActionIcon name="share" /> Share
                </button>
                <hr />
                <button
                  type="button"
                  role="menuitem"
                  className="is-destructive"
                  onClick={() => {
                    setMenuOpen(false);
                    onRemove?.(agent);
                  }}
                >
                  <ActionIcon name="trash" /> Remove from dashboard
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="hermes-agent-card-stats">
        <span className="hermes-agent-card-stat">
          <span className="hermes-agent-card-stat-label">Win</span>
          <strong className="mono">{winPct}%</strong>
        </span>
        <span className="hermes-agent-card-stat">
          <span className="hermes-agent-card-stat-label">P&amp;L</span>
          <strong
            className="mono"
            style={{ color: positive ? "var(--accent-success, #10b981)" : "var(--accent-danger, #ef4444)" }}
          >
            {format(agent.pnlUsd, { signed: true })}
          </strong>
        </span>
        <span className={`hermes-agent-card-pill ${isPaper ? "is-paper" : "is-live"}`}>
          {isPaper ? "PAPER" : "LIVE"}
        </span>
        <div className="hermes-agent-card-spark">
          <SparkLine
            points={
              Array.isArray(agent.spark) && agent.spark.length > 1
                ? agent.spark
                : Array.isArray(agent.equityHistory) && agent.equityHistory.length > 1
                  ? agent.equityHistory
                  : [0, 1, 0.6, 1.4, 1.2, 1.6, 1.8]
            }
            color={positive ? "var(--accent-success, #10b981)" : "var(--accent-danger, #ef4444)"}
          />
        </div>
      </div>

      <footer className="hermes-agent-card-actions">
        <button
          type="button"
          className="hermes-pill-action"
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.(agent);
          }}
        >
          <ActionIcon name={isLive ? "pause" : "start"} />
          {isLive ? "PAUSE" : "START"}
        </button>
        <button
          type="button"
          className="hermes-pill-action"
          onClick={(e) => {
            e.stopPropagation();
            onDetails?.(agent);
          }}
        >
          <ActionIcon name="chart" />
          CHART
        </button>
        <button
          type="button"
          className="hermes-pill-action"
          onClick={(e) => {
            e.stopPropagation();
            onExport?.(agent);
          }}
        >
          <ActionIcon name="export" />
          EXPORT
        </button>
      </footer>
    </article>
  );
}

export default memo(AgentCardCompact);
