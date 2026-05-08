import { useCallback, useEffect, useMemo, useState } from "react";
import client from "../api/client";
import SwarmBuilderModal from "../components/SwarmBuilderModal";
import SwarmStatusPanel from "../components/SwarmStatusPanel";
import swarmApi from "../api/swarm";

const DEFAULT_SWARMS = [
  { swarm_name: "orchestra", display_name: "Orchestra", icon: "🎼", description: "Master coordinator - routes tasks to other swarms", color: "oklch(0.72 0.18 295)" },
  { swarm_name: "trading", display_name: "Trading", icon: "📈", description: "Executes and monitors trading strategies", color: "oklch(0.78 0.16 155)" },
  { swarm_name: "intelligence", display_name: "Intelligence", icon: "🔍", description: "Research, news analysis, trend detection", color: "oklch(0.78 0.14 75)" },
  { swarm_name: "marketing", display_name: "Marketing", icon: "📣", description: "Social media, content, SEO, growth", color: "oklch(0.72 0.18 15)" },
  { swarm_name: "maintenance", display_name: "Maintenance", icon: "🔧", description: "Infrastructure, monitoring, security", color: "oklch(0.65 0.12 220)" },
];

function formatUptime(seconds) {
  const s = Math.max(0, Number(seconds || 0));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function formatAgo(value) {
  if (!value) return "n/a";
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return "n/a";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  return `${Math.floor(diffSec / 3600)}h ago`;
}

function apiMessage(error, fallback) {
  if (error?.response?.status === 403) return "Admin access required";
  return error?.userMessage || error?.response?.data?.error || fallback;
}

const MAX_DIRECTORY_ROWS = 100;
const ROUTER_CAP_OPTIONS = [
  "trading",
  "momentum",
  "crypto",
  "risk",
  "portfolio",
  "research",
  "news",
  "analysis",
  "trends",
  "marketing",
  "content",
  "seo",
  "monitoring",
  "security",
  "routing",
  "orchestration",
  "reporting",
];

export default function AdminSwarm({ onNav, onToast }) {
  const [registryData, setRegistryData] = useState({ redis_agents: [], db_agents: [] });
  const [queueStats, setQueueStats] = useState({ pending: 0, agents_alive: 0, agents_total: 0 });
  const [systemHealth, setSystemHealth] = useState({ cpu_percent: 0, memory_percent: 0, redis: false, db: false, queue_pending: 0 });
  const [queueTasks, setQueueTasks] = useState([]);
  const [expandedSwarms, setExpandedSwarms] = useState({});
  const [directoryOpen, setDirectoryOpen] = useState(true);
  const [search, setSearch] = useState("");
  const [swarmFilter, setSwarmFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [taskType, setTaskType] = useState("generic");
  const [taskPayloadText, setTaskPayloadText] = useState("{\"source\":\"war-room\"}");
  const [taskPriority, setTaskPriority] = useState(5);
  const [uptimeSec, setUptimeSec] = useState(0);
  const [showBuilder, setShowBuilder] = useState(false);
  const [apiError, setApiError] = useState("");
  const [isBulkUpdating, setIsBulkUpdating] = useState(false);
  const [isPushingTask, setIsPushingTask] = useState(false);
  const [routerOpen, setRouterOpen] = useState(true);
  const [routingLog, setRoutingLog] = useState([]);
  const [routingTaskType, setRoutingTaskType] = useState("manual");
  const [routingPriority, setRoutingPriority] = useState(5);
  const [routingPayload, setRoutingPayload] = useState("{\"source\":\"war-room-router\"}");
  const [routingCaps, setRoutingCaps] = useState([]);
  const [simulateTaskType, setSimulateTaskType] = useState("analysis");
  const [simulateCaps, setSimulateCaps] = useState([]);
  const [simulateResult, setSimulateResult] = useState(null);
  const [routingBusy, setRoutingBusy] = useState(false);

  const mergeAgents = useMemo(() => {
    const redisById = new Map((registryData.redis_agents || []).map((agent) => [String(agent.agent_id), agent]));
    return (registryData.db_agents || []).map((dbAgent) => {
      const id = String(dbAgent.agent_id || "");
      const redisAgent = redisById.get(id) || {};
      return {
        ...dbAgent,
        ...redisAgent,
        agent_id: id,
        swarm_name: redisAgent.swarm || dbAgent.swarm_name || "default",
        capabilities: Array.isArray(redisAgent.capabilities) ? redisAgent.capabilities : Array.isArray(dbAgent.capabilities) ? dbAgent.capabilities : [],
        config: typeof redisAgent.config === "object" && redisAgent.config ? redisAgent.config : (dbAgent.config || {}),
        alive: Boolean(redisAgent.alive),
      };
    });
  }, [registryData]);

  const fetchRegistry = useCallback(async () => {
    const { data } = await client.get("/api/admin/registry/agents");
    setRegistryData({
      redis_agents: Array.isArray(data?.redis_agents) ? data.redis_agents : [],
      db_agents: Array.isArray(data?.db_agents) ? data.db_agents : [],
    });
    setQueueStats(data?.queue_stats || { pending: 0, agents_alive: 0, agents_total: 0 });
    setApiError("");
  }, []);

  const fetchQueueTasks = useCallback(async () => {
    const { data } = await client.get("/api/admin/queue/tasks");
    setQueueTasks(Array.isArray(data) ? data : []);
  }, []);

  const fetchSystemHealth = useCallback(async () => {
    const { data } = await client.get("/api/admin/system/health");
    setSystemHealth(data || {});
  }, []);

  const fetchRoutingLog = useCallback(async () => {
    const { data } = await client.get("/api/admin/router/log?limit=10");
    setRoutingLog(Array.isArray(data) ? data : []);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchRegistry().catch((error) => {
        const msg = apiMessage(error, "Unable to load registry");
        setApiError(msg);
        onToast?.(msg);
      });
      fetchQueueTasks().catch(() => setQueueTasks([]));
      fetchSystemHealth().catch((error) => {
        const msg = apiMessage(error, "Unable to load system health");
        setApiError(msg);
      });
      fetchRoutingLog().catch(() => setRoutingLog([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchQueueTasks, fetchRegistry, fetchRoutingLog, fetchSystemHealth, onToast]);

  useEffect(() => {
    const queueTimer = setInterval(() => fetchQueueTasks().catch(() => {}), 5000);
    const summaryTimer = setInterval(() => {
      fetchRegistry().catch(() => {});
      fetchSystemHealth().catch(() => {});
    }, 10000);
    const routerTimer = setInterval(() => {
      fetchRoutingLog().catch(() => {});
    }, 10000);
    const uptimeTimer = setInterval(() => setUptimeSec((prev) => prev + 1), 1000);
    return () => {
      clearInterval(queueTimer);
      clearInterval(summaryTimer);
      clearInterval(routerTimer);
      clearInterval(uptimeTimer);
    };
  }, [fetchQueueTasks, fetchRegistry, fetchRoutingLog, fetchSystemHealth]);

  function closeTaskModal() {
    setShowTaskModal(false);
    setTaskType("generic");
    setTaskPayloadText("{\"source\":\"war-room\"}");
    setTaskPriority(5);
  }

  useEffect(() => {
    const handler = (event) => {
      if (event.key !== "Escape") return;
      if (showTaskModal) closeTaskModal();
      if (selectedAgent) setSelectedAgent(null);
      if (showBuilder) setShowBuilder(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedAgent, showBuilder, showTaskModal]);

  const filteredAgents = useMemo(() => {
    return mergeAgents.filter((agent) => {
      const hay = `${agent.agent_id} ${agent.name || ""}`.toLowerCase();
      if (search && !hay.includes(search.toLowerCase())) return false;
      if (swarmFilter !== "all" && String(agent.swarm_name) !== swarmFilter) return false;
      if (statusFilter !== "all" && String(agent.status || "idle").toLowerCase() !== statusFilter) return false;
      return true;
    }).slice(0, MAX_DIRECTORY_ROWS);
  }, [mergeAgents, search, statusFilter, swarmFilter]);

  const updateStatus = async (agentId, status) => {
    try {
      await client.post(`/api/admin/registry/agents/${agentId}/status`, { status });
      onToast?.(`Agent ${agentId} set to ${status}`);
      fetchRegistry().catch(() => {});
    } catch (error) {
      onToast?.(apiMessage(error, `Failed to set ${status} for ${agentId}`));
    }
  };

  const bulkStatusUpdate = async (status, agents) => {
    setIsBulkUpdating(true);
    const jobs = (agents || []).map((agent) => updateStatus(agent.agent_id, status));
    await Promise.allSettled(jobs);
    fetchRegistry().catch(() => {});
    setIsBulkUpdating(false);
  };

  const emergencyStop = async () => {
    if (!window.confirm("Are you sure? This stops ALL agents.")) return;
    await bulkStatusUpdate("stopped", mergeAgents);
    onToast?.("Emergency stop triggered");
  };

  const pushTask = async () => {
    let payload;
    try {
      payload = taskPayloadText.trim() ? JSON.parse(taskPayloadText) : {};
    } catch {
      onToast?.("Payload must be valid JSON");
      return;
    }
    setIsPushingTask(true);
    try {
      await client.post("/api/admin/queue/push", {
        task_type: taskType || "generic",
        payload,
        priority: Number(taskPriority || 5),
      });
      onToast?.("Task queued");
      closeTaskModal();
      fetchQueueTasks().catch(() => {});
      fetchRegistry().catch(() => {});
    } catch {
      onToast?.("Failed to queue task");
    } finally {
      setIsPushingTask(false);
    }
  };

  const toggleCap = (current, setCurrent, cap) => {
    setCurrent((prev) => (prev.includes(cap) ? prev.filter((item) => item !== cap) : [...prev, cap]));
  };

  const manualRouteNow = async () => {
    let payload;
    try {
      payload = routingPayload.trim() ? JSON.parse(routingPayload) : {};
    } catch {
      onToast?.("Router payload must be valid JSON");
      return;
    }
    setRoutingBusy(true);
    try {
      const data = await swarmApi.dispatch({
        taskType: routingTaskType || "manual",
        payload,
        priority: Number(routingPriority || 5),
        requiredCapabilities: routingCaps,
      });
      const dispatched = data?.dispatched_to_dramatiq ? " · Dramatiq dispatched" : "";
      onToast?.(
        data?.assigned_agent
          ? `Routed to ${data.assigned_agent}${dispatched}`
          : "Task queued without assignment",
      );
      fetchRoutingLog().catch(() => {});
      fetchQueueTasks().catch(() => {});
      fetchRegistry().catch(() => {});
    } catch (error) {
      onToast?.(apiMessage(error, "Manual route failed"));
    } finally {
      setRoutingBusy(false);
    }
  };

  const simulateRouteNow = async () => {
    setRoutingBusy(true);
    try {
      const data = await swarmApi.simulate({
        taskType: simulateTaskType || "generic",
        requiredCapabilities: simulateCaps,
      });
      setSimulateResult({
        agent_name: data?.agent_name,
        agent_id: data?.would_assign_to,
        swarm: data?.swarm,
        score: data?.score,
        reason: data?.reason,
      });
    } catch (error) {
      onToast?.(apiMessage(error, "Simulation failed"));
    } finally {
      setRoutingBusy(false);
    }
  };

  return (
    <section className="page-content">
      <div className="warroom-head glass">
        <button type="button" className="share-btn" onClick={() => onNav?.("admin")}>← Admin</button>
        <strong>Swarm War Room</strong>
        <div className="row gap-2">
          <button type="button" className="share-btn" onClick={() => setShowBuilder(true)}>+ Create New Swarm</button>
          <span className="warroom-live"><span className="warroom-live-dot" />LIVE</span>
        </div>
      </div>

      <div className="warroom-banner glass-2">
        <span className="warroom-live"><span className="warroom-live-dot" />LIVE</span>
        <span>Queue: {queueStats.pending || 0} pending</span>
        <span>{queueStats.agents_alive || 0} agents alive</span>
        <span>{queueStats.agents_total || 0} total agents</span>
        <span>Uptime: {formatUptime(uptimeSec)}</span>
      </div>

      <SwarmStatusPanel
        refreshIntervalMs={5000}
        onError={(message) => {
          if (message) onToast?.(message);
        }}
      />

      <div className="warroom-layout">
        <div className="col gap-3">
          <article className="glass warroom-controls">
            <div className="section-title">Global Controls</div>
            {apiError ? <div className="text-3 fs-12" style={{ marginBottom: 8 }}>{apiError}</div> : null}
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              <button type="button" className="pill pill-green" disabled={isBulkUpdating} onClick={() => bulkStatusUpdate("running", mergeAgents)}>Start All</button>
              <button type="button" className="pill pill-gray" disabled={isBulkUpdating} onClick={() => bulkStatusUpdate("paused", mergeAgents)}>Pause All</button>
              <button type="button" className="pill pill-red" disabled={isBulkUpdating} onClick={() => bulkStatusUpdate("stopped", mergeAgents)}>Stop All</button>
              <button type="button" className="pill pill-red warroom-emergency" disabled={isBulkUpdating} onClick={emergencyStop}>Emergency Stop</button>
            </div>
          </article>

          <div className="warroom-swarm-grid">
            {(() => {
              const known = new Set(DEFAULT_SWARMS.map((s) => s.swarm_name));
              const seen = new Set();
              const customSwarms = [];
              for (const agent of mergeAgents) {
                const sn = String(agent.swarm_name || "").trim();
                if (!sn || known.has(sn) || seen.has(sn)) continue;
                seen.add(sn);
                const meta = (agent.metadata && typeof agent.metadata === "object") ? agent.metadata : {};
                customSwarms.push({
                  swarm_name: sn,
                  display_name: meta.display_name || meta.swarm_display_name || sn,
                  icon: meta.icon || "🤖",
                  description: meta.description || "Custom swarm built via Prompt Builder",
                  color: meta.color || "oklch(0.72 0.18 295)",
                });
              }
              return [...DEFAULT_SWARMS, ...customSwarms];
            })().map((swarm) => {
              const agents = mergeAgents.filter((agent) => String(agent.swarm_name) === swarm.swarm_name);
              const alive = agents.filter((agent) => Boolean(agent.alive)).length;
              const completed = agents.reduce((sum, agent) => sum + Number(agent.tasks_completed || 0), 0);
              const failed = agents.reduce((sum, agent) => sum + Number(agent.tasks_failed || 0), 0);
              const expanded = Boolean(expandedSwarms[swarm.swarm_name]);
              return (
                <article key={swarm.swarm_name} className="glass-2 warroom-swarm-card" style={{ borderLeft: `3px solid ${swarm.color}` }}>
                  <div className="row between">
                    <strong>{swarm.icon} {swarm.display_name}</strong>
                    <span className={`pill ${alive > 0 ? "pill-green" : "pill-red"}`}>{alive > 0 ? "active" : "down"}</span>
                  </div>
                  <div className="text-3 fs-12" style={{ marginTop: 6 }}>{swarm.description}</div>
                  <div className="warroom-swarm-meta">Agents: {alive}/{agents.length} alive</div>
                  <div className="warroom-swarm-meta">Tasks today: {completed} | Errors: {failed}</div>
                  <div className="row gap-2" style={{ marginTop: 10, flexWrap: "wrap" }}>
                    <button type="button" className="pill pill-gray" onClick={() => setExpandedSwarms((prev) => ({ ...prev, [swarm.swarm_name]: !prev[swarm.swarm_name] }))}>
                      {expanded ? "View Agents ▲" : "View Agents ▼"}
                    </button>
                    <button type="button" className="pill pill-violet" onClick={() => onToast?.("Add Agent flow is coming next")}>+ Add Agent</button>
                    <button type="button" className="pill pill-gray" onClick={() => bulkStatusUpdate("paused", agents)}>⏸ Pause</button>
                    {!["orchestra", "trading", "intelligence", "marketing", "maintenance"].includes(swarm.swarm_name) ? (
                      <button
                        type="button"
                        className="pill pill-red"
                        onClick={async () => {
                          if (!window.confirm(`Delete swarm "${swarm.swarm_name}" and all its agents?`)) return;
                          try {
                            await client.delete(`/api/admin/swarm-builder/swarms/${encodeURIComponent(swarm.swarm_name)}`);
                            onToast?.(`Swarm ${swarm.swarm_name} deleted`);
                            fetchRegistry().catch(() => {});
                          } catch (error) {
                            onToast?.(apiMessage(error, "Delete failed"));
                          }
                        }}
                      >
                        🗑 Delete Swarm
                      </button>
                    ) : null}
                  </div>
                  {expanded ? (
                    <div className="warroom-inline-list">
                      {agents.map((agent) => (
                        <div key={agent.agent_id} className="warroom-inline-agent">
                          <span className={`swarm-dot ${agent.alive ? "swarm-dot-alive" : "swarm-dot-dead"}`} />
                          <button type="button" className="warroom-linklike" onClick={() => setSelectedAgent(agent)}>{agent.agent_id}</button>
                          <span className="text-3">{agent.name || "Unnamed"}</span>
                          <span className="pill pill-gray">{String(agent.status || "idle")}</span>
                          <div className="row gap-1">
                            <button type="button" className="pill pill-green" onClick={() => updateStatus(agent.agent_id, "running")}>▶</button>
                            <button type="button" className="pill pill-gray" onClick={() => updateStatus(agent.agent_id, "paused")}>⏸</button>
                            <button type="button" className="pill pill-red" onClick={() => updateStatus(agent.agent_id, "stopped")}>⏹</button>
                            <button type="button" className="pill pill-violet" onClick={() => setSelectedAgent(agent)}>⚙</button>
                          </div>
                        </div>
                      ))}
                      {agents.length === 0 ? <div className="text-3 fs-12">No agents in this swarm.</div> : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </div>

        <aside className="col gap-3">
          <article className="glass warroom-right-panel">
            <div className="row between">
              <div className="section-title">Task Queue</div>
              <span className="pill pill-violet">pending: {queueStats.pending || 0}</span>
            </div>
            <div className="warroom-task-list">
              {queueTasks.slice(0, 8).map((task) => (
                <div key={task.task_id} className="warroom-task-item">
                  <span>↑ P:{task.priority || 0}</span>
                  <strong>{task.task_type}</strong>
                  <span className="text-3">{formatAgo(task.created_at)}</span>
                </div>
              ))}
              {queueTasks.length === 0 ? <div className="text-3 fs-12">No queued tasks.</div> : null}
            </div>
            <button type="button" className="share-btn" onClick={() => setShowTaskModal(true)}>+ Push Test Task</button>
          </article>

          <article className="glass warroom-right-panel">
            <div className="section-title">System Health</div>
            <div className="warroom-health-row"><span>CPU</span><div className="warroom-meter"><i style={{ width: `${Math.min(100, Number(systemHealth.cpu_percent || 0))}%` }} /></div><span>{Math.round(Number(systemHealth.cpu_percent || 0))}%</span></div>
            <div className="warroom-health-row"><span>Memory</span><div className="warroom-meter"><i style={{ width: `${Math.min(100, Number(systemHealth.memory_percent || 0))}%` }} /></div><span>{Math.round(Number(systemHealth.memory_percent || 0))}%</span></div>
            <div className="warroom-health-kv"><span>Redis</span><span>{systemHealth.redis ? "connected" : "down"}</span></div>
            <div className="warroom-health-kv"><span>DB</span><span>{systemHealth.db ? "connected" : "down"}</span></div>
            <div className="warroom-health-kv"><span>Queue</span><span>{systemHealth.queue_pending || 0} pending</span></div>
          </article>
        </aside>
      </div>

      <article className="glass warroom-directory">
        <button type="button" className="warroom-directory-toggle" onClick={() => setDirectoryOpen((prev) => !prev)}>
          {directoryOpen ? "▼" : "▶"} Agent Directory - {mergeAgents.length} agents
        </button>
        {directoryOpen ? (
          <>
            <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 10 }}>
              <input className="bt-field warroom-search" placeholder="Search by agent ID or name..." value={search} onChange={(event) => setSearch(event.target.value)} />
              {["all", ...DEFAULT_SWARMS.map((swarm) => swarm.swarm_name)].map((swarm) => (
                <button key={swarm} type="button" className={`pill ${swarmFilter === swarm ? "pill-violet" : "pill-gray"}`} onClick={() => setSwarmFilter(swarm)}>
                  {swarm === "all" ? "All" : swarm}
                </button>
              ))}
              {["all", "running", "idle", "paused", "error", "stopped"].map((status) => (
                <button key={status} type="button" className={`pill ${statusFilter === status ? "pill-violet" : "pill-gray"}`} onClick={() => setStatusFilter(status)}>
                  {status[0].toUpperCase() + status.slice(1)}
                </button>
              ))}
            </div>
            <div className="leaderboard-table-wrap" style={{ marginTop: 10 }}>
              <table className="leaderboard-table" style={{ minWidth: 1100 }}>
                <thead>
                  <tr>
                    <th>Agent ID</th><th>Name</th><th>Swarm</th><th>Capabilities</th><th>Status</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAgents.map((agent) => (
                    <tr key={agent.agent_id} onClick={() => setSelectedAgent(agent)} className="warroom-table-row">
                      <td><span className={`swarm-dot ${agent.alive ? "swarm-dot-alive" : "swarm-dot-dead"}`} /> {agent.agent_id}</td>
                      <td>{agent.name || "Unnamed"}</td>
                      <td>{agent.swarm_name}</td>
                      <td>{(agent.capabilities || []).slice(0, 3).join(", ") || "-"}</td>
                      <td>{String(agent.status || "idle")}</td>
                      <td>
                        <div className="row gap-1">
                          <button type="button" className="pill pill-green" onClick={(event) => { event.stopPropagation(); updateStatus(agent.agent_id, "running"); }}>▶</button>
                          <button type="button" className="pill pill-gray" onClick={(event) => { event.stopPropagation(); updateStatus(agent.agent_id, "paused"); }}>⏸</button>
                          <button type="button" className="pill pill-violet" onClick={(event) => { event.stopPropagation(); setSelectedAgent(agent); }}>⚙</button>
                          <button type="button" className="pill pill-red" onClick={(event) => { event.stopPropagation(); updateStatus(agent.agent_id, "stopped"); }}>🗑</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {mergeAgents.length > MAX_DIRECTORY_ROWS ? (
              <div className="text-3 fs-12" style={{ marginTop: 8 }}>
                Showing first {MAX_DIRECTORY_ROWS} agents. Narrow filters to see specific entries.
              </div>
            ) : null}
          </>
        ) : null}
      </article>

      <article className="glass warroom-router">
        <button type="button" className="warroom-directory-toggle" onClick={() => setRouterOpen((prev) => !prev)}>
          {routerOpen ? "▼" : "▶"} Task Router
        </button>
        {routerOpen ? (
          <div className="warroom-router-body">
            <div className="warroom-router-grid">
              <section className="glass-2 warroom-router-panel">
                <div className="section-title">Manual Route Task</div>
                <label className="fs-12 text-3">Task type</label>
                <input className="bt-field" value={routingTaskType} onChange={(event) => setRoutingTaskType(event.target.value)} />
                <label className="fs-12 text-3">Required capabilities</label>
                <div className="row gap-1" style={{ flexWrap: "wrap" }}>
                  {ROUTER_CAP_OPTIONS.map((cap) => (
                    <button
                      key={`route-${cap}`}
                      type="button"
                      className={`pill ${routingCaps.includes(cap) ? "pill-violet" : "pill-gray"}`}
                      onClick={() => toggleCap(routingCaps, setRoutingCaps, cap)}
                    >
                      {cap}
                    </button>
                  ))}
                </div>
                <label className="fs-12 text-3">Priority ({routingPriority})</label>
                <input type="range" min={1} max={10} value={routingPriority} onChange={(event) => setRoutingPriority(Number(event.target.value || 5))} />
                <label className="fs-12 text-3">Payload JSON</label>
                <textarea className="bt-field warroom-payload" value={routingPayload} onChange={(event) => setRoutingPayload(event.target.value)} />
                <button type="button" className="share-btn" disabled={routingBusy} onClick={manualRouteNow}>Route Now</button>
              </section>

              <section className="glass-2 warroom-router-panel">
                <div className="section-title">Simulate Route</div>
                <label className="fs-12 text-3">Task type</label>
                <input className="bt-field" value={simulateTaskType} onChange={(event) => setSimulateTaskType(event.target.value)} />
                <label className="fs-12 text-3">Required capabilities</label>
                <div className="row gap-1" style={{ flexWrap: "wrap" }}>
                  {ROUTER_CAP_OPTIONS.map((cap) => (
                    <button
                      key={`simulate-${cap}`}
                      type="button"
                      className={`pill ${simulateCaps.includes(cap) ? "pill-violet" : "pill-gray"}`}
                      onClick={() => toggleCap(simulateCaps, setSimulateCaps, cap)}
                    >
                      {cap}
                    </button>
                  ))}
                </div>
                <button type="button" className="share-btn" disabled={routingBusy} onClick={simulateRouteNow}>Simulate</button>
                {simulateResult ? (
                  <div className="warroom-sim-result">
                    <strong>Would assign to:</strong> {simulateResult.agent_name || "UNASSIGNED"}
                    {simulateResult.agent_id ? ` (${simulateResult.agent_id})` : ""}
                    <div className="text-3 fs-12">
                      {simulateResult.swarm ? `swarm: ${simulateResult.swarm} · ` : ""}
                      score: {Number(simulateResult.score || 0)}
                    </div>
                    <div className="text-3 fs-12">{simulateResult.reason}</div>
                  </div>
                ) : null}
              </section>
            </div>

            <section className="warroom-routing-log">
              <div className="section-title">Routing Log (last 10)</div>
              <div className="warroom-routing-list">
                {routingLog.map((item) => (
                  <div key={`${item.task_id}-${item.timestamp}`} className="warroom-routing-item">
                    <span className={item.status === "assigned" ? "router-ok" : "router-warn"}>
                      {item.status === "assigned" ? "✓" : "⚠"}
                    </span>
                    <span>
                      {item.task_type} → {item.assigned_agent || "UNASSIGNED"} {item.assigned_agent_name ? `(${item.assigned_agent_name})` : ""}
                    </span>
                    <span className="text-3">{formatAgo(item.timestamp)}</span>
                  </div>
                ))}
                {routingLog.length === 0 ? <div className="text-3 fs-12">No routing decisions yet.</div> : null}
              </div>
            </section>
          </div>
        ) : null}
      </article>

      {selectedAgent ? (
        <div className="warroom-drawer-overlay" onClick={() => setSelectedAgent(null)}>
          <aside className="warroom-drawer glass" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="warroom-drawer-close" onClick={() => setSelectedAgent(null)}>×</button>
            <div className="section-title">{selectedAgent.agent_id} - {selectedAgent.name || "Unnamed Agent"}</div>
            <div className="text-3 fs-12">Swarm: {selectedAgent.swarm_name} | Type: {selectedAgent.agent_type || "worker"} | Priority: {selectedAgent.priority || 5}</div>
            <div className="warroom-drawer-block">
              <strong>Status</strong>
              <div>● {selectedAgent.status || "idle"} since {formatAgo(selectedAgent.updated_at)}</div>
              <div>Tasks: {selectedAgent.tasks_completed || 0} completed | {selectedAgent.tasks_failed || 0} failed</div>
              <div>Last heartbeat: {formatAgo(selectedAgent.last_heartbeat)}</div>
            </div>
            <div className="warroom-drawer-block">
              <strong>Capabilities</strong>
              <div className="row gap-1" style={{ flexWrap: "wrap", marginTop: 6 }}>
                {(selectedAgent.capabilities || []).map((cap) => <span key={cap} className="pill pill-gray">{cap}</span>)}
                <button type="button" className="pill pill-violet" onClick={() => onToast?.("Capability editing is coming next")}>+ add</button>
              </div>
            </div>
            <div className="warroom-drawer-block">
              <strong>Config</strong>
              <pre className="warroom-config">{JSON.stringify(selectedAgent.config || {}, null, 2)}</pre>
              <button type="button" className="pill pill-gray" onClick={() => onToast?.("Config editor is coming next")}>Edit Config JSON</button>
            </div>
            <div className="warroom-drawer-block">
              <strong>Memory Snapshot</strong>
              <div className="text-3 fs-12">last_trade_symbol: {selectedAgent?.config?.last_trade_symbol || "n/a"}</div>
              <div className="text-3 fs-12">last_trade_pnl: {selectedAgent?.config?.last_trade_pnl || "n/a"}</div>
              <button type="button" className="pill pill-gray" onClick={() => onToast?.("Memory details are coming next")}>View Full Memory</button>
            </div>
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              <button type="button" className="pill pill-green" onClick={() => updateStatus(selectedAgent.agent_id, "running")}>▶ Start</button>
              <button type="button" className="pill pill-gray" onClick={() => updateStatus(selectedAgent.agent_id, "paused")}>⏸ Pause</button>
              <button type="button" className="pill pill-red" onClick={() => updateStatus(selectedAgent.agent_id, "stopped")}>⏹ Stop</button>
              <button type="button" className="pill pill-violet" onClick={() => updateStatus(selectedAgent.agent_id, "running")}>🔄 Restart</button>
            </div>
            <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              <button type="button" className="pill pill-gray" onClick={() => onToast?.("Clone flow is coming next")}>📋 Clone</button>
              <button type="button" className="pill pill-red" onClick={() => updateStatus(selectedAgent.agent_id, "stopped")}>🗑 Delete</button>
            </div>
          </aside>
        </div>
      ) : null}

      {showTaskModal ? (
        <div className="modal-overlay" onClick={closeTaskModal}>
          <article className="modal glass warroom-task-modal" onClick={(event) => event.stopPropagation()}>
            <div className="section-title">Push Test Task</div>
            <label className="fs-12 text-3">Task type</label>
            <input className="bt-field" value={taskType} onChange={(event) => setTaskType(event.target.value)} />
            <label className="fs-12 text-3">Payload JSON</label>
            <textarea className="bt-field warroom-payload" value={taskPayloadText} onChange={(event) => setTaskPayloadText(event.target.value)} />
            <label className="fs-12 text-3">Priority (1-10)</label>
            <input className="bt-field" type="number" min={1} max={10} value={taskPriority} onChange={(event) => setTaskPriority(event.target.value)} />
            <div className="row gap-2">
              <button type="button" className="pill pill-violet" disabled={isPushingTask} onClick={pushTask}>
                {isPushingTask ? "Queueing..." : "Queue Task"}
              </button>
              <button type="button" className="pill pill-gray" onClick={closeTaskModal}>Cancel</button>
            </div>
          </article>
        </div>
      ) : null}
      <SwarmBuilderModal
        open={showBuilder}
        onClose={() => setShowBuilder(false)}
        onToast={onToast}
        onCreated={() => {
          fetchRegistry().catch(() => {});
        }}
      />
    </section>
  );
}
