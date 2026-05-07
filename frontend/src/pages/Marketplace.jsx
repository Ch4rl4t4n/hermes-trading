import { useMemo, useState } from "react";
import { useBreakpoint } from "../hooks/useBreakpoint";

export default function Marketplace({ agents, onToast }) {
  const { isMobile, isDesktop } = useBreakpoint();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const filters = ["All", "Crypto", "Stocks", "Commodities", "Forex"];
  const [strategy, setStrategy] = useState("Any");
  const [sortBy, setSortBy] = useState("pnl");

  const visible = useMemo(() => {
    const filtered = agents.filter((agent) => {
      const byFilter = filter === "All" || agent.category === filter;
      const byStrategy = strategy === "Any" || agent.strategy === strategy;
      const q = query.trim().toLowerCase();
      const byQuery = !q || agent.name.toLowerCase().includes(q) || agent.strategy.toLowerCase().includes(q);
      return byFilter && byQuery && byStrategy;
    });
    if (sortBy === "subs") return filtered.sort((a, b) => b.subscribers - a.subscribers);
    if (sortBy === "win") return filtered.sort((a, b) => b.winRate - a.winRate);
    return filtered.sort((a, b) => b.pnlPct - a.pnlPct);
  }, [agents, filter, query, strategy, sortBy]);

  return (
    <section className="page-content marketplace-page">
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search agents or strategies..." />

      <div className={`marketplace-layout ${isDesktop ? "desktop" : "mobile"}`}>
        {isDesktop ? (
          <aside className="marketplace-filters glass">
            <h3>Filters</h3>
            <div className="col gap-2">
              {filters.map((item) => (
                <button
                  key={item}
                  className={`pill ${filter === item ? "pill-violet" : "pill-gray"}`}
                  style={{ border: "none", justifyContent: "center" }}
                  onClick={() => setFilter(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <label className="col gap-2 fs-12 text-2">
              Strategy
              <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                <option>Any</option>
                <option>Momentum</option>
                <option>Quant Hybrid</option>
              </select>
            </label>
            <label className="col gap-2 fs-12 text-2">
              Sort by
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                <option value="pnl">PnL</option>
                <option value="win">Win Rate</option>
                <option value="subs">Subscribers</option>
              </select>
            </label>
          </aside>
        ) : (
          <div className="row gap-2" style={{ overflowX: "auto", paddingBottom: 4 }}>
            {filters.map((item) => (
              <button
                key={item}
                className={`pill ${filter === item ? "pill-violet" : "pill-gray"}`}
                style={{ border: "none" }}
                onClick={() => setFilter(item)}
              >
                {item}
              </button>
            ))}
          </div>
        )}

        <div className={`marketplace-grid ${isDesktop ? "desktop" : isMobile ? "mobile" : "tablet"}`}>
          {visible.map((agent) => (
            <article key={agent.id} className="mp-card agent-card marketplace-card">
              <div className="mp-card-inner">
                <div className="agent-card-header">
                  <span className="agent-name" style={{ fontSize: 14, fontWeight: 600 }}>{agent.name}</span>
                </div>
                <div className="mp-meta">
                  <span className="pill pill-gray" style={{ fontSize: 11 }}>{agent.strategy}</span>
                </div>
                <div className="row gap-2 fs-12 text-2" style={{ marginTop: 8 }}>
                  <span
                    className={`pill ${
                      agent.category === "Crypto"
                        ? "pill-violet"
                        : agent.category === "Stocks"
                          ? "pill-green"
                          : agent.category === "Commodities"
                            ? "pill-amber"
                            : "pill-gray"
                    }`}
                    style={agent.category === "Forex" ? { background: "oklch(0.55 0.12 250 / .25)", color: "oklch(0.82 0.08 250)" } : undefined}
                  >
                    {agent.category}
                  </span>
                  <span className="pill pill-gray">Win {agent.winRate}%</span>
                  <span className="pill pill-green">
                    {agent.pnlPct >= 0 ? "+" : ""}
                    {agent.pnlPct}%
                  </span>
                </div>
                <div className="mp-meta" style={{ marginTop: 8 }}>
                  👥 {agent.subscribers} subscribers
                </div>
              </div>
              <button
                onClick={() => onToast(`Subscribed to ${agent.name}`)}
                style={{
                  border: "none",
                  width: "100%",
                  borderRadius: 8,
                  padding: "10px 12px",
                  background: "oklch(0.72 0.18 295)",
                  color: "#fff",
                  fontWeight: 600,
                  marginTop: 10,
                }}
              >
                Subscribe
              </button>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

