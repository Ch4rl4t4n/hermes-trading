import client from "./client";
import { activeAlerts, recentTrades as demoRecentTrades } from "../data/demoData";

function mapTrade(row, idx) {
  const pnl = Number(row?.pnl ?? 0);
  const ts = row?.timestamp || row?.ts || "";
  const shortTs = typeof ts === "string" && ts.length > 0 ? ts.replace("T", " ").slice(0, 16) : "now";
  return {
    id: row?.id ?? `trade-${idx}`,
    symbol: row?.symbol || "N/A",
    action: String(row?.action || "hold").toUpperCase(),
    pnl: Number.isFinite(pnl) ? pnl : 0,
    ts: shortTs,
  };
}

function mapAlert(rule, idx) {
  const type = String(rule?.alert_type || "alert");
  const titleMap = {
    pnl_drop: "Risk alert",
    agent_inactive: "Agent inactive",
    price_target: "Price target",
    weekly_summary: "Weekly summary",
  };
  return {
    id: rule?.id ?? `alert-${idx}`,
    title: titleMap[type] || "Alert",
    message: rule?.agent_name
      ? `${rule.agent_name}: ${type.replaceAll("_", " ")} threshold ${rule?.threshold ?? ""}`.trim()
      : `Rule ${type.replaceAll("_", " ")} is ${rule?.is_enabled ? "enabled" : "disabled"}.`,
  };
}

export async function getDashboardData() {
  try {
    const [agentsRes, tradesRes, alertsRes] = await Promise.all([
      client.get("/api/agents"),
      client.get("/api/trades/history?limit=5"),
      client.get("/api/alerts/rules"),
    ]);
    const recentTrades = Array.isArray(tradesRes.data?.trades)
      ? tradesRes.data.trades.map(mapTrade)
      : demoRecentTrades;
    const alerts = Array.isArray(alertsRes.data?.rules) ? alertsRes.data.rules.map(mapAlert) : activeAlerts;
    return { data: {
      agents: agentsRes.data,
      recentTrades,
      alerts,
    }, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
