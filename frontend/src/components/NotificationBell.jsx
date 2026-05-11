import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/notifications";
import { sendNotification } from "../utils/notifications";

const POLL_MS = 30_000;

/** Inbox tabs (eToro-style). Backend may send `category` later — until then we derive from `type`. */
const INBOX_FILTERS = [
  { id: "all", label: "All" },
  { id: "investing", label: "Investing" },
  { id: "social", label: "Social" },
  { id: "marketing", label: "Marketing" },
];

/**
 * Maps API notification.type → inbox tab. Extend when backend adds explicit category.
 */
function inboxCategory(type) {
  const t = String(type || "").toLowerCase();
  if (t.includes("weekly") || t.includes("billing") || t.includes("payment") || t.includes("stripe")) return "marketing";
  if (t.includes("community") || t.includes("social") || t.includes("referral") || t.includes("share")) return "social";
  return "investing";
}

/** Prefer explicit category from API when we add it; otherwise derive from type. */
function resolvedCategory(n) {
  const raw = n?.inbox_category || n?.category;
  if (raw && ["investing", "social", "marketing"].includes(String(raw).toLowerCase())) {
    return String(raw).toLowerCase();
  }
  return inboxCategory(n?.type);
}

function thumbInitial(n) {
  const cat = resolvedCategory(n);
  if (cat === "marketing") return "M";
  if (cat === "social") return "S";
  const ch = String(n.title || "H").trim()[0];
  return ch ? ch.toUpperCase() : "H";
}

const TYPE_TO_PAGE = {
  marketplace: "marketplace",
  community: "marketplace",
  builder: "builder",
  alert: "dashboard",
  alert_pnl: "dashboard",
  alert_inactive: "dashboard",
  trade: "dashboard",
  payment: "settings",
  billing: "settings",
  weekly_report: "settings",
  system: "dashboard",
};

function formatTime(iso) {
  if (!iso) return "—";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  const now = Date.now();
  const diffMin = Math.round((now - t.getTime()) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 8) return `${diffDay}d ago`;
  return t.toLocaleString("en-US", { dateStyle: "short", timeStyle: "short" });
}

function typeBadge(type) {
  const t = String(type || "").toLowerCase();
  if (t.startsWith("alert")) return { label: "Alert", cls: "pill-amber" };
  if (t.includes("trade")) return { label: "Trade", cls: "pill-violet" };
  if (t.includes("market")) return { label: "Market", cls: "pill-violet" };
  if (t.includes("billing") || t.includes("payment")) return { label: "Billing", cls: "pill-green" };
  if (t.includes("weekly")) return { label: "Report", cls: "pill-gray" };
  return { label: t.toUpperCase().slice(0, 8) || "INFO", cls: "pill-gray" };
}

export default function NotificationBell({ user, onNav }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const [inboxTab, setInboxTab] = useState("all");
  const lastSeenIdsRef = useRef(new Set());
  const wrapperRef = useRef(null);

  const filteredItems = useMemo(() => {
    if (inboxTab === "all") return items;
    return items.filter((n) => resolvedCategory(n) === inboxTab);
  }, [items, inboxTab]);

  const loadList = useCallback(async () => {
    setLoading(true);
    const result = await listNotifications();
    setItems(result.items);
    setUnread(result.unread);
    setLoading(false);
  }, []);

  const refreshCount = useCallback(async () => {
    const { unread: n } = await getUnreadCount();
    setUnread(n);
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    refreshCount();
    const id = window.setInterval(refreshCount, POLL_MS);
    return () => window.clearInterval(id);
  }, [user, refreshCount]);

  // Load full list when opened, and try to send browser notification for any new arrivals
  useEffect(() => {
    if (!open) return;
    loadList();
  }, [open, loadList]);

  useEffect(() => {
    const fresh = items.filter((n) => !lastSeenIdsRef.current.has(n.id) && !n.is_read);
    if (fresh.length && lastSeenIdsRef.current.size > 0) {
      const top = fresh[0];
      sendNotification(top.title || "Hermes", String(top.message || "").slice(0, 140));
    }
    items.forEach((n) => lastSeenIdsRef.current.add(n.id));
  }, [items]);

  useEffect(() => {
    if (!open) return undefined;
    const onClick = (ev) => {
      if (!wrapperRef.current?.contains(ev.target)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const onClickItem = async (n) => {
    if (!n.is_read) {
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
      await markNotificationRead(n.id);
    }
    const target = TYPE_TO_PAGE[String(n.type || "").toLowerCase()];
    if (target && onNav) onNav(target);
    setOpen(false);
  };

  const onMarkAll = async () => {
    setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
    setUnread(0);
    await markAllNotificationsRead();
  };

  const openSettings = () => {
    setOpen(false);
    onNav?.("settings");
  };

  return (
    <div ref={wrapperRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="topbar-bell"
        aria-label="Notifications"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{ position: "relative" }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
          <path d="M10.4 20a2.1 2.1 0 0 0 3.2 0" />
        </svg>
        {unread > 0 ? (
          <span
            aria-label={`${unread} unread`}
            style={{
              position: "absolute",
              top: -4,
              right: -4,
              minWidth: 18,
              height: 18,
              padding: "0 5px",
              borderRadius: 999,
              background: "oklch(0.62 0.22 25)",
              color: "#fff",
              fontSize: 11,
              fontWeight: 700,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 10px oklch(0.62 0.22 25 / 0.55)",
            }}
          >
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="Notifications"
          className="notify-panel glass"
        >
          <header className="notify-panel-header">
            <strong className="notify-panel-title">Notifications</strong>
            <button
              type="button"
              className="notify-panel-gear"
              aria-label="Notification settings"
              title="Notification settings"
              onClick={openSettings}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
          </header>

          <div className="notify-panel-filters" role="tablist" aria-label="Notification categories">
            {INBOX_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                role="tab"
                aria-selected={inboxTab === f.id}
                className={`notify-pill${inboxTab === f.id ? " is-active" : ""}`}
                onClick={() => setInboxTab(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="notify-panel-toolbar">
            <button
              type="button"
              className="notify-mark-all"
              disabled={loading || unread === 0}
              onClick={onMarkAll}
            >
              {unread > 0 ? `Mark all as read (${unread})` : "All caught up"}
            </button>
          </div>

          <div className="notify-panel-list">
            {loading && items.length === 0 ? (
              <div className="text-3 fs-13 notify-panel-empty">Loading…</div>
            ) : null}
            {!loading && items.length === 0 ? (
              <div className="text-3 fs-13 notify-panel-empty">No notifications yet.</div>
            ) : null}
            {!loading && items.length > 0 && filteredItems.length === 0 ? (
              <div className="text-3 fs-13 notify-panel-empty">Nothing in this category yet.</div>
            ) : null}
            {filteredItems.map((n) => {
              const badge = typeBadge(n.type);
              const cat = resolvedCategory(n);
              return (
                <button
                  type="button"
                  key={n.id}
                  className={`notify-item${n.is_read ? "" : " is-unread"}`}
                  onClick={() => onClickItem(n)}
                >
                  <div className={`notify-item-thumb notify-item-thumb--${cat}`} aria-hidden="true">
                    {thumbInitial(n)}
                  </div>
                  <div className="notify-item-body">
                    <div className="notify-item-top">
                      <strong className="notify-item-title">{n.title || "—"}</strong>
                      <span className={`pill ${badge.cls} notify-item-badge`}>{badge.label}</span>
                    </div>
                    <div className="notify-item-message">{String(n.message || "").slice(0, 220)}</div>
                    <div className="notify-item-time">{formatTime(n.created_at)}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
