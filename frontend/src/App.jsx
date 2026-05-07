import { useEffect, useState } from "react";
import { fetchAgents, pauseAgent } from "./api/agents";
import { getCurrentUser, logout } from "./api/auth";
import { getDashboardData } from "./api/dashboard";
import Layout from "./components/layout/Layout";
import Toast from "./components/ui/Toast";
import { activeAlerts, demoAgents, demoUser, marketplaceAgents, recentTrades as demoRecentTrades } from "./data/demoData";
import Backtest from "./pages/Backtest";
import Builder from "./pages/Builder";
import Dashboard from "./pages/Dashboard";
import Leaderboard from "./pages/Leaderboard";
import Login from "./pages/Login";
import Marketplace from "./pages/Marketplace";
import Admin from "./pages/Admin";

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState("dashboard");
  const [agents, setAgents] = useState(demoAgents);
  const [recentTrades, setRecentTrades] = useState(demoRecentTrades);
  const [alerts, setAlerts] = useState(activeAlerts);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    getCurrentUser().then((u) => {
      if (u) setUser(u);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!user) return;
    getDashboardData()
      .then((payload) => {
        if (!payload) throw new Error("dashboard-unavailable");
        fetchAgents().then((rows) => setAgents(rows)).catch(() => setAgents(demoAgents));
        if (Array.isArray(payload.recentTrades)) setRecentTrades(payload.recentTrades);
        if (Array.isArray(payload.alerts)) setAlerts(payload.alerts);
      })
      .catch(() => {
        fetchAgents().then((rows) => setAgents(rows)).catch(() => setAgents(demoAgents));
        setRecentTrades(demoRecentTrades);
        setAlerts(activeAlerts);
      });
  }, [user]);

  const onToast = (message) => setToast({ message, t: Date.now() });

  const onToggleAgent = async (agentId) => {
    const response = await pauseAgent(agentId).catch(() => null);
    const pausedFromApi = typeof response?.paused === "boolean" ? response.paused : null;
    setAgents((prev) =>
      prev.map((agent) => {
        const isTarget = agent.id === agentId || agent.symbol === agentId;
        if (!isTarget) return agent;
        const status = pausedFromApi === null ? (agent.status === "live" ? "paused" : "live") : pausedFromApi ? "paused" : "live";
        return { ...agent, status };
      }),
    );
    onToast("Agent status updated");
  };

  let content = (
    <Dashboard
      agents={agents}
      onToast={onToast}
      onToggleAgent={onToggleAgent}
      alerts={alerts}
      recentTrades={recentTrades}
    />
  );
  if (page === "marketplace") content = <Marketplace agents={marketplaceAgents} onToast={onToast} />;
  if (page === "builder") content = <Builder user={user} onToast={onToast} onNav={setPage} />;
  if (page === "leaderboard") content = <Leaderboard onToast={onToast} />;
  if (page === "backtest") content = <Backtest />;
  if (page === "admin" && user?.isAdmin) content = <Admin />;

  if (loading) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <div className="glass row gap-2" style={{ padding: "10px 14px" }}>
          <span className="spinner active" />
          <span>Loading session...</span>
        </div>
      </main>
    );
  }

  if (!user) return <Login onLogin={(u) => setUser(u || demoUser)} />;

  return (
    <>
      <Layout
        page={page}
        setPage={setPage}
        user={user}
        onLogout={async () => {
          await logout();
          setUser(null);
        }}
      >
        {content}
      </Layout>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </>
  );
}

export default App;
