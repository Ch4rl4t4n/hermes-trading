function formatSigned(value, digits = 2, prefix = "") {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${prefix}${number.toFixed(digits)}`;
}

function buildShareText(agent) {
  const agentName = agent?.name || "Hermes";
  const pnlPct = Number(agent?.pnlPct ?? (Number(agent?.pnlUsd || 0) / 100)).toFixed(2);
  return `My ${agentName} agent is up +${pnlPct}% on @HermesTrade! 🤖📈
Let Agents Cook 🔥
#AlgoTrading #HermesTrade #LetAgentsCook
https://letagentscook.lol`;
}

export default function ShareModal({ agent, onClose }) {
  if (!agent) return null;

  const pnlUsd = Number(agent.pnlUsd ?? agent.pnl ?? 0);
  const winRate = Number(agent.winRate ?? 50);
  const trades = Number(agent.trades ?? 0);
  const shareText = buildShareText(agent);

  const onShareTwitter = () => {
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}`;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const onCopyLink = async () => {
    const url = `https://letagentscook.lol/agents/${encodeURIComponent(agent.id || agent.symbol || "agent")}`;
    await navigator.clipboard.writeText(url);
  };

  const onCopyText = async () => {
    const cardText = `${agent.name}
PnL: ${formatSigned(pnlUsd, 2, "$")}
Win rate: ${winRate.toFixed(1)}%
Trades: ${trades}
Let Agents Cook 🔥`;
    await navigator.clipboard.writeText(cardText);
  };

  return (
    <div className="agent-evo-overlay" onClick={onClose} role="presentation">
      <div className="glass" style={{ width: "min(560px, 96vw)", padding: 20 }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3>Share Performance</h3>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
        </div>

        <div className="share-card" style={{ width: "100%", maxWidth: 400, minHeight: 250, margin: "0 auto 14px" }}>
          <div className="row between">
            <div>
              <div className="fs-12 text-3">Agent</div>
              <strong style={{ fontSize: 18 }}>{agent.name}</strong>
            </div>
            <span className="pill pill-violet">{agent.symbol}</span>
          </div>
          <div style={{ marginTop: 24, marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", letterSpacing: ".07em" }}>TOTAL PNL</div>
            <div style={{ fontSize: 42, fontWeight: 800, color: "oklch(0.72 0.18 155)", lineHeight: 1.1 }}>
              {formatSigned(pnlUsd, 2, "$")}
            </div>
          </div>
          <div className="row between fs-13" style={{ marginTop: 4 }}>
            <div>{`Win rate ${winRate.toFixed(1)}%`}</div>
            <div>{`${trades} trades`}</div>
          </div>
          <div className="row between" style={{ marginTop: 18 }}>
            <span className="fs-12 text-3">Let Agents Cook 🔥</span>
            <strong style={{ color: "oklch(0.84 0.12 295)" }}>⚡ HERMES</strong>
          </div>
        </div>

        <div className="row" style={{ gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
          <button type="button" className="share-btn share-btn-twitter" onClick={onShareTwitter}>𝕏 Share on X</button>
          <button type="button" className="share-btn" onClick={onCopyLink}>Copy link</button>
          <button type="button" className="share-btn" onClick={onCopyText}>Copy image text</button>
        </div>
      </div>
    </div>
  );
}
