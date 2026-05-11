/**
 * Prototype-style marketplace card:
 *   - top: avatar circle + name + author + status pill (TOP / HOT / STEADY / RELIABLE)
 *   - middle: 2-stat tile grid (Win rate, 30d P&L)
 *   - bottom: subscribers count + "Predplatiť" gradient button
 */

function badgeFor(agent) {
  const win = Number(agent.win_rate ?? agent.winRate ?? 0);
  const ret = Number(agent.total_return ?? agent.pnlPct ?? 0);
  const subs = Number(agent.subscribers ?? agent.followers ?? 0);
  if (win >= 70 && ret > 15) return { label: "TOP", icon: "🏆", color: "amber" };
  if (ret > 20) return { label: "HOT", icon: "🔥", color: "red" };
  if (win >= 65 && ret < 15) return { label: "STEADY", icon: "🎯", color: "green" };
  if (subs > 800 && win >= 70) return { label: "RELIABLE", icon: "⚡", color: "blue" };
  return null;
}

function symbolBlock(agent) {
  const sym = String(agent.symbol || "—").toUpperCase();
  const cat = String(agent.category || "").toLowerCase();
  const strat = agent.strategy || "—";
  const display = cat === "crypto" || cat === "stocks" || cat === "commodity" ? cat.toUpperCase() : "TRADE";
  return { sym, display, strat };
}

function categoryGlyph(category) {
  const c = String(category || "").toLowerCase();
  if (c === "crypto") return { letter: "₿", color: "#a78bfa" };
  if (c === "stocks") return { letter: "$", color: "#22d3ee" };
  if (c === "commodity" || c === "commodities") return { letter: "◉", color: "#fbbf24" };
  return { letter: "▲", color: "#94a3b8" };
}

export default function MarketplaceCard({ agent, isCommunity = false, onSubscribe, onPause }) {
  const win = Number(agent.win_rate ?? agent.winRate ?? 0);
  const ret = Number(agent.total_return ?? agent.pnlPct ?? 0);
  const subs = Number(agent.subscribers ?? 0);
  const isSubscribed = Boolean(agent.subscribed) || Boolean(agent.user_has_clone);
  const badge = badgeFor(agent);
  const { sym, strat } = symbolBlock(agent);
  const glyph = categoryGlyph(agent.category);

  return (
    <article className="hermes-mp-card glass">
      <header className="hermes-mp-card-head">
        <div
          className="hermes-mp-card-avatar"
          style={{
            background: `linear-gradient(135deg, ${glyph.color}, color-mix(in srgb, ${glyph.color} 50%, #0b0b14))`,
          }}
          aria-hidden="true"
        >
          <span style={{ color: "#0b0b14", fontWeight: 800, fontSize: 16 }}>{glyph.letter}</span>
        </div>

        <div className="hermes-mp-card-titles">
          <strong className="hermes-mp-card-name">{agent.name || sym}</strong>
          <span className="text-3 fs-12">
            {sym} · {strat}
          </span>
        </div>

        {badge ? (
          <span className={`hermes-mp-card-badge is-${badge.color}`}>
            <span aria-hidden="true">{badge.icon}</span> {badge.label}
          </span>
        ) : null}
      </header>

      <div className="hermes-mp-card-author">
        by <strong>@{agent.author_handle || agent.author || "Hermes Labs"}</strong>
        {agent.author_verified !== false ? <span className="hermes-mp-card-verified" aria-label="Verified">✓</span> : null}
      </div>

      <div className="hermes-mp-card-stats">
        <div className="hermes-mp-card-stat">
          <span className="text-3 fs-12">Win rate</span>
          <strong className="mono" style={{ color: win >= 60 ? "var(--accent-success, #10b981)" : "var(--text-primary)" }}>
            {win.toFixed(0)}%
          </strong>
        </div>
        <div className="hermes-mp-card-stat">
          <span className="text-3 fs-12">30d P&L</span>
          <strong
            className="mono"
            style={{ color: ret >= 0 ? "var(--accent-success, #10b981)" : "var(--accent-danger, #ef4444)" }}
          >
            {ret >= 0 ? "+" : ""}{ret.toFixed(1)}%
          </strong>
        </div>
      </div>

      <footer className="hermes-mp-card-foot">
        <span className="hermes-mp-card-followers">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          {subs.toLocaleString()} followers
        </span>

        {isSubscribed ? (
          <button type="button" className="hermes-mp-card-btn is-subscribed" onClick={() => onPause?.(agent)}>
            Already cloned
          </button>
        ) : (
          <button type="button" className="hermes-mp-card-btn" onClick={() => onSubscribe?.(agent, isCommunity)}>
            Subscribe
          </button>
        )}
      </footer>
    </article>
  );
}
