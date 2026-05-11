export default function AgentDetailDrawer({
  selectedAgent,
  setSelectedAgent,
  formatAgo,
  onToast,
  updateStatus,
}) {
  if (!selectedAgent) return null;

  return (
    <div className="warroom-drawer-overlay" onClick={() => setSelectedAgent(null)}>
      <aside className="warroom-drawer glass" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Agent detail">
        <button type="button" className="warroom-drawer-close" aria-label="Close agent detail" onClick={() => setSelectedAgent(null)}>×</button>
        <div className="section-title">{selectedAgent.agent_id} - {selectedAgent.name || "Unnamed agent"}</div>
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
            <button type="button" className="pill pill-violet" onClick={() => onToast?.("Capability editing comes in a later step")}>+ add</button>
          </div>
        </div>
        <div className="warroom-drawer-block">
          <strong>Config</strong>
          <pre className="warroom-config">{JSON.stringify(selectedAgent.config || {}, null, 2)}</pre>
          <button type="button" className="pill pill-gray" onClick={() => onToast?.("Config editor comes in a later step")}>Edit config JSON</button>
        </div>
        <div className="warroom-drawer-block">
          <strong>Memory Snapshot</strong>
          <div className="text-3 fs-12">last_trade_symbol: {selectedAgent?.config?.last_trade_symbol || "no data"}</div>
          <div className="text-3 fs-12">last_trade_pnl: {selectedAgent?.config?.last_trade_pnl || "no data"}</div>
          <button type="button" className="pill pill-gray" onClick={() => onToast?.("Full memory view comes in a later step")}>View full memory</button>
        </div>
        <div className="row gap-2" style={{ flexWrap: "wrap" }}>
          <button type="button" className="pill pill-green" onClick={() => updateStatus(selectedAgent.agent_id, "running")}>▶ Start</button>
          <button type="button" className="pill pill-gray" onClick={() => updateStatus(selectedAgent.agent_id, "paused")}>⏸ Pause</button>
          <button type="button" className="pill pill-red" onClick={() => updateStatus(selectedAgent.agent_id, "stopped")}>⏹ Stop</button>
          <button type="button" className="pill pill-violet" onClick={() => updateStatus(selectedAgent.agent_id, "running")}>🔄 Restart</button>
        </div>
        <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
          <button type="button" className="pill pill-gray" onClick={() => onToast?.("Cloning comes in a later step")}>📋 Clone</button>
          <button type="button" className="pill pill-red" onClick={() => updateStatus(selectedAgent.agent_id, "stopped")}>🗑 Delete</button>
        </div>
      </aside>
    </div>
  );
}
