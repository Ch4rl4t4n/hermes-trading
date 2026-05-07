import client from "./client";
import { DEMO_AGENTS } from "../data/demoData";

function pickNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const num = Number(value);
    if (Number.isFinite(num)) return num;
  }
  return 0;
}

export function normalizeAgent(raw) {
  const pnl = pickNumber(raw?.pnl, raw?.total_pnl, raw?.pnl_usd, raw?.realized_pnl_today_usd);
  const confidence = pickNumber(raw?.confidence, 0.5);
  const winRate = pickNumber(raw?.win_rate, raw?.winRate, raw?.win_rate_pct, confidence * 100);
  const trades = pickNumber(raw?.trade_count, raw?.trades, raw?.trades_today);
  const status = (raw?.status || "").toLowerCase();
  const spark = Array.isArray(raw?.spark)
    ? raw.spark
    : Array.isArray(raw?.sparks)
      ? raw.sparks
      : Array.isArray(raw?.pnl_history)
        ? raw.pnl_history
        : [10, 11, 12, 11, 13, 14, 13, 15, 16, 17];

  const normalizedStatus = raw?.paused || status === "paused"
    ? "paused"
    : (status === "active" || status === "live" || raw?.is_active ? "live" : "paused");

  return {
    id: raw?.id || raw?.symbol,
    name: raw?.name || raw?.agent_name || raw?.symbol || "Agent",
    symbol: raw?.symbol,
    category: raw?.category || raw?.asset_type || "crypto",
    pnl,
    pnlUsd: pnl,
    pnlPct: 0,
    winRate: Math.max(0, Math.min(100, Math.round(winRate))),
    status: normalizedStatus,
    strategy: raw?.strategy || raw?.trading_mode || "Momentum",
    risk: raw?.risk || raw?.risk_level || "medium",
    trades,
    trade_count: trades,
    spark,
    sparks: spark,
    badges: [],
  };
}

export async function fetchAgents() {
  return getUserAgents();
}

export async function getUserAgents() {
  try {
    const res = await client.get("/api/agents");
    const data = Array.isArray(res.data) ? res.data : res.data?.agents || [];
    if (Array.isArray(data)) return data.map(normalizeAgent);
    return DEMO_AGENTS;
  } catch {
    return DEMO_AGENTS;
  }
}

export async function pauseAgent(agentIdOrSymbol) {
  const symbol = String(agentIdOrSymbol || "").replaceAll("/", "-");
  try {
    const { data } = await client.post(`/api/agent/${encodeURIComponent(symbol)}/toggle`);
    return data;
  } catch {
    return { success: false, symbol: agentIdOrSymbol, paused: null };
  }
}

export async function getAgentTrades(agentIdOrSymbol) {
  const symbol = String(agentIdOrSymbol || "").replaceAll("/", "-");
  try {
    const { data } = await client.get(`/api/trades/${encodeURIComponent(symbol)}`);
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}
