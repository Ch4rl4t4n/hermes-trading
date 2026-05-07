import { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import SparkLine from "../components/ui/SparkLine";
import { useBreakpoint } from "../hooks/useBreakpoint";

function normalizeLeaderboardEntry(raw) {
  return {
    rank: raw.rank,
    agentId: raw.agent_id || raw.agentId,
    name: raw.agent_name || raw.name,
    strategy: raw.strategy || "Momentum",
    symbol: raw.symbol || "BTC/USD",
    pnlPct: raw.pnl_pct || raw.pnl_percent || 0,
    pnlUsd: raw.pnl_usd || 0,
    winRate: raw.win_rate || 0,
    trades: raw.trade_count || raw.trades || 0,
    subscribers: raw.subscriber_count || raw.subscribers || 0,
    isSubscribed: Boolean(raw.is_subscribed || raw.isSubscribed),
  };
}

function generateSparkline(entry, points = 30) {
  const out = [];
  const seed = Number(entry.pnlUsd || 0) + Number(entry.trades || 0) * 13;
  let cur = 100 + (seed % 20);
  for (let i = 0; i < points; i += 1) {
    const drift = (Number(entry.pnlPct || 0) / 200) + ((Math.sin(i * 0.7 + seed) * 1.6));
    cur += drift;
    out.push(Number(cur.toFixed(2)));
  }
  return out;
}

function topRankStyle(rank) {
  if (rank === 1) return { borderColor: "oklch(0.82 0.14 75)", color: "oklch(0.9 0.1 75)" };
  if (rank === 2) return { borderColor: "oklch(0.80 0.02 260)", color: "oklch(0.88 0.01 260)" };
  if (rank === 3) return { borderColor: "oklch(0.72 0.12 55)", color: "oklch(0.86 0.09 55)" };
  return { borderColor: "transparent", color: "var(--text-2)" };
}

export default function Leaderboard({ onToast }) {
  const { isDesktop } = useBreakpoint();
  const [tab, setTab] = useState("weekly");
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState([]);
  const [followingEntries, setFollowingEntries] = useState([]);
  const [subscribedMap, setSubscribedMap] = useState({});
  const [sort, setSort] = useState({ key: "rank", dir: "asc" });
  const [activeAgent, setActiveAgent] = useState(null);

  const tabs = [
    { id: "weekly", label: "7D" },
    { id: "monthly", label: "30D" },
    { id: "alltime", label: "All Time" },
    { id: "following", label: "Following" },
  ];

  useEffect(() => {
    if (tab === "following") return;
    let cancelled = false;
    setLoading(true);
    client
      .get(`/api/leaderboard?period=${tab}`)
      .then(({ data }) => {
        if (cancelled) return;
        const rows = Array.isArray(data) ? data : data?.leaderboard || [];
        const normalized = rows.map(normalizeLeaderboardEntry);
        setEntries(normalized);
        setSubscribedMap((prev) => {
          const next = { ...prev };
          normalized.forEach((row) => {
            next[row.agentId] = row.isSubscribed;
          });
          return next;
        });
      })
      .catch(() => {
        if (!cancelled) setEntries([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab]);

  useEffect(() => {
    let cancelled = false;
    client
      .get("/api/agents")
      .then(({ data }) => {
        if (cancelled) return;
        const rows = Array.isArray(data) ? data : data?.agents || [];
        const normalized = rows.map((raw, idx) => normalizeLeaderboardEntry({
          rank: idx + 1,
          agent_id: raw.id || raw.symbol,
          name: raw.name,
          strategy: raw.trading_mode || raw.strategy,
          symbol: raw.symbol,
          pnl_pct: raw.pnl_pct || raw.realized_pnl_today_usd || 0,
          pnl_usd: raw.realized_pnl_today_usd || raw.pnl_usd || 0,
          win_rate: (raw.confidence || 0.5) * 100,
          trade_count: raw.trades_today || 0,
          subscriber_count: raw.subscriber_count || 0,
          is_subscribed: true,
        }));
        setFollowingEntries(normalized);
      })
      .catch(() => {
        if (!cancelled) setFollowingEntries([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sorted = useMemo(() => {
    const source = tab === "following" ? followingEntries : entries;
    const arr = [...source];
    arr.sort((a, b) => {
      const mul = sort.dir === "asc" ? 1 : -1;
      if (sort.key === "name" || sort.key === "strategy" || sort.key === "symbol") {
        return String(a[sort.key]).localeCompare(String(b[sort.key])) * mul;
      }
      return (Number(a[sort.key]) - Number(b[sort.key])) * mul;
    });
    return arr;
  }, [entries, followingEntries, sort, tab]);

  const onSort = (key) =>
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );

  const toggleSubscribe = async (entry) => {
    const isSub = Boolean(subscribedMap[entry.agentId]);
    const endpoint = isSub ? "/api/marketplace/unsubscribe" : "/api/marketplace/subscribe";
    try {
      await client.post(endpoint, { agent_id: entry.agentId });
      setSubscribedMap((prev) => ({ ...prev, [entry.agentId]: !isSub }));
      onToast?.(!isSub ? "Subscribed" : "Unsubscribed");
    } catch {
      onToast?.("Action failed");
    }
  };

  const renderSortLabel = (key, label) => (
    <button type="button" className="lb-sort-btn" onClick={() => onSort(key)}>
      <span>{label}</span>
      <span style={{ opacity: sort.key === key ? 1 : 0.35 }}>{sort.key === key ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}</span>
    </button>
  );

  const selectedAgent = activeAgent
    ? {
        ...activeAgent,
        spark: generateSparkline(activeAgent, 30),
        age: Math.max(7, Math.round((Number(activeAgent.trades) || 0) * 1.7)),
      }
    : null;

  return (
    <section className="page-content">
      <div className="lb-period-tabs row gap-2" style={{ marginBottom: 14 }}>
        {tabs.map((tabItem) => (
          <button
            key={tabItem.id}
            className={`lb-tab ${tabItem.id === tab ? "active" : ""}`}
            style={{ border: "none" }}
            onClick={() => setTab(tabItem.id)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="glass row gap-2" style={{ padding: 12, marginBottom: 10 }}>
          <span className="spinner active" />
          <span>Loading leaderboard...</span>
        </div>
      ) : null}

      {tab === "following" && sorted.length === 0 && !loading ? (
        <div className="glass" style={{ padding: 18, color: "var(--text-2)" }}>
          Subscribe to agents to see them here
        </div>
      ) : null}

      {isDesktop ? (
        <div className="glass lb-table-wrap">
          <table className="leaderboard-table lb-table-fixed">
            <colgroup>
              <col style={{ width: 50 }} />
              <col style={{ width: 220 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 80 }} />
            </colgroup>
            <thead>
              <tr>
                <th>{renderSortLabel("rank", "Rank")}</th>
                <th>{renderSortLabel("name", "Agent")}</th>
                <th>{renderSortLabel("strategy", "Strategy")}</th>
                <th>{renderSortLabel("symbol", "Symbol")}</th>
                <th>{renderSortLabel("pnlPct", "PnL %")}</th>
                <th>{renderSortLabel("winRate", "Win Rate")}</th>
                <th>{renderSortLabel("trades", "Trades")}</th>
                <th>{renderSortLabel("subscribers", "Followers")}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry) => {
                const style = topRankStyle(entry.rank);
                const mine = Boolean(subscribedMap[entry.agentId]);
                return (
                  <tr
                    key={entry.agentId}
                    className={`${mine ? "mine" : ""} rank-${entry.rank}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => setActiveAgent(entry)}
                  >
                    <td style={{ borderLeft: `3px solid ${style.borderColor}` }}>
                      <strong style={{ color: style.color }}>{`#${entry.rank}`}</strong>
                    </td>
                    <td>{entry.name}</td>
                    <td>{entry.strategy}</td>
                    <td className="mono">{entry.symbol}</td>
                    <td>
                      <span className={`pill ${entry.pnlPct >= 0 ? "pill-green" : "pill-red"}`}>
                        {entry.pnlPct >= 0 ? "+" : ""}
                        {Number(entry.pnlPct).toFixed(2)}%
                      </span>
                    </td>
                    <td>
                      <div>
                        <div className="fs-12">{`${Number(entry.winRate).toFixed(1)}%`}</div>
                        <div className="progress" style={{ height: 4, marginTop: 4 }}>
                          <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, Number(entry.winRate)))}%` }} />
                        </div>
                      </div>
                    </td>
                    <td>{entry.trades}</td>
                    <td>{entry.subscribers}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <article className="glass col" style={{ padding: 12, gap: 8 }}>
          {sorted.map((entry) => (
            <div
              key={entry.agentId}
              className={`lb-mobile-card ${subscribedMap[entry.agentId] ? "mine" : ""}`}
              style={{ cursor: "pointer" }}
              onClick={() => setActiveAgent(entry)}
            >
              <div className="row between">
                <div className="row gap-2" style={{ minWidth: 0 }}>
                  <span className="mono fw-600" style={{ fontSize: 20, ...topRankStyle(entry.rank) }}>
                    #{entry.rank}
                  </span>
                  <div className="col" style={{ minWidth: 0 }}>
                    <strong style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.name}</strong>
                    <span className="pill pill-gray" style={{ width: "fit-content", marginTop: 4 }}>{entry.strategy}</span>
                  </div>
                </div>
                {!subscribedMap[entry.agentId] ? (
                  <button
                    type="button"
                    className="share-btn"
                    style={{ padding: "8px 12px", fontSize: 12 }}
                    onClick={(e) => { e.stopPropagation(); toggleSubscribe(entry); }}
                  >
                    Subscribe
                  </button>
                ) : null}
              </div>

              <div className="row between" style={{ marginTop: 10 }}>
                <span className="mono" style={{ fontSize: 24, color: entry.pnlPct >= 0 ? "var(--color-green)" : "var(--color-red)" }}>
                  {entry.pnlPct >= 0 ? "+" : ""}
                  {Number(entry.pnlPct).toFixed(2)}%
                </span>
                <span className="mono text-2">{`${Number(entry.pnlUsd).toFixed(2)}$`}</span>
              </div>
              <div className="row between fs-12" style={{ marginTop: 8 }}>
                <span className="text-2">{`Win rate ${Number(entry.winRate).toFixed(1)}%`}</span>
                <span className="text-3">{`${entry.trades} trades`}</span>
              </div>
            </div>
          ))}
        </article>
      )}

      <div className={`lb-panel-backdrop ${selectedAgent ? "open" : ""}`} onClick={() => setActiveAgent(null)} />
      <aside className={`lb-side-panel ${selectedAgent ? "open" : ""}`}>
        {selectedAgent ? (
          <>
            <div className="row between" style={{ marginBottom: 10 }}>
              <h3>{selectedAgent.name}</h3>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setActiveAgent(null)}>Close</button>
            </div>
            <div className="row gap-2" style={{ marginBottom: 10 }}>
              <span className="pill pill-gray">{selectedAgent.symbol}</span>
              <span className="pill pill-violet">{selectedAgent.strategy}</span>
            </div>
            <div className="glass-2" style={{ padding: 12, marginBottom: 12 }}>
              <SparkLine points={selectedAgent.spark} />
            </div>
            <div className="lb-side-stats">
              <div><span>Total PnL</span><strong>{`${selectedAgent.pnlUsd >= 0 ? "+" : ""}$${Number(selectedAgent.pnlUsd).toFixed(2)}`}</strong></div>
              <div><span>Win rate</span><strong>{`${Number(selectedAgent.winRate).toFixed(1)}%`}</strong></div>
              <div><span>Trades</span><strong>{selectedAgent.trades}</strong></div>
              <div><span>Subscribers</span><strong>{selectedAgent.subscribers}</strong></div>
              <div><span>Age</span><strong>{`${selectedAgent.age} days`}</strong></div>
            </div>
            <p className="text-2 fs-13" style={{ marginTop: 12 }}>
              {`${selectedAgent.name} runs a ${selectedAgent.strategy} profile around ${selectedAgent.symbol} with balanced entry/exit discipline and adaptive risk handling.`}
            </p>
            <button
              type="button"
              className="share-btn"
              style={{ marginTop: 10, width: "100%", justifyContent: "center" }}
              onClick={() => toggleSubscribe(selectedAgent)}
            >
              {subscribedMap[selectedAgent.agentId] ? "Unsubscribed" : "Subscribe"}
            </button>
            <div style={{ marginTop: 14 }}>
              <div className="fs-12 text-3" style={{ marginBottom: 8 }}>Recent trades</div>
              {[0, 1, 2, 3, 4].map((idx) => {
                const pnl = Number(selectedAgent.pnlUsd || 0) / Math.max(1, selectedAgent.trades || 1) * (1 + idx / 5);
                return (
                  <div key={idx} className="row between fs-12" style={{ padding: "7px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                    <span>{`${selectedAgent.symbol} · ${idx % 2 ? "SELL" : "BUY"}`}</span>
                    <span style={{ color: pnl >= 0 ? "var(--color-green)" : "var(--color-red)" }}>{`${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`}</span>
                  </div>
                );
              })}
            </div>
          </>
        ) : null}
      </aside>
    </section>
  );
}

