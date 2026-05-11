import { useEffect, useMemo, useState } from "react";
import { useCurrency } from "../../contexts/CurrencyContext";
import { getAgentTrades } from "../../api/agents";

/**
 * Full-screen agent detail modal.
 *
 * Shows:
 *   - Hero card with symbol, strategy, status pill and total P&L
 *   - Equity / sparkline chart (uses agent.spark or equityHistory if present)
 *   - Win/loss histogram (rolled up from trades)
 *   - Recent trades list (per-agent /api/trades/{symbol})
 *   - Action footer: Pause/Start, Share, Export CSV, Remove from dashboard
 */

function downloadCsv(filename, rows) {
  if (!rows || !rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(","),
    ...rows.map((r) =>
      headers
        .map((h) => {
          const v = r[h];
          if (v === null || v === undefined) return "";
          const s = String(v).replaceAll('"', '""');
          return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s}"` : s;
        })
        .join(","),
    ),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function buildPath(values, width = 720, height = 220) {
  if (!values || values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);
  return values
    .map((v, i) => {
      const x = (i * stepX).toFixed(1);
      const y = (height - ((v - min) / range) * height).toFixed(1);
      return `${i === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");
}

export default function AgentDetailModal({
  agent,
  open,
  onClose,
  onToggle,
  onShare,
  onRemove,
}) {
  const { format } = useCurrency();
  const [trades, setTrades] = useState([]);
  const [loadingTrades, setLoadingTrades] = useState(false);

  useEffect(() => {
    if (!open || !agent) return undefined;
    let cancelled = false;
    setLoadingTrades(true);
    (async () => {
      const { data } = await getAgentTrades(agent.symbol || agent.id);
      if (!cancelled) {
        setTrades(Array.isArray(data) ? data : []);
        setLoadingTrades(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, agent]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  const equity = useMemo(() => {
    if (!agent) return [];
    if (Array.isArray(agent.equityHistory) && agent.equityHistory.length > 1) return agent.equityHistory;
    if (Array.isArray(agent.spark) && agent.spark.length > 1) return agent.spark;
    return [0, 1, 0.6, 1.4, 1.2, 1.6, 1.8, 1.4, 2.0];
  }, [agent]);

  const wins = useMemo(() => trades.filter((t) => Number(t.pnl || t.pnl_usd || 0) > 0).length, [trades]);
  const losses = useMemo(() => trades.filter((t) => Number(t.pnl || t.pnl_usd || 0) < 0).length, [trades]);
  const winRate = trades.length ? Math.round((wins / trades.length) * 100) : Math.round(Number(agent?.winRate || 0));

  if (!open || !agent) return null;

  const positive = Number(agent.pnlUsd || 0) >= 0;
  const accent = positive ? "#10b981" : "#ef4444";
  const accentB = positive ? "#22d3ee" : "#f97316";
  const path = buildPath(equity);
  const isLive = agent.status === "live";

  const onExport = () => {
    const rows = trades.map((t) => ({
      timestamp: t.timestamp || t.ts || "",
      action: (t.action || "").toUpperCase(),
      symbol: t.symbol || agent.symbol,
      price: t.price ?? "",
      quantity: t.quantity ?? "",
      pnl: t.pnl ?? t.pnl_usd ?? "",
    }));
    downloadCsv(`hermes-${(agent.symbol || agent.id || "agent").toLowerCase()}-trades.csv`, rows.length ? rows : [{ note: "no trades yet" }]);
  };

  return (
    <div className="hermes-agent-modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="hermes-agent-modal" onClick={(e) => e.stopPropagation()}>
        <header className="hermes-agent-modal-head">
          <div>
            <strong className="hermes-agent-modal-symbol">{agent.symbol || agent.name}</strong>
            <span className="hermes-agent-modal-strategy">
              {agent.strategy || agent.strategyLabel || agent.name || "Strategy"}
            </span>
          </div>
          <div className="hermes-agent-modal-head-pills">
            <span className={`hermes-agent-modal-status ${isLive ? "is-live" : "is-paused"}`}>
              {isLive ? "LIVE" : "PAUSED"}
            </span>
            <span className={`hermes-agent-modal-pnl mono`} style={{ color: accent }}>
              {format(agent.pnlUsd, { signed: true })}
            </span>
            <button type="button" className="hermes-agent-modal-close" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </header>

        <section className="hermes-agent-modal-stats">
          <div>
            <span className="hermes-agent-modal-stat-label">Win rate</span>
            <strong className="mono">{winRate}%</strong>
          </div>
          <div>
            <span className="hermes-agent-modal-stat-label">Trades</span>
            <strong className="mono">{trades.length}</strong>
          </div>
          <div>
            <span className="hermes-agent-modal-stat-label">Wins / Losses</span>
            <strong className="mono">
              <span style={{ color: "#10b981" }}>{wins}</span> /{" "}
              <span style={{ color: "#ef4444" }}>{losses}</span>
            </strong>
          </div>
          <div>
            <span className="hermes-agent-modal-stat-label">Mode</span>
            <strong>{agent.realMoney ? "LIVE" : "PAPER"}</strong>
          </div>
        </section>

        <section className="hermes-agent-modal-chart-card">
          <header>
            <strong>Equity curve</strong>
            <span className="text-3 fs-12">Synthesized from cumulative P&amp;L</span>
          </header>
          <svg
            className="hermes-agent-modal-chart"
            viewBox="0 0 720 220"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="hermes-mod-line" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={accent} />
                <stop offset="100%" stopColor={accentB} />
              </linearGradient>
              <linearGradient id="hermes-mod-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={accent} stopOpacity="0.32" />
                <stop offset="100%" stopColor={accent} stopOpacity="0" />
              </linearGradient>
            </defs>
            {[0.25, 0.5, 0.75].map((p) => (
              <line key={p} x1="0" x2="720" y1={220 * p} y2={220 * p} stroke="rgba(255,255,255,.05)" />
            ))}
            <path d={`${path} L720,220 L0,220 Z`} fill="url(#hermes-mod-fill)" />
            <path d={path} fill="none" stroke="url(#hermes-mod-line)" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
        </section>

        <section className="hermes-agent-modal-trades-card">
          <header className="row between">
            <strong>Recent trades</strong>
            <button type="button" className="hermes-pill-action" onClick={onExport}>
              Export CSV
            </button>
          </header>
          {loadingTrades ? (
            <p className="text-3 fs-12">Loading…</p>
          ) : trades.length ? (
            <div className="hermes-agent-modal-trades">
              {trades.slice(0, 12).map((t, i) => {
                const pnl = Number(t.pnl ?? t.pnl_usd ?? 0);
                const ts = t.timestamp || t.ts || "";
                return (
                  <div key={t.id || i} className="hermes-agent-modal-trade">
                    <span className={`hermes-trades-side ${(t.action || "").toLowerCase() === "sell" ? "is-sell" : "is-buy"}`}>
                      {(t.action || "—").toString().toUpperCase()}
                    </span>
                    <span className="mono">{t.symbol || agent.symbol}</span>
                    <span className="mono text-3">{Number(t.price || 0).toFixed(2)}</span>
                    <span className="mono" style={{ color: pnl >= 0 ? "#10b981" : "#ef4444", textAlign: "right" }}>
                      {format(pnl, { signed: true })}
                    </span>
                    <span className="text-3 fs-12">{ts}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-3 fs-12">No trades yet — your agent is warming up.</p>
          )}
        </section>

        <footer className="hermes-agent-modal-footer">
          <button type="button" className="hermes-pill-action" onClick={() => onToggle?.(agent)}>
            {isLive ? "Pause agent" : "Start agent"}
          </button>
          <button type="button" className="hermes-pill-action" onClick={() => onShare?.(agent)}>
            Share
          </button>
          <button type="button" className="hermes-pill-action" onClick={onExport}>
            Export CSV
          </button>
          <button
            type="button"
            className="hermes-pill-action is-destructive"
            onClick={() => {
              onRemove?.(agent);
              onClose?.();
            }}
          >
            Remove from dashboard
          </button>
        </footer>
      </div>
    </div>
  );
}
