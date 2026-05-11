import NotificationBell from "../NotificationBell";
import { useCurrency } from "../../contexts/CurrencyContext";

export default function TopNav({ user, onNav, totalPnl = 0 }) {
  const { format } = useCurrency();
  const pnlValue = Number(totalPnl) || 0;
  const pnlSign = pnlValue > 0 ? "pos" : pnlValue < 0 ? "neg" : "flat";
  return (
    <header
      aria-label="Top bar"
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
            type="button"
            className={`hermes-topnav-pill is-pnl is-${pnlSign}`}
            onClick={() => onNav?.("dashboard")}
            title="Total paper P&L"
          >
            <span className="hermes-topnav-pill-suffix">P&amp;L</span>
            <span className="mono">{format(pnlValue, { decimals: 0, signed: true })}</span>
          </button>
          <NotificationBell user={user} onNav={onNav} />
          <div
            role="img"
            aria-label={`User profile ${user?.name || "Agent"}`}
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
            <span aria-hidden="true">{(user?.name || "A")[0]}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

