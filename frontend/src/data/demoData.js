export const demoUser = {
  email: "trader@letagentscook.lol",
  handle: "@manhattan_alpha",
  name: "Manhattan Alpha",
  tier: "pro",
  isAdmin: false,
  notifications: 4,
};

export const demoAgents = [
  {
    id: "btc_momentum",
    name: "BTC Momentum Prime",
    symbol: "BTC/USD",
    category: "Crypto",
    strategy: "momentum",
    pnlUsd: 1842.62,
    pnlPct: 18.42,
    winRate: 71,
    status: "live",
    trades: 84,
    spark: [44, 46, 49, 51, 53, 55, 57, 56, 60, 63, 65, 69],
    badges: [{ label: "Hot streak", icon: "🔥" }],
    tradesFeed: [
      { symbol: "BTC/USD", action: "BUY", pnl: 312.4, ts: "2m ago" },
      { symbol: "BTC/USD", action: "SELL", pnl: 148.1, ts: "11m ago" },
    ],
  },
  {
    id: "eth_breakout",
    name: "ETH Breakout Vault",
    symbol: "ETH/USD",
    category: "Crypto",
    strategy: "breakout",
    pnlUsd: 962.77,
    pnlPct: 9.62,
    winRate: 66,
    status: "live",
    trades: 61,
    spark: [30, 31, 32, 33, 35, 37, 39, 38, 41, 44, 46, 49],
    badges: [{ label: "Reliable", icon: "🛡️" }],
    tradesFeed: [{ symbol: "ETH/USD", action: "SELL", pnl: 92.2, ts: "18m ago" }],
  },
  {
    id: "nasdaq_mean",
    name: "Nasdaq Mean Revert",
    symbol: "QQQ",
    category: "Stocks",
    strategy: "mean_reversion",
    pnlUsd: -214.13,
    pnlPct: -2.14,
    winRate: 54,
    status: "paused",
    trades: 39,
    spark: [49, 48, 46, 45, 44, 43, 42, 40, 39, 38, 37, 35],
    badges: [{ label: "Steady", icon: "⚖️" }],
    tradesFeed: [{ symbol: "QQQ", action: "BUY", pnl: -41.8, ts: "26m ago" }],
  },
  {
    id: "eurusd_scalp",
    name: "Euro Session Scalper",
    symbol: "EUR/USD",
    category: "Forex",
    strategy: "scalping",
    pnlUsd: 438.6,
    pnlPct: 4.39,
    winRate: 59,
    status: "live",
    trades: 73,
    spark: [24, 25, 26, 27, 28, 27, 29, 30, 31, 33, 34, 35],
    badges: [{ label: "Fast", icon: "⚡" }],
    tradesFeed: [{ symbol: "EUR/USD", action: "SELL", pnl: 77.5, ts: "34m ago" }],
  },
  {
    id: "gold_hedge",
    name: "Gold Inflation Hedge",
    symbol: "GLD",
    category: "Commodities",
    strategy: "trend_following",
    pnlUsd: 1264.55,
    pnlPct: 12.64,
    winRate: 68,
    status: "live",
    trades: 58,
    spark: [36, 37, 38, 39, 41, 42, 44, 45, 46, 49, 52, 54],
    badges: [{ label: "Top gainer", icon: "🏆" }],
    tradesFeed: [{ symbol: "GLD", action: "SELL", pnl: 53.4, ts: "47m ago" }],
  },
  {
    id: "oil_grid",
    name: "WTI Grid Defender",
    symbol: "USO",
    category: "Commodities",
    strategy: "grid",
    pnlUsd: -82.07,
    pnlPct: -0.82,
    winRate: 51,
    status: "paused",
    trades: 44,
    spark: [41, 40, 39, 39, 38, 37, 36, 35, 34, 34, 33, 32],
    badges: [{ label: "Range", icon: "🔲" }],
    tradesFeed: [{ symbol: "USO", action: "BUY", pnl: -22.3, ts: "1h ago" }],
  },
];

export const DEMO_AGENTS = demoAgents;

const marketplaceSeed = [
  ["S&P Macro Rotation", "Stocks", "trend_following"],
  ["Tokyo Session Pulse", "Forex", "momentum"],
  ["Silver Breakout Engine", "Commodities", "breakout"],
  ["Nasdaq Grid Defense", "Stocks", "grid"],
  ["EUR Carry Momentum", "Forex", "momentum"],
  ["Copper Trend Wave", "Commodities", "trend_following"],
  ["DXY Reversion Lab", "Forex", "mean_reversion"],
  ["FTSE Intraday Flow", "Stocks", "scalping"],
  ["WTI Volatility Surf", "Commodities", "breakout"],
  ["Cardano Swing Atlas", "Crypto", "swing"],
  ["Solana Impulse AI", "Crypto", "momentum"],
  ["BNB Range Matrix", "Crypto", "grid"],
  ["Tesla News Reactor", "Stocks", "event"],
  ["AAPL Liquidity Sniper", "Stocks", "scalping"],
  ["XAU Macro Shield", "Commodities", "hedge"],
];

export const marketplaceAgents = marketplaceSeed.map((row, idx) => ({
  id: `mk_${idx + 1}`,
  name: row[0],
  category: row[1],
  strategy: row[2],
  winRate: 52 + (idx % 8) * 3,
  subscribers: 190 + idx * 41,
  pnlPct: Number((1.9 + idx * 0.94).toFixed(2)),
}));

export const leaderboardEntries = Array.from({ length: 15 }).map((_, idx) => ({
  rank: idx + 1,
  agentId: `lb_${idx + 1}`,
  name: marketplaceAgents[idx]?.name || `Agent ${idx + 1}`,
  strategy: marketplaceAgents[idx]?.strategy || "momentum",
  symbol: ["BTC/USD", "ETH/USD", "QQQ", "EUR/USD", "GLD", "USO"][idx % 6],
  pnlPct: Number((21.4 - idx * 1.07).toFixed(2)),
  winRate: 76 - idx,
  trades: 138 - idx * 4,
  subscribers: 1290 - idx * 53,
  isMine: idx === 0 || idx === 4 || idx === 9,
}));

export const recentTrades = [
  { id: 1, symbol: "BTC/USD", action: "BUY", pnl: 312.4, ts: "2m ago" },
  { id: 2, symbol: "GLD", action: "SELL", pnl: 53.4, ts: "9m ago" },
  { id: 3, symbol: "ETH/USD", action: "BUY", pnl: -32.9, ts: "14m ago" },
  { id: 4, symbol: "EUR/USD", action: "SELL", pnl: 77.5, ts: "19m ago" },
  { id: 5, symbol: "QQQ", action: "BUY", pnl: -18.4, ts: "28m ago" },
];

export const activeAlerts = [
  { id: "a1", title: "Risk alert", message: "Daily drawdown reached 62% of your limit. Position sizes auto-capped." },
  { id: "a2", title: "Agent inactive", message: "WTI Grid Defender is paused due to volatility filter." },
];

export const onboardingSteps = [
  { key: "agent_added", label: "Add your first agent", done: true },
  { key: "alert_configured", label: "Configure alerts", done: true },
  { key: "telegram_connected", label: "Connect Telegram", done: false },
  { key: "first_backtest", label: "Run your first backtest", done: false },
];

