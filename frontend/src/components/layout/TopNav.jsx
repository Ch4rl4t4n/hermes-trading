export default function TopNav({ user, onMore }) {
  return (
    <header
      style={{
        height: 56,
        position: "sticky",
        top: 0,
        zIndex: 90,
        background: "color-mix(in oklab, var(--color-surface) 78%, transparent)",
        backdropFilter: "blur(14px)",
        borderBottom: "1px solid var(--color-border-soft)",
      }}
    >
      <div className="row between" style={{ height: "100%", padding: "0 4px" }}>
        <div className="row gap-2">
          <span className="row gap-2" style={{ fontWeight: 800, letterSpacing: ".09em" }}>
            <span style={{ color: "var(--color-violet)", filter: "drop-shadow(var(--neon-violet))" }}>⚡</span>
            HERMES
          </span>
          <span className="pill pill-violet">{user?.tier || "Basic"}</span>
        </div>

        <div className="row gap-2">
          <button
            onClick={onMore}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--color-text-2)",
              width: 34,
              height: 34,
              position: "relative",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
              <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
              <path d="M10.4 20a2.1 2.1 0 0 0 3.2 0" />
            </svg>
            <span
              style={{
                position: "absolute",
                top: 1,
                right: 2,
                minWidth: 16,
                height: 16,
                borderRadius: 999,
                fontSize: 10,
                fontWeight: 700,
                background: "var(--color-red)",
                color: "#fff",
                display: "grid",
                placeItems: "center",
              }}
            >
              {user?.notifications || 0}
            </span>
          </button>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 999,
              background: "linear-gradient(135deg,#8b5cf6,#06b6d4)",
              display: "grid",
              placeItems: "center",
              fontWeight: 700,
            }}
          >
            {(user?.name || "A")[0]}
          </div>
        </div>
      </div>
    </header>
  );
}

