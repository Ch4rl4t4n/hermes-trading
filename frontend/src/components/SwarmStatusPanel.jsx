import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import swarmApi from "../api/swarm";

const SWARM_META = {
  orchestra: { icon: "🎼", color: "oklch(0.72 0.18 295)", label: "Orchestra" },
  trading: { icon: "📈", color: "oklch(0.78 0.16 155)", label: "Trade Execution" },
  intelligence: { icon: "🔍", color: "oklch(0.78 0.14 75)", label: "Intelligence" },
  marketing: { icon: "📣", color: "oklch(0.72 0.18 15)", label: "Marketing" },
  maintenance: { icon: "🔧", color: "oklch(0.65 0.12 220)", label: "Infrastructure" },
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

  return (
    <article className="glass swarm-v2-panel">
      <div className="row between">
        <div className="row gap-2">
          <strong>⚡ Swarm v2 Live Status</strong>
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
            {status?.agents?.alive ?? 0} alive · {status?.agents?.running ?? 0} running
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
          <strong>Routing Decisions (DB-persistent)</strong>
          <span className="text-3 fs-12">{routingLog.length} entries</span>
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
              No routing decisions yet. Push a test task or wait for orchestra ticks.
            </div>
          ) : null}
        </div>
      </div>

      {totalQueueItems > 0 ? (
        <div className="swarm-v2-recent">
          <strong>Recent Tasks ({queue?.recent?.length || 0})</strong>
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
