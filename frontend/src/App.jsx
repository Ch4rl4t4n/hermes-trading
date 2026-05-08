import { Suspense, lazy, useEffect, useState } from "react";
import { fetchAgents, pauseAgent } from "./api/agents";
import { getCurrentUser, logout } from "./api/auth";
import { getDashboardData } from "./api/dashboard";
import Layout from "./components/layout/Layout";
import CoachMessage from "./components/CoachMessage";
import InstallPrompt from "./components/InstallPrompt";
import OfflineBanner from "./components/OfflineBanner";
import Toast from "./components/ui/Toast";
import { activeAlerts, demoAgents, demoUser, recentTrades as demoRecentTrades } from "./data/demoData";
import Dashboard from "./pages/Dashboard";
import Leaderboard from "./pages/Leaderboard";
import Login from "./pages/Login";
import Marketplace from "./pages/Marketplace";
import Developer from "./pages/Developer";
import Settings from "./pages/Settings";
const Builder = lazy(() => import("./pages/Builder"));
const Backtest = lazy(() => import("./pages/Backtest"));
const Admin = lazy(() => import("./pages/Admin"));
const AdminSwarm = lazy(() => import("./pages/AdminSwarm"));

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState("dashboard");
  const [agents, setAgents] = useState(demoAgents);
  const [recentTrades, setRecentTrades] = useState(demoRecentTrades);
  const [alerts, setAlerts] = useState(activeAlerts);
  const [toast, setToast] = useState(null);
  const totalPnl = agents.reduce((sum, a) => sum + Number(a.pnlUsd || 0), 0);

  useEffect(() => {
    getCurrentUser().then((result) => {
      if (result.data) setUser(result.data);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!user) return;
    getDashboardData()
      .then((result) => {
        if (!result.data) throw new Error("dashboard-unavailable");
        fetchAgents().then((rowsResult) => setAgents(rowsResult.data || demoAgents)).catch(() => setAgents(demoAgents));
        if (Array.isArray(result.data.recentTrades)) setRecentTrades(result.data.recentTrades);
        if (Array.isArray(result.data.alerts)) setAlerts(result.data.alerts);
      })
      .catch(() => {
        fetchAgents().then((rowsResult) => setAgents(rowsResult.data || demoAgents)).catch(() => setAgents(demoAgents));
        setRecentTrades(demoRecentTrades);
        setAlerts(activeAlerts);
      });
  }, [user]);

  const onToast = (message) => setToast({ message, t: Date.now() });

  const onToggleAgent = async (agentId) => {
    const response = await pauseAgent(agentId).catch(() => null);
    const pausedFromApi = typeof response?.data?.paused === "boolean" ? response.data.paused : null;
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
  if (page === "marketplace") content = <Marketplace agents={[]} user={user} onToast={onToast} />;
  if (page === "builder") content = <Builder user={user} onToast={onToast} onNav={setPage} />;
  if (page === "leaderboard") content = <Leaderboard onToast={onToast} />;
  if (page === "backtest") content = <Backtest />;
  if (page === "settings") content = <Settings />;
  if (page === "developer") content = <Developer user={user} />;
  if (page === "admin" && user?.isAdmin) content = <Admin onToast={onToast} onNav={setPage} />;
  if (page === "admin-swarm" && user?.isAdmin) content = <AdminSwarm onToast={onToast} onNav={setPage} />;

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
        <Suspense fallback={<div className="glass" style={{ padding: 12, margin: 16 }}>Loading page...</div>}>{content}</Suspense>
      </Layout>
      <OfflineBanner />
      <CoachMessage totalPnl={totalPnl} />
      <InstallPrompt />
      <Toast toast={toast} onClose={() => setToast(null)} />
    </>
  );
}

export default App;
