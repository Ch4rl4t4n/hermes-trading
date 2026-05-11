import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  aiAnalyzeOwnerDesign,
  aiGenerateOwnerDesign,
  applyOwnerDesignSchema,
  getOwnerDesignHistory,
  getOwnerDesignSchema,
  getOwnerDesignTemplate,
  importOwnerDesign,
  revertOwnerDesignVersion,
} from "../api/ownerDesign";
import OwnerDesignImportModal from "../components/OwnerDesignImportModal";
import { applyGlobalCssVars, bustDesignCachesAndRefresh, fetchAndApplyActiveDesignSchema } from "../utils/designSchema";

function apiErr(error, fallback) {
  return error?.response?.data?.error || error?.message || fallback;
}

function safeParse(text) {
  try {
    return [JSON.parse(text), null];
  } catch (err) {
    return [null, err.message];
  }
}

export default function OwnerDesign({ onToast }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [text, setText] = useState("{}");
  const [label, setLabel] = useState("");
  const [meta, setMeta] = useState({ active_version_id: null, applied_at: null });
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const fileRef = useRef(null);

  const [parsedSchema, parseError] = useMemo(() => safeParse(text), [text]);

  const previewVars = useMemo(() => {
    if (!parsedSchema || typeof parsedSchema !== "object") return {};
    const v = parsedSchema.globalCssVars;
    return v && typeof v === "object" ? v : {};
  }, [parsedSchema]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    const cur = await getOwnerDesignSchema();
    if (cur.error) {
      setError(apiErr(cur.error, "Load failed."));
      setLoading(false);
      return;
    }
    const schema = cur.data?.schema || {};
    setText(JSON.stringify(schema, null, 2));
    setMeta({
      active_version_id: cur.data?.active_version_id ?? null,
      applied_at: cur.data?.applied_at ?? null,
    });
    const hist = await getOwnerDesignHistory(40);
    setHistory(Array.isArray(hist.data?.versions) ? hist.data.versions : []);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const onLoadTemplate = async () => {
    const t = await getOwnerDesignTemplate();
    if (t.error) {
      onToast?.(apiErr(t.error, "Template unavailable."));
      return;
    }
    const schema = t.data?.schema || {};
    setText(JSON.stringify(schema, null, 2));
    onToast?.("Template loaded into editor.");
  };

  const onApply = async () => {
    if (parseError || !parsedSchema) {
      setError(`Invalid JSON: ${parseError}`);
      onToast?.("Fix the JSON in the editor.");
      return;
    }
    setSaving(true);
    setError("");
    const result = await applyOwnerDesignSchema(parsedSchema, label.trim());
    if (result.error || result.data?.error) {
      const msg = result.data?.error || apiErr(result.error, "Apply failed.");
      setError(msg);
      onToast?.(msg);
      setSaving(false);
      return;
    }
    onToast?.(result.data?.message || "Schema activated.");
    applyGlobalCssVars(parsedSchema.globalCssVars);
    await bustDesignCachesAndRefresh();
    setLabel("");
    await loadAll();
    setSaving(false);
  };

  const onRevert = async (versionId) => {
    if (!window.confirm(`Restore version #${versionId} as the new active version?`)) return;
    setSaving(true);
    const result = await revertOwnerDesignVersion(versionId);
    if (result.error || result.data?.error) {
      const msg = result.data?.error || apiErr(result.error, "Revert failed.");
      setError(msg);
      onToast?.(msg);
      setSaving(false);
      return;
    }
    onToast?.(result.data?.message || "Revert complete.");
    await bustDesignCachesAndRefresh();
    await loadAll();
    setSaving(false);
  };

  const onAnalyze = async () => {
    if (!parsedSchema) {
      onToast?.("Fix the JSON in the editor first.");
      return;
    }
    setAiBusy(true);
    setAnalysis("");
    const result = await aiAnalyzeOwnerDesign(parsedSchema);
    if (result.error || result.data?.error) {
      const msg = result.data?.error || apiErr(result.error, "Analyze failed.");
      onToast?.(msg);
      setAnalysis(`> Error: ${msg}`);
    } else {
      setAnalysis(String(result.data?.report_md || ""));
      onToast?.("AI audit complete.");
    }
    setAiBusy(false);
  };

  const onGenerate = async () => {
    const prompt = aiPrompt.trim();
    if (!prompt) {
      onToast?.("Enter a prompt for the AI generator.");
      return;
    }
    if (!parsedSchema) {
      onToast?.("Fix the JSON in the editor first.");
      return;
    }
    setAiBusy(true);
    const result = await aiGenerateOwnerDesign(prompt, parsedSchema);
    if (result.error || result.data?.error) {
      const msg = result.data?.error || apiErr(result.error, "Generate failed.");
      onToast?.(msg);
    } else {
      const next = result.data?.schema;
      if (next) {
        setText(JSON.stringify(next, null, 2));
        onToast?.("AI proposal loaded into the editor — review and Apply.");
      }
    }
    setAiBusy(false);
  };

  const onImportFile = async (file) => {
    if (!file) return;
    if (file.size > 480_000) {
      onToast?.("File is too large (>480 KB).");
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => onToast?.("Failed to read file.");
    reader.onload = async () => {
      const content = String(reader.result || "");
      const result = await importOwnerDesign({ content_json: content });
      if (result.error || result.data?.error) {
        const msg = result.data?.error || apiErr(result.error, "Import failed.");
        onToast?.(msg);
        return;
      }
      const next = result.data?.schema;
      if (next) {
        setText(JSON.stringify(next, null, 2));
        onToast?.("Import OK — review and Apply.");
      }
    };
    reader.readAsText(file);
  };

  if (loading) {
    return (
      <section className="page-content">
        <p className="text-3">Loading Owner CMS…</p>
      </section>
    );
  }

  return (
    <section className="page-content hermes-owner-design col gap-3">
      <header className="hermes-page-head">
        <div>
          <h1 className="hermes-page-title">Owner — Design System</h1>
          <p className="hermes-page-lead">Design token editor, bundle import from Claude Designer / Figma and the active production version</p>
        </div>
      </header>
      <article className="glass" style={{ padding: 16, maxWidth: 980 }}>
        <div className="row between" style={{ alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <h3 style={{ margin: 0 }}>Editor</h3>
          <div className="row gap-2 fs-12 text-3" style={{ flexWrap: "wrap" }}>
            <span>Active DB version: {meta.active_version_id ?? "—"}</span>
            <span>·</span>
            <span>Applied: {meta.applied_at ?? "—"}</span>
          </div>
        </div>
        <p className="text-3 fs-13" style={{ marginTop: 6 }}>
          JSON schema editor. After <strong>Apply</strong>, tokens are applied immediately to <code className="fs-12">:root</code>, service worker caches are cleared,
          and the DB history gets a new row (append-only audit).
        </p>
        {error ? (
          <div className="glass" style={{ padding: 10, marginBottom: 10, border: "1px solid oklch(0.65 0.2 25 / 0.5)" }}>
            {error}
          </div>
        ) : null}
        {parseError ? (
          <div className="glass" style={{ padding: 10, marginBottom: 10, border: "1px solid oklch(0.65 0.2 25 / 0.5)" }}>
            JSON parse: {parseError}
          </div>
        ) : null}

        <div className="row gap-2" style={{ flexWrap: "wrap", marginBottom: 10 }}>
          <button type="button" className="pill pill-violet" style={{ border: "none" }} disabled={saving || Boolean(parseError)} onClick={onApply}>
            {saving ? "Saving…" : "Save and activate"}
          </button>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} disabled={saving} onClick={onLoadTemplate}>
            Load template
          </button>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} disabled={saving} onClick={loadAll}>
            Refresh from DB
          </button>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} disabled={aiBusy || Boolean(parseError)} onClick={onAnalyze}>
            {aiBusy ? "AI…" : "AI Analyze"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json,text/plain"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onImportFile(f);
              e.target.value = "";
            }}
          />
          <button type="button" className="pill pill-violet" style={{ border: "none" }} onClick={() => setImportOpen(true)}>
            Import (JSON / CSS / ZIP)
          </button>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} onClick={() => fileRef.current?.click()}>
            Quick JSON paste
          </button>
        </div>

        <label className="col gap-2 fs-12 text-2" style={{ marginBottom: 10 }}>
          Revision note (optional)
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. violet glow tweak" />
        </label>

        <div className="row gap-2" style={{ alignItems: "stretch", flexWrap: "wrap" }}>
          <div className="col" style={{ flex: "2 1 380px", minWidth: 0 }}>
            <textarea
              className="inp"
              value={text}
              onChange={(e) => setText(e.target.value)}
              spellCheck={false}
              style={{
                width: "100%",
                minHeight: 360,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: 12,
                lineHeight: 1.45,
              }}
            />
          </div>
          <div
            className="glass col gap-2"
            style={{
              flex: "1 1 240px",
              minWidth: 220,
              padding: 12,
              ...previewVars,
            }}
          >
            <span className="fs-12 text-3">LIVE PREVIEW (editor — not yet applied)</span>
            <article
              className="agent-card"
              style={{
                padding: 14,
                borderRadius: 14,
                border: "1px solid var(--border-subtle)",
                background: "var(--surface-glass)",
                boxShadow: "0 0 28px var(--accent-glow)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <strong style={{ color: "var(--accent)" }}>Agent ξ-OWL</strong>
                <span className="pill pill-violet" style={{ background: "var(--accent)", color: "#000" }}>LIVE</span>
              </div>
              <div className="text-3 fs-12" style={{ marginBottom: 4 }}>BTC/USD · momentum</div>
              <div className="row gap-2 fs-12">
                <span className="pill pill-gray">Win 64%</span>
                <span className="pill pill-green">+12.3%</span>
              </div>
            </article>
            <span className="fs-12 text-3">tokens in globalCssVars: {Object.keys(previewVars).length}</span>
          </div>
        </div>
      </article>

      <article className="glass" style={{ padding: 16, maxWidth: 980 }}>
        <h4 style={{ marginTop: 0 }}>AI Generate</h4>
        <p className="text-3 fs-12">
          Describe what the AI should change — it will generate full valid schema JSON from the current editor and load it back (Apply is still manual).
        </p>
        <textarea
          className="inp"
          rows={3}
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          placeholder="e.g. “change primary accent to cyan and soften glow” or “add a lighter --surface-elevated token”"
          style={{ width: "100%" }}
        />
        <div className="row gap-2" style={{ marginTop: 8, flexWrap: "wrap" }}>
          <button type="button" className="pill pill-violet" style={{ border: "none" }} disabled={aiBusy || !aiPrompt.trim() || Boolean(parseError)} onClick={onGenerate}>
            {aiBusy ? "Generating…" : "Generate proposal"}
          </button>
          <span className="text-3 fs-12">model: claude-sonnet-4 (rate-limit ~6s)</span>
        </div>
        {analysis ? (
          <div className="glass" style={{ padding: 12, marginTop: 12 }}>
            <strong style={{ display: "block", marginBottom: 6 }}>AI Audit</strong>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, lineHeight: 1.5, margin: 0 }}>{analysis}</pre>
          </div>
        ) : null}
      </article>

      <OwnerDesignImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onToast={onToast}
        onAccept={(s) => {
          setText(JSON.stringify(s, null, 2));
          onToast?.("Bundle inserted into the editor — review and Apply.");
        }}
      />

      <article className="glass" style={{ padding: 16, maxWidth: 980 }}>
        <h4 style={{ marginTop: 0 }}>Version history</h4>
        <p className="text-3 fs-12">Revert creates a new record with a copy of the old JSON (append-only). Name your revision clearly when you Apply.</p>
        <div className="community-submissions">
          {history.map((row) => (
            <div key={row.id} className="community-submission-item">
              <div className="col">
                <strong>#{row.id}</strong>
                <span className="text-3 fs-12">
                  {row.label || "—"} · created: {row.created_at || "—"}
                  {row.applied_at ? ` · applied: ${row.applied_at}` : ""}
                </span>
              </div>
              <button type="button" className="pill pill-gray" style={{ border: "none" }} disabled={saving} onClick={() => onRevert(row.id)}>
                Revert to this
              </button>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
