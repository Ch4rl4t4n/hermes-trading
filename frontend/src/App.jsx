import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { fetchAgents, pauseAgent } from "./api/agents";
import { getCurrentUser, logout } from "./api/auth";
import { ensureCsrfToken } from "./api/client";
import { getDashboardData } from "./api/dashboard";
import Layout from "./components/layout/Layout";
import CoachMessage from "./components/CoachMessage";
import InstallPrompt from "./components/InstallPrompt";
import OfflineBanner from "./components/OfflineBanner";
import OnboardingModal from "./components/OnboardingModal";
import OnboardingProgressModal from "./components/OnboardingProgressModal";
import Toast from "./components/ui/Toast";
import { activeAlerts, demoAgents, demoUser, recentTrades as demoRecentTrades } from "./data/demoData";
import { normalizeUrlPath, pageToPath, pathToPage, resolvePageForUser } from "./utils/appRoutes";
import { fetchAndApplyActiveDesignSchema } from "./utils/designSchema";
import { deriveOnboardingSteps, onboardingPercent } from "./utils/onboarding";
import { STORAGE_KEYS } from "./utils/storageKeys";
import Dashboard from "./pages/Dashboard";
import Leaderboard from "./pages/Leaderboard";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Marketplace from "./pages/Marketplace";
import Developer from "./pages/Developer";
import Settings from "./pages/Settings";
const Builder = lazy(() => import("./pages/Builder"));
const Backtest = lazy(() => import("./pages/Backtest"));
const Admin = lazy(() => import("./pages/Admin"));
const AdminSwarm = lazy(() => import("./pages/AdminSwarm"));
const OwnerDesign = lazy(() => import("./pages/OwnerDesign"));
const Tiers = lazy(() => import("./pages/Tiers"));
const Discover = lazy(() => import("./pages/Discover"));
const Invite = lazy(() => import("./pages/Invite"));
const Rewards = lazy(() => import("./pages/Rewards"));

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [guestRoute, setGuestRoute] = useState(() =>
    typeof window !== "undefined" && normalizeUrlPath(window.location.pathname) === "/register"
      ? "register"
      : "login",
  );
  const [page, setPage] = useState(() =>
    typeof window !== "undefined" ? pathToPage(window.location.pathname) : "dashboard",
  );
  const [agents, setAgents] = useState(demoAgents);
  const [recentTrades, setRecentTrades] = useState(demoRecentTrades);
  const [alerts, setAlerts] = useState(activeAlerts);
  const [toast, setToast] = useState(null);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [progressModalOpen, setProgressModalOpen] = useState(false);
  const totalPnl = agents.reduce((sum, a) => sum + Number(a.pnlUsd || 0), 0);

  const onboardingSteps = deriveOnboardingSteps(user, agents, { demoAgentsRef: demoAgents });
  const onboardingPct = onboardingPercent(onboardingSteps);

  useEffect(() => {
    fetchAndApplyActiveDesignSchema();
  }, []);

  /** Záložky / starý klient na ``/login/google`` za SPA fallbackom — presmeruj na API vstup OAuth. */
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (normalizeUrlPath(window.location.pathname) !== "/login/google") return;
    window.location.replace("/api/auth/google/start");
  }, []);

  useEffect(() => {
    // Mintne fresh CSRF token zo session pre prípad, že po reštarte servera má
    // localStorage zastaraný token a my by sme zlyhávali na 403 csrf_required.
    ensureCsrfToken().finally(() => {
      getCurrentUser().then((result) => {
        if (result.data) setUser(result.data);
        setLoading(false);
      });
    });
  }, []);

  const reloadAgents = useCallback(() => {
    fetchAgents()
      .then((rowsResult) => setAgents(rowsResult.data || demoAgents))
      .catch(() => setAgents(demoAgents));
  }, []);

  useEffect(() => {
    if (!user) return;
    getDashboardData()
      .then((result) => {
        if (!result.data) throw new Error("dashboard-unavailable");
        reloadAgents();
        if (Array.isArray(result.data.recentTrades)) setRecentTrades(result.data.recentTrades);
        if (Array.isArray(result.data.alerts)) setAlerts(result.data.alerts);
      })
      .catch(() => {
        reloadAgents();
        setRecentTrades(demoRecentTrades);
        setAlerts(activeAlerts);
      });
  }, [user, reloadAgents]);

  const navigate = useCallback(
    (nextRaw) => {
      const next = resolvePageForUser(nextRaw, user);
      setPage(next);
      if (typeof window === "undefined") return;
      const destPath = pageToPath(next);
      if (normalizeUrlPath(window.location.pathname) !== normalizeUrlPath(destPath)) {
        window.history.pushState({ hermesPage: next }, "", destPath);
      }
    },
    [user],
  );

  const goRegister = useCallback(() => {
    window.history.pushState({ hermesGuest: "register" }, "", "/register");
    setGuestRoute("register");
  }, []);

  const goLogin = useCallback(() => {
    window.history.pushState({ hermesGuest: "login" }, "", "/");
    setGuestRoute("login");
  }, []);

  useEffect(() => {
    if (user) return undefined;
    const syncGuestRoute = () => {
      setGuestRoute(normalizeUrlPath(window.location.pathname) === "/register" ? "register" : "login");
    };
    window.addEventListener("popstate", syncGuestRoute);
    return () => window.removeEventListener("popstate", syncGuestRoute);
  }, [user]);

  useEffect(() => {
    if (!user || loading) return;
    const path = window.location.pathname;
    const next = resolvePageForUser(pathToPage(path), user);
    setPage(next);
    const canon = pageToPath(next);
    if (normalizeUrlPath(path) !== normalizeUrlPath(canon)) {
      window.history.replaceState({ hermesPage: next }, "", canon);
    }
  }, [user, loading]);

  useEffect(() => {
    if (!user) return undefined;
    const onPopState = () => {
      setPage(resolvePageForUser(pathToPage(window.location.pathname), user));
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [user]);

  // Show 3-step welcome carousel once for fresh accounts (no agents yet, flag not set).
  useEffect(() => {
    if (!user || loading) return;
    let seen = false;
    try {
      seen = window.localStorage.getItem(STORAGE_KEYS.ONBOARDING_SEEN) === "1";
    } catch {
      /* ignore */
    }
    if (seen) return;
    const tier = String(user?.tier || "basic").toLowerCase();
    const hasAgents = Array.isArray(agents) && agents.length > 0 && agents !== demoAgents;
    if (tier === "basic" && !hasAgents) {
      const t = setTimeout(() => setOnboardingOpen(true), 600);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [user, loading, agents]);

  // Auto-pop the progress checklist popup if onboarding is incomplete.
  // Cooldown: 24h between auto-pops; never pops while welcome carousel is on screen
  // or when progress is 100%.
  useEffect(() => {
    if (!user || loading) return undefined;
    if (onboardingOpen) return undefined;
    if (progressModalOpen) return undefined;
    if (onboardingPct >= 100) return undefined;
    let dismissedAt = 0;
    try {
      dismissedAt = parseInt(
        window.localStorage.getItem(STORAGE_KEYS.ONBOARDING_PROGRESS_DISMISSED) || "0",
        10,
      );
    } catch {
      /* ignore */
    }
    const COOLDOWN_MS = 24 * 60 * 60 * 1000;
    if (Number.isFinite(dismissedAt) && Date.now() - dismissedAt < COOLDOWN_MS) {
      return undefined;
    }
    const t = setTimeout(() => setProgressModalOpen(true), 1400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loading, onboardingPct, onboardingOpen]);

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
      onNav={navigate}
      user={user}
      onAgentsChanged={reloadAgents}
    />
  );
  if (page === "marketplace") content = <Marketplace agents={[]} user={user} onToast={onToast} />;
  if (page === "discover") content = <Discover user={user} onToast={onToast} onNav={navigate} />;
  if (page === "builder") content = <Builder user={user} onToast={onToast} onNav={navigate} />;
  if (page === "leaderboard") content = <Leaderboard onToast={onToast} />;
  if (page === "backtest") content = <Backtest />;
  if (page === "settings") content = <Settings user={user} onToast={onToast} onNav={navigate} />;
  if (page === "developer") content = <Developer user={user} />;
  if (page === "pricing") content = <Tiers user={user} onToast={onToast} onNav={navigate} />;
  if (page === "invite") content = <Invite onToast={onToast} onNav={navigate} />;
  if (page === "rewards")
    content = (
      <Rewards
        user={user}
        onToast={onToast}
        onNav={navigate}
        onboardingSteps={onboardingSteps}
        onOpenOnboarding={() => setProgressModalOpen(true)}
      />
    );
  if (page === "admin" && user?.isAdmin) content = <Admin onToast={onToast} onNav={navigate} />;
  if (page === "admin-swarm" && user?.isAdmin) content = <AdminSwarm onToast={onToast} onNav={navigate} />;
  if (page === "owner-design" && user?.isOwner) content = <OwnerDesign onToast={onToast} />;

  if (loading) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <div className="glass row gap-2" style={{ padding: "10px 14px" }}>
          <span className="spinner active" />
          <span>Loading session…</span>
        </div>
      </main>
    );
  }

  if (!user) {
    if (guestRoute === "register") {
      return (
        <Register
          onRegistered={(u) => {
            if (normalizeUrlPath(window.location.pathname) === "/register") {
              window.history.replaceState({}, "", "/");
            }
            setUser(u);
          }}
          onGoLogin={goLogin}
        />
      );
    }
    return <Login onLogin={(u) => setUser(u || demoUser)} onGoRegister={goRegister} />;
  }

  return (
    <>
      <Layout
        page={page}
        setPage={navigate}
        user={user}
        totalPnl={totalPnl}
        onLogout={async () => {
          await logout();
          setUser(null);
        }}
      >
        <Suspense fallback={<div className="glass" style={{ padding: 12, margin: 16 }}>Loading page…</div>}>{content}</Suspense>
      </Layout>
      <OfflineBanner />
      <CoachMessage totalPnl={totalPnl} onReviewTrades={() => navigate("dashboard")} />
      <InstallPrompt />
      <OnboardingModal
        open={onboardingOpen}
        onClose={() => setOnboardingOpen(false)}
        onComplete={() => navigate("marketplace")}
      />
      <OnboardingProgressModal
        open={progressModalOpen}
        steps={onboardingSteps}
        onClose={() => setProgressModalOpen(false)}
        onNavigate={(p) => {
          setProgressModalOpen(false);
          navigate(p);
        }}
      />
      <Toast toast={toast} onClose={() => setToast(null)} />
    </>
  );
}

export default App;
