import { useEffect, useMemo, useState } from "react";
import client from "../api/client";

const PROMPT_LIBRARY_KEY = "hermes_prompt_library";
const EXAMPLE_PROMPTS = [
  { label: "📈 Crypto trading swarm", prompt: "Create a crypto trading swarm that runs momentum and mean-reversion strategies, controls risk tightly, and sends Telegram alerts for high-confidence entries." },
  { label: "📣 Social media automation", prompt: "Create a marketing swarm that posts daily to Twitter and Instagram, monitors competitor accounts, generates weekly performance reports, and alerts me about viral trends." },
  { label: "🔧 Web maintenance & monitoring", prompt: "Create a maintenance swarm that monitors uptime, scans logs for anomalies, runs security audits, and triggers recovery tasks automatically." },
  { label: "📊 Daily reporting & analytics", prompt: "Create an analytics swarm that aggregates daily metrics, creates KPI reports, sends summaries via email, and highlights outliers automatically." },
  { label: "🎯 SEO & content creation", prompt: "Create an SEO and content swarm that researches keywords, drafts article outlines, optimizes pages, and tracks ranking movement." },
];
const QUICK_TEMPLATES = [
  { label: "📈 Trading", prompt: "Create a trading swarm focused on crypto momentum, portfolio risk balancing, and daily trade reports." },
  { label: "📣 Marketing", prompt: "Create a marketing swarm focused on social content, campaign experiments, and weekly growth analysis." },
  { label: "🔧 Maintenance", prompt: "Create a maintenance swarm focused on uptime monitoring, security checks, and incident response." },
  { label: "📊 Analytics", prompt: "Create an analytics swarm focused on KPI dashboards, anomaly detection, and executive summaries." },
];

function readPromptLibrary() {
  try {
    const raw = localStorage.getItem(PROMPT_LIBRARY_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function writePromptLibrary(items) {
  try {
    localStorage.setItem(PROMPT_LIBRARY_KEY, JSON.stringify(items.slice(0, 30)));
    return true;
  } catch {
    return false;
  }
}

function capabilityClass(cap) {
  const value = String(cap || "").toLowerCase();
  if (["trading", "momentum", "crypto", "risk", "portfolio", "backtest", "ml"].some((k) => value.includes(k))) return "cap-chip-trading";
  if (["marketing", "content", "seo", "social", "reels", "tiktok"].some((k) => value.includes(k))) return "cap-chip-marketing";
  if (["maintenance", "monitoring", "security", "audit", "backup"].some((k) => value.includes(k))) return "cap-chip-maintenance";
  if (["analysis", "research", "news", "trends", "sentiment", "reporting", "data"].some((k) => value.includes(k))) return "cap-chip-analysis";
  return "cap-chip-default";
}

export default function SwarmBuilderModal({ open, onClose, onCreated, onToast }) {
  const [prompt, setPrompt] = useState("");
  const [refinement, setRefinement] = useState("");
  const [config, setConfig] = useState(null);
  const [loadingGenerate, setLoadingGenerate] = useState(false);
  const [loadingCreate, setLoadingCreate] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(true);
  const [showLibrary, setShowLibrary] = useState(false);
  const [savedPrompts, setSavedPrompts] = useState([]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      setSavedPrompts(readPromptLibrary());
    }, 0);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (open) return;
    const timer = setTimeout(() => {
      setPrompt("");
      setRefinement("");
      setConfig(null);
      setLoadingGenerate(false);
      setLoadingCreate(false);
      setShowAdvanced(true);
      setShowLibrary(false);
    }, 0);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  const promptLength = prompt.length;
  const previewAgents = useMemo(() => (Array.isArray(config?.agents) ? config.agents : []), [config]);

  const runGenerate = async (inputPrompt) => {
    const finalPrompt = String(inputPrompt || prompt || "").trim().slice(0, 2000);
    if (!finalPrompt) {
      onToast?.("Prompt required");
      return;
    }
    setLoadingGenerate(true);
    try {
      const { data } = await client.post("/api/admin/swarm-builder/generate", { prompt: finalPrompt });
      if (!data?.config) {
        onToast?.("AI did not return config");
      } else {
        setConfig(data.config);
        setPrompt(finalPrompt);
        onToast?.("Preview generated");
      }
    } catch (error) {
      onToast?.(error?.response?.data?.error || "Generate failed");
    } finally {
      setLoadingGenerate(false);
    }
  };

  const runRefine = async () => {
    if (!config) return;
    const refineText = String(refinement || "").trim();
    if (!refineText) return;
    const refinePrompt = `${prompt}\n\nRefine this config: ${JSON.stringify(config)}\n\nChanges: ${refineText}`;
    await runGenerate(refinePrompt);
    setRefinement("");
  };

  const savePrompt = () => {
    if (!prompt.trim() || !config) return;
    const next = [
      {
        prompt,
        swarm_name: String(config.swarm_name || "custom"),
        created_at: new Date().toISOString(),
        config_preview: {
          display_name: config.display_name,
          agents: previewAgents.length,
          color: config.color,
        },
      },
      ...savedPrompts,
    ];
    setSavedPrompts(next);
    if (!writePromptLibrary(next)) {
      onToast?.("Unable to save prompt on this browser");
      return;
    }
    onToast?.("Prompt saved");
  };

  const updateConfig = (patch) => setConfig((prev) => ({ ...(prev || {}), ...patch }));

  const createSwarm = async () => {
    if (!config) return;
    setLoadingCreate(true);
    try {
      const payload = {
        ...config,
        priority: Number(config.priority || 5),
        cost_limit_daily: Number(config.cost_limit_daily || 0),
        task_queue_settings: {
          ...(config.task_queue_settings || {}),
          max_concurrent: Number(config?.task_queue_settings?.max_concurrent || 3),
        },
      };
      const { data } = await client.post("/api/admin/swarm-builder/create", { config: payload });
      onToast?.(`Created ${data?.agents_created || 0} agents`);
      onCreated?.();
      onClose?.();
    } catch (error) {
      onToast?.(error?.response?.data?.error || "Create failed");
    } finally {
      setLoadingCreate(false);
    }
  };

  if (!open) return null;

  return (
    <div className="modal-overlay swarm-builder-overlay" onClick={(event) => event.target === event.currentTarget && onClose?.()}>
      <article className="modal glass swarm-builder-modal">
        <div className="row between">
          <button type="button" className="share-btn" onClick={onClose}>× Close</button>
          <strong>🚀 Swarm Builder</strong>
          <span />
        </div>
        <div className="swarm-builder-grid">
          <section className="swarm-builder-left">
            <textarea
              className="bt-field swarm-builder-textarea"
              placeholder={"Describe what this swarm should do...\n\nExample: Create a marketing swarm that posts daily to Twitter and Instagram, monitors competitor accounts, generates weekly performance reports, and alerts me about viral trends."}
              maxLength={2000}
              value={prompt}
              onChange={(event) => {
                setPrompt(event.target.value.slice(0, 2000));
                event.target.style.height = "auto";
                event.target.style.height = `${Math.max(160, event.target.scrollHeight)}px`;
              }}
            />
            <div className="row between fs-12 text-3">
              <span>Prompt</span>
              <span>{promptLength}/2000</span>
            </div>
            <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              {EXAMPLE_PROMPTS.map((item) => (
                <button key={item.label} type="button" className="pill pill-gray" onClick={() => setPrompt(item.prompt)}>
                  {item.label}
                </button>
              ))}
            </div>
            <button type="button" className={`swarm-generate-btn ${loadingGenerate ? "is-loading" : ""}`} disabled={loadingGenerate} onClick={() => runGenerate(prompt)}>
              {loadingGenerate ? "AI is designing your swarm..." : "✨ Generate Preview"}
            </button>

            {config ? (
              <div className="swarm-refine-wrap">
                <input className="bt-field" placeholder="Refine: add a voice agent, remove SEO..." value={refinement} onChange={(event) => setRefinement(event.target.value)} />
                <div className="row gap-2">
                  <button type="button" className="pill pill-violet" disabled={loadingGenerate || loadingCreate} onClick={runRefine}>Refine</button>
                  <button type="button" className="pill pill-gray" disabled={loadingGenerate || loadingCreate} onClick={savePrompt}>Save this prompt</button>
                </div>
              </div>
            ) : null}
          </section>

          <aside className="swarm-builder-right">
            {!config ? (
              <div className="swarm-builder-empty">
                <strong>✨ Describe your swarm on the left and click Generate Preview</strong>
              </div>
            ) : (
              <>
                <article className="glass-2 swarm-preview-card" style={{ borderLeft: `3px solid ${config.color || "oklch(0.72 0.18 295)"}` }}>
                  <div className="row gap-2">
                    <span>{config.icon || "🤖"}</span>
                    <strong>{config.display_name || "New Swarm"}</strong>
                  </div>
                  <div className="text-3 fs-12" style={{ marginTop: 6 }}>{config.description || "No description provided."}</div>
                  <div className="text-3 fs-12" style={{ marginTop: 8 }}>Agents: {previewAgents.length}</div>
                  <div className="row gap-1" style={{ flexWrap: "wrap", marginTop: 8 }}>
                    {previewAgents.map((agent) => (
                      <span key={agent.agent_id || agent.name} className="pill pill-gray">{agent.name || agent.agent_id}</span>
                    ))}
                  </div>
                  <div className="row gap-1" style={{ flexWrap: "wrap", marginTop: 8 }}>
                    {previewAgents.flatMap((agent) => (Array.isArray(agent.capabilities) ? agent.capabilities : [])).slice(0, 10).map((cap, idx) => (
                      <span key={`${cap}-${idx}`} className={`cap-chip ${capabilityClass(cap)}`}>{cap}</span>
                    ))}
                  </div>
                </article>

                <article className="glass-2 swarm-advanced">
                  <button type="button" className="warroom-directory-toggle" onClick={() => setShowAdvanced((prev) => !prev)}>
                    {showAdvanced ? "▼" : "▶"} Advanced Settings
                  </button>
                  {showAdvanced ? (
                    <div className="swarm-advanced-body">
                      <label className="fs-12 text-3">Swarm Name</label>
                      <input className="bt-field" value={config.swarm_name || ""} onChange={(event) => updateConfig({ swarm_name: event.target.value })} />
                      <label className="fs-12 text-3">Priority ({Number(config.priority || 5)})</label>
                      <input type="range" min={1} max={10} value={Number(config.priority || 5)} onChange={(event) => updateConfig({ priority: Number(event.target.value) })} />
                      <label className="fs-12 text-3">Max concurrent tasks</label>
                      <input
                        className="bt-field"
                        type="number"
                        min={1}
                        value={Number(config?.task_queue_settings?.max_concurrent || 3)}
                        onChange={(event) => updateConfig({ task_queue_settings: { ...(config.task_queue_settings || {}), max_concurrent: Number(event.target.value || 1) } })}
                      />
                      <label className="fs-12 text-3">Cost limit/day (€)</label>
                      <input className="bt-field" type="number" min={0} step="0.1" value={Number(config.cost_limit_daily || 0)} onChange={(event) => updateConfig({ cost_limit_daily: Number(event.target.value || 0) })} />
                      <label className="swarm-toggle"><input type="checkbox" checked={Boolean(config.memory_enabled)} onChange={(event) => updateConfig({ memory_enabled: event.target.checked })} /> Memory enabled</label>
                      <label className="swarm-toggle"><input type="checkbox" checked={Boolean(config.human_approval_required)} onChange={(event) => updateConfig({ human_approval_required: event.target.checked })} /> Human approval required</label>
                    </div>
                  ) : null}
                </article>

                <article className="glass-2 swarm-cost-card">
                  <strong>Cost Estimate</strong>
                  <div className="text-3 fs-12">Estimated monthly cost: ~€{Number(config.estimated_monthly_cost || 0)}</div>
                  <div className="text-3 fs-12">Agents: {previewAgents.length} | Tasks/day: ~{Number(config?.task_queue_settings?.rate_limit_per_hour || 0)}</div>
                </article>

                <button type="button" className="swarm-create-btn" disabled={loadingCreate || !config} onClick={createSwarm}>
                  {loadingCreate ? "Creating agents..." : "🚀 Create Swarm"}
                </button>

                <div className="swarm-templates">
                  <strong>Quick Templates:</strong>
                  <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
                    {QUICK_TEMPLATES.map((template) => (
                      <button key={template.label} type="button" className="pill pill-gray" disabled={loadingGenerate || loadingCreate} onClick={() => { setPrompt(template.prompt); runGenerate(template.prompt); }}>
                        {template.label}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}

            <article className="glass-2 swarm-library">
              <button type="button" className="warroom-directory-toggle" onClick={() => setShowLibrary((prev) => !prev)}>
                {showLibrary ? "▼" : "▶"} 📚 My Saved Prompts
              </button>
              {showLibrary ? (
                <div className="swarm-library-list">
                  {savedPrompts.map((item, index) => (
                    <button
                      key={`${item.created_at}-${index}`}
                      type="button"
                      className="swarm-library-item"
                      onClick={() => {
                        setPrompt(String(item.prompt || ""));
                        if (item.config_preview?.display_name) {
                          onToast?.(`Loaded: ${item.config_preview.display_name}`);
                        }
                      }}
                    >
                      <strong>{item.swarm_name || "saved_prompt"}</strong>
                      <span>{new Date(item.created_at || 0).toLocaleString()}</span>
                    </button>
                  ))}
                  {savedPrompts.length === 0 ? <span className="text-3 fs-12">No saved prompts yet.</span> : null}
                </div>
              ) : null}
            </article>
          </aside>
        </div>
      </article>
    </div>
  );
}
