const titles = {
  dashboard: "Dashboard",
  marketplace: "Marketplace",
  builder: "Agent Builder",
  leaderboard: "Leaderboard",
  backtest: "Backtest",
  admin: "Admin",
};

export default function TopBar({ page, user }) {
  return (
    <header className="topbar">
      <strong>{titles[page] || "Hermes"}</strong>
      <div className="row gap-2">
        <input className="topbar-search" placeholder="Search agents, symbols..." />
        <button className="topbar-bell" aria-label="Notifications">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
            <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
            <path d="M10.4 20a2.1 2.1 0 0 0 3.2 0" />
          </svg>
          <span>{user?.notifications || 0}</span>
        </button>
        <div className="topbar-avatar">{(user?.name || "A")[0]}</div>
      </div>
    </header>
  );
}

