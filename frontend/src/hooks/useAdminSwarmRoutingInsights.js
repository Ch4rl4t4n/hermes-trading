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
        if (!row) return { cap, level: "unknown", message: "Capability nie je v registri." };
        const idle = Number(row.idle_agents || 0);
        const running = Number(row.running_agents || 0);
        const active = Number(row.active_tasks || 0);
        if (idle <= 0) return { cap, level: "high", message: "Žiadna idle kapacita." };
        if (running > 0 && active > running) return { cap, level: "medium", message: "Load je vyšší než počet bežiacich agentov." };
        return { cap, level: "ok", message: "Kapacita je dostupná." };
      })
      .filter((item) => item.level !== "ok");
  }, [capabilityByName, routingCaps]);

  const simulateCapabilityAlerts = useMemo(() => {
    return simulateCaps
      .map((cap) => {
        const row = capabilityByName.get(cap);
        if (!row) return { cap, level: "unknown", message: "Capability nie je v registri." };
        const idle = Number(row.idle_agents || 0);
        const running = Number(row.running_agents || 0);
        const active = Number(row.active_tasks || 0);
        if (idle <= 0) return { cap, level: "high", message: "Žiadna idle kapacita." };
        if (running > 0 && active > running) return { cap, level: "medium", message: "Load je vyšší než počet bežiacich agentov." };
        return { cap, level: "ok", message: "Kapacita je dostupná." };
      })
      .filter((item) => item.level !== "ok");
  }, [capabilityByName, simulateCaps]);

  const routingConfidence = useMemo(() => {
    const high = routingCapabilityAlerts.filter((item) => item.level === "high").length;
    const medium = routingCapabilityAlerts.filter((item) => item.level === "medium").length;
    const selected = routingCaps.length;
    const score = Number(suggestedRoutingSwarm?.score || 0);
    if (selected === 0) return { level: "low", label: "nízka", reason: "Nie sú zvolené capability." };
    if (high > 0) return { level: "low", label: "nízka", reason: "Aspoň jedna capability je bez idle kapacity." };
    if (score >= 10 && medium === 0) return { level: "high", label: "vysoká", reason: "Silný capability match a dostupná kapacita." };
    if (score >= 5) return { level: "medium", label: "stredná", reason: "Čiastočný match alebo zvýšený load." };
    return { level: "low", label: "nízka", reason: "Slabý match medzi capability a dostupnými swarmami." };
  }, [routingCapabilityAlerts, routingCaps.length, suggestedRoutingSwarm?.score]);

  const simulateConfidence = useMemo(() => {
    const high = simulateCapabilityAlerts.filter((item) => item.level === "high").length;
    const medium = simulateCapabilityAlerts.filter((item) => item.level === "medium").length;
    const selected = simulateCaps.length;
    const score = Number(suggestedSimulateSwarm?.score || 0);
    if (selected === 0) return { level: "low", label: "nízka", reason: "Nie sú zvolené capability." };
    if (high > 0) return { level: "low", label: "nízka", reason: "Aspoň jedna capability je bez idle kapacity." };
    if (score >= 10 && medium === 0) return { level: "high", label: "vysoká", reason: "Silný capability match a dostupná kapacita." };
    if (score >= 5) return { level: "medium", label: "stredná", reason: "Čiastočný match alebo zvýšený load." };
    return { level: "low", label: "nízka", reason: "Slabý match medzi capability a dostupnými swarmami." };
  }, [simulateCapabilityAlerts, simulateCaps.length, suggestedSimulateSwarm?.score]);

  const routingChecklist = useMemo(() => {
    const selected = routingCaps.length;
    const highAlerts = routingCapabilityAlerts.filter((item) => item.level === "high").length;
    const preferred = routingPreferredSwarm || suggestedRoutingSwarm?.swarm || "";
    return [
      {
        key: "caps",
        ok: selected > 0,
        label: "Capability výber",
        detail: selected > 0 ? `${selected} zvolené` : "žiadne capability",
      },
      {
        key: "capacity",
        ok: highAlerts === 0,
        label: "Idle kapacita",
        detail: highAlerts === 0 ? "bez kritických alertov" : `${highAlerts} kritických alertov`,
      },
      {
        key: "swarm",
        ok: Boolean(preferred),
        label: "Cieľový swarm",
        detail: preferred || "auto výber bez návrhu",
      },
      {
        key: "confidence",
        ok: routingConfidence.level !== "low",
        label: "Istota routingu",
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
