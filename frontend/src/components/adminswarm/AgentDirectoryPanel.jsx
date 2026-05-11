export default function AgentDirectoryPanel({
  directoryOpen,
  setDirectoryOpen,
  mergeAgents,
  search,
  setSearch,
  DEFAULT_SWARMS,
  swarmFilter,
  setSwarmFilter,
  statusFilter,
  setStatusFilter,
  filteredAgents,
  setSelectedAgent,
  updateStatus,
  MAX_DIRECTORY_ROWS,
}) {
  return (
    <article className="glass warroom-directory">
      <button type="button" className="warroom-directory-toggle" onClick={() => setDirectoryOpen((prev) => !prev)}>
        {directoryOpen ? "▼" : "▶"} Agent directory — {mergeAgents.length} agents
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
                {status === "all" ? "All" : status[0].toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>
          <div className="leaderboard-table-wrap warroom-directory-table-wrap" style={{ marginTop: 10 }}>
            <table className="leaderboard-table warroom-directory-table" style={{ minWidth: 980 }}>
              <thead>
                <tr>
                  <th>Agent ID</th><th>Name</th><th>Swarm</th><th>Capability</th><th>Status</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredAgents.map((agent) => (
                  <tr key={agent.agent_id} onClick={() => setSelectedAgent(agent)} className="warroom-table-row">
                    <td data-label="Agent ID"><span className={`swarm-dot ${agent.alive ? "swarm-dot-alive" : "swarm-dot-dead"}`} /> {agent.agent_id}</td>
                    <td data-label="Name">{agent.name || "Unnamed"}</td>
                    <td data-label="Swarm">{agent.swarm_name}</td>
                    <td data-label="Capability">{(agent.capabilities || []).slice(0, 3).join(", ") || "-"}</td>
                    <td data-label="Status">{String(agent.status || "idle")}</td>
                    <td data-label="Actions">
                      <div className="row gap-1 warroom-table-actions">
                        <button type="button" className="pill pill-green warroom-action-btn" aria-label={`Start ${agent.agent_id}`} onClick={(event) => { event.stopPropagation(); updateStatus(agent.agent_id, "running"); }}>▶</button>
                        <button type="button" className="pill pill-gray warroom-action-btn" aria-label={`Pause ${agent.agent_id}`} onClick={(event) => { event.stopPropagation(); updateStatus(agent.agent_id, "paused"); }}>⏸</button>
                        <button type="button" className="pill pill-violet warroom-action-btn" aria-label={`Settings ${agent.agent_id}`} onClick={(event) => { event.stopPropagation(); setSelectedAgent(agent); }}>⚙</button>
                        <button type="button" className="pill pill-red warroom-action-btn" aria-label={`Stop ${agent.agent_id}`} onClick={(event) => { event.stopPropagation(); updateStatus(agent.agent_id, "stopped"); }}>🗑</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {mergeAgents.length > MAX_DIRECTORY_ROWS ? (
            <div className="text-3 fs-12" style={{ marginTop: 8 }}>
              Showing first {MAX_DIRECTORY_ROWS} agents. Narrow filters for specific results.
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}
