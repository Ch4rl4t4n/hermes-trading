import { useEffect, useRef, useState } from "react";
import CurrencySelector from "../CurrencySelector";
import NotificationBell from "../NotificationBell";
import { useCurrency } from "../../contexts/CurrencyContext";

/**
 * Desktop horizontal top navigation (prototype style).
 *
 * Primary: Dashboard … Backtesting
 * ADMIN dropdown: Developer API (Elite+), Administrácia / Swarmy (admin), Owner DS (owner)
 * Account: Nastavenia len pod avatarom
 */

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "discover", label: "Discover" },
  { key: "marketplace", label: "Marketplace" },
  { key: "builder", label: "Builder" },
  { key: "leaderboard", label: "Leaderboard" },
  { key: "backtest", label: "Backtesting" },
];

const ADMIN_MENU_DEF = [
  { key: "developer", label: "Developer API", show: ({ tier, isAdmin }) => tier === "elite" || isAdmin },
  { key: "admin", label: "Administration", show: ({ isAdmin }) => isAdmin },
  { key: "admin-swarm", label: "Swarm Center", show: ({ isAdmin }) => isAdmin },
  { key: "owner-design", label: "Owner — Design System", show: ({ isOwner }) => isOwner },
];

function tierLabel(tier) {
  const t = String(tier || "basic").toLowerCase();
  if (t === "admin") return "ADMIN";
  if (t === "elite") return "ELITE";
  if (t === "pro") return "PRO";
  return "BASIC";
}

function trialDays(user) {
  if (!user) return null;
  if (user.tier === "pro" || user.tier === "elite" || user.tier === "admin") return null;
  return "13d";
}

function buildAdminMenuItems(user) {
  const tier = String(user?.tier || "").toLowerCase();
  const isAdmin = Boolean(user?.isAdmin) || tier === "admin";
  const isOwner = Boolean(user?.isOwner);
  const ctx = { tier, isAdmin, isOwner };
  return ADMIN_MENU_DEF.filter((def) => def.show(ctx));
}

export default function HermesTopNav({ page, user, onNav, onLogout, totalPnl = 0 }) {
  const trial = trialDays(user);
  const adminItems = buildAdminMenuItems(user);
  const showAdminMenu = adminItems.length > 0;
  const { format } = useCurrency();
  const pnlValue = Number(totalPnl) || 0;
  const pnlSign = pnlValue > 0 ? "pos" : pnlValue < 0 ? "neg" : "flat";

  const [profileOpen, setProfileOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const profileRef = useRef(null);
  const adminRef = useRef(null);

  useEffect(() => {
    if (!profileOpen && !adminOpen) return undefined;
    const onDocClick = (ev) => {
      if (profileOpen && profileRef.current && !profileRef.current.contains(ev.target)) {
        setProfileOpen(false);
      }
      if (adminOpen && adminRef.current && !adminRef.current.contains(ev.target)) {
        setAdminOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [profileOpen, adminOpen]);

  const closeMenus = () => {
    setProfileOpen(false);
    setAdminOpen(false);
  };

  return (
    <header className="hermes-topnav" role="banner" aria-label="Main navigation">
      <div className="hermes-topnav-inner">
        <button
          type="button"
          className="hermes-topnav-brand"
          onClick={() => onNav?.("dashboard")}
          aria-label="HERMES home"
        >
          <span className="hermes-topnav-logo" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <defs>
                <linearGradient id="hermes-logo-grad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#a78bfa" />
                  <stop offset="100%" stopColor="#22d3ee" />
                </linearGradient>
              </defs>
              <rect x="2" y="2" width="28" height="28" rx="8" fill="url(#hermes-logo-grad)" />
              <text
                x="16"
                y="22"
                fontFamily="Inter, system-ui, sans-serif"
                fontWeight="800"
                fontSize="18"
                fill="#0b0b14"
                textAnchor="middle"
              >
                H
              </text>
            </svg>
          </span>
          <span className="hermes-topnav-wordmark">HERMES</span>
          <span className="hermes-topnav-pill is-sandbox">SANDBOX</span>
        </button>

        <nav className="hermes-topnav-primary" aria-label="Primary navigation">
          {NAV_ITEMS.map((it) => {
            const active = page === it.key;
            return (
              <button
                key={it.key}
                type="button"
                className={`hermes-topnav-link${active ? " is-active" : ""}`}
                onClick={() => onNav?.(it.key)}
                aria-current={active ? "page" : undefined}
              >
                {it.label}
              </button>
            );
          })}
        </nav>

        <div className="hermes-topnav-right">
          {trial ? (
            <button
              type="button"
              className="hermes-topnav-pill is-trial"
              onClick={() => onNav?.("pricing")}
              title="Compare plans"
            >
              <span className="hermes-topnav-pill-spark" aria-hidden="true">✦</span>
              PRO TRIAL
              <span className="hermes-topnav-pill-suffix">· {trial}</span>
            </button>
          ) : (
            <button
              type="button"
              className="hermes-topnav-pill is-tier"
              onClick={() => onNav?.("pricing")}
              title="Compare plans"
            >
              {tierLabel(user?.tier)}
            </button>
          )}

          <button
            type="button"
            className={`hermes-topnav-pill is-pnl is-${pnlSign}`}
            onClick={() => onNav?.("dashboard")}
            title="Total paper P&L"
            aria-label={`Total paper P&L ${format(pnlValue, { decimals: 0, signed: true })}`}
          >
            <span className="hermes-topnav-pill-suffix">P&amp;L</span>
            <span className="mono">{format(pnlValue, { decimals: 0, signed: true })}</span>
          </button>

          <CurrencySelector />

          <NotificationBell user={user} onNav={onNav} />

          {showAdminMenu ? (
            <div className="hermes-topnav-admin" ref={adminRef}>
              <button
                type="button"
                className={`hermes-topnav-pill is-icon is-admin-icon${adminOpen ? " is-open" : ""}`}
                onClick={() => {
                  setProfileOpen(false);
                  setAdminOpen((o) => !o);
                }}
                aria-expanded={adminOpen}
                aria-haspopup="menu"
                aria-label="Administration and tools"
                title="Admin tools"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </button>
              {adminOpen ? (
                <div className="hermes-topnav-admin-menu" role="menu">
                  {adminItems.map((it) => {
                    const active = page === it.key;
                    return (
                      <button
                        key={it.key}
                        type="button"
                        role="menuitem"
                        className={active ? "is-active" : ""}
                        onClick={() => {
                          setAdminOpen(false);
                          onNav?.(it.key);
                        }}
                      >
                        {it.label}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="hermes-topnav-profile" ref={profileRef}>
            <button
              type="button"
              className="hermes-topnav-avatar"
              onClick={() => {
                setAdminOpen(false);
                setProfileOpen((p) => !p);
              }}
              aria-label={`Account ${user?.name || "Agent"}`}
              aria-haspopup="menu"
              aria-expanded={profileOpen}
              title={user?.email || user?.name || "Account"}
            >
              {(user?.name || user?.email || "A")[0].toUpperCase()}
            </button>
            {profileOpen ? (
              <div className="hermes-topnav-profile-menu" role="menu">
                <div className="hermes-topnav-profile-head">
                  <strong>{user?.name || "Agent"}</strong>
                  <span className="text-3 fs-12">{user?.email || ""}</span>
                  <span className="hermes-topnav-pill is-tier" style={{ marginTop: 4, alignSelf: "flex-start" }}>{tierLabel(user?.tier)}</span>
                </div>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    closeMenus();
                    onNav?.("rewards");
                  }}
                >
                  Rewards
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    closeMenus();
                    onNav?.("invite");
                  }}
                >
                  Invite friends
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    closeMenus();
                    onNav?.("settings");
                  }}
                >
                  Settings
                </button>
                <hr />
                <button
                  type="button"
                  role="menuitem"
                  className="hermes-topnav-profile-logout"
                  onClick={() => {
                    closeMenus();
                    onLogout?.();
                  }}
                >
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
