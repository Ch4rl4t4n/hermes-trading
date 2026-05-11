export default function RoutingPanel({
  routerOpen,
  setRouterOpen,
  routingTaskType,
  setRoutingTaskType,
  recommendedCapabilities,
  routingCaps,
  setRoutingCaps,
  toggleCap,
  ROUTER_CAP_OPTIONS,
  routingCapabilityAlerts,
  routingPreferredSwarm,
  setRoutingPreferredSwarm,
  swarmOptions,
  suggestedRoutingSwarm,
  routingConfidence,
  routingChecklist,
  routingPriority,
  setRoutingPriority,
  routingPayload,
  setRoutingPayload,
  routingBusy,
  manualRouteNow,
  simulateTaskType,
  setSimulateTaskType,
  simulateCaps,
  setSimulateCaps,
  simulateCapabilityAlerts,
  simulatePreferredSwarm,
  setSimulatePreferredSwarm,
  suggestedSimulateSwarm,
  simulateConfidence,
  simulateRouteNow,
  simulateResult,
  routingLog,
  formatAgo,
}) {
  return (
    <article className="glass warroom-router">
      <button type="button" className="warroom-directory-toggle" onClick={() => setRouterOpen((prev) => !prev)}>
        {routerOpen ? "▼" : "▶"} Task router
      </button>
      {routerOpen ? (
        <div className="warroom-router-body">
          <div className="warroom-router-grid">
            <section className="glass-2 warroom-router-panel">
              <div className="section-title">Manual task routing</div>
              <label className="fs-12 text-3">Task type</label>
              <input className="bt-field" value={routingTaskType} onChange={(event) => setRoutingTaskType(event.target.value)} />
              <label className="fs-12 text-3">Required capabilities</label>
              {recommendedCapabilities.length > 0 ? (
                <div className="row gap-1" style={{ flexWrap: "wrap", marginBottom: 6 }}>
                  {recommendedCapabilities.map((row) => (
                    <button
                      key={`routing-rec-${row.capability}`}
                      type="button"
                      className={`pill ${routingCaps.includes(row.capability) ? "pill-violet" : "pill-gray"}`}
                      onClick={() => toggleCap(routingCaps, setRoutingCaps, row.capability)}
                      title={`running: ${row.running_agents || 0}, idle: ${row.idle_agents || 0}, load: ${row.active_tasks || 0}`}
                    >
                      {row.capability}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="pill pill-gray"
                    onClick={() => setRoutingCaps(recommendedCapabilities.slice(0, 3).map((row) => row.capability))}
                  >
                    Use top 3
                  </button>
                </div>
              ) : null}
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
              {routingCapabilityAlerts.length > 0 ? (
                <div className="text-3 fs-12" style={{ marginTop: 8 }}>
                  {routingCapabilityAlerts.map((item) => (
                    <div key={`alert-${item.cap}`}>
                      {item.level === "high" ? "⚠" : "ℹ"} {item.cap}: {item.message}
                    </div>
                  ))}
                </div>
              ) : null}
              <label className="fs-12 text-3">Preferred swarm</label>
              <div className="row gap-1" style={{ flexWrap: "wrap", marginBottom: 6 }}>
                <select
                  className="bt-field"
                  value={routingPreferredSwarm}
                  onChange={(event) => setRoutingPreferredSwarm(event.target.value)}
                  style={{ minWidth: 180 }}
                >
                  <option value="">auto</option>
                  {swarmOptions.map((swarm) => (
                    <option key={`route-pref-${swarm}`} value={swarm}>{swarm}</option>
                  ))}
                </select>
                {suggestedRoutingSwarm ? (
                  <button
                    type="button"
                    className="pill pill-gray"
                    onClick={() => setRoutingPreferredSwarm(suggestedRoutingSwarm.swarm)}
                  >
                    Suggest: {suggestedRoutingSwarm.swarm}
                  </button>
                ) : null}
              </div>
              <div className="row gap-1" style={{ alignItems: "center", marginBottom: 6 }}>
                <span className={`pill ${routingConfidence.level === "high" ? "pill-green" : routingConfidence.level === "medium" ? "pill-gray" : "pill-red"}`}>
                  Routing confidence: {routingConfidence.label}
                </span>
                <span className="text-3 fs-12">{routingConfidence.reason}</span>
              </div>
              <div className="glass-2" style={{ padding: 8, marginBottom: 8 }}>
                <div className="fs-12 text-3" style={{ marginBottom: 6 }}>Pre-dispatch checklist</div>
                {routingChecklist.map((item) => (
                  <div key={item.key} className="row between fs-12" style={{ marginBottom: 4 }}>
                    <span>{item.ok ? "✓" : "⚠"} {item.label}</span>
                    <span className="text-3">{item.detail}</span>
                  </div>
                ))}
              </div>
              <label className="fs-12 text-3">Priority ({routingPriority})</label>
              <input type="range" min={1} max={10} value={routingPriority} onChange={(event) => setRoutingPriority(Number(event.target.value || 5))} />
              <label className="fs-12 text-3">Payload JSON</label>
              <textarea className="bt-field warroom-payload" value={routingPayload} onChange={(event) => setRoutingPayload(event.target.value)} />
              <button type="button" className="share-btn" disabled={routingBusy} onClick={manualRouteNow}>Route now</button>
            </section>

            <section className="glass-2 warroom-router-panel">
              <div className="section-title">Simulate routing</div>
              <label className="fs-12 text-3">Task type</label>
              <input className="bt-field" value={simulateTaskType} onChange={(event) => setSimulateTaskType(event.target.value)} />
              <label className="fs-12 text-3">Required capabilities</label>
              {recommendedCapabilities.length > 0 ? (
                <div className="row gap-1" style={{ flexWrap: "wrap", marginBottom: 6 }}>
                  {recommendedCapabilities.map((row) => (
                    <button
                      key={`simulate-rec-${row.capability}`}
                      type="button"
                      className={`pill ${simulateCaps.includes(row.capability) ? "pill-violet" : "pill-gray"}`}
                      onClick={() => toggleCap(simulateCaps, setSimulateCaps, row.capability)}
                      title={`running: ${row.running_agents || 0}, idle: ${row.idle_agents || 0}, load: ${row.active_tasks || 0}`}
                    >
                      {row.capability}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="pill pill-gray"
                    onClick={() => setSimulateCaps(recommendedCapabilities.slice(0, 3).map((row) => row.capability))}
                  >
                    Use top 3
                  </button>
                </div>
              ) : null}
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
              {simulateCapabilityAlerts.length > 0 ? (
                <div className="text-3 fs-12" style={{ marginTop: 8 }}>
                  {simulateCapabilityAlerts.map((item) => (
                    <div key={`sim-alert-${item.cap}`}>
                      {item.level === "high" ? "⚠" : "ℹ"} {item.cap}: {item.message}
                    </div>
                  ))}
                </div>
              ) : null}
              <label className="fs-12 text-3">Preferred swarm</label>
              <div className="row gap-1" style={{ flexWrap: "wrap", marginBottom: 6 }}>
                <select
                  className="bt-field"
                  value={simulatePreferredSwarm}
                  onChange={(event) => setSimulatePreferredSwarm(event.target.value)}
                  style={{ minWidth: 180 }}
                >
                  <option value="">auto</option>
                  {swarmOptions.map((swarm) => (
                    <option key={`simulate-pref-${swarm}`} value={swarm}>{swarm}</option>
                  ))}
                </select>
                {suggestedSimulateSwarm ? (
                  <button
                    type="button"
                    className="pill pill-gray"
                    onClick={() => setSimulatePreferredSwarm(suggestedSimulateSwarm.swarm)}
                  >
                    Suggest: {suggestedSimulateSwarm.swarm}
                  </button>
                ) : null}
              </div>
              <div className="row gap-1" style={{ alignItems: "center", marginBottom: 6 }}>
                <span className={`pill ${simulateConfidence.level === "high" ? "pill-green" : simulateConfidence.level === "medium" ? "pill-gray" : "pill-red"}`}>
                  Simulation confidence: {simulateConfidence.label}
                </span>
                <span className="text-3 fs-12">{simulateConfidence.reason}</span>
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
            <div className="section-title">Routing log (last 10)</div>
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
  );
}
