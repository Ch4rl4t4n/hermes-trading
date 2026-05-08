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
    if (Array.isArray(data)) return { data: data.map(normalizeAgent), error: null };
    return { data: DEMO_AGENTS, error: null };
  } catch (error) {
    return { data: DEMO_AGENTS, error };
  }
}

export async function pauseAgent(agentIdOrSymbol) {
  const symbol = String(agentIdOrSymbol || "").replaceAll("/", "-");
  try {
    const { data } = await client.post(`/api/agent/${encodeURIComponent(symbol)}/toggle`);
    return { data, error: null };
  } catch (error) {
    return { data: { success: false, symbol: agentIdOrSymbol, paused: null }, error };
  }
}

export async function getAgentTrades(agentIdOrSymbol) {
  const symbol = String(agentIdOrSymbol || "").replaceAll("/", "-");
  try {
    const { data } = await client.get(`/api/trades/${encodeURIComponent(symbol)}`);
    return { data: Array.isArray(data) ? data : [], error: null };
  } catch (error) {
    return { data: [], error };
  }
}

export async function getAgentMemory(agentId) {
  try {
    const { data } = await client.get(`/api/agents/${encodeURIComponent(String(agentId))}/memory`);
    return { data: Array.isArray(data) ? data : [], error: null };
  } catch (error) {
    return { data: [], error };
  }
}

export async function setAgentMemory(agentId, key, value) {
  const payload = { key: String(key || ""), value: String(value || "") };
  try {
    const { data } = await client.post(`/api/agents/${encodeURIComponent(String(agentId))}/memory`, payload);
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function deleteAgentMemory(agentId, key) {
  const cleanKey = encodeURIComponent(String(key || ""));
  try {
    const { data } = await client.delete(`/api/agents/${encodeURIComponent(String(agentId))}/memory/${cleanKey}`);
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
