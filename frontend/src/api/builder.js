import client from "./client";

export async function createAgentFromConversation(messages) {
  try {
    const res = await client.post("/api/ai/builder", { messages });
    return res.data;
  } catch {
    return parseAgentLocally(messages);
  }
}

export async function deployAgent(agentConfig) {
  try {
    const res = await client.post("/api/agents/create", agentConfig);
    return res.data;
  } catch {
    const symbolRaw = String(agentConfig?.symbol || "BTC/USD").toUpperCase();
    const symbol = symbolRaw.replace("/USD", "").replace("-USD", "").replace("/", "");
    const strategyLower = String(agentConfig?.strategy || "Momentum").toLowerCase();
    const strategyType = strategyLower.includes("scalp")
      ? "scalping"
      : strategyLower.includes("swing")
        ? "trend_following"
        : strategyLower.includes("grid")
          ? "grid"
          : strategyLower.includes("dca")
            ? "dca"
            : "momentum";
    const fallback = await client.post("/api/agent-builder/create", {
      name: agentConfig?.name || "AI Agent",
      symbol,
      strategy_type: strategyType,
      config_json: {
        risk: agentConfig?.risk || "medium",
        indicators: Array.isArray(agentConfig?.indicators) ? agentConfig.indicators : ["RSI", "EMA"],
      },
    });
    return fallback.data;
  }
}

function parseAgentLocally(messages) {
  const lastUserMsg = messages.filter((m) => m.role === "user").pop()?.content || "";
  const lower = lastUserMsg.toLowerCase();

  const symbol = lower.includes("btc")
    ? "BTC/USD"
    : lower.includes("eth")
      ? "ETH/USD"
      : lower.includes("sol")
        ? "SOL/USD"
        : lower.includes("gold") || lower.includes("gld")
          ? "GLD"
          : lower.includes("aapl") || lower.includes("apple")
            ? "AAPL"
            : lower.includes("nvda")
              ? "NVDA"
              : "BTC/USD";

  const risk = lower.includes("safe") || lower.includes("conserv")
    ? "low"
    : lower.includes("aggress")
      ? "high"
      : "medium";

  const category = ["btc", "eth", "sol", "crypto"].some((k) => lower.includes(k))
    ? "crypto"
    : ["gold", "oil", "gld", "uso"].some((k) => lower.includes(k))
      ? "commodities"
      : ["aapl", "nvda", "stock"].some((k) => lower.includes(k))
        ? "stocks"
        : "crypto";

  const strategyName = risk === "high" ? "Aggressive" : risk === "low" ? "Safe" : "Momentum";

  return {
    message: `I've built a preview for your ${symbol} ${strategyName} agent! Check the panel on the right. Adjust anything by describing changes, or click "Deploy Agent" to launch it.`,
    agentConfig: {
      name: `${symbol.split("/")[0]} ${strategyName} Agent`,
      symbol,
      category,
      strategy: lower.includes("scalp") ? "Scalping" : lower.includes("swing") ? "Swing" : "Momentum",
      risk,
      indicators: ["RSI", lower.includes("macd") ? "MACD" : "EMA"],
    },
  };
}
