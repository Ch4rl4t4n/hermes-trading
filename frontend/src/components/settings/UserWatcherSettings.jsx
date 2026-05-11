import { useCallback, useEffect, useState } from "react";

import {
  fetchWatcherSettings,
  listBuilderAgents,
  resetWatcherSettings,
  saveWatcherSettings,
} from "../../api/watcherSettings";

const DAYS = [
  { v: 1, l: "Mon" },
  { v: 2, l: "Tue" },
  { v: 3, l: "Wed" },
  { v: 4, l: "Thu" },
  { v: 5, l: "Fri" },
  { v: 6, l: "Sat" },
  { v: 7, l: "Sun" },
];

function cfgField(ev, cast) {
  const raw = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
  if (cast === "int") return parseInt(String(raw), 10);
  if (cast === "float") return parseFloat(String(raw));
  return raw;
}

export default function UserWatcherSettings({ user, onToast }) {
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState("");
  const [tab, setTab] = useState("basic");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingCfg, setLoadingCfg] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState(null);
  const [cfg, setCfg] = useState(null);

  const tierAllowed = meta?.tier_limits?.allowed !== false;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingList(true);
      const { agents: rows, error: err } = await listBuilderAgents();
      if (cancelled) return;
      if (err) {
        setError("Failed to load agent list.");
        setAgents([]);
      } else {
        setAgents(rows);
        setError("");
        if (rows.length) setAgentId((prev) => prev || String(rows[0].id));
      }
      setLoadingList(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadCfg = useCallback(async () => {
    if (!agentId) return;
    setLoadingCfg(true);
    setError("");
    try {
      const data = await fetchWatcherSettings(agentId);
      setMeta(data);
      setCfg(data?.watcher_config || {});
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || "Failed to load watcher settings.");
      setCfg(null);
      setMeta(null);
    }
    setLoadingCfg(false);
  }, [agentId]);

  useEffect(() => {
    if (agentId) loadCfg();
  }, [agentId, loadCfg]);

  const setC = (key, value) => setCfg((prev) => ({ ...(prev || {}), [key]: value }));

  const toggleDay = (d) => {
    const cur = Array.isArray(cfg?.trading_days) ? [...cfg.trading_days] : [];
    const i = cur.indexOf(d);
    if (i >= 0) cur.splice(i, 1);
    else cur.push(d);
    cur.sort((a, b) => a - b);
    setC("trading_days", cur);
  };

  const onSave = async () => {
    if (!agentId || !cfg) return;
    setSaving(true);
    setError("");
    try {
      await saveWatcherSettings(agentId, cfg);
      onToast?.("Watcher settings saved.");
      await loadCfg();
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || "Save failed.";
      setError(msg);
      onToast?.(msg);
    }
    setSaving(false);
  };

  const onReset = async () => {
    if (!agentId) return;
    if (!window.confirm("Reset watcher defaults for this agent?")) return;
    setSaving(true);
    setError("");
    try {
      const data = await resetWatcherSettings(agentId);
      setCfg(data?.watcher_config || {});
      onToast?.("Defaults restored.");
      await loadCfg();
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || "Reset failed.";
      setError(msg);
      onToast?.(msg);
    }
    setSaving(false);
  };

  const lim = meta?.tier_limits || {};
  const canTrail = lim.trailing_stop === true;
  const canHours = lim.trading_hours_enabled === true;
  const canHighPri = lim.priority === "high";

  if (loadingList) {
    return (
      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <p className="text-3 fs-13">Loading your agents…</p>
      </article>
    );
  }

  if (!agents.length) {
    return (
      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <h4 style={{ marginTop: 0 }}>Watcher — your agents</h4>
        <p className="text-3 fs-13">
          You don’t have any user-built agents from Agent Builder yet. Create one in Builder — then you can adjust interval,
          risk, and trading hours here.
        </p>
      </article>
    );
  }

  return (
    <article className="glass settings-card" style={{ padding: 16, maxWidth: 760, position: "relative" }}>
      <div className="row between" style={{ alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
        <div>
          <h4 style={{ margin: 0 }}>Watcher — your agents</h4>
          <span className="text-3 fs-12">Paper trading cycle on the server (Hermes watcher)</span>
        </div>
        <label className="col fs-12 text-2" style={{ minWidth: 200 }}>
          Agent
          <select value={agentId} onChange={(e) => setAgentId(e.target.value)} disabled={loadingCfg}>
            {agents.map((a) => (
              <option key={a.id} value={String(a.id)}>
                {a.name || `Agent #${a.id}`} ({a.symbol || "?"})
              </option>
            ))}
          </select>
        </label>
      </div>

      {!tierAllowed ? (
        <div className="watcher-lock-overlay" style={{ display: "flex", borderRadius: 12 }}>
          <div className="glass" style={{ padding: 16, maxWidth: 420 }}>
            <strong>Pro tier and up</strong>
            <p className="text-3 fs-13" style={{ marginBottom: 12 }}>
              Custom watcher settings are locked on the basic tier. Upgrade to Pro or Elite to edit intervals,
              risk, and the trading calendar.
            </p>
            <span className="pill pill-gray">{String(user?.tier || "basic").toUpperCase()}</span>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="glass" style={{ padding: 10, marginBottom: 10, border: "1px solid oklch(0.65 0.2 25 / 0.5)" }}>
          <span className="fs-13">{error}</span>
        </div>
      ) : null}

      {loadingCfg || !cfg ? (
        <p className="text-3 fs-13">Loading configuration…</p>
      ) : (
        <>
          <div className="watcher-tabs" role="tablist">
            {[
              { id: "basic", label: "Basics" },
              { id: "hours", label: "Time windows" },
              { id: "risk", label: "Risk" },
              { id: "alerts", label: "Signals" },
            ].map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`watcher-tab-btn ${tab === t.id ? "active" : ""}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className={`watcher-tab ${tab === "basic" ? "active" : ""}`}>
            <div className="watcher-grid" style={{ marginTop: 12 }}>
              <label className="watcher-row fs-12 text-2">
                Cycle interval (s)
                <input
                  type="number"
                  min={lim.polling_interval_sec?.min}
                  max={lim.polling_interval_sec?.max}
                  value={cfg.polling_interval_sec ?? ""}
                  onChange={(e) => setC("polling_interval_sec", cfgField(e, "int"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="watcher-row fs-12 text-2">
                Priority
                <select
                  value={cfg.priority || "normal"}
                  onChange={(e) => setC("priority", e.target.value)}
                  disabled={!tierAllowed || !canHighPri}
                >
                  <option value="normal">normal</option>
                  <option value="high">high (Elite)</option>
                </select>
              </label>
              <label className="watcher-row fs-12 text-2">
                Max position (%)
                <input
                  type="number"
                  step="0.1"
                  min={lim.max_position_size_pct?.min}
                  max={lim.max_position_size_pct?.max}
                  value={cfg.max_position_size_pct ?? ""}
                  onChange={(e) => setC("max_position_size_pct", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="watcher-row fs-12 text-2">
                Max trades / day
                <input
                  type="number"
                  min={lim.max_daily_trades?.min}
                  max={lim.max_daily_trades?.max}
                  value={cfg.max_daily_trades ?? ""}
                  onChange={(e) => setC("max_daily_trades", cfgField(e, "int"))}
                  disabled={!tierAllowed}
                />
              </label>
            </div>
          </div>

          <div className={`watcher-tab ${tab === "hours" ? "active" : ""}`}>
            <label className="row gap-2 fs-13" style={{ marginTop: 12, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={Boolean(cfg.trading_hours_enabled)}
                onChange={(e) => setC("trading_hours_enabled", cfgField(e))}
                disabled={!tierAllowed || !canHours}
              />
              Limit trading to a time window (UTC)
            </label>
            {!canHours ? (
              <p className="text-3 fs-12">Time windows require at least Pro tier.</p>
            ) : (
              <div className="watcher-grid" style={{ marginTop: 12 }}>
                <label className="watcher-row fs-12 text-2">
                  From (UTC)
                  <input
                    type="time"
                    value={cfg.trading_hours_start || "09:00"}
                    onChange={(e) => setC("trading_hours_start", e.target.value)}
                    disabled={!tierAllowed || !cfg.trading_hours_enabled}
                  />
                </label>
                <label className="watcher-row fs-12 text-2">
                  To (UTC)
                  <input
                    type="time"
                    value={cfg.trading_hours_end || "17:00"}
                    onChange={(e) => setC("trading_hours_end", e.target.value)}
                    disabled={!tierAllowed || !cfg.trading_hours_enabled}
                  />
                </label>
              </div>
            )}
            <div className="watcher-days" style={{ marginTop: 14 }}>
              {DAYS.map((d) => (
                <button
                  key={d.v}
                  type="button"
                  className={`watcher-day ${cfg.trading_days?.includes(d.v) ? "active" : ""}`}
                  style={
                    cfg.trading_days?.includes(d.v)
                      ? { borderColor: "oklch(0.72 0.18 295 / 0.65)", color: "var(--text)" }
                      : {}
                  }
                  onClick={() => tierAllowed && canHours && cfg.trading_hours_enabled && toggleDay(d.v)}
                  disabled={!tierAllowed || !canHours || !cfg.trading_hours_enabled}
                >
                  {d.l}
                </button>
              ))}
            </div>
            <div className="watcher-presets">
              <button
                type="button"
                className="pill pill-gray"
                style={{ border: "none", fontSize: 11 }}
                disabled={!tierAllowed || !canHours || !cfg.trading_hours_enabled}
                onClick={() => setC("trading_days", [1, 2, 3, 4, 5])}
              >
                Mon–Fri
              </button>
              <button
                type="button"
                className="pill pill-gray"
                style={{ border: "none", fontSize: 11 }}
                disabled={!tierAllowed || !canHours || !cfg.trading_hours_enabled}
                onClick={() => setC("trading_days", [1, 2, 3, 4, 5, 6, 7])}
              >
                7 days
              </button>
            </div>
          </div>

          <div className={`watcher-tab ${tab === "risk" ? "active" : ""}`}>
            <div className="watcher-grid" style={{ marginTop: 12 }}>
              <label className="watcher-row fs-12 text-2">
                Stop-loss (%)
                <input
                  type="number"
                  step="0.1"
                  min={lim.stop_loss_pct?.min}
                  max={lim.stop_loss_pct?.max}
                  value={cfg.stop_loss_pct ?? ""}
                  onChange={(e) => setC("stop_loss_pct", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="watcher-row fs-12 text-2">
                Take-profit (%)
                <input
                  type="number"
                  step="0.1"
                  min={lim.take_profit_pct?.min}
                  max={lim.take_profit_pct?.max}
                  value={cfg.take_profit_pct ?? ""}
                  onChange={(e) => setC("take_profit_pct", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="row gap-2 fs-13" style={{ alignItems: "center", gridColumn: "1 / -1" }}>
                <input
                  type="checkbox"
                  checked={Boolean(cfg.trailing_stop)}
                  onChange={(e) => setC("trailing_stop", cfgField(e))}
                  disabled={!tierAllowed || !canTrail}
                />
                Trailing stop {canTrail ? "" : "(Elite)"}
              </label>
              {canTrail ? (
                <label className="watcher-row fs-12 text-2">
                  Trailing (%)
                  <input
                    type="number"
                    step="0.1"
                    value={cfg.trailing_stop_pct ?? ""}
                    onChange={(e) => setC("trailing_stop_pct", cfgField(e, "float"))}
                    disabled={!tierAllowed || !cfg.trailing_stop}
                  />
                </label>
              ) : null}
              <label className="watcher-row fs-12 text-2">
                Max daily drawdown (%)
                <input
                  type="number"
                  step="0.1"
                  min={lim.max_daily_drawdown_pct?.min}
                  max={lim.max_daily_drawdown_pct?.max}
                  value={cfg.max_daily_drawdown_pct ?? ""}
                  onChange={(e) => setC("max_daily_drawdown_pct", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="watcher-row fs-12 text-2">
                Momentum lookback
                <input
                  type="number"
                  value={cfg.momentum_lookback ?? ""}
                  onChange={(e) => setC("momentum_lookback", cfgField(e, "int"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="watcher-row fs-12 text-2">
                Mean-reversion threshold
                <input
                  type="number"
                  step="0.1"
                  value={cfg.mean_reversion_threshold ?? ""}
                  onChange={(e) => setC("mean_reversion_threshold", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
            </div>
          </div>

          <div className={`watcher-tab ${tab === "alerts" ? "active" : ""}`}>
            <div className="watcher-grid" style={{ marginTop: 12 }}>
              <label className="watcher-row fs-12 text-2">
                P&amp;L drop alert (%)
                <input
                  type="number"
                  step="0.1"
                  value={cfg.alert_pnl_drop_pct ?? ""}
                  onChange={(e) => setC("alert_pnl_drop_pct", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
              <label className="watcher-row fs-12 text-2">
                Target price alert (0 = off)
                <input
                  type="number"
                  step="0.01"
                  value={cfg.alert_price_target ?? ""}
                  onChange={(e) => setC("alert_price_target", cfgField(e, "float"))}
                  disabled={!tierAllowed}
                />
              </label>
            </div>
          </div>

          <div className="row gap-2" style={{ marginTop: 18, flexWrap: "wrap" }}>
            <button type="button" className="pill pill-violet" style={{ border: "none" }} disabled={!tierAllowed || saving} onClick={onSave}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button type="button" className="pill pill-gray" style={{ border: "none" }} disabled={!tierAllowed || saving} onClick={onReset}>
              Restore defaults
            </button>
          </div>
        </>
      )}
    </article>
  );
}
