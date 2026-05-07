const SKINS = ["basic", "neon", "meme_cat", "wolf", "cosmic"];
const PERSONALITIES = ["zen_monk", "aggressive", "wall_street", "degen"];

export function calculateXP(agent) {
  const trades = agent.trades || 0;
  const winRate = agent.winRate || 50;
  const pnl = agent.pnl ?? agent.pnlUsd ?? 0;

  let xp = trades * 10;
  xp += (trades * (winRate / 100)) * 50;
  if (pnl > 0) xp += Math.floor(pnl / 10);

  return Math.floor(xp);
}

export function getLevel(xp) {
  if (xp >= 10000) return { level: 5, title: "Legend", next: null };
  if (xp >= 5000) return { level: 4, title: "Expert", next: 10000 };
  if (xp >= 2000) return { level: 3, title: "Veteran", next: 5000 };
  if (xp >= 500) return { level: 2, title: "Apprentice", next: 2000 };
  return { level: 1, title: "Rookie", next: 500 };
}

export function getUnlockedSkins(level) {
  return SKINS.slice(0, level);
}

export function getUnlockedPersonalities(level) {
  return PERSONALITIES.slice(0, Math.max(1, level - 1));
}

function evolutionStorageKey(agent) {
  const id = agent?.id ?? agent?.symbol ?? "unknown";
  return `hermes-agent-evolution:${id}`;
}

export function getStoredEvolution(agent, level) {
  const defaults = {
    skin: getUnlockedSkins(level)[0] || "basic",
    personality: getUnlockedPersonalities(level)[0] || "zen_monk",
  };
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(evolutionStorageKey(agent));
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    return {
      skin: parsed.skin || defaults.skin,
      personality: parsed.personality || defaults.personality,
    };
  } catch {
    return defaults;
  }
}

export function saveStoredEvolution(agent, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(evolutionStorageKey(agent), JSON.stringify(value));
  } catch {
    // Ignore localStorage write failures.
  }
}
