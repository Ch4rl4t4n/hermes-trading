/** Map internal page keys ↔ URL paths (SPA + Vercel rewrite na index.html). */

export const PAGE_PATHS = {
  dashboard: "/",
  marketplace: "/marketplace",
  builder: "/builder",
  leaderboard: "/leaderboard",
  backtest: "/backtest",
  settings: "/settings",
  developer: "/developer",
  admin: "/admin",
  "admin-swarm": "/admin-swarm",
};

const LEGACY_PATH_ALIASES = {
  "/dashboard": "dashboard",
  "/trades": "dashboard",
  "/war-room": "admin-swarm",
  "/swarm": "admin-swarm",
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
  const isAdmin = Boolean(user?.isAdmin);
  if ((page === "admin" || page === "admin-swarm") && !isAdmin) return "dashboard";
  return page;
}
