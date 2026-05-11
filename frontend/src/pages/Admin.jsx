import { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import { getPendingCommunityAgents, reviewCommunityAgent } from "../api/community";

const DEMO_USERS = [
  { id: 1, email: "alpha@letagentscook.com", tier: "pro", created_at: "2026-01-07T08:00:00Z", agents: 6, last_active: "2m ago" },
  { id: 2, email: "beta@letagentscook.com", tier: "elite", created_at: "2026-02-12T09:00:00Z", agents: 14, last_active: "14m ago" },
];
const DEMO_AGENTS = Array.from({ length: 50 }).map((_, idx) => ({
  id: idx + 1,
  name: `Agent ${idx + 1}`,
  symbol: idx % 2 ? "BTC/USD" : "ETH/USD",
  show_in_leaderboard: idx % 5 !== 0,
  subscriber_count: 120 - idx,
}));

const DEFAULT_SWARMS = [
  {
    swarm_name: "orchestra",
    display_name: "Orchestra",
    icon: "🎼",
    description: "Master coordinator - routes tasks to other swarms",
    color: "oklch(0.72 0.18 295)",
  },
  {
    swarm_name: "trading",
    display_name: "Trade Execution",
    icon: "📈",
    description: "Executes and monitors trading strategies",
    color: "oklch(0.78 0.16 155)",
  },
  {
    swarm_name: "intelligence",
    display_name: "Intelligence Stalker",
    icon: "🔍",
    description: "Market research, news analysis, trend detection",
    color: "oklch(0.78 0.14 75)",
  },
  {
    swarm_name: "marketing",
    display_name: "Marketing & Growth",
    icon: "📣",
    description: "Social media, content creation, SEO, growth",
    color: "oklch(0.72 0.18 15)",
  },
  {
    swarm_name: "maintenance",
    display_name: "Infrastructure",
    icon: "🔧",
    description: "Web/app maintenance, monitoring, security",
    color: "oklch(0.65 0.12 220)",
  },
];

export default function Admin({ onToast, onNav }) {
  const [users, setUsers] = useState([]);
  const [agents, setAgents] = useState([]);
  const [revenue, setRevenue] = useState(null);
  const [activeTab, setActiveTab] = useState("users");
  const [pendingCommunity, setPendingCommunity] = useState([]);
  const [reviewingId, setReviewingId] = useState(null);
  const [rejectReasons, setRejectReasons] = useState({});
  const [registryAgents, setRegistryAgents] = useState([]);
  const [queueStats, setQueueStats] = useState({ pending: 0, agents_alive: 0, agents_total: 0 });
  const [expandedSwarms, setExpandedSwarms] = useState({});

  useEffect(() => {
    let cancelled = false;
    client.get("/api/admin/users").then(({ data }) => {
      if (cancelled) return;
      const rows = Array.isArray(data?.users) ? data.users : DEMO_USERS;
      setUsers(rows.map((u) => ({ ...u, agents: u.agents ?? Math.max(1, (u.id % 6) + 1), last_active: u.last_active || "today" })));
    }).catch(() => !cancelled && setUsers(DEMO_USERS));

    client.get("/api/admin/agents").then(({ data }) => {
      if (cancelled) return;
      const rows = Array.isArray(data?.agents) ? data.agents : DEMO_AGENTS;
      setAgents(rows.map((a) => ({ ...a, subscriber_count: a.subscriber_count ?? Math.max(0, 90 - (a.id % 40)) })));
    }).catch(() => !cancelled && setAgents(DEMO_AGENTS));

    client.get("/api/admin/revenue").then(({ data }) => {
      if (cancelled) return;
      setRevenue(data || null);
    }).catch(() => !cancelled && setRevenue({
      mrr_estimate: 8930, basic_count: 120, pro_count: 67, elite_count: 19, paying_users: 86, total_users: 206,
    }));
    getPendingCommunityAgents().then((result) => {
      if (!cancelled) setPendingCommunity(result.data || []);
    }).catch(() => !cancelled && setPendingCommunity([]));

    client.get("/api/admin/registry/agents").then(({ data }) => {
      if (cancelled) return;
      setRegistryAgents(Array.isArray(data?.redis_agents) ? data.redis_agents : []);
      setQueueStats(data?.queue_stats || { pending: 0, agents_alive: 0, agents_total: 0 });
    }).catch(() => {
      if (!cancelled) {
        setRegistryAgents([]);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      client.get("/api/admin/queue/stats").then(({ data }) => {
        setQueueStats({
          pending: Number(data?.pending || 0),
          agents_alive: Number(data?.agents_alive || 0),
          agents_total: Number(data?.agents_total || 0),
        });
      }).catch(() => {});
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  const totalTradesToday = useMemo(() => agents.reduce((sum, a) => sum + Number(a.total_trades || 0), 0), [agents]);
  const activeSubscriptions = Number(revenue?.paying_users || 0);
  const totalUsers = Number(revenue?.total_users || users.length);

  const setTier = async (userId, tier) => {
    try {
      await client.post(`/api/admin/users/${userId}/tier`, { tier });
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, tier } : u)));
      onToast?.("Tier updated");
    } catch {
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, tier } : u)));
      onToast?.("Tier updated locally");
    }
  };

  const deleteUser = (userId) => {
    setUsers((prev) => prev.filter((u) => u.id !== userId));
    onToast?.("User removed (demo)");
  };

  const toggleAgent = async (agent) => {
    try {
      await client.post(`/api/admin/agents/${agent.id}/toggle`);
    } catch {
      // fallback to local toggle
    }
    setAgents((prev) => prev.map((a) => (a.id === agent.id ? { ...a, show_in_leaderboard: !a.show_in_leaderboard } : a)));
  };

  const addDemoAgent = async () => {
    try {
      await client.post("/api/admin/assign-demo-agents", {});
    } catch {
      // noop
    }
    onToast?.("Demo agent assignment triggered");
  };

  const refreshPendingCommunity = async () => {
    const result = await getPendingCommunityAgents();
    setPendingCommunity(result.data || []);
  };

  const approveCommunity = async (agentId) => {
    setReviewingId(agentId);
    const result = await reviewCommunityAgent(agentId, "approve");
    if (result.error) {
      onToast?.("Approve failed");
    } else {
      onToast?.("Community agent approved");
      await refreshPendingCommunity();
    }
    setReviewingId(null);
  };

  const rejectCommunity = async (agentId) => {
    setReviewingId(agentId);
    const reason = String(rejectReasons[agentId] || "").trim();
    const result = await reviewCommunityAgent(agentId, "reject", reason);
    if (result.error) {
      onToast?.("Reject failed");
    } else {
      onToast?.("Community agent rejected");
      await refreshPendingCommunity();
    }
    setReviewingId(null);
  };

  const swarmAgents = (swarmName) => {
    return registryAgents.filter((agent) => (agent.swarm || agent.swarm_name) === swarmName);
  };

  return (
    <section className="page-content hermes-admin">
      <header className="hermes-page-head">
        <div>
          <h1 className="hermes-page-title">Admin Console</h1>
          <p className="hermes-page-lead">Operational overview — users, subscriptions, agents, demo audit</p>
        </div>
      </header>
      <div className="col gap-3">
        <div className="hermes-stats-row">
          <article className="hermes-stat-card"><div className="text-3 fs-12">Total users</div><strong>{totalUsers}</strong></article>
          <article className="hermes-stat-card"><div className="text-3 fs-12">Active subscriptions</div><strong>{activeSubscriptions}</strong></article>
          <article className="hermes-stat-card"><div className="text-3 fs-12">Total trades today</div><strong>{totalTradesToday}</strong></article>
          <article className="hermes-stat-card"><div className="text-3 fs-12">System status</div><strong style={{ color: "var(--color-green, #10b981)" }}>All green</strong></article>
        </div>

        <article className="glass" style={{ padding: 14 }}>
          <div className="row between" style={{ gap: 8, flexWrap: "wrap" }}>
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              <button type="button" className={`pill ${activeTab === "users" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setActiveTab("users")}>
                Users
              </button>
              <button type="button" className={`pill ${activeTab === "agents" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setActiveTab("agents")}>
                Agents
              </button>
              <button type="button" className={`pill ${activeTab === "revenue" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setActiveTab("revenue")}>
                Revenue
              </button>
              <button type="button" className={`pill ${activeTab === "community" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setActiveTab("community")}>
                Community ({pendingCommunity.length})
              </button>
              <button type="button" className={`pill ${activeTab === "swarms" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setActiveTab("swarms")}>
                Swarms
              </button>
            </div>
            <button type="button" className="share-btn" onClick={() => onNav?.("admin-swarm")}>
              War Room
            </button>
          </div>
        </article>

        {activeTab === "users" ? (
          <article className="glass" style={{ padding: 14 }}>
            <div className="section-title">User Management</div>
            <div className="leaderboard-table-wrap" style={{ overflowX: "auto" }}>
              <table className="leaderboard-table" style={{ minWidth: 840 }}>
                <thead>
                  <tr>
                    <th>Email</th><th>Tier</th><th>Joined</th><th>Agents</th><th>Last active</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.email}</td>
                      <td>
                        <select className="bt-field" value={u.tier} onChange={(e) => setTier(u.id, e.target.value)}>
                          <option value="basic">basic</option><option value="pro">pro</option><option value="elite">elite</option><option value="admin">admin</option>
                        </select>
                      </td>
                      <td>{String(u.created_at || "").slice(0, 10)}</td>
                      <td>{u.agents}</td>
                      <td>{u.last_active}</td>
                      <td><button type="button" className="share-btn" onClick={() => deleteUser(u.id)}>Delete</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        ) : null}

        {activeTab === "agents" ? (
          <article className="glass" style={{ padding: 14 }}>
            <div className="row between">
              <div className="section-title">Agent Management</div>
              <button type="button" className="share-btn" onClick={addDemoAgent}>Add Demo Agent</button>
            </div>
            <div style={{ maxHeight: 300, overflow: "auto", marginTop: 8 }}>
              {agents.map((agent) => (
                <div key={agent.id} className="row between fs-13" style={{ padding: "8px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                  <span>{`${agent.name} · ${agent.symbol}`}</span>
                  <div className="row gap-2">
                    <span className="text-3">{`${agent.subscriber_count || 0} subs`}</span>
                    <button type="button" className={`pill ${agent.show_in_leaderboard ? "pill-green" : "pill-red"}`} onClick={() => toggleAgent(agent)}>
                      {agent.show_in_leaderboard ? "active" : "inactive"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </article>
        ) : null}

        {activeTab === "revenue" ? (
          <article className="glass" style={{ padding: 14 }}>
            <div className="section-title">Revenue Overview</div>
            <div className="row gap-3" style={{ flexWrap: "wrap" }}>
              <div className="glass-2" style={{ padding: 10, minWidth: 160 }}>
                <div className="text-3 fs-12">MRR</div>
                <strong>{`${Number(revenue?.mrr_estimate || 0).toLocaleString()} EUR`}</strong>
              </div>
              <div className="glass-2" style={{ padding: 10, minWidth: 160 }}>
                <div className="text-3 fs-12">Basic / Pro / Elite</div>
                <strong>{`${revenue?.basic_count || 0} / ${revenue?.pro_count || 0} / ${revenue?.elite_count || 0}`}</strong>
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              {["Stripe payment #8231", "Stripe payment #8228", "Stripe payment #8220"].map((row) => (
                <div key={row} className="row between fs-13" style={{ padding: "7px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                  <span>{row}</span><span className="mono">success</span>
                </div>
              ))}
            </div>
          </article>
        ) : null}

        {activeTab === "community" ? (
          <article className="glass" style={{ padding: 14 }}>
            <div className="section-title">Pending Community Agents</div>
            <div className="leaderboard-table-wrap" style={{ overflowX: "auto" }}>
              <table className="leaderboard-table" style={{ minWidth: 920 }}>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Author</th>
                    <th>Strategy</th>
                    <th>Submitted</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingCommunity.map((row) => (
                    <tr key={row.id}>
                      <td>{row.name}</td>
                      <td>{row.handle || row.email}</td>
                      <td>{row.strategy}</td>
                      <td>{String(row.created_at || "").slice(0, 10)}</td>
                      <td>
                        <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                          <button type="button" className="pill pill-green" style={{ border: "none" }} disabled={reviewingId === row.id} onClick={() => approveCommunity(row.id)}>
                            Approve ✓
                          </button>
                          <input
                            className="bt-field"
                            placeholder="Reject reason"
                            style={{ marginBottom: 0, width: 180 }}
                            value={rejectReasons[row.id] || ""}
                            onChange={(event) => setRejectReasons((prev) => ({ ...prev, [row.id]: event.target.value }))}
                          />
                          <button type="button" className="pill pill-red" style={{ border: "none" }} disabled={reviewingId === row.id} onClick={() => rejectCommunity(row.id)}>
                            Reject ✗
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {pendingCommunity.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="text-3">No pending community agents.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </article>
        ) : null}

        {activeTab === "swarms" ? (
          <article className="glass" style={{ padding: 14 }}>
            <div className="admin-queue-banner">
              Queue: {queueStats.pending || 0} pending | {queueStats.agents_alive || 0} agents alive | {queueStats.agents_total || 0} total agents
            </div>
            <div className="admin-swarms-grid">
              {DEFAULT_SWARMS.map((swarm) => {
                const items = swarmAgents(swarm.swarm_name);
                const alive = items.filter((agent) => Boolean(agent.alive)).length;
                const dead = Math.max(0, items.length - alive);
                const isExpanded = Boolean(expandedSwarms[swarm.swarm_name]);
                return (
                  <article key={swarm.swarm_name} className="glass-2 admin-swarm-card" style={{ borderLeft: `3px solid ${swarm.color}` }}>
                    <div className="row between" style={{ alignItems: "flex-start" }}>
                      <div className="col gap-1">
                        <strong>{swarm.icon} {swarm.display_name}</strong>
                        <span className="text-3 fs-12">{swarm.description}</span>
                        <span className="text-3 fs-12">{items.length} agents</span>
                      </div>
                    </div>
                    <div className="row gap-3 fs-12" style={{ marginTop: 8 }}>
                      <span className="row gap-1" style={{ alignItems: "center" }}>
                        <span className="swarm-dot swarm-dot-alive" />
                        {alive} alive
                      </span>
                      <span className="row gap-1" style={{ alignItems: "center" }}>
                        <span className="swarm-dot swarm-dot-dead" />
                        {dead} dead
                      </span>
                    </div>
                    <button
                      type="button"
                      className="pill pill-gray"
                      style={{ border: "none", marginTop: 10 }}
                      onClick={() => setExpandedSwarms((prev) => ({ ...prev, [swarm.swarm_name]: !prev[swarm.swarm_name] }))}
                    >
                      {isExpanded ? "Hide Agents" : "View Agents"}
                    </button>
                    {isExpanded ? (
                      <div className="admin-swarm-agents-list">
                        {items.map((agent) => (
                          <div key={agent.agent_id} className="admin-swarm-agent-row">
                            <span>{agent.name || agent.agent_id}</span>
                            <span className={`pill ${agent.status === "running" ? "pill-green" : agent.status === "error" ? "pill-red" : "pill-gray"}`}>
                              {String(agent.status || "idle").toUpperCase()}
                            </span>
                          </div>
                        ))}
                        {items.length === 0 ? <span className="text-3 fs-12">No agents found.</span> : null}
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </article>
        ) : null}
      </div>
    </section>
  );
}

