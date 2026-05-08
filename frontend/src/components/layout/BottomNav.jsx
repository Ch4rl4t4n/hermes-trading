const iconBase = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.9,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

const icons = {
  dashboard: (
    <svg {...iconBase}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" />
      <rect x="13" y="3.5" width="7.5" height="7.5" />
      <rect x="3.5" y="13" width="7.5" height="7.5" />
      <rect x="13" y="13" width="7.5" height="7.5" />
    </svg>
  ),
  market: (
    <svg {...iconBase}>
      <path d="M5 8h14l-1.4 10.2a1.2 1.2 0 0 1-1.2 1H7.6a1.2 1.2 0 0 1-1.2-1z" />
      <path d="M9 8a3 3 0 0 1 6 0" />
    </svg>
  ),
  builder: (
    <svg {...iconBase}>
      <path d="m4 20 8-8" />
      <path d="m14 6 4-4 4 4-4 4z" />
      <path d="M12 8 4 16l4 4 8-8" />
      <path d="M16 10l-2-2" />
    </svg>
  ),
  ranks: (
    <svg {...iconBase}>
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <path d="M7 4h10l-1 6a4 4 0 0 1-4 3 4 4 0 0 1-4-3z" />
      <path d="M7 6H5a2 2 0 0 0 0 4h2" />
      <path d="M17 6h2a2 2 0 0 1 0 4h-2" />
    </svg>
  ),
  more: (
    <svg {...iconBase}>
      <circle cx="6" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="18" cy="12" r="1.8" />
    </svg>
  ),
  settings: (
    <svg {...iconBase}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1 1 0 0 0 .2 1.1l.1.1a1 1 0 0 1 0 1.4l-1.4 1.4a1 1 0 0 1-1.4 0l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a1 1 0 0 1-1.4 0L4.2 17.8a1 1 0 0 1 0-1.4l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H3.5a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a1 1 0 0 1 0-1.4L5.7 4a1 1 0 0 1 1.4 0l.1.1a1 1 0 0 0 1.1.2h.1a1 1 0 0 0 .5-.9V3.2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v.2a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a1 1 0 0 1 1.4 0l1.4 1.4a1 1 0 0 1 0 1.4l-.1.1a1 1 0 0 0-.2 1.1v.1a1 1 0 0 0 .9.5h.2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1h-.2a1 1 0 0 0-.9.6z" />
    </svg>
  ),
  developer: (
    <svg {...iconBase}>
      <rect x="4" y="4" width="16" height="16" rx="2.5" />
      <path d="M9 9h6v2H9z" />
      <path d="M9 13h4v2H9z" />
      <path d="m14.5 14.5 1.5 1.5 2.5-2.5" />
    </svg>
  ),
};

const tabs = [
  { key: "dashboard", label: "Dashboard", icon: "dashboard" },
  { key: "marketplace", label: "Market", icon: "market" },
  { key: "builder", label: "Build", icon: "builder" },
  { key: "leaderboard", label: "Ranks", icon: "ranks" },
  { key: "developer", label: "Dev", icon: "developer" },
  { key: "settings", label: "Settings", icon: "settings" },
];

export default function BottomNav({ page, onNav }) {
  const current = page === "marketplace"
    ? "market"
    : page === "builder"
      ? "builder"
      : page === "leaderboard"
        ? "ranks"
          : page === "developer"
            ? "developer"
        : page === "settings"
          ? "settings"
          : "dashboard";
  return (
    <nav className="bottom-nav" style={{ height: "calc(64px + env(safe-area-inset-bottom))", paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", height: 64 }}>
        {tabs.map((tab) => {
          const isActive = current === tab.icon;
          const color = isActive ? "oklch(0.72 0.18 295)" : "oklch(0.45 0.04 240)";
          return (
            <button
              key={tab.key}
              onClick={() => onNav(tab.key)}
              style={{
                border: "none",
                outline: "none",
                background: "transparent",
                color,
                display: "grid",
                placeItems: "center",
                gap: 2,
                alignContent: "center",
              }}
            >
              <span style={{ display: "inline-flex", color }}>{icons[tab.icon]}</span>
              <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

