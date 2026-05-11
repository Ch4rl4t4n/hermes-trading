/**
 * Design schema applier — Hermes Universal CMS regenerator.
 *
 * Schémy z rôznych zdrojov (Claude prototype, Figma export, Tailwind...) používajú
 * iné názvy CSS premenných ako Hermes UI. Tento súbor obsahuje aliasing tabuľku,
 * ktorá hodnoty z importovaných tokenov propaguje aj na premenné, ktoré skutočne
 * používa Hermes `globals.css` (a opačne — keby niekto importoval Hermes naming).
 */

// Pravostranné názvy = Hermes UI v globals.css. Ľavostranné = ekvivalenty z Claude/Figma/Tailwind.
const TOKEN_ALIAS_MAP = {
  // Brand / accent
  "--violet": ["--accent", "--accent-primary", "--accent-secondary", "--neon-violet", "--purple", "--color-violet"],
  "--violet-glow": ["--accent-glow", "--glow", "--shadow-accent"],
  "--violet-soft": ["--accent-soft", "--accent-tint"],

  // Backgrounds (depth)
  "--bg-0": ["--bg", "--bg-primary", "--color-bg", "--background", "--app-bg"],
  "--bg-1": ["--bg-secondary"],
  "--bg-2": ["--bg-tertiary"],

  // Surfaces (cards, modals, glass)
  "--surface-1": ["--card", "--bg-card", "--color-surface", "--surface", "--header-bg"],
  "--surface-2": ["--bg-elevated", "--color-surface-2", "--modal-surface"],
  "--surface-3": ["--burger-panel-bg"],

  // Text hierarchy
  "--text-1": ["--text", "--text-primary", "--color-text"],
  "--text-2": ["--text-secondary", "--color-text-2"],
  "--text-3": ["--text-muted", "--color-text-3", "--muted", "--dim"],
  "--text-4": [],

  // Borders
  "--border-1": ["--border", "--border-default", "--border-subtle", "--color-border-soft"],
  "--border-2": ["--border-light", "--color-border"],
  "--border-3": ["--border-strong"],

  // Status colors
  "--green": ["--accent-success", "--success", "--color-green", "--neon-green"],
  "--green-soft": ["--success-soft"],
  "--red": ["--accent-danger", "--danger", "--color-red", "--neon-red"],
  "--red-soft": ["--danger-soft"],
  "--amber": ["--accent-warning", "--warning", "--yellow", "--neon-amber"],
  "--amber-soft": ["--warning-soft"],
  "--teal": ["--accent-info", "--info"],
  "--teal-soft": ["--info-soft"],
  "--pink": [],

  // Radii / shadows / typography (zhoduje sa, alias je no-op, ale necháme placeholder pre budúcnosť)
  "--radius-sm": [],
  "--radius-md": [],
  "--radius-lg": [],
  "--radius-xl": [],
  "--font-ui": ["--font-sans"],
  "--font-mono": [],
};

// Reverzná mapa pre prípad, že schéma má Hermes naming a chceme ho propagovať na Claude naming
const REVERSE_ALIAS = {};
Object.entries(TOKEN_ALIAS_MAP).forEach(([primary, aliases]) => {
  aliases.forEach((a) => {
    if (!REVERSE_ALIAS[a]) REVERSE_ALIAS[a] = [];
    REVERSE_ALIAS[a].push(primary);
  });
});

function expandWithAliases(vars) {
  const out = { ...vars };
  // 1) Forward: pre každý primary key v schéme propaguj na aliasy (ak nie sú už explicitne vyplnené)
  Object.entries(TOKEN_ALIAS_MAP).forEach(([primary, aliases]) => {
    const value = vars[primary];
    if (typeof value !== "string") return;
    aliases.forEach((alias) => {
      if (out[alias] === undefined) out[alias] = value;
    });
  });
  // 2) Reverse: ak má schéma Hermes naming (--accent, --bg, ...), propaguj späť na Claude naming
  Object.entries(REVERSE_ALIAS).forEach(([alias, primaries]) => {
    const value = vars[alias];
    if (typeof value !== "string") return;
    primaries.forEach((primary) => {
      if (out[primary] === undefined) out[primary] = value;
    });
  });
  return out;
}

export function applyGlobalCssVars(vars) {
  if (!vars || typeof vars !== "object") return;
  const expanded = expandWithAliases(vars);
  const root = document.documentElement;
  Object.entries(expanded).forEach(([k, v]) => {
    if (typeof v === "string" && k.startsWith("--")) {
      root.style.setProperty(k, v);
    }
  });
}

export async function fetchAndApplyActiveDesignSchema() {
  try {
    const r = await fetch("/api/design/active-schema", { credentials: "include" });
    if (!r.ok) return;
    const data = await r.json();
    applyGlobalCssVars(data?.globalCssVars);
  } catch {
    /* ignore */
  }
}

/**
 * After Owner Apply: prefer SW-side cache clear, fall back to direct caches API if SW missing.
 * Also re-fetches the active schema so the live document picks new tokens immediately.
 */
export async function bustDesignCachesAndRefresh() {
  try {
    if ("serviceWorker" in navigator) {
      const reg = await navigator.serviceWorker.getRegistration();
      if (reg) {
        try {
          reg.active?.postMessage?.({ type: "HERMES_DESIGN_BUMP" });
        } catch {
          /* ignore */
        }
        try {
          await reg.update();
        } catch {
          /* ignore */
        }
      }
    }
    if (typeof caches !== "undefined" && caches?.keys) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch {
    /* ignore */
  }
  await fetchAndApplyActiveDesignSchema();
}
