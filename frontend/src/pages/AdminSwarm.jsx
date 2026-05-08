import { useCallback, useEffect, useMemo, useState } from "react";
import client from "../api/client";
import SwarmBuilderModal from "../components/SwarmBuilderModal";
import SwarmStatusPanel from "../components/SwarmStatusPanel";
import AgentDetailDrawer from "../components/adminswarm/AgentDetailDrawer";
import AgentDirectoryPanel from "../components/adminswarm/AgentDirectoryPanel";
import RightSidebarPanel from "../components/adminswarm/RightSidebarPanel";
import RoutingPanel from "../components/adminswarm/RoutingPanel";
import SwarmGridPanel from "../components/adminswarm/SwarmGridPanel";
import useAdminSwarmRoutingInsights from "../hooks/useAdminSwarmRoutingInsights";
import swarmApi from "../api/swarm";

const DEFAULT_SWARMS = [
  { swarm_name: "orchestra", display_name: "Orchestra", icon: "🎼", description: "Hlavný koordinátor - routuje tasky do ostatných swarmov", color: "oklch(0.72 0.18 295)" },
  { swarm_name: "trading", display_name: "Trading", icon: "📈", description: "Vykonáva a monitoruje trading stratégie", color: "oklch(0.78 0.16 155)" },
  { swarm_name: "intelligence", display_name: "Intelligence", icon: "🔍", description: "Research, analýza správ a detekcia trendov", color: "oklch(0.78 0.14 75)" },
  { swarm_name: "marketing", display_name: "Marketing", icon: "📣", description: "Sociálne siete, obsah, SEO a rast", color: "oklch(0.72 0.18 15)" },
  { swarm_name: "maintenance", display_name: "Maintenance", icon: "🔧", description: "Infraštruktúra, monitoring a bezpečnosť", color: "oklch(0.65 0.12 220)" },
];

function formatUptime(seconds) {
  const s = Math.max(0, Number(seconds || 0));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function formatAgo(value) {
  if (!value) return "bez dát";
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return "bez dát";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return `pred ${diffSec}s`;
  if (diffSec < 3600) return `pred ${Math.floor(diffSec / 60)}m`;
  return `pred ${Math.floor(diffSec / 3600)}h`;
}

function apiMessage(error, fallback) {
  if (error?.response?.status === 403) return "Vyžaduje sa admin prístup";
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
const STORAGE_ROUTING_SWARM_KEY = "hermes.warroom.routingPreferredSwarm";
const STORAGE_SIMULATE_SWARM_KEY = "hermes.warroom.simulatePreferredSwarm";

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
  const [routingPreferredSwarm, setRoutingPreferredSwarm] = useState("");
  const [simulateTaskType, setSimulateTaskType] = useState("analysis");
  const [simulateCaps, setSimulateCaps] = useState([]);
  const [simulatePreferredSwarm, setSimulatePreferredSwarm] = useState("");
  const [simulateResult, setSimulateResult] = useState(null);
  const [routingBusy, setRoutingBusy] = useState(false);
  const [capabilityRows, setCapabilityRows] = useState([]);
  const [capabilityFilter, setCapabilityFilter] = useState("all");

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

  const {
    recommendedCapabilities,
    swarmOptions,
    suggestedRoutingSwarm,
    suggestedSimulateSwarm,
    filteredCapabilityRows,
    routingCapabilityAlerts,
    simulateCapabilityAlerts,
    routingConfidence,
    simulateConfidence,
    routingChecklist,
  } = useAdminSwarmRoutingInsights({
    mergeAgents,
    capabilityRows,
    capabilityFilter,
    routingCaps,
    simulateCaps,
    routingPreferredSwarm,
  });

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

  const fetchCapabilities = useCallback(async () => {
    const data = await swarmApi.capabilities();
    setCapabilityRows(Array.isArray(data?.items) ? data.items : []);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchRegistry().catch((error) => {
        const msg = apiMessage(error, "Nepodarilo sa načítať registry");
        setApiError(msg);
        onToast?.(msg);
      });
      fetchQueueTasks().catch(() => setQueueTasks([]));
      fetchSystemHealth().catch((error) => {
        const msg = apiMessage(error, "Nepodarilo sa načítať zdravie systému");
        setApiError(msg);
      });
      fetchRoutingLog().catch(() => setRoutingLog([]));
      fetchCapabilities().catch(() => setCapabilityRows([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchCapabilities, fetchQueueTasks, fetchRegistry, fetchRoutingLog, fetchSystemHealth, onToast]);

  useEffect(() => {
    const queueTimer = setInterval(() => fetchQueueTasks().catch(() => {}), 5000);
    const summaryTimer = setInterval(() => {
      fetchRegistry().catch(() => {});
      fetchSystemHealth().catch(() => {});
    }, 10000);
    const routerTimer = setInterval(() => {
      fetchRoutingLog().catch(() => {});
    }, 10000);
    const capabilityTimer = setInterval(() => {
      fetchCapabilities().catch(() => {});
    }, 12000);
    const uptimeTimer = setInterval(() => setUptimeSec((prev) => prev + 1), 1000);
    return () => {
      clearInterval(queueTimer);
      clearInterval(summaryTimer);
      clearInterval(routerTimer);
      clearInterval(capabilityTimer);
      clearInterval(uptimeTimer);
    };
  }, [fetchCapabilities, fetchQueueTasks, fetchRegistry, fetchRoutingLog, fetchSystemHealth]);

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

  useEffect(() => {
    try {
      const savedRouting = window.localStorage.getItem(STORAGE_ROUTING_SWARM_KEY) || "";
      const savedSimulate = window.localStorage.getItem(STORAGE_SIMULATE_SWARM_KEY) || "";
      if (savedRouting) setRoutingPreferredSwarm(savedRouting);
      if (savedSimulate) setSimulatePreferredSwarm(savedSimulate);
    } catch {
      // ignore storage read issues (private mode, blocked storage)
    }
  }, []);

  useEffect(() => {
    try {
      if (routingPreferredSwarm) window.localStorage.setItem(STORAGE_ROUTING_SWARM_KEY, routingPreferredSwarm);
      else window.localStorage.removeItem(STORAGE_ROUTING_SWARM_KEY);
    } catch {
      // ignore storage write issues
    }
  }, [routingPreferredSwarm]);

  useEffect(() => {
    try {
      if (simulatePreferredSwarm) window.localStorage.setItem(STORAGE_SIMULATE_SWARM_KEY, simulatePreferredSwarm);
      else window.localStorage.removeItem(STORAGE_SIMULATE_SWARM_KEY);
    } catch {
      // ignore storage write issues
    }
  }, [simulatePreferredSwarm]);

  useEffect(() => {
    if (routingPreferredSwarm && !swarmOptions.includes(routingPreferredSwarm)) {
      setRoutingPreferredSwarm("");
    }
    if (simulatePreferredSwarm && !swarmOptions.includes(simulatePreferredSwarm)) {
      setSimulatePreferredSwarm("");
    }
  }, [routingPreferredSwarm, simulatePreferredSwarm, swarmOptions]);

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
      onToast?.(`Agent ${agentId} nastavený na ${status}`);
      fetchRegistry().catch(() => {});
    } catch (error) {
      onToast?.(apiMessage(error, `Nepodarilo sa nastaviť ${status} pre ${agentId}`));
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
    if (!window.confirm("Si si istý? Toto zastaví VŠETKÝCH agentov.")) return;
    await bulkStatusUpdate("stopped", mergeAgents);
    onToast?.("Núdzové zastavenie spustené");
  };

  const pushTask = async () => {
    let payload;
    try {
      payload = taskPayloadText.trim() ? JSON.parse(taskPayloadText) : {};
    } catch {
      onToast?.("Payload musí byť validný JSON");
      return;
    }
    setIsPushingTask(true);
    try {
      await client.post("/api/admin/queue/push", {
        task_type: taskType || "generic",
        payload,
        priority: Number(taskPriority || 5),
      });
      onToast?.("Task bol zaradený do fronty");
      closeTaskModal();
      fetchQueueTasks().catch(() => {});
      fetchRegistry().catch(() => {});
    } catch {
      onToast?.("Nepodarilo sa zaradiť task do fronty");
    } finally {
      setIsPushingTask(false);
    }
  };

  const toggleCap = (current, setCurrent, cap) => {
    setCurrent((prev) => (prev.includes(cap) ? prev.filter((item) => item !== cap) : [...prev, cap]));
  };

  const manualRouteNow = async () => {
    const hardWarnings = routingCapabilityAlerts.filter((item) => item.level === "high");
    if (hardWarnings.length > 0) {
      const detail = hardWarnings.map((w) => w.cap).join(", ");
      const ok = window.confirm(`Vybrané capability sú bez idle kapacity: ${detail}. Pokračovať v routovaní?`);
      if (!ok) return;
    }
    let payload;
    try {
      payload = routingPayload.trim() ? JSON.parse(routingPayload) : {};
    } catch {
      onToast?.("Router payload musí byť validný JSON");
      return;
    }
    setRoutingBusy(true);
    try {
      const data = await swarmApi.dispatch({
        taskType: routingTaskType || "manual",
        payload,
        priority: Number(routingPriority || 5),
        requiredCapabilities: routingCaps,
        preferredSwarm: routingPreferredSwarm || undefined,
      });
      const dispatched = data?.dispatched_to_dramatiq ? " · odoslané do Dramatiq" : "";
      onToast?.(
        data?.assigned_agent
          ? `Routované na ${data.assigned_agent}${dispatched}`
          : "Task zaradený bez priradenia",
      );
      fetchRoutingLog().catch(() => {});
      fetchQueueTasks().catch(() => {});
      fetchRegistry().catch(() => {});
    } catch (error) {
      onToast?.(apiMessage(error, "Manuálne routovanie zlyhalo"));
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
        preferredSwarm: simulatePreferredSwarm || undefined,
      });
      setSimulateResult({
        agent_name: data?.agent_name,
        agent_id: data?.would_assign_to,
        swarm: data?.swarm,
        score: data?.score,
        reason: data?.reason,
      });
    } catch (error) {
      onToast?.(apiMessage(error, "Simulácia zlyhala"));
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
          <button type="button" className="share-btn" onClick={() => setShowBuilder(true)}>+ Vytvoriť nový swarm</button>
          <span className="warroom-live"><span className="warroom-live-dot" />LIVE</span>
        </div>
      </div>

      <div className="warroom-banner glass-2">
        <span className="warroom-live"><span className="warroom-live-dot" />LIVE</span>
        <span>Fronta: {queueStats.pending || 0} čaká</span>
        <span>{queueStats.agents_alive || 0} agentov online</span>
        <span>{queueStats.agents_total || 0} agentov celkom</span>
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
            <div className="section-title">Globálne ovládanie</div>
            {apiError ? <div className="text-3 fs-12" style={{ marginBottom: 8 }}>{apiError}</div> : null}
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              <button type="button" className="pill pill-green" disabled={isBulkUpdating} onClick={() => bulkStatusUpdate("running", mergeAgents)}>Spustiť všetko</button>
              <button type="button" className="pill pill-gray" disabled={isBulkUpdating} onClick={() => bulkStatusUpdate("paused", mergeAgents)}>Pozastaviť všetko</button>
              <button type="button" className="pill pill-red" disabled={isBulkUpdating} onClick={() => bulkStatusUpdate("stopped", mergeAgents)}>Zastaviť všetko</button>
              <button type="button" className="pill pill-red warroom-emergency" disabled={isBulkUpdating} onClick={emergencyStop}>Núdzové zastavenie</button>
            </div>
          </article>

          <SwarmGridPanel
            mergeAgents={mergeAgents}
            DEFAULT_SWARMS={DEFAULT_SWARMS}
            expandedSwarms={expandedSwarms}
            setExpandedSwarms={setExpandedSwarms}
            onToast={onToast}
            bulkStatusUpdate={bulkStatusUpdate}
            setSelectedAgent={setSelectedAgent}
            updateStatus={updateStatus}
            fetchRegistry={fetchRegistry}
            client={client}
            apiMessage={apiMessage}
          />
        </div>

        <RightSidebarPanel
          queueStats={queueStats}
          queueTasks={queueTasks}
          setShowTaskModal={setShowTaskModal}
          systemHealth={systemHealth}
          capabilityFilter={capabilityFilter}
          setCapabilityFilter={setCapabilityFilter}
          filteredCapabilityRows={filteredCapabilityRows}
          formatAgo={formatAgo}
        />
      </div>

      <AgentDirectoryPanel
        directoryOpen={directoryOpen}
        setDirectoryOpen={setDirectoryOpen}
        mergeAgents={mergeAgents}
        search={search}
        setSearch={setSearch}
        DEFAULT_SWARMS={DEFAULT_SWARMS}
        swarmFilter={swarmFilter}
        setSwarmFilter={setSwarmFilter}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        filteredAgents={filteredAgents}
        setSelectedAgent={setSelectedAgent}
        updateStatus={updateStatus}
        MAX_DIRECTORY_ROWS={MAX_DIRECTORY_ROWS}
      />

      <RoutingPanel
        routerOpen={routerOpen}
        setRouterOpen={setRouterOpen}
        routingTaskType={routingTaskType}
        setRoutingTaskType={setRoutingTaskType}
        recommendedCapabilities={recommendedCapabilities}
        routingCaps={routingCaps}
        setRoutingCaps={setRoutingCaps}
        toggleCap={toggleCap}
        ROUTER_CAP_OPTIONS={ROUTER_CAP_OPTIONS}
        routingCapabilityAlerts={routingCapabilityAlerts}
        routingPreferredSwarm={routingPreferredSwarm}
        setRoutingPreferredSwarm={setRoutingPreferredSwarm}
        swarmOptions={swarmOptions}
        suggestedRoutingSwarm={suggestedRoutingSwarm}
        routingConfidence={routingConfidence}
        routingChecklist={routingChecklist}
        routingPriority={routingPriority}
        setRoutingPriority={setRoutingPriority}
        routingPayload={routingPayload}
        setRoutingPayload={setRoutingPayload}
        routingBusy={routingBusy}
        manualRouteNow={manualRouteNow}
        simulateTaskType={simulateTaskType}
        setSimulateTaskType={setSimulateTaskType}
        simulateCaps={simulateCaps}
        setSimulateCaps={setSimulateCaps}
        simulateCapabilityAlerts={simulateCapabilityAlerts}
        simulatePreferredSwarm={simulatePreferredSwarm}
        setSimulatePreferredSwarm={setSimulatePreferredSwarm}
        suggestedSimulateSwarm={suggestedSimulateSwarm}
        simulateConfidence={simulateConfidence}
        simulateRouteNow={simulateRouteNow}
        simulateResult={simulateResult}
        routingLog={routingLog}
        formatAgo={formatAgo}
      />

      <AgentDetailDrawer
        selectedAgent={selectedAgent}
        setSelectedAgent={setSelectedAgent}
        formatAgo={formatAgo}
        onToast={onToast}
        updateStatus={updateStatus}
      />

      {showTaskModal ? (
        <div className="modal-overlay" onClick={closeTaskModal}>
          <article className="modal glass warroom-task-modal" role="dialog" aria-modal="true" aria-label="Pridať test task" onClick={(event) => event.stopPropagation()}>
            <div className="section-title">Pridať test task</div>
            <label className="fs-12 text-3">Typ tasku</label>
            <input className="bt-field" value={taskType} onChange={(event) => setTaskType(event.target.value)} />
            <label className="fs-12 text-3">Payload JSON</label>
            <textarea className="bt-field warroom-payload" value={taskPayloadText} onChange={(event) => setTaskPayloadText(event.target.value)} />
            <label className="fs-12 text-3">Priority (1-10)</label>
            <input className="bt-field" type="number" min={1} max={10} value={taskPriority} onChange={(event) => setTaskPriority(event.target.value)} />
            <div className="row gap-2">
              <button type="button" className="pill pill-violet" disabled={isPushingTask} onClick={pushTask}>
                {isPushingTask ? "Zaraďujem..." : "Zaradiť task"}
              </button>
              <button type="button" className="pill pill-gray" onClick={closeTaskModal}>Zrušiť</button>
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
