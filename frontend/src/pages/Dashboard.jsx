import { useEffect, useState } from "react";
import AgentCard from "../components/agents/AgentCard";
import AgentEvolution from "../components/agents/AgentEvolution";
import TradingQuote from "../components/TradingQuote";
import ExportButton from "../components/ExportButton";
import IntelligenceFeed from "../components/IntelligenceFeed";
import AlertBanner from "../components/ui/AlertBanner";
import Confetti from "../components/ui/Confetti";
import OnboardingChecklist from "../components/ui/OnboardingChecklist";
import ShareModal from "../components/ui/ShareModal";
import { activeAlerts, onboardingSteps, recentTrades as demoRecentTrades } from "../data/demoData";
import { useBreakpoint } from "../hooks/useBreakpoint";
import { calculateXP, getLevel, getStoredEvolution } from "../utils/agentXP";

export default function Dashboard({ agents, onToast, onToggleAgent, recentTrades = demoRecentTrades, alerts = activeAlerts }) {
  const { isMobile, isTablet, isDesktop } = useBreakpoint();
  const [tradesOpen, setTradesOpen] = useState(!isMobile);
  const [evolutionAgent, setEvolutionAgent] = useState(null);
  const [evolutionRevision, setEvolutionRevision] = useState(0);
  const [shareAgent, setShareAgent] = useState(null);
  const [confettiTick, setConfettiTick] = useState(0);

  const personalityPills = {
    zen_monk: "🧘 Zen",
    aggressive: "🚀 Meme",
    wall_street: "📊 Pro",
    degen: "💀 Degen",
  };

  const getAgentEvolutionView = (agent) => {
    const xp = calculateXP(agent);
    const level = getLevel(xp).level;
    const evo = getStoredEvolution(agent, level);
    return {
      skin: evo.skin || "basic",
      personality: personalityPills[evo.personality] || "🧘 Zen",
    };
  };

  useEffect(() => {
    if (isMobile) return;
    const timer = window.setTimeout(() => setTradesOpen(true), 0);
    return () => window.clearTimeout(timer);
  }, [isMobile]);
  const totalPnl = agents.reduce((sum, a) => sum + a.pnlUsd, 0);
  const equity = 10000 + totalPnl;
  const dayChange = totalPnl * 0.16;
  const liveCount = agents.filter((a) => a.status === "live").length;
  const winRateAvg = Math.round(agents.reduce((sum, a) => sum + a.winRate, 0) / agents.length);
  const totalTrades = agents.reduce((sum, a) => sum + a.trades, 0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (totalPnl > 0 && !window.sessionStorage.getItem("hermes-confetti-dashboard-positive")) {
      window.sessionStorage.setItem("hermes-confetti-dashboard-positive", "1");
      const timer = window.setTimeout(() => setConfettiTick((v) => v + 1), 0);
      return () => window.clearTimeout(timer);
    }
  }, [totalPnl]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let shouldTrigger = false;
    for (const agent of agents) {
      const id = agent.id || agent.symbol;
      if (!id) continue;
      const pnl = Number(agent.pnlUsd ?? agent.pnl ?? 0);
      const key = `hermes-confetti-agent-positive:${id}`;
      if (pnl > 0 && !window.sessionStorage.getItem(key)) {
        window.sessionStorage.setItem(key, "1");
        shouldTrigger = true;
      }
    }
    if (!shouldTrigger) return;
    const timer = window.setTimeout(() => setConfettiTick((v) => v + 1), 0);
    return () => window.clearTimeout(timer);
  }, [agents]);

  const statsCards = (
    <div className={isMobile ? "dashboard-stats-scroll" : "dashboard-stats"} style={{ marginTop: 12 }}>
      <article className="glass stat-card" style={{ padding: "20px" }}>
        <div className="mp-meta">Active agents</div>
        <strong className="mono" style={{ fontSize: 24 }}>{liveCount}</strong>
      </article>
      <article className="glass stat-card" style={{ padding: "20px" }}>
        <div className="mp-meta">Average win rate</div>
        <strong className="mono" style={{ fontSize: 24 }}>{winRateAvg}%</strong>
      </article>
      <article className="glass stat-card" style={{ padding: "20px" }}>
        <div className="mp-meta">Total trades</div>
        <strong className="mono" style={{ fontSize: 24 }}>{totalTrades}</strong>
      </article>
    </div>
  );

  const tradesBlock = (
    <article className="glass">
      <div className="row between" style={{ alignItems: "center", padding: "0 12px" }}>
        <div className="section-title" style={{ margin: "14px 0 10px" }}>Recent trades</div>
        <ExportButton />
      </div>
      {recentTrades.map((trade) => (
        <div key={trade.id} className="row between fs-13" style={{ padding: "8px 12px", borderBottom: "1px solid var(--border-subtle)" }}>
          <span>
            {trade.symbol} · {trade.action}
          </span>
          <span className="mono" style={{ color: trade.pnl >= 0 ? "oklch(0.72 0.18 155)" : "oklch(0.65 0.2 25)" }}>
            {trade.pnl >= 0 ? "+" : ""}
            {trade.pnl.toFixed(2)}
          </span>
          <span className="text-3 fs-12">{trade.ts}</span>
        </div>
      ))}
    </article>
  );

  const exportDataBlock = (
    <article className="glass export-data-card">
      <div className="section-title" style={{ marginTop: 0 }}>Export Data</div>
      <div className="col gap-2">
        <button
          type="button"
          className="btn btn-ghost"
          style={{ width: "100%" }}
          onClick={() => window.open("/api/export/trades.csv", "_blank", "noopener,noreferrer")}
        >
          Download Trade History (CSV)
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ width: "100%" }}
          onClick={() => window.open("/api/export/report.pdf", "_blank", "noopener,noreferrer")}
        >
          Download Performance Report (PDF)
        </button>
      </div>
    </article>
  );

  return (
    <section className="page-content">
      <article className="agent-card glass" style={{ boxShadow: totalPnl >= 0 ? "0 0 28px oklch(0.72 0.18 155 / 0.2)" : "none" }}>
        <div className="text-3" style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase" }}>
          Total Paper P&L
        </div>
        <div className="mono" style={{ fontSize: 40, fontWeight: 800, color: totalPnl >= 0 ? "oklch(0.72 0.18 155)" : "oklch(0.65 0.2 25)" }}>
          {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}
        </div>
        <div className="text-2 fs-13">
          Portfolio equity <span className="mono">${equity.toFixed(2)}</span>
        </div>
        <span className={`pill ${dayChange >= 0 ? "pill-green" : "pill-red"}`}>
          Day {dayChange >= 0 ? "+" : ""}${dayChange.toFixed(2)}
        </span>
      </article>
      <TradingQuote isEmpty={!agents.length} />
      {statsCards}

      {isDesktop ? (
        <div className="dashboard-desktop">
          <div className="dashboard-left">
            <OnboardingChecklist steps={onboardingSteps} />
            <div className="agents-grid desktop">
              {agents.map((agent) => (
                (() => {
                  const evo = getAgentEvolutionView(agent);
                  return (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onToggle={() => onToggleAgent(agent.symbol || agent.id)}
                  onDetails={() => onToast(`Opened ${agent.name}`)}
                  onOpenEvolution={() => setEvolutionAgent(agent)}
                  onShare={() => setShareAgent(agent)}
                  personalityTag={evo.personality}
                  evolutionSkin={evo.skin}
                />
                  );
                })()
              ))}
            </div>
          </div>
          <aside className="dashboard-right">
            {tradesBlock}
            <AlertBanner alert={alerts[0]} />
            <IntelligenceFeed />
            {exportDataBlock}
          </aside>
        </div>
      ) : (
        <>
          <div className={`agents-grid ${isTablet ? "tablet" : "mobile"}`}>
            {agents.map((agent) => (
              (() => {
                const evo = getAgentEvolutionView(agent);
                return (
              <AgentCard
                key={agent.id}
                agent={agent}
                onToggle={() => onToggleAgent(agent.symbol || agent.id)}
                onDetails={() => onToast(`Opened ${agent.name}`)}
                onOpenEvolution={() => setEvolutionAgent(agent)}
                onShare={() => setShareAgent(agent)}
                personalityTag={evo.personality}
                evolutionSkin={evo.skin}
              />
                );
              })()
            ))}
          </div>
          {isMobile ? (
            <article className="glass col gap-2" style={{ padding: 12 }}>
              <button
                className="row between"
                style={{ border: "none", background: "transparent", color: "var(--color-text)", padding: 0 }}
                onClick={() => setTradesOpen((v) => !v)}
              >
                <h3>Recent Trades</h3>
                <span>{tradesOpen ? "−" : "+"}</span>
              </button>
              {tradesOpen && tradesBlock}
            </article>
          ) : (
            tradesBlock
          )}
          <AlertBanner alert={alerts[0]} />
          <IntelligenceFeed />
          {exportDataBlock}
        </>
      )}
      <AgentEvolution
        agent={evolutionAgent}
        open={Boolean(evolutionAgent)}
        onClose={() => setEvolutionAgent(null)}
        onChange={() => setEvolutionRevision((v) => v + 1)}
        key={`${evolutionAgent?.id || "none"}-${evolutionRevision}`}
      />
      <ShareModal agent={shareAgent} onClose={() => setShareAgent(null)} />
      <Confetti trigger={confettiTick} />
    </section>
  );
}

