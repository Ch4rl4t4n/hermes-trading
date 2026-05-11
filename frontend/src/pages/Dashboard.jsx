import { useEffect, useMemo, useState } from "react";
import AgentEvolution from "../components/agents/AgentEvolution";
import AgentDetailModal from "../components/agents/AgentDetailModal";
import Heatmap from "../components/dashboard/Heatmap";
import AlertBanner from "../components/ui/AlertBanner";
import Confetti from "../components/ui/Confetti";
import ShareModal from "../components/ui/ShareModal";
import TrendingBanner from "../components/dashboard/TrendingBanner";
import IntelligenceBubbles from "../components/dashboard/IntelligenceBubbles";
import CategorySection from "../components/dashboard/CategorySection";
import CommunityFeed from "../components/dashboard/CommunityFeed";
import client from "../api/client";
import { activeAlerts } from "../data/demoData";
import { useBreakpoint } from "../hooks/useBreakpoint";
import { calculateXP, getLevel, getStoredEvolution } from "../utils/agentXP";
import { groupAgentsByCategory, tierSlotLimits } from "../utils/agentCategory";
import { STORAGE_KEYS } from "../utils/storageKeys";
import { getAgentTrades } from "../api/agents";

const personalityPills = {
  zen_monk: "🧘 Zen",
  aggressive: "🚀 Meme",
  wall_street: "📊 Pro",
  degen: "💀 Degen",
};

function getEvolutionView(agent) {
  const xp = calculateXP(agent);
  const level = getLevel(xp).level;
  const evo = getStoredEvolution(agent, level);
  return {
    skin: evo.skin || "basic",
    personality: personalityPills[evo.personality] || "🧘 Zen",
  };
}

function loadOrder() {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEYS.DASHBOARD_ORDER) || "{}") || {};
  } catch {
    return {};
  }
}

function saveOrder(order) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEYS.DASHBOARD_ORDER, JSON.stringify(order || {}));
  } catch {
    /* noop */
  }
}

function applyOrder(list, ids) {
  if (!Array.isArray(ids) || !ids.length) return list;
  const byId = new Map(list.map((a) => [a.id || a.symbol, a]));
  const out = [];
  for (const id of ids) {
    const item = byId.get(id);
    if (item) {
      out.push(item);
      byId.delete(id);
    }
  }
  for (const [, item] of byId) out.push(item);
  return out;
}

function downloadCsv(filename, rows) {
  if (!rows || !rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(","),
    ...rows.map((r) =>
      headers
        .map((h) => {
          const v = r[h];
          if (v === null || v === undefined) return "";
          const s = String(v).replaceAll('"', '""');
          return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s}"` : s;
        })
        .join(","),
    ),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function Dashboard({
  agents = [],
  onToast,
  onToggleAgent,
  alerts = activeAlerts,
  onNav,
  onAgentsChanged,
  user,
}) {
  const { isDesktop } = useBreakpoint();
  const [evolutionAgent, setEvolutionAgent] = useState(null);
  const [evolutionRevision, setEvolutionRevision] = useState(0);
  const [shareAgent, setShareAgent] = useState(null);
  const [detailAgent, setDetailAgent] = useState(null);
  const [confettiTick, setConfettiTick] = useState(0);
  const [orderMap, setOrderMap] = useState(() => loadOrder());

  const totalPnl = agents.reduce((sum, a) => sum + Number(a.pnlUsd || 0), 0);

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

  const grouped = useMemo(() => {
    const raw = groupAgentsByCategory(agents);
    return {
      crypto: applyOrder(raw.crypto, orderMap.crypto),
      stocks: applyOrder(raw.stocks, orderMap.stocks),
      commodity: applyOrder(raw.commodity, orderMap.commodity),
    };
  }, [agents, orderMap]);

  const limits = tierSlotLimits(user?.tier);
  const counts = {
    crypto: { used: grouped.crypto.length, max: limits.crypto === 99 ? Math.max(grouped.crypto.length, 4) : limits.crypto },
    stocks: { used: grouped.stocks.length, max: limits.stocks === 99 ? Math.max(grouped.stocks.length, 4) : limits.stocks },
    commodity: { used: grouped.commodity.length, max: limits.commodity === 99 ? Math.max(grouped.commodity.length, 2) : limits.commodity },
  };

  const goMarketplace = () => onNav?.("marketplace");

  const handleReorder = (cat) => (ids) => {
    const next = { ...orderMap, [cat]: ids };
    setOrderMap(next);
    saveOrder(next);
    onToast?.("Order saved");
  };

  const handleExport = async (agent) => {
    onToast?.(`Exporting ${agent.symbol}…`);
    const { data } = await getAgentTrades(agent.symbol || agent.id);
    const rows = (Array.isArray(data) ? data : []).map((t) => ({
      timestamp: t.timestamp || t.ts || "",
      action: (t.action || "").toUpperCase(),
      symbol: t.symbol || agent.symbol,
      price: t.price ?? "",
      quantity: t.quantity ?? "",
      pnl: t.pnl ?? t.pnl_usd ?? "",
    }));
    downloadCsv(
      `hermes-${(agent.symbol || agent.id || "agent").toLowerCase()}-trades.csv`,
      rows.length ? rows : [{ note: "no trades yet" }],
    );
  };

  const handleRemove = async (agent) => {
    if (typeof window !== "undefined") {
      const ok = window.confirm(
        `Remove ${agent.symbol || agent.name} from your dashboard? You can re-subscribe from Marketplace.`,
      );
      if (!ok) return;
    }
    try {
      await client.post("/api/marketplace/unsubscribe", { agent_id: agent.id });
      onToast?.(`Removed ${agent.symbol || agent.name}`);
      onAgentsChanged?.();
    } catch (err) {
      onToast?.("Could not remove agent — please try again.");
    }
  };

  return (
    <section className="page-content hermes-dashboard">
      <TrendingBanner
        onSelect={() => onNav?.("marketplace")}
        onAdd={() => onNav?.("marketplace")}
      />

      <IntelligenceBubbles />

      <div className={isDesktop ? "hermes-dashboard-grid" : "hermes-dashboard-grid hermes-dashboard-grid--stack"}>
        <div className="hermes-dashboard-main">
          <CategorySection
            title="Crypto"
            used={counts.crypto.used}
            max={counts.crypto.max}
            agents={grouped.crypto}
            emptyLabel="add crypto"
            onToggleAgent={onToggleAgent}
            onShare={(a) => setShareAgent(a)}
            onDetails={(a) => setDetailAgent(a)}
            onExport={(a) => handleExport(a)}
            onRemove={(a) => handleRemove(a)}
            onReorder={handleReorder("crypto")}
            onAddAgent={goMarketplace}
            getEvolutionView={getEvolutionView}
          />
          <CategorySection
            title="Stocks"
            used={counts.stocks.used}
            max={counts.stocks.max}
            agents={grouped.stocks}
            emptyLabel="add stock"
            onToggleAgent={onToggleAgent}
            onShare={(a) => setShareAgent(a)}
            onDetails={(a) => setDetailAgent(a)}
            onExport={(a) => handleExport(a)}
            onRemove={(a) => handleRemove(a)}
            onReorder={handleReorder("stocks")}
            onAddAgent={goMarketplace}
            getEvolutionView={getEvolutionView}
          />
          <CategorySection
            title="Commodities"
            used={counts.commodity.used}
            max={counts.commodity.max}
            agents={grouped.commodity}
            emptyLabel="add commodity"
            onToggleAgent={onToggleAgent}
            onShare={(a) => setShareAgent(a)}
            onDetails={(a) => setDetailAgent(a)}
            onExport={(a) => handleExport(a)}
            onRemove={(a) => handleRemove(a)}
            onReorder={handleReorder("commodity")}
            onAddAgent={goMarketplace}
            getEvolutionView={getEvolutionView}
          />
        </div>

        <CommunityFeed user={user} onToast={onToast} />
      </div>

      <section className="hermes-dashboard-secondary">
        <AlertBanner alert={alerts[0]} />
        <Heatmap />
      </section>

      <AgentEvolution
        agent={evolutionAgent}
        open={Boolean(evolutionAgent)}
        onClose={() => setEvolutionAgent(null)}
        onChange={() => setEvolutionRevision((v) => v + 1)}
        key={`${evolutionAgent?.id || "none"}-${evolutionRevision}`}
      />
      <AgentDetailModal
        agent={detailAgent}
        open={Boolean(detailAgent)}
        onClose={() => setDetailAgent(null)}
        onToggle={(a) => {
          onToggleAgent?.(a.symbol || a.id);
        }}
        onShare={(a) => setShareAgent(a)}
        onRemove={(a) => handleRemove(a)}
      />
      <ShareModal agent={shareAgent} onClose={() => setShareAgent(null)} />
      <Confetti trigger={confettiTick} />
    </section>
  );
}
