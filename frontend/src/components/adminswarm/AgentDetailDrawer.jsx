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
      <aside className="warroom-drawer glass" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Detail agenta">
        <button type="button" className="warroom-drawer-close" aria-label="Zavrieť detail agenta" onClick={() => setSelectedAgent(null)}>×</button>
        <div className="section-title">{selectedAgent.agent_id} - {selectedAgent.name || "Nepomenovaný agent"}</div>
        <div className="text-3 fs-12">Swarm: {selectedAgent.swarm_name} | Typ: {selectedAgent.agent_type || "worker"} | Priorita: {selectedAgent.priority || 5}</div>
        <div className="warroom-drawer-block">
          <strong>Status</strong>
          <div>● {selectedAgent.status || "idle"} od {formatAgo(selectedAgent.updated_at)}</div>
          <div>Tasky: {selectedAgent.tasks_completed || 0} dokončené | {selectedAgent.tasks_failed || 0} zlyhané</div>
          <div>Posledný heartbeat: {formatAgo(selectedAgent.last_heartbeat)}</div>
        </div>
        <div className="warroom-drawer-block">
          <strong>Capabilities</strong>
          <div className="row gap-1" style={{ flexWrap: "wrap", marginTop: 6 }}>
            {(selectedAgent.capabilities || []).map((cap) => <span key={cap} className="pill pill-gray">{cap}</span>)}
            <button type="button" className="pill pill-violet" onClick={() => onToast?.("Editácia capability príde v ďalšom kroku")}>+ pridať</button>
          </div>
        </div>
        <div className="warroom-drawer-block">
          <strong>Config</strong>
          <pre className="warroom-config">{JSON.stringify(selectedAgent.config || {}, null, 2)}</pre>
          <button type="button" className="pill pill-gray" onClick={() => onToast?.("Config editor príde v ďalšom kroku")}>Upraviť Config JSON</button>
        </div>
        <div className="warroom-drawer-block">
          <strong>Memory Snapshot</strong>
          <div className="text-3 fs-12">last_trade_symbol: {selectedAgent?.config?.last_trade_symbol || "bez dát"}</div>
          <div className="text-3 fs-12">last_trade_pnl: {selectedAgent?.config?.last_trade_pnl || "bez dát"}</div>
          <button type="button" className="pill pill-gray" onClick={() => onToast?.("Detail pamäte príde v ďalšom kroku")}>Zobraziť celú pamäť</button>
        </div>
        <div className="row gap-2" style={{ flexWrap: "wrap" }}>
          <button type="button" className="pill pill-green" onClick={() => updateStatus(selectedAgent.agent_id, "running")}>▶ Spustiť</button>
          <button type="button" className="pill pill-gray" onClick={() => updateStatus(selectedAgent.agent_id, "paused")}>⏸ Pauza</button>
          <button type="button" className="pill pill-red" onClick={() => updateStatus(selectedAgent.agent_id, "stopped")}>⏹ Stop</button>
          <button type="button" className="pill pill-violet" onClick={() => updateStatus(selectedAgent.agent_id, "running")}>🔄 Reštart</button>
        </div>
        <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
          <button type="button" className="pill pill-gray" onClick={() => onToast?.("Klonovanie príde v ďalšom kroku")}>📋 Klonovať</button>
          <button type="button" className="pill pill-red" onClick={() => updateStatus(selectedAgent.agent_id, "stopped")}>🗑 Zmazať</button>
        </div>
      </aside>
    </div>
  );
}
