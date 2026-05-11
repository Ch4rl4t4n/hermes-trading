import { useCallback, useMemo } from "react";

export default function useAdminSwarmRoutingInsights({
  mergeAgents,
  capabilityRows,
  capabilityFilter,
  routingCaps,
  simulateCaps,
  routingPreferredSwarm,
}) {
  const recommendedCapabilities = useMemo(() => {
    return [...capabilityRows]
      .filter((row) => Number(row?.total_agents || 0) > 0)
      .sort((a, b) => {
        const aRunning = Number(a?.running_agents || 0);
        const bRunning = Number(b?.running_agents || 0);
        if (bRunning !== aRunning) return bRunning - aRunning;
        const aIdle = Number(a?.idle_agents || 0);
        const bIdle = Number(b?.idle_agents || 0);
        if (bIdle !== aIdle) return bIdle - aIdle;
        const aLoad = Number(a?.active_tasks || 0);
        const bLoad = Number(b?.active_tasks || 0);
        if (aLoad !== bLoad) return aLoad - bLoad;
        return String(a?.capability || "").localeCompare(String(b?.capability || ""));
      })
      .slice(0, 6);
  }, [capabilityRows]);

  const swarmOptions = useMemo(() => {
    return [...new Set(mergeAgents.map((agent) => String(agent.swarm_name || "").trim()).filter(Boolean))].sort();
  }, [mergeAgents]);

  const computeSuggestedSwarm = useCallback((caps) => {
    const selectedCaps = (caps || []).filter(Boolean);
    const bySwarm = new Map();
    for (const agent of mergeAgents) {
      const swarm = String(agent.swarm_name || "").trim();
      if (!swarm) continue;
      const item = bySwarm.get(swarm) || { swarm, score: 0, idle: 0, running: 0, alive: 0 };
      const status = String(agent.status || "").toLowerCase();
      if (Boolean(agent.alive)) item.alive += 1;
      if (status === "idle") item.idle += 1;
      if (status === "running") item.running += 1;
      const agentCaps = Array.isArray(agent.capabilities) ? agent.capabilities.map((c) => String(c)) : [];
      const capMatches = selectedCaps.length > 0
        ? selectedCaps.filter((cap) => agentCaps.includes(cap)).length
        : 0;
      item.score += capMatches * 3 + (status === "idle" ? 2 : status === "running" ? 1 : 0) + (Boolean(agent.alive) ? 1 : 0);
      bySwarm.set(swarm, item);
    }
    return [...bySwarm.values()]
      .sort((a, b) => (b.score - a.score) || (b.idle - a.idle) || (b.alive - a.alive) || a.swarm.localeCompare(b.swarm))[0] || null;
  }, [mergeAgents]);

  const suggestedRoutingSwarm = useMemo(
    () => computeSuggestedSwarm(routingCaps),
    [computeSuggestedSwarm, routingCaps],
  );
  const suggestedSimulateSwarm = useMemo(
    () => computeSuggestedSwarm(simulateCaps),
    [computeSuggestedSwarm, simulateCaps],
  );

  const capabilityByName = useMemo(() => {
    const m = new Map();
    for (const row of capabilityRows) {
      m.set(String(row?.capability || ""), row || {});
    }
    return m;
  }, [capabilityRows]);

  const filteredCapabilityRows = useMemo(() => {
    const rows = [...capabilityRows];
    if (capabilityFilter === "saturated") {
      return rows.filter((row) => Number(row?.idle_agents || 0) <= 0 || Number(row?.active_tasks || 0) > Number(row?.running_agents || 0));
    }
    if (capabilityFilter === "healthy") {
      return rows.filter((row) => Number(row?.idle_agents || 0) > 0 && Number(row?.active_tasks || 0) <= Number(row?.running_agents || 0));
    }
    return rows;
  }, [capabilityFilter, capabilityRows]);

  const routingCapabilityAlerts = useMemo(() => {
    return routingCaps
      .map((cap) => {
        const row = capabilityByName.get(cap);
        if (!row) return { cap, level: "unknown", message: "Capability not in registry." };
        const idle = Number(row.idle_agents || 0);
        const running = Number(row.running_agents || 0);
        const active = Number(row.active_tasks || 0);
        if (idle <= 0) return { cap, level: "high", message: "No idle capacity." };
        if (running > 0 && active > running) return { cap, level: "medium", message: "Load exceeds running agents." };
        return { cap, level: "ok", message: "Capacity available." };
      })
      .filter((item) => item.level !== "ok");
  }, [capabilityByName, routingCaps]);

  const simulateCapabilityAlerts = useMemo(() => {
    return simulateCaps
      .map((cap) => {
        const row = capabilityByName.get(cap);
        if (!row) return { cap, level: "unknown", message: "Capability not in registry." };
        const idle = Number(row.idle_agents || 0);
        const running = Number(row.running_agents || 0);
        const active = Number(row.active_tasks || 0);
        if (idle <= 0) return { cap, level: "high", message: "No idle capacity." };
        if (running > 0 && active > running) return { cap, level: "medium", message: "Load exceeds running agents." };
        return { cap, level: "ok", message: "Capacity available." };
      })
      .filter((item) => item.level !== "ok");
  }, [capabilityByName, simulateCaps]);

  const routingConfidence = useMemo(() => {
    const high = routingCapabilityAlerts.filter((item) => item.level === "high").length;
    const medium = routingCapabilityAlerts.filter((item) => item.level === "medium").length;
    const selected = routingCaps.length;
    const score = Number(suggestedRoutingSwarm?.score || 0);
    if (selected === 0) return { level: "low", label: "low", reason: "No capabilities selected." };
    if (high > 0) return { level: "low", label: "low", reason: "At least one capability has no idle capacity." };
    if (score >= 10 && medium === 0) return { level: "high", label: "high", reason: "Strong capability match with available capacity." };
    if (score >= 5) return { level: "medium", label: "medium", reason: "Partial match or elevated load." };
    return { level: "low", label: "low", reason: "Weak match between capabilities and available swarms." };
  }, [routingCapabilityAlerts, routingCaps.length, suggestedRoutingSwarm?.score]);

  const simulateConfidence = useMemo(() => {
    const high = simulateCapabilityAlerts.filter((item) => item.level === "high").length;
    const medium = simulateCapabilityAlerts.filter((item) => item.level === "medium").length;
    const selected = simulateCaps.length;
    const score = Number(suggestedSimulateSwarm?.score || 0);
    if (selected === 0) return { level: "low", label: "low", reason: "No capabilities selected." };
    if (high > 0) return { level: "low", label: "low", reason: "At least one capability has no idle capacity." };
    if (score >= 10 && medium === 0) return { level: "high", label: "high", reason: "Strong capability match with available capacity." };
    if (score >= 5) return { level: "medium", label: "medium", reason: "Partial match or elevated load." };
    return { level: "low", label: "low", reason: "Weak match between capabilities and available swarms." };
  }, [simulateCapabilityAlerts, simulateCaps.length, suggestedSimulateSwarm?.score]);

  const routingChecklist = useMemo(() => {
    const selected = routingCaps.length;
    const highAlerts = routingCapabilityAlerts.filter((item) => item.level === "high").length;
    const preferred = routingPreferredSwarm || suggestedRoutingSwarm?.swarm || "";
    return [
      {
        key: "caps",
        ok: selected > 0,
        label: "Capability selection",
        detail: selected > 0 ? `${selected} selected` : "no capabilities",
      },
      {
        key: "capacity",
        ok: highAlerts === 0,
        label: "Idle capacity",
        detail: highAlerts === 0 ? "no critical alerts" : `${highAlerts} critical alerts`,
      },
      {
        key: "swarm",
        ok: Boolean(preferred),
        label: "Target swarm",
        detail: preferred || "auto pick without suggestion",
      },
      {
        key: "confidence",
        ok: routingConfidence.level !== "low",
        label: "Routing confidence",
        detail: routingConfidence.label,
      },
    ];
  }, [routingCaps.length, routingCapabilityAlerts, routingPreferredSwarm, routingConfidence.label, routingConfidence.level, suggestedRoutingSwarm?.swarm]);

  return {
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
  };
}
