import NotificationBell from "../NotificationBell";

const titles = {
  dashboard: "Dashboard",
  marketplace: "Market",
  builder: "Agent Builder",
  leaderboard: "Leaderboard",
  backtest: "Backtest",
  settings: "Settings",
  developer: "Developer API",
  admin: "Administration",
  "admin-swarm": "Swarm Center",
};

export default function TopBar({ page, user, onNav }) {
  return (
    <header className="topbar" aria-label="Top bar">
      <strong>{titles[page] || "Hermes"}</strong>
      <div className="row gap-2">
        <input className="topbar-search" placeholder="Search agents, symbols..." aria-label="Search agents and symbols" />
        <NotificationBell user={user} onNav={onNav} />
        <div className="topbar-avatar" role="img" aria-label={`User profile ${user?.name || "Agent"}`}>
          {(user?.name || "A")[0]}
        </div>
      </div>
    </header>
  );
}
