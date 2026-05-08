import { memo, useEffect, useMemo, useState } from "react";

import { deleteAgentMemory, getAgentMemory, setAgentMemory } from "../api/agents";

function formatTimestamp(value) {
  if (!value) return "Unknown update";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "Unknown update";
  return dt.toLocaleString();
}

function MemoryVault({ agentId }) {
  const normalizedAgentId = useMemo(() => String(agentId || "").trim(), [agentId]);
  const [memories, setMemories] = useState([]);
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    if (!normalizedAgentId) {
      setMemories([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await getAgentMemory(normalizedAgentId);
      setMemories(Array.isArray(result.data) ? result.data : []);
    } catch {
      setError("Unable to load memory entries.");
    } finally {
      setLoading(false);
    }
  };

  const add = async () => {
    const key = newKey.trim();
    if (!key || saving || !normalizedAgentId) return;
    setSaving(true);
    setError("");
    try {
      const result = await setAgentMemory(normalizedAgentId, key, newVal);
      if (!result.data) throw new Error("save_failed");
      setNewKey("");
      setNewVal("");
      await load();
    } catch {
      setError("Unable to save memory entry.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (key) => {
    if (!key || saving || !normalizedAgentId) return;
    setSaving(true);
    setError("");
    try {
      const result = await deleteAgentMemory(normalizedAgentId, key);
      if (!result.data) throw new Error("delete_failed");
      await load();
    } catch {
      setError("Unable to delete memory entry.");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!normalizedAgentId) return undefined;
    const timer = window.setTimeout(() => {
      load();
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedAgentId]);

  return (
    <section className="memory-vault glass-2">
      <div className="memory-vault-head">
        <div className="memory-vault-title">
          <span aria-hidden="true">🧠</span>
          <h4>Memory Vault</h4>
        </div>
        <span className="pill pill-violet">{`${memories.length} entries`}</span>
      </div>

      {error ? <div className="memory-vault-error">{error}</div> : null}
      {loading ? (
        <div className="memory-vault-empty">Loading memory entries...</div>
      ) : memories.length === 0 ? (
        <div className="memory-vault-empty">No memories yet. Agent will learn from trades automatically.</div>
      ) : (
        <div className="memory-vault-list">
          {memories.map((entry) => (
            <article key={entry.key} className="memory-vault-card">
              <div className="memory-vault-card-head">
                <span className="memory-vault-key">{String(entry.key || "").toUpperCase()}</span>
                <button
                  type="button"
                  className="memory-vault-delete"
                  aria-label={`Delete memory ${entry.key}`}
                  onClick={() => remove(entry.key)}
                  disabled={saving}
                >
                  ×
                </button>
              </div>
              <div className="memory-vault-value">{String(entry.value ?? "")}</div>
              <div className="memory-vault-time">{formatTimestamp(entry.updated_at)}</div>
            </article>
          ))}
        </div>
      )}

      <div className="memory-vault-input-row">
        <input
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          maxLength={100}
          placeholder="memory key"
          disabled={saving}
        />
        <input
          value={newVal}
          onChange={(e) => setNewVal(e.target.value)}
          maxLength={2000}
          placeholder="memory value"
          disabled={saving}
        />
        <button type="button" className="btn btn-sm" onClick={add} disabled={saving || !newKey.trim()}>
          {saving ? "Saving..." : "Add"}
        </button>
      </div>
    </section>
  );
}

export default memo(MemoryVault);
