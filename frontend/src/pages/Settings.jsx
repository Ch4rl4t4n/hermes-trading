import { useEffect, useState } from "react";

import UserWatcherSettings from "../components/settings/UserWatcherSettings";
import client from "../api/client";
import { useVoice } from "../hooks/useVoice";
import { useCurrency } from "../contexts/CurrencyContext";
import { requestPermission } from "../utils/notifications";
import { STORAGE_KEYS } from "../utils/storageKeys";

const TIER_DISPLAY = {
  basic: { label: "BASIC", color: "var(--text-secondary)", desc: "Free starter — 3 agents, 30-day history." },
  pro: { label: "PRO", color: "#22c55e", desc: "10 agents, 365-day history, Telegram & email alerts." },
  elite: { label: "ELITE", color: "#c4b5fd", desc: "Unlimited agents, full API access, live trading." },
  admin: { label: "ADMIN", color: "#fbbf24", desc: "All limits removed (internal account)." },
};

export default function Settings({ user, onToast, onNav }) {
  const { isSupported } = useVoice();
  const { format } = useCurrency();
  const [recentTrades, setRecentTrades] = useState([]);
  const [loadingTrades, setLoadingTrades] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadingTrades(true);
    client
      .get("/api/trades/history?limit=10")
      .then(({ data }) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : data?.trades || [];
        setRecentTrades(list);
      })
      .catch(() => {
        if (!cancelled) setRecentTrades([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingTrades(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const [voiceEnabled, setVoiceEnabled] = useState(() => {
    const raw = window.localStorage.getItem(STORAGE_KEYS.VOICE_ENABLED);
    return raw === null ? true : raw === "true";
  });
  const [notificationState, setNotificationState] = useState(() => {
    if (!("Notification" in window)) return "unsupported";
    return Notification.permission;
  });
  const [portalLoading, setPortalLoading] = useState(false);

  const tierKey = String(user?.tier || "basic").toLowerCase();
  const tier = TIER_DISPLAY[tierKey] || TIER_DISPLAY.basic;
  const canManage = tierKey === "pro" || tierKey === "elite";

  const onManageSubscription = async () => {
    setPortalLoading(true);
    try {
      const { data } = await client.post("/api/stripe/create-portal-session", {});
      if (data?.portal_url) {
        window.location.href = data.portal_url;
        return;
      }
      onToast?.(data?.error || "Could not open billing portal.");
    } catch (err) {
      onToast?.(err?.response?.data?.error || "Could not open billing portal.");
    } finally {
      setPortalLoading(false);
    }
  };

  const onToggleVoice = (nextValue) => {
    setVoiceEnabled(nextValue);
    window.localStorage.setItem(STORAGE_KEYS.VOICE_ENABLED, String(nextValue));
  };

  const onEnableNotifications = async () => {
    if (!("Notification" in window)) {
      setNotificationState("unsupported");
      return;
    }
    const granted = await requestPermission();
    if (granted) {
      setNotificationState("granted");
      return;
    }
    setNotificationState(Notification.permission);
  };

  return (
    <section className="page-content hermes-settings col" style={{ gap: 18 }}>
      <header className="hermes-page-head">
        <div>
          <h1 className="hermes-page-title">Settings</h1>
          <p className="hermes-page-lead">Agent voice, notifications, weekly report and integrations</p>
        </div>
      </header>

      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <h3 style={{ marginTop: 0, marginBottom: 10 }}>Subscription</h3>
        <div className="settings-row">
          <div className="settings-row-info">
            <strong className="settings-label">
              Current plan{" "}
              <span className="pill" style={{ background: "rgba(167,139,250,.12)", color: tier.color, marginLeft: 6 }}>
                {tier.label}
              </span>
            </strong>
            <span className="settings-desc">{tier.desc}</span>
          </div>
          <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
            <button
              type="button"
              className="pill pill-violet"
              style={{ border: "none", minWidth: 170 }}
              onClick={() => onNav?.("pricing")}
            >
              Compare plans
            </button>
            {canManage ? (
              <button
                type="button"
                className="pill pill-gray"
                style={{ border: "none", minWidth: 170 }}
                onClick={onManageSubscription}
                disabled={portalLoading}
              >
                {portalLoading ? "Opening…" : "Manage in Stripe"}
              </button>
            ) : null}
          </div>
        </div>
      </article>

      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <header className="row between" style={{ alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Recent trades</h3>
          <button
            type="button"
            className="pill pill-gray"
            style={{ border: "none" }}
            onClick={() => onNav?.("dashboard")}
          >
            Open dashboard
          </button>
        </header>
        {loadingTrades ? (
          <p className="text-3 fs-12">Loading…</p>
        ) : recentTrades.length ? (
          <div className="hermes-trades-list">
            {recentTrades.slice(0, 8).map((t, idx) => {
              const action = String(t.action || t.side || "").toUpperCase();
              const pnl = Number(t.pnl ?? t.pnl_usd ?? 0);
              const ts = t.timestamp || t.ts || t.created_at || "";
              return (
                <div key={t.id || idx} className="hermes-trades-row">
                  <span className={`hermes-trades-side ${action === "SELL" ? "is-sell" : "is-buy"}`}>{action || "—"}</span>
                  <span className="hermes-trades-symbol mono">{t.symbol || t.ticker || "—"}</span>
                  <span
                    className="mono"
                    style={{ color: pnl >= 0 ? "#10b981" : "#ef4444", fontSize: 12, marginLeft: "auto" }}
                  >
                    {format(pnl, { signed: true })}
                  </span>
                  <span className="text-3 fs-12 hermes-trades-time">{ts}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-3 fs-12">No trades yet — head to the marketplace to subscribe to an agent.</p>
        )}
      </article>

      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <h3 style={{ marginTop: 0, marginBottom: 10 }}>Rewards &amp; loyalty</h3>
        <div className="settings-row">
          <div className="settings-row-info">
            <strong className="settings-label">Loyalty hub</strong>
            <span className="settings-desc">Achievements, tier perks and your loyalty score in one place.</span>
          </div>
          <button
            type="button"
            className="pill pill-violet"
            style={{ border: "none", minWidth: 170 }}
            onClick={() => onNav?.("rewards")}
          >
            Open rewards
          </button>
        </div>
        <div className="settings-row" style={{ marginTop: 14 }}>
          <div className="settings-row-info">
            <strong className="settings-label">Referral program</strong>
            <span className="settings-desc">Share your link — you and friends can earn bonus agent slots.</span>
          </div>
          <button
            type="button"
            className="pill pill-gray"
            style={{ border: "none", minWidth: 170 }}
            onClick={() => onNav?.("invite")}
          >
            Open invite page
          </button>
        </div>
      </article>

      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <h3 style={{ marginTop: 0, marginBottom: 10 }}>Profile &amp; preferences</h3>
        <div className="settings-row">
          <div className="settings-row-info">
            <strong className="settings-label">
              Agent Voice {!isSupported.tts ? <span className="text-3">(not supported by browser)</span> : null}
            </strong>
            <span className="settings-desc">Agent speaks after profitable trades</span>
          </div>
          <button
            type="button"
            className={`pill ${voiceEnabled ? "pill-violet" : "pill-gray"}`}
            onClick={() => onToggleVoice(!voiceEnabled)}
            disabled={!isSupported.tts}
            style={{ border: "none", minWidth: 70 }}
          >
            {voiceEnabled ? "On" : "Off"}
          </button>
        </div>

        <div className="settings-row" style={{ marginTop: 14 }}>
          <div className="settings-row-info">
            <strong className="settings-label">Notifications</strong>
            <span className="settings-desc">Browser notifications for alerts and profitable trades</span>
          </div>
          <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
            <button
              type="button"
              className="pill pill-violet"
              style={{ border: "none", minWidth: 170 }}
              onClick={onEnableNotifications}
              disabled={notificationState === "unsupported" || notificationState === "granted"}
            >
              Enable Notifications
            </button>
            {notificationState === "granted" ? <span className="text-3 fs-12">✓ Notifications enabled</span> : null}
            {notificationState === "denied" ? <span className="text-3 fs-12">Blocked in browser settings</span> : null}
            {notificationState === "unsupported" ? <span className="text-3 fs-12">Not supported by browser</span> : null}
          </div>
        </div>
      </article>

      <UserWatcherSettings user={user} onToast={onToast} />
    </section>
  );
}
