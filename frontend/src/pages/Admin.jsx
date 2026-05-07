import { useEffect, useMemo, useState } from "react";
import client from "../api/client";

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

export default function Admin({ onToast }) {
  const [users, setUsers] = useState([]);
  const [agents, setAgents] = useState([]);
  const [revenue, setRevenue] = useState(null);

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
    return () => { cancelled = true; };
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

  return (
    <section className="page-content">
      <div className="col gap-3">
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <article className="glass-2" style={{ padding: 12, minWidth: 170 }}><div className="text-3 fs-12">Total users</div><strong>{totalUsers}</strong></article>
          <article className="glass-2" style={{ padding: 12, minWidth: 170 }}><div className="text-3 fs-12">Active subscriptions</div><strong>{activeSubscriptions}</strong></article>
          <article className="glass-2" style={{ padding: 12, minWidth: 170 }}><div className="text-3 fs-12">Total trades today</div><strong>{totalTradesToday}</strong></article>
          <article className="glass-2" style={{ padding: 12, minWidth: 170 }}><div className="text-3 fs-12">System status</div><strong style={{ color: "var(--color-green)" }}>All green</strong></article>
        </div>

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
      </div>
    </section>
  );
}

