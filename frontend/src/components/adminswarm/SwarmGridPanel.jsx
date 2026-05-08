export default function SwarmGridPanel({
  mergeAgents,
  DEFAULT_SWARMS,
  expandedSwarms,
  setExpandedSwarms,
  onToast,
  bulkStatusUpdate,
  setSelectedAgent,
  updateStatus,
  fetchRegistry,
  client,
  apiMessage,
}) {
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
      description: meta.description || "Custom swarm vytvorený cez Prompt Builder",
      color: meta.color || "oklch(0.72 0.18 295)",
    });
  }

  return (
    <div className="warroom-swarm-grid">
      {[...DEFAULT_SWARMS, ...customSwarms].map((swarm) => {
        const agents = mergeAgents.filter((agent) => String(agent.swarm_name) === swarm.swarm_name);
        const alive = agents.filter((agent) => Boolean(agent.alive)).length;
        const completed = agents.reduce((sum, agent) => sum + Number(agent.tasks_completed || 0), 0);
        const failed = agents.reduce((sum, agent) => sum + Number(agent.tasks_failed || 0), 0);
        const expanded = Boolean(expandedSwarms[swarm.swarm_name]);
        return (
          <article key={swarm.swarm_name} className="glass-2 warroom-swarm-card" style={{ borderLeft: `3px solid ${swarm.color}` }}>
            <div className="row between">
              <strong>{swarm.icon} {swarm.display_name}</strong>
              <span className={`pill ${alive > 0 ? "pill-green" : "pill-red"}`}>{alive > 0 ? "aktívny" : "nedostupný"}</span>
            </div>
            <div className="text-3 fs-12" style={{ marginTop: 6 }}>{swarm.description}</div>
            <div className="warroom-swarm-meta">Agenti: {alive}/{agents.length} online</div>
            <div className="warroom-swarm-meta">Tasky dnes: {completed} | Chyby: {failed}</div>
            <div className="row gap-2" style={{ marginTop: 10, flexWrap: "wrap" }}>
              <button type="button" className="pill pill-gray" onClick={() => setExpandedSwarms((prev) => ({ ...prev, [swarm.swarm_name]: !prev[swarm.swarm_name] }))}>
                {expanded ? "Zobraziť agentov ▲" : "Zobraziť agentov ▼"}
              </button>
              <button type="button" className="pill pill-violet" onClick={() => onToast?.("Flow pridania agenta bude v ďalšom kroku")}>+ Pridať agenta</button>
              <button type="button" className="pill pill-gray" onClick={() => bulkStatusUpdate("paused", agents)}>⏸ Pauza</button>
              {!["orchestra", "trading", "intelligence", "marketing", "maintenance"].includes(swarm.swarm_name) ? (
                <button
                  type="button"
                  className="pill pill-red"
                  onClick={async () => {
                    if (!window.confirm(`Zmazať swarm "${swarm.swarm_name}" a všetkých jeho agentov?`)) return;
                    try {
                      await client.delete(`/api/admin/swarm-builder/swarms/${encodeURIComponent(swarm.swarm_name)}`);
                      onToast?.(`Swarm ${swarm.swarm_name} bol zmazaný`);
                      fetchRegistry().catch(() => {});
                    } catch (error) {
                      onToast?.(apiMessage(error, "Mazanie zlyhalo"));
                    }
                  }}
                >
                  🗑 Zmazať swarm
                </button>
              ) : null}
            </div>
            {expanded ? (
              <div className="warroom-inline-list">
                {agents.map((agent) => (
                  <div key={agent.agent_id} className="warroom-inline-agent">
                    <span className={`swarm-dot ${agent.alive ? "swarm-dot-alive" : "swarm-dot-dead"}`} />
                    <button type="button" className="warroom-linklike" onClick={() => setSelectedAgent(agent)}>{agent.agent_id}</button>
                    <span className="text-3">{agent.name || "Nepomenovaný"}</span>
                    <span className="pill pill-gray">{String(agent.status || "idle")}</span>
                    <div className="row gap-1">
                      <button type="button" className="pill pill-green" onClick={() => updateStatus(agent.agent_id, "running")}>▶</button>
                      <button type="button" className="pill pill-gray" onClick={() => updateStatus(agent.agent_id, "paused")}>⏸</button>
                      <button type="button" className="pill pill-red" onClick={() => updateStatus(agent.agent_id, "stopped")}>⏹</button>
                      <button type="button" className="pill pill-violet" onClick={() => setSelectedAgent(agent)}>⚙</button>
                    </div>
                  </div>
                ))}
                {agents.length === 0 ? <div className="text-3 fs-12">V tomto swarme nie sú žiadni agenti.</div> : null}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
