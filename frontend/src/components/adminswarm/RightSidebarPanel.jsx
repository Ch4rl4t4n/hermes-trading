export default function RightSidebarPanel({
  queueStats,
  queueTasks,
  setShowTaskModal,
  systemHealth,
  capabilityFilter,
  setCapabilityFilter,
  filteredCapabilityRows,
  formatAgo,
}) {
  return (
    <aside className="col gap-3">
      <article className="glass warroom-right-panel">
        <div className="row between">
          <div className="section-title">Task fronta</div>
          <span className="pill pill-violet">čaká: {queueStats.pending || 0}</span>
        </div>
        <div className="warroom-task-list">
          {queueTasks.slice(0, 8).map((task) => (
            <div key={task.task_id} className="warroom-task-item">
              <span>↑ P:{task.priority || 0}</span>
              <strong>{task.task_type}</strong>
              <span className="text-3">{formatAgo(task.created_at)}</span>
            </div>
          ))}
          {queueTasks.length === 0 ? <div className="text-3 fs-12">Vo fronte nie sú žiadne tasky.</div> : null}
        </div>
        <button type="button" className="share-btn" onClick={() => setShowTaskModal(true)}>+ Pridať test task</button>
      </article>

      <article className="glass warroom-right-panel">
        <div className="section-title">Zdravie systému</div>
        <div className="warroom-health-row"><span>CPU</span><div className="warroom-meter"><i style={{ width: `${Math.min(100, Number(systemHealth.cpu_percent || 0))}%` }} /></div><span>{Math.round(Number(systemHealth.cpu_percent || 0))}%</span></div>
        <div className="warroom-health-row"><span>Memory</span><div className="warroom-meter"><i style={{ width: `${Math.min(100, Number(systemHealth.memory_percent || 0))}%` }} /></div><span>{Math.round(Number(systemHealth.memory_percent || 0))}%</span></div>
        <div className="warroom-health-kv"><span>Redis</span><span>{systemHealth.redis ? "pripojené" : "výpadok"}</span></div>
        <div className="warroom-health-kv"><span>DB</span><span>{systemHealth.db ? "pripojená" : "výpadok"}</span></div>
        <div className="warroom-health-kv"><span>Fronta</span><span>{systemHealth.queue_pending || 0} čaká</span></div>
      </article>

      <article className="glass warroom-right-panel">
        <div className="section-title">Capability pokrytie</div>
        <div className="row gap-1" style={{ flexWrap: "wrap", marginBottom: 8 }}>
          {[
            { key: "all", label: "Všetky" },
            { key: "saturated", label: "Preťažené" },
            { key: "healthy", label: "Voľná kapacita" },
          ].map((filter) => (
            <button
              key={filter.key}
              type="button"
              className={`pill ${capabilityFilter === filter.key ? "pill-violet" : "pill-gray"}`}
              onClick={() => setCapabilityFilter(filter.key)}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <div className="warroom-task-list">
          {filteredCapabilityRows.slice(0, 8).map((row) => (
            <div key={row.capability} className="warroom-task-item">
              <strong>{row.capability}</strong>
              <span className="text-3">{row.total_agents || 0} agentov</span>
              <span className="text-3">beží: {row.running_agents || 0} | idle: {row.idle_agents || 0}</span>
              <span className={`pill ${Number(row.idle_agents || 0) <= 0 ? "pill-red" : Number(row.active_tasks || 0) > Number(row.running_agents || 0) ? "pill-gray" : "pill-green"}`}>
                {Number(row.idle_agents || 0) <= 0 ? "bez idle kapacity" : Number(row.active_tasks || 0) > Number(row.running_agents || 0) ? "zvýšený load" : "stabilné"}
              </span>
            </div>
          ))}
          {filteredCapabilityRows.length === 0 ? <div className="text-3 fs-12">Pre zvolený filter nie sú dáta.</div> : null}
        </div>
      </article>
    </aside>
  );
}
