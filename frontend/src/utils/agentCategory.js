/**
 * Categorize trading agents by symbol into Crypto / Akcie (Stocks) / Komodity (Commodities).
 * The backend doesn't expose category directly on every agent payload yet, so we infer.
 */

const CRYPTO_TOKENS = [
  "BTC",
  "ETH",
  "SOL",
  "USDT",
  "USDC",
  "DOGE",
  "ADA",
  "LINK",
  "XRP",
  "AVAX",
  "DOT",
  "MATIC",
  "LTC",
  "BCH",
  "ATOM",
  "ARB",
  "OP",
  "INJ",
  "TRX",
  "TON",
  "PEPE",
  "SHIB",
];

const STOCK_TOKENS = [
  "NVDA",
  "AMD",
  "TSLA",
  "AAPL",
  "MSFT",
  "GOOGL",
  "GOOG",
  "META",
  "AMZN",
  "NFLX",
  "INTC",
  "PLTR",
  "BABA",
  "JPM",
  "BAC",
];

const COMMODITY_TOKENS = ["GLD", "USO", "SLV", "GOLD", "OIL", "WTI", "BRENT", "COPPER", "SILVER", "WHEAT", "CORN"];

export function categorizeAgent(agent) {
  const explicit = String(agent?.category || "").toLowerCase();
  if (explicit === "crypto") return "crypto";
  if (explicit === "stock" || explicit === "stocks") return "stocks";
  if (explicit === "commodity" || explicit === "commodities" || explicit === "etf") return "commodity";

  const sym = String(agent?.symbol || "").toUpperCase();
  if (!sym) return "stocks";

  if (CRYPTO_TOKENS.some((t) => sym.includes(t))) return "crypto";
  if (COMMODITY_TOKENS.some((t) => sym.includes(t))) return "commodity";
  if (STOCK_TOKENS.some((t) => sym.includes(t))) return "stocks";

  // Fallback heuristic: presence of "/USD" usually means crypto pair
  if (sym.includes("/USD") || sym.includes("USDT") || sym.includes("USDC")) return "crypto";
  return "stocks";
}

/**
 * Return tier-based slot limits per category.
 * Mirrors the prototype values; can be overridden by `featuresPayload` from /api/auth/me later.
 */
export function tierSlotLimits(tier) {
  const t = String(tier || "basic").toLowerCase();
  if (t === "admin" || t === "elite") return { crypto: 99, stocks: 99, commodity: 99 };
  if (t === "pro") return { crypto: 4, stocks: 4, commodity: 2 };
  return { crypto: 2, stocks: 1, commodity: 1 };
}

/** Group agents into the three categories as plain arrays. */
export function groupAgentsByCategory(agents = []) {
  const out = { crypto: [], stocks: [], commodity: [] };
  for (const a of agents) {
    const cat = categorizeAgent(a);
    out[cat]?.push(a);
  }
  return out;
}
