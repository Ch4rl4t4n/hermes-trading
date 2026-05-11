import { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import { fetchAgents } from "../api/agents";
import SparkLine from "../components/ui/SparkLine";
import { useCurrency } from "../contexts/CurrencyContext";

/**
 * Discover — hub for finding interesting agents and instruments.
 * Inspired by eToro Discover page.
 *
 * Sections:
 *   1. Sub-tabs: Overview / Crypto / Stocks / Pro Agents / Smart Portfolios / Commodities
 *   2. Investment Opportunities — featured / capital-guarantee / featured agents (4 cards)
 *   3. Daily Movers — gainers vs losers (2-column grid)
 *   4. Alpha Portfolios — 4 swarms with risk badges
 *   5. By Performance — top 5 instruments table with sparkline + signal pill
 *   6. Pro Agents Trending — 3 trending agents with avatars and stats
 */

const DISCOVER_TABS = [
  { id: "overview", label: "Overview" },
  { id: "stocks", label: "Stocks" },
  { id: "crypto", label: "Crypto" },
  { id: "pro", label: "Pro Agents" },
  { id: "portfolios", label: "Smart Portfolios" },
  { id: "etfs", label: "ETFs" },
  { id: "indices", label: "Indices" },
  { id: "commodities", label: "Commodities" },
];

const FEATURED_OPPORTUNITIES = [
  {
    id: "guarantee-eur",
    badge: "CAPITAL-GUARANTEE",
    title: "Equity-HedgeEUR",
    return2y: "34.25%",
    type: "guarantee",
    accent: "#fbbf24",
  },
  {
    id: "guarantee-usd",
    badge: "CAPITAL-GUARANTEE",
    title: "Equity-HedgeUSD",
    return2y: "33.28%",
    type: "guarantee",
    accent: "#fbbf24",
  },
  {
    id: "featured-trader",
    badge: "FEATURED",
    title: "Demtheo27",
    subtitle: "Top community pro",
    return2y: "87.39%",
    copiers: "408",
    type: "trader",
    accent: "#a78bfa",
  },
  {
    id: "featured-quantum",
    badge: "FEATURED",
    title: "Quantum",
    subtitle: "Quantum Computing Index",
    price: "1289.808",
    delta: "-0.54%",
    deltaPositive: false,
    type: "index",
    accent: "#22d3ee",
  },
];

const ALPHA_PORTFOLIOS = [
  { name: "PureMomentum", style: "Directional", return2y: 111.23, risk: 6, gradient: "linear-gradient(135deg,#22c55e 0%,#10b981 60%,#0d9488 100%)" },
  { name: "PureGrowth", style: "Specialized", return2y: 99.61, risk: 4, gradient: "linear-gradient(135deg,#f59e0b 0%,#d97706 60%,#92400e 100%)" },
  { name: "Momentum-LS", style: "Directional", return2y: 98.08, risk: 5, gradient: "linear-gradient(135deg,#ef4444 0%,#dc2626 60%,#7f1d1d 100%)" },
  { name: "OutSmartNSDQ", style: "Directional", return2y: 40.65, risk: 4, gradient: "linear-gradient(135deg,#6366f1 0%,#8b5cf6 60%,#4338ca 100%)" },
];

const BY_PERFORMANCE = [
  { sym: "BTC", name: "Bitcoin", price: 80131.74, change24h: -0.57, marketCap: "1.6T", volume: "34.06B", signal: "HOLD", indicators: "4/8" },
  { sym: "ETH", name: "Ethereum", price: 2310.61, change24h: 1.23, marketCap: "276.84B", volume: "20.56B", signal: "HOLD", indicators: "4/8" },
  { sym: "BNB", name: "Build and Build", price: 645.99, change24h: 1.29, marketCap: "86.66B", volume: "1.48B", signal: "HOLD", indicators: "4/8" },
  { sym: "XRP", name: "XRP", price: 1.406, change24h: 1.74, marketCap: "86.26B", volume: "1.57B", signal: "BUY", indicators: "5/8" },
  { sym: "USDC", name: "USDC", price: 0.9998, change24h: 0, marketCap: "78.13B", volume: "12.59B", signal: "N/A", indicators: "0/8" },
];

const DAILY_MOVERS_UP = [
  { sym: "PYX", name: "Pyx Resources Limited", change: 40.0 },
  { sym: "NPA", name: "Napatech A/S", change: 38.61 },
  { sym: "2INV", name: "2Invest AG", change: 37.35 },
  { sym: "WEST", name: "Westrock Coffee Company", change: 34.58 },
  { sym: "2020", name: "2020 Bulkers Ltd", change: 32.62 },
];

const DAILY_MOVERS_DOWN = [
  { sym: "CRZK", name: "CR Energy AG", change: -34.67 },
  { sym: "GWH", name: "Ess Tech Inc", change: -33.12 },
  { sym: "SKIN", name: "SkinHealth Systems Inc", change: -29.36 },
  { sym: "TSSI", name: "TSS Inc", change: -28.03 },
  { sym: "FIGS", name: "FIGS Inc.", change: -27.52 },
];

function generateSpark(seed = 0) {
  const out = [];
  let v = 100;
  for (let i = 0; i < 24; i += 1) {
    v += Math.sin(i * 0.6 + seed) * 2 + (Math.random() - 0.5) * 1.4;
    out.push(Number(v.toFixed(2)));
  }
  return out;
}

function signalColor(sig) {
  if (sig === "BUY") return "is-buy";
  if (sig === "SELL") return "is-sell";
  if (sig === "HOLD") return "is-hold";
  return "is-na";
}

function FeaturedCard({ item, onAction, format }) {
  return (
    <article
      className={`hermes-discover-feature is-${item.type}`}
      style={{
        backgroundImage: `radial-gradient(circle at 80% 30%, ${item.accent}33, transparent 65%), linear-gradient(135deg, rgba(13,16,24,.85), rgba(20,24,38,.95))`,
        borderColor: `${item.accent}55`,
      }}
      onClick={() => onAction?.(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onAction?.(item)}
    >
      <span className="hermes-discover-feature-badge" style={{ background: `${item.accent}30`, color: item.accent }}>
        {item.badge}
      </span>
      <div className="hermes-discover-feature-body">
        <strong className="hermes-discover-feature-title">{item.title}</strong>
        {item.subtitle ? <span className="text-3 fs-12">{item.subtitle}</span> : null}
        <div className="hermes-discover-feature-stats">
          {item.return2y ? (
            <span className="hermes-discover-feature-return">
              <strong className="mono">{item.return2y}</strong>
              <span className="text-3 fs-12">Return (2Y)</span>
            </span>
          ) : null}
          {item.copiers ? (
            <span className="hermes-discover-feature-meta">
              <strong className="mono">{item.copiers}</strong>
              <span className="text-3 fs-12">Copiers</span>
            </span>
          ) : null}
          {item.price ? (
            <span className="hermes-discover-feature-meta">
              <strong className="mono">{item.price}</strong>
              {item.delta ? (
                <span className={`text-3 fs-12 ${item.deltaPositive ? "is-pos" : "is-neg"}`}>{item.delta}</span>
              ) : null}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function MoverRow({ mover, type }) {
  const isUp = type === "up";
  return (
    <div className={`hermes-mover-row is-${type}`}>
      <span className="hermes-mover-icon" style={{ background: isUp ? "rgba(34,197,94,.18)" : "rgba(239,68,68,.18)", color: isUp ? "#22c55e" : "#ef4444" }}>
        {mover.sym.slice(0, 2)}
      </span>
      <span className="hermes-mover-info">
        <strong className="hermes-mover-sym">{mover.sym}</strong>
        <span className="text-3 fs-12">{mover.name}</span>
      </span>
      <strong className={`hermes-mover-change ${isUp ? "is-pos" : "is-neg"}`}>
        {mover.change > 0 ? "+" : ""}
        {mover.change.toFixed(2)}%
      </strong>
    </div>
  );
}

function ProAgentTile({ agent, format }) {
  const positive = Number(agent.pnlUsd || 0) >= 0;
  return (
    <article className="glass hermes-discover-pro-tile">
      <div className="row gap-2" style={{ alignItems: "center" }}>
        <span
          className="hermes-discover-pro-avatar"
          style={{ background: positive ? "linear-gradient(135deg,#22c55e,#0d9488)" : "linear-gradient(135deg,#ef4444,#7f1d1d)" }}
          aria-hidden="true"
        >
          {(agent.symbol || agent.name || "A")[0]}
        </span>
        <div className="col" style={{ minWidth: 0, gap: 2 }}>
          <strong className="hermes-discover-pro-name">{agent.name || agent.symbol}</strong>
          <span className="text-3 fs-12">{agent.strategy || "Strategy"} · {agent.symbol}</span>
        </div>
        <span className="pill pill-violet" style={{ marginLeft: "auto", border: "none" }}>VERIFIED</span>
      </div>
      <div className="row between" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <div className="col">
          <strong className="mono" style={{ fontSize: 22, color: positive ? "#22c55e" : "#ef4444", letterSpacing: "-0.02em" }}>
            {format(agent.pnlUsd, { signed: true, decimals: 0 })}
          </strong>
          <span className="text-3 fs-12">P&amp;L · {agent.winRate || 0}% win</span>
        </div>
        <div style={{ width: 90, height: 32 }}>
          <SparkLine
            points={Array.isArray(agent.spark) && agent.spark.length > 1 ? agent.spark : generateSpark(agent.id || 1)}
            color={positive ? "#22c55e" : "#ef4444"}
          />
        </div>
      </div>
    </article>
  );
}

export default function Discover({ user, onNav, onToast }) {
  const { format } = useCurrency();
  const [tab, setTab] = useState("overview");
  const [proAgents, setProAgents] = useState([]);

  useEffect(() => {
    fetchAgents()
      .then((res) => {
        const rows = res?.data || [];
        const sorted = [...rows].sort((a, b) => Number(b.pnlUsd || 0) - Number(a.pnlUsd || 0)).slice(0, 3);
        setProAgents(sorted);
      })
      .catch(() => setProAgents([]));
  }, []);

  const opportunities = useMemo(() => FEATURED_OPPORTUNITIES, []);

  const onFeatureClick = (item) => {
    if (item.type === "trader" || item.type === "guarantee") {
      onNav?.("marketplace");
      return;
    }
    onToast?.(`Opening ${item.title}…`);
  };

  return (
    <section className="page-content hermes-discover col" style={{ gap: 18 }}>
      <header className="hermes-page-head">
        <div>
          <h1 className="hermes-page-title">Discover</h1>
          <p className="hermes-page-lead">Investment opportunities — explore live agents, sectors and movers</p>
        </div>
      </header>

      <nav className="hermes-discover-tabs" aria-label="Discover categories">
        {DISCOVER_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`hermes-discover-tab${tab === t.id ? " is-active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <section className="hermes-discover-section">
        <div className="hermes-discover-section-head">
          <div>
            <span className="text-3 fs-12">Investment Opportunities</span>
            <h2 className="hermes-discover-section-title">Explore Hermes Markets</h2>
          </div>
          <div className="hermes-discover-section-arrows" aria-hidden="true">
            <button type="button" className="hermes-discover-arrow">‹</button>
            <button type="button" className="hermes-discover-arrow">›</button>
          </div>
        </div>
        <div className="hermes-discover-features">
          {opportunities.map((item) => (
            <FeaturedCard key={item.id} item={item} onAction={onFeatureClick} format={format} />
          ))}
        </div>
      </section>

      <section className="hermes-discover-section">
        <div className="hermes-discover-section-head">
          <div>
            <h2 className="hermes-discover-section-title">Daily Movers</h2>
            <p className="text-3 fs-12">Today's biggest gainers and losers.</p>
          </div>
          <button type="button" className="hermes-discover-view-all">View all</button>
        </div>
        <div className="hermes-discover-movers">
          <div className="hermes-discover-movers-col is-up">
            {DAILY_MOVERS_UP.map((m, idx) => (
              <MoverRow key={`up-${m.sym}`} mover={m} type={idx === 0 ? "up-hero" : "up"} />
            ))}
          </div>
          <div className="hermes-discover-movers-col is-down">
            {DAILY_MOVERS_DOWN.map((m, idx) => (
              <MoverRow key={`down-${m.sym}`} mover={m} type={idx === 0 ? "down-hero" : "down"} />
            ))}
          </div>
        </div>
      </section>

      <section className="hermes-discover-section">
        <div className="hermes-discover-section-head">
          <div>
            <h2 className="hermes-discover-section-title">Alpha Portfolios</h2>
            <p className="text-3 fs-12">AI-driven strategies — exclusively on Hermes.</p>
          </div>
          <button type="button" className="hermes-discover-view-all">View all</button>
        </div>
        <div className="hermes-discover-alpha">
          {ALPHA_PORTFOLIOS.map((p) => (
            <article
              key={p.name}
              className="hermes-discover-alpha-card"
              style={{ background: p.gradient }}
              onClick={() => onNav?.("marketplace")}
              role="button"
              tabIndex={0}
            >
              <div className="hermes-discover-alpha-body">
                <strong className="hermes-discover-alpha-name">{p.name}</strong>
                <span className="hermes-discover-alpha-style">{p.style}</span>
              </div>
              <div className="hermes-discover-alpha-foot">
                <span className="hermes-discover-alpha-return">
                  <strong className="mono">{p.return2y.toFixed(2)}%</strong>
                  <span>Return (2Y)</span>
                </span>
                <span className="hermes-discover-alpha-risk" aria-label={`Risk ${p.risk}`}>
                  <span>{p.risk}</span>
                  <small>RISK</small>
                </span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="hermes-discover-section">
        <div className="hermes-discover-section-head">
          <div>
            <h2 className="hermes-discover-section-title">By Performance</h2>
            <p className="text-3 fs-12">
              Crypto market cap is <strong>2.66T</strong>, +0.48% over the last day.
            </p>
          </div>
          <button type="button" className="hermes-discover-view-all">View all</button>
        </div>
        <div className="hermes-discover-table-wrap">
          <table className="hermes-discover-table">
            <thead>
              <tr>
                <th>Coin</th>
                <th>Price</th>
                <th>Last 7 days</th>
                <th>Market cap</th>
                <th>Volume (24h)</th>
                <th>Signal</th>
              </tr>
            </thead>
            <tbody>
              {BY_PERFORMANCE.map((row) => (
                <tr key={row.sym}>
                  <td>
                    <div className="row gap-2" style={{ alignItems: "center" }}>
                      <span
                        className="hermes-discover-coin-icon"
                        style={{
                          background:
                            row.sym === "BTC"
                              ? "linear-gradient(135deg,#f59e0b,#d97706)"
                              : row.sym === "ETH"
                                ? "linear-gradient(135deg,#94a3b8,#475569)"
                                : row.sym === "BNB"
                                  ? "linear-gradient(135deg,#fbbf24,#d97706)"
                                  : row.sym === "XRP"
                                    ? "linear-gradient(135deg,#1f2937,#0f172a)"
                                    : "linear-gradient(135deg,#3b82f6,#1d4ed8)",
                        }}
                        aria-hidden="true"
                      >
                        {row.sym[0]}
                      </span>
                      <span className="col" style={{ gap: 0 }}>
                        <strong>{row.sym}</strong>
                        <span className="text-3 fs-12">{row.name}</span>
                      </span>
                    </div>
                  </td>
                  <td>
                    <strong className="mono">{format(row.price, { decimals: row.price < 10 ? 4 : 2 })}</strong>
                    <div className={`text-3 fs-12 ${row.change24h >= 0 ? "is-pos" : "is-neg"}`}>
                      ({row.change24h >= 0 ? "+" : ""}{row.change24h.toFixed(2)}%)
                    </div>
                  </td>
                  <td>
                    <div style={{ width: 80, height: 26 }}>
                      <SparkLine
                        points={generateSpark(row.sym.charCodeAt(0))}
                        color={row.change24h >= 0 ? "#22c55e" : "#ef4444"}
                      />
                    </div>
                  </td>
                  <td><strong className="mono">{row.marketCap}</strong></td>
                  <td><strong className="mono">{row.volume}</strong></td>
                  <td>
                    <span className={`hermes-discover-signal ${signalColor(row.signal)}`}>
                      {row.signal}
                    </span>
                    <div className="text-3 fs-12">{row.indicators} indicators</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {proAgents.length ? (
        <section className="hermes-discover-section">
          <div className="hermes-discover-section-head">
            <div>
              <h2 className="hermes-discover-section-title">Pro Agents Trending</h2>
              <p className="text-3 fs-12">Verified performers worth watching this week.</p>
            </div>
            <button type="button" className="hermes-discover-view-all" onClick={() => onNav?.("leaderboard")}>
              View all
            </button>
          </div>
          <div className="hermes-discover-pro-grid">
            {proAgents.slice(0, 3).map((a) => (
              <ProAgentTile key={a.id || a.symbol} agent={a} format={format} />
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
