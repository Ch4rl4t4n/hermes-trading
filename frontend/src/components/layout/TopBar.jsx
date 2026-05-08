import SwarmHealthBadge from "../SwarmHealthBadge";

const titles = {
  dashboard: "Prehľad",
  marketplace: "Market",
  builder: "Agent Builder",
  leaderboard: "Rebríček",
  backtest: "Backtest",
  settings: "Nastavenia",
  developer: "Developer API",
  admin: "Administrácia",
  "admin-swarm": "Swarm War Room",
};

export default function TopBar({ page, user, onNav }) {
  const isAdmin = Boolean(user?.isAdmin) || String(user?.tier || "").toLowerCase() === "admin";
  return (
    <header className="topbar">
      <strong>{titles[page] || "Hermes"}</strong>
      <div className="row gap-2">
        <input className="topbar-search" placeholder="Hľadať agentov, symboly..." aria-label="Vyhľadávanie agentov a symbolov" />
        <SwarmHealthBadge
          isAdmin={isAdmin}
          onClick={() => onNav?.("admin-swarm")}
        />
        <button className="topbar-bell" aria-label="Notifikácie">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
            <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
            <path d="M10.4 20a2.1 2.1 0 0 0 3.2 0" />
          </svg>
          <span>{user?.notifications || 0}</span>
        </button>
        <div className="topbar-avatar" role="img" aria-label={`Profil používateľa ${user?.name || "Agent"}`}>
          {(user?.name || "A")[0]}
        </div>
      </div>
    </header>
  );
}
