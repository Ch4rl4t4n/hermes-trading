const iconBase = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.9,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

const navItems = [
  {
    key: "dashboard",
    label: "Prehľad",
    icon: (
      <svg {...iconBase}>
        <rect x="3.5" y="3.5" width="7.5" height="7.5" />
        <rect x="13" y="3.5" width="7.5" height="7.5" />
        <rect x="3.5" y="13" width="7.5" height="7.5" />
        <rect x="13" y="13" width="7.5" height="7.5" />
      </svg>
    ),
  },
  {
    key: "marketplace",
    label: "Market",
    icon: (
      <svg {...iconBase}>
        <path d="M5 8h14l-1.4 10.2a1.2 1.2 0 0 1-1.2 1H7.6a1.2 1.2 0 0 1-1.2-1z" />
        <path d="M9 8a3 3 0 0 1 6 0" />
      </svg>
    ),
  },
  {
    key: "builder",
    label: "Builder",
    icon: (
      <svg {...iconBase}>
        <path d="m4 20 8-8" />
        <path d="m14 6 4-4 4 4-4 4z" />
        <path d="M12 8 4 16l4 4 8-8" />
      </svg>
    ),
  },
  {
    key: "leaderboard",
    label: "Rebríček",
    icon: (
      <svg {...iconBase}>
        <path d="M8 21h8" />
        <path d="M12 17v4" />
        <path d="M7 4h10l-1 6a4 4 0 0 1-4 3 4 4 0 0 1-4-3z" />
      </svg>
    ),
  },
  {
    key: "backtest",
    label: "Backtest",
    icon: (
      <svg {...iconBase}>
        <path d="M3 3v18h18" />
        <path d="m7 14 4-4 3 3 5-6" />
      </svg>
    ),
  },
  {
    key: "settings",
    label: "Nastavenia",
    icon: (
      <svg {...iconBase}>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1 1 0 0 0 .2 1.1l.1.1a1 1 0 0 1 0 1.4l-1.4 1.4a1 1 0 0 1-1.4 0l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a1 1 0 0 1-1.4 0L4.2 17.8a1 1 0 0 1 0-1.4l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H3.5a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a1 1 0 0 1 0-1.4L5.7 4a1 1 0 0 1 1.4 0l.1.1a1 1 0 0 0 1.1.2h.1a1 1 0 0 0 .5-.9V3.2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v.2a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a1 1 0 0 1 1.4 0l1.4 1.4a1 1 0 0 1 0 1.4l-.1.1a1 1 0 0 0-.2 1.1v.1a1 1 0 0 0 .9.5h.2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1h-.2a1 1 0 0 0-.9.6z" />
      </svg>
    ),
  },
  {
    key: "developer",
    label: "Vývoj",
    icon: (
      <svg {...iconBase}>
        <rect x="4" y="4" width="16" height="16" rx="2.5" />
        <path d="M9 9h6v2H9z" />
        <path d="M9 13h4v2H9z" />
        <path d="m14.5 14.5 1.5 1.5 2.5-2.5" />
      </svg>
    ),
  },
];

const adminItem = {
  key: "admin",
  label: "Admin",
  icon: (
    <svg {...iconBase}>
      <path d="M12 3 4 7v6c0 4.5 2.8 7.4 8 8 5.2-.6 8-3.5 8-8V7z" />
      <path d="M9.5 12.5 11 14l3.5-3.5" />
    </svg>
  ),
};

const adminSwarmItem = {
  key: "admin-swarm",
  label: "Centrum swarmov",
  icon: (
    <svg {...iconBase}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      <circle cx="12" cy="12" r="3.5" />
    </svg>
  ),
};

export default function Sidebar({ page, onNav, user, onLogout }) {
  const items = user?.isAdmin ? [...navItems, adminItem, adminSwarmItem] : navItems;
  return (
    <aside className="sidebar" style={{ background: "oklch(0.12 0.02 260)" }}>
      <div className="sidebar-logo" style={{ letterSpacing: "0.06em", fontWeight: 700 }}>
        <span style={{ color: "oklch(0.72 0.18 295)", filter: "drop-shadow(0 0 20px oklch(0.72 0.18 295 / .45))" }}>⚡</span>
        HERMES
      </div>

      <nav className="sidebar-nav" aria-label="Bočná navigácia">
        {items.map((item) => {
          const active = page === item.key;
          return (
            <button
              key={item.key}
              type="button"
              className={`sidebar-item ${active ? "active" : ""}`}
              onClick={() => onNav(item.key)}
              aria-label={item.label}
              aria-current={active ? "page" : undefined}
              style={{
                borderLeft: active ? "2px solid oklch(0.72 0.18 295)" : "2px solid transparent",
                background: active ? "oklch(0.72 0.18 295 / 0.15)" : "transparent",
                color: active ? "oklch(0.82 0.14 295)" : "var(--text-3, var(--text-muted))",
                fontSize: 13,
                fontWeight: 500,
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.background = "oklch(1 0 0 / 0.04)";
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.background = "transparent";
              }}
            >
              <span style={{ width: 18, height: 18, display: "inline-flex", color: "currentColor" }} aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-user">
        <div className="sidebar-avatar" style={{ background: "linear-gradient(135deg,#8b5cf6,#06b6d4)" }}>
          {(user?.name || user?.handle || "A")[0]}
        </div>
        <div className="col" style={{ minWidth: 0, gap: 2 }}>
          <strong style={{ fontSize: 13 }}>{user?.name || user?.handle}</strong>
          <span className="text-3 fs-12" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.email || "admin@hermes.app"}
          </span>
        </div>
        <span className="pill pill-violet">{String(user?.tier || "basic").toUpperCase()}</span>
        <button type="button" className="sidebar-logout" onClick={onLogout} aria-label="Odhlásiť sa">
          Odhlásiť
        </button>
      </div>
    </aside>
  );
}

