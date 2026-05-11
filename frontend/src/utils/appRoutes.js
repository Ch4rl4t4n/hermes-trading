/** Map internal page keys ↔ URL paths (SPA + Vercel rewrite na index.html). */

export const PAGE_PATHS = {
  dashboard: "/",
  /** Verejná registrácia (SPA + nginx fallback na index.html). */
  register: "/register",
  discover: "/discover",
  marketplace: "/marketplace",
  builder: "/builder",
  leaderboard: "/leaderboard",
  backtest: "/backtest",
  settings: "/settings",
  developer: "/developer",
  pricing: "/pricing",
  invite: "/invite",
  rewards: "/rewards",
  admin: "/admin",
  "admin-swarm": "/admin-swarm",
  "owner-design": "/owner/design",
};

const LEGACY_PATH_ALIASES = {
  "/dashboard": "dashboard",
  "/trades": "dashboard",
  "/war-room": "admin-swarm",
  "/swarm": "admin-swarm",
  "/tiers": "pricing",
  "/club": "pricing",
  "/upgrade": "pricing",
  "/forum": "discover",
  "/community": "discover",
  "/explore": "discover",
};

export function normalizeUrlPath(pathname) {
  const n = pathname.replace(/\/+$/, "") || "/";
  return n;
}

export function pathToPage(pathname) {
  const n = normalizeUrlPath(pathname);
  if (LEGACY_PATH_ALIASES[n]) return LEGACY_PATH_ALIASES[n];
  for (const [pageId, path] of Object.entries(PAGE_PATHS)) {
    const p = normalizeUrlPath(path);
    if (p === n) return pageId;
  }
  return "dashboard";
}

export function pageToPath(page) {
  const path = PAGE_PATHS[page];
  return path ?? "/";
}

export function resolvePageForUser(page, user) {
  if (user && page === "register") return "dashboard";
  const isAdmin = Boolean(user?.isAdmin);
  const isOwner = Boolean(user?.isOwner);
  if ((page === "admin" || page === "admin-swarm") && !isAdmin) return "dashboard";
  if (page === "owner-design" && !isOwner) return "dashboard";
  return page;
}
