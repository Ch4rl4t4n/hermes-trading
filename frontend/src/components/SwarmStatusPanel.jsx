import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import swarmApi from "../api/swarm";

const SWARM_META = {
  orchestra: { icon: "🎼", color: "oklch(0.72 0.18 295)", label: "Orchestra" },
  trading: { icon: "📈", color: "oklch(0.78 0.16 155)", label: "Trade Execution" },
  intelligence: { icon: "🔍", color: "oklch(0.78 0.14 75)", label: "Intelligence" },
  marketing: { icon: "📣", color: "oklch(0.72 0.18 15)", label: "Marketing" },
  maintenance: { icon: "🔧", color: "oklch(0.65 0.12 220)", label: "Infrastructure" },
};
const RECOMMENDED_POLICY = {
  heartbeat_ttl_seconds: 60,
  stopped_to_paused_seconds: 1800,
  auto_resume_swarms: ["maintenance", "orchestra"],
};

function pct(part, total) {
  if (!total) return 0;
  return Math.min(100, Math.round((part * 100) / Math.max(1, total)));
}

function formatTimeAgo(value) {
  if (!value) return "n/a";
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return "n/a";
  const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function SwarmStatusPanel({ refreshIntervalMs = 5000, onError }) {
  const [status, setStatus] = useState(null);
  const [queue, setQueue] = useState(null);
  const [routingLog, setRoutingLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [copiedAction, setCopiedAction] = useState("");
  const errorReported = useRef(false);

  const fetchAll = useCallback(async () => {
    try {
      const [statusData, queueData, routingData] = await Promise.all([
        swarmApi.status(),
        swarmApi.queue(8),
        swarmApi.routingLog(10),
      ]);
      setStatus(statusData || null);
      setQueue(queueData || null);
      setRoutingLog(Array.isArray(routingData?.items) ? routingData.items : []);
      setLastUpdated(new Date());
      errorReported.current = false;
    } catch (err) {
      if (!errorReported.current) {
        errorReported.current = true;
        onError?.(err?.response?.data?.detail || err?.message || "Swarm v2 API unreachable");
      }
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, refreshIntervalMs);
    return () => clearInterval(timer);
  }, [fetchAll, refreshIntervalMs]);

  const swarms = useMemo(() => {
    const list = Array.isArray(status?.swarms) ? status.swarms : [];
    return list.map((row) => ({
      ...row,
      meta: SWARM_META[row.name] || { icon: "🤖", color: "oklch(0.7 0.1 280)", label: row.name },
    }));
  }, [status]);

  const queueStats = queue?.stats || {};
  const totalQueueItems = Object.values(queueStats).reduce((sum, value) => sum + Number(value || 0), 0);
  const policyDrift = useMemo(() => {
    const policy = status?.policy;
    if (!policy) return [];
    const drift = [];
    if (Number(policy.heartbeat_ttl_seconds || 0) !== RECOMMENDED_POLICY.heartbeat_ttl_seconds) {
      drift.push(
        `Heartbeat TTL is ${Number(policy.heartbeat_ttl_seconds || 0)}s (recommended ${RECOMMENDED_POLICY.heartbeat_ttl_seconds}s)`
      );
    }
    if (
      Number(policy.stopped_to_paused_seconds || 0) !==
      RECOMMENDED_POLICY.stopped_to_paused_seconds
    ) {
      drift.push(
        `Cleanup stopped is ${Number(policy.stopped_to_paused_seconds || 0)}s (recommended ${RECOMMENDED_POLICY.stopped_to_paused_seconds}s)`
      );
    }
    const liveSwarms = Array.isArray(policy.auto_resume_swarms)
      ? policy.auto_resume_swarms.map((s) => String(s).toLowerCase()).sort()
      : [];
    const expectedSwarms = [...RECOMMENDED_POLICY.auto_resume_swarms].sort();
    if (liveSwarms.join(",") !== expectedSwarms.join(",")) {
      drift.push(
        `Auto-resume swarms are [${liveSwarms.join(", ") || "none"}] (recommended [${expectedSwarms.join(", ")}])`
      );
    }
    return drift;
  }, [status]);
  const policyExportSnippets = useMemo(() => {
    const livePolicy = status?.policy || {};
    const recommendedSnippet = [
      `export HERMES_SWARM_HEARTBEAT_TTL=${RECOMMENDED_POLICY.heartbeat_ttl_seconds}`,
      `export HERMES_SWARM_STOPPED_TO_PAUSED_SECONDS=${RECOMMENDED_POLICY.stopped_to_paused_seconds}`,
      `export HERMES_SWARM_AUTO_RESUME_SWARMS=${RECOMMENDED_POLICY.auto_resume_swarms.join(",")}`,
    ].join("\n");
    const liveAutoResume = Array.isArray(livePolicy.auto_resume_swarms)
      ? livePolicy.auto_resume_swarms.join(",")
      : "";
    const liveSnippet = [
      `export HERMES_SWARM_HEARTBEAT_TTL=${Number(livePolicy.heartbeat_ttl_seconds || 0)}`,
      `export HERMES_SWARM_STOPPED_TO_PAUSED_SECONDS=${Number(livePolicy.stopped_to_paused_seconds || 0)}`,
      `export HERMES_SWARM_AUTO_RESUME_SWARMS=${liveAutoResume}`,
    ].join("\n");
    const remediationSnippet = [
      "cd /root/hermes",
      "# Apply recommended Swarm v2 runtime policy",
      ...recommendedSnippet.split("\n"),
      "",
      "# Verify policy over API",
      "TOKEN=\"$(venv/bin/python scripts/mint_fastapi_token.py 2>/dev/null || true)\"",
      "curl -s \"http://127.0.0.1:8001/api/v2/swarm/status\" -H \"Authorization: Bearer $TOKEN\"",
      "",
      "# Persist these env values in /root/hermes/.env and restart services via your deploy playbook.",
    ].join("\n");
    const envPatchSnippet = [
      `HERMES_SWARM_HEARTBEAT_TTL=${RECOMMENDED_POLICY.heartbeat_ttl_seconds}`,
      `HERMES_SWARM_STOPPED_TO_PAUSED_SECONDS=${RECOMMENDED_POLICY.stopped_to_paused_seconds}`,
      `HERMES_SWARM_AUTO_RESUME_SWARMS=${RECOMMENDED_POLICY.auto_resume_swarms.join(",")}`,
    ].join("\n");
    return { recommendedSnippet, liveSnippet, remediationSnippet, envPatchSnippet };
  }, [status]);

  const copyText = useCallback(async (text, key) => {
    try {
      if (!text) return;
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.focus();
        area.select();
        document.execCommand("copy");
        document.body.removeChild(area);
      }
      setCopiedAction(key);
      window.setTimeout(() => setCopiedAction(""), 1400);
    } catch {
      onError?.("Copy to clipboard failed.");
    }
  }, [onError]);

  return (
    <article className="glass swarm-v2-panel">
      <div className="row between">
        <div className="row gap-2">
          <strong>⚡ Swarm v2 live status</strong>
          {status?.redis_ok ? (
            <span className="pill pill-green">Redis OK</span>
          ) : (
            <span className="pill pill-red">Redis DOWN</span>
          )}
        </div>
        <span className="text-3 fs-12">
          {loading ? "Loading…" : lastUpdated ? `Updated ${formatTimeAgo(lastUpdated.toISOString())}` : "—"}
        </span>
      </div>

      <div className="swarm-v2-kpis">
        <div className="swarm-v2-kpi">
          <span className="text-3 fs-12">Agents</span>
          <strong>{status?.agents?.total ?? 0}</strong>
          <span className="text-3 fs-12">
            {status?.agents?.alive ?? 0} online · {status?.agents?.running ?? 0} running
          </span>
        </div>
        <div className="swarm-v2-kpi">
          <span className="text-3 fs-12">Queue</span>
          <strong>{queueStats.pending ?? 0}</strong>
          <span className="text-3 fs-12">
            {queueStats.assigned ?? 0} assigned · {queueStats.running ?? 0} running
          </span>
        </div>
        <div className="swarm-v2-kpi">
          <span className="text-3 fs-12">Completed</span>
          <strong>{queueStats.completed ?? 0}</strong>
          <span className="text-3 fs-12">
            {queueStats.failed ?? 0} failed · {queueStats.dead ?? 0} dead
          </span>
        </div>
        <div className="swarm-v2-kpi">
          <span className="text-3 fs-12">Throughput</span>
          <strong>{routingLog.length}</strong>
          <span className="text-3 fs-12">recent routes</span>
        </div>
      </div>

      {status?.policy ? (
        <div className="swarm-v2-policy glass-2">
          <div className="row between">
            <strong>Runtime policy</strong>
            <span className="text-3 fs-12">live configuration</span>
          </div>
          <div className="swarm-v2-policy-grid">
            <div>
              <span className="text-3 fs-12">Heartbeat TTL</span>
              <strong>{Number(status.policy.heartbeat_ttl_seconds || 0)}s</strong>
            </div>
            <div>
              <span className="text-3 fs-12">Cleanup stopped</span>
              <strong>{Number(status.policy.stopped_to_paused_seconds || 0)}s</strong>
            </div>
            <div>
              <span className="text-3 fs-12">Auto-resume swarms</span>
              <strong>
                {(status.policy.auto_resume_swarms || []).length
                  ? status.policy.auto_resume_swarms.join(", ")
                  : "none"}
              </strong>
            </div>
          </div>
          {policyDrift.length ? (
            <div className="swarm-v2-policy-warning">
              <div className="row between">
                <strong>Policy drift detected</strong>
                <span className="pill pill-red">{policyDrift.length}</span>
              </div>
              <ul>
                {policyDrift.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="swarm-v2-policy-ok">Policy matches the recommended baseline.</div>
          )}
          <div className="swarm-v2-policy-actions">
            <button
              type="button"
              className="swarm-v2-action-btn"
              onClick={() => copyText(policyExportSnippets.recommendedSnippet, "recommended")}
            >
              {copiedAction === "recommended" ? "Copied" : "Copy recommended exports"}
            </button>
            <button
              type="button"
              className="swarm-v2-action-btn"
              onClick={() => copyText(policyExportSnippets.liveSnippet, "live")}
            >
              {copiedAction === "live" ? "Copied" : "Copy live exports"}
            </button>
            <button
              type="button"
              className="swarm-v2-action-btn"
              onClick={() => copyText(policyExportSnippets.remediationSnippet, "remediation")}
            >
              {copiedAction === "remediation" ? "Copied" : "Copy remediation commands"}
            </button>
            <button
              type="button"
              className="swarm-v2-action-btn"
              onClick={() => copyText(policyExportSnippets.envPatchSnippet, "envpatch")}
            >
              {copiedAction === "envpatch" ? "Copied" : "Copy .env patch block"}
            </button>
          </div>
        </div>
      ) : null}

      <div className="swarm-v2-grid">
        {swarms.map((swarm) => {
          const alive = Number(swarm.alive_members || 0);
          const total = Number(swarm.members || 0);
          return (
            <div
              key={swarm.name}
              className="swarm-v2-card glass-2"
              style={{ borderLeft: `3px solid ${swarm.meta.color}` }}
            >
              <div className="row between">
                <strong>
                  {swarm.meta.icon} {swarm.meta.label}
                </strong>
                <span className={`pill ${alive > 0 ? "pill-green" : "pill-gray"}`}>
                  {alive}/{total}
                </span>
              </div>
              <div className="swarm-v2-meter">
                <i style={{ width: `${pct(alive, total)}%`, background: swarm.meta.color }} />
              </div>
              <div className="text-3 fs-12">
                running: {Number(swarm.running || 0)}
              </div>
            </div>
          );
        })}
        {swarms.length === 0 ? (
          <div className="text-3 fs-12">No swarms registered yet. Run /api/v2/swarm/seed.</div>
        ) : null}
      </div>

      <div className="swarm-v2-routing">
        <div className="row between">
          <strong>Routing decisions (DB persist)</strong>
          <span className="text-3 fs-12">{routingLog.length} records</span>
        </div>
        <div className="swarm-v2-routing-list">
          {routingLog.map((item, idx) => (
            <div key={`${item.task_id}-${idx}`} className="swarm-v2-routing-item">
              <span className={item.assigned_agent ? "router-ok" : "router-warn"}>
                {item.assigned_agent ? "✓" : "⚠"}
              </span>
              <span>
                <strong>{item.task_type}</strong> → {item.assigned_agent || "UNASSIGNED"}
                {item.assigned_swarm ? ` [${item.assigned_swarm}]` : ""}
              </span>
              <span className="pill pill-gray">score {Number(item.score || 0)}</span>
              <span className="text-3 fs-12">{formatTimeAgo(item.decided_at)}</span>
            </div>
          ))}
          {routingLog.length === 0 ? (
            <div className="text-3 fs-12">
              No routing decisions yet. Add a test task or wait for an orchestra tick.
            </div>
          ) : null}
        </div>
      </div>

      {totalQueueItems > 0 ? (
        <div className="swarm-v2-recent">
          <strong>Recent tasks ({queue?.recent?.length || 0})</strong>
          <div className="swarm-v2-task-list">
            {(queue?.recent || []).slice(0, 6).map((task) => (
              <div key={task.task_id} className="swarm-v2-task-row">
                <span className="pill pill-violet">P{task.priority || 0}</span>
                <span>
                  <strong>{task.task_type}</strong>
                  {task.assigned_to ? ` → ${task.assigned_to}` : ""}
                </span>
                <span className={`pill pill-${
                  task.status === "completed"
                    ? "green"
                    : task.status === "failed" || task.status === "dead"
                      ? "red"
                      : "gray"
                }`}>
                  {task.status}
                </span>
                <span className="text-3 fs-12">{formatTimeAgo(task.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}
