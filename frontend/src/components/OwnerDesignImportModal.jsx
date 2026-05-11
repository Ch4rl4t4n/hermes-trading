import { useEffect, useRef, useState } from "react";

import { importOwnerDesignBundle } from "../api/ownerDesign";

const ACCEPTED_EXT = [
  ".json",
  ".css",
  ".scss",
  ".less",
  ".html",
  ".htm",
  ".tsx",
  ".jsx",
  ".ts",
  ".js",
  ".cjs",
  ".mjs",
  ".zip",
];
const ACCEPTED =
  ACCEPTED_EXT.join(",") +
  ",application/json,text/css,application/zip,application/x-zip-compressed,text/html,text/javascript,application/javascript";
const MAX_BYTES = 32 * 1024 * 1024;

function fileSizeLabel(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function statusGlyph(status) {
  if (status === "ok") return { label: "OK", color: "var(--accent-success, oklch(0.72 0.18 155))" };
  if (status === "error") return { label: "ERROR", color: "oklch(0.65 0.2 25)" };
  return { label: "SKIPPED", color: "var(--text-3, oklch(0.6 0.02 260))" };
}

export default function OwnerDesignImportModal({ open, onClose, onAccept, onToast }) {
  const [busy, setBusy] = useState(false);
  const [filename, setFilename] = useState("");
  const [report, setReport] = useState(null);
  const [schema, setSchema] = useState(null);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) {
      setBusy(false);
      setFilename("");
      setReport(null);
      setSchema(null);
      setError("");
      setDragOver(false);
    }
  }, [open]);

  if (!open) return null;

  const handleFile = async (file) => {
    if (!file) return;
    setError("");
    setReport(null);
    setSchema(null);
    setFilename(file.name);
    if (file.size > MAX_BYTES) {
      setError(`File exceeds limit (${MAX_BYTES / (1024 * 1024)} MB).`);
      onToast?.(`File exceeds ${MAX_BYTES / (1024 * 1024)} MB.`);
      return;
    }
    const lower = (file.name || "").toLowerCase();
    if (!ACCEPTED_EXT.some((ext) => lower.endsWith(ext))) {
      const msg =
        "Supported: .json, .css/.scss/.less, .html, .tsx/.jsx/.ts/.js, or .zip. " +
        "For Claude prototypes, upload the full .zip — tokens are extracted from all sources at once.";
      setError(msg);
      onToast?.("Unsupported file type.");
      return;
    }
    setBusy(true);
    const result = await importOwnerDesignBundle(file);
    setBusy(false);
    const data = result.data || {};
    // Backend vracia success na vrchu payloadu; report ho neobsahuje — bez toho je ok=false a tlačidlo ostane disabled.
    if (data.report) {
      setReport({ ...data.report, importSucceeded: Boolean(data.success) });
    } else {
      setReport(null);
    }
    if (data.schema) setSchema(data.schema);
    if (data.error) {
      setError(String(data.error));
      onToast?.(String(data.error));
      return;
    }
    if (data.success === false) {
      onToast?.("Bundle has errors — fix and try again.");
      return;
    }
    if (data.success && data.schema) {
      onToast?.("Bundle looks good — you can insert it into the editor.");
    }
  };

  const onDrop = (ev) => {
    ev.preventDefault();
    setDragOver(false);
    const dt = ev.dataTransfer;
    const items = dt?.items;
    if (items && items.length) {
      for (let i = 0; i < items.length; i += 1) {
        const item = items[i];
        const entry = typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null;
        if (entry?.isDirectory) {
          setError(
            "You dropped a folder. Zip it first (right-click → “Send to → Compressed (zip) folder”) " +
              "and upload the resulting .zip — or extract only .css / .json / .html files."
          );
          onToast?.("Folders aren’t supported — zip it first.");
          return;
        }
      }
    }
    const f = dt?.files?.[0];
    if (f) handleFile(f);
    else {
      setError("Could not read any file from the drop. Try clicking the dropzone and picking a file manually.");
    }
  };

  const tokens = report?.stats?.tokens ?? (schema?.globalCssVars ? Object.keys(schema.globalCssVars).length : 0);
  const errorCount = (report?.errors?.length || 0) + (error ? 1 : 0);
  const warnCount = report?.warnings?.length || 0;
  const ok = Boolean(report?.importSucceeded && schema && !error);

  const onAcceptClick = () => {
    if (!ok || !schema) return;
    onAccept?.(schema);
    onClose?.();
  };

  return (
    <div
      className="developer-modal-backdrop"
      role="presentation"
      onClick={() => onClose?.()}
      onDragOver={(ev) => ev.preventDefault()}
    >
      <div
        className="glass"
        role="dialog"
        aria-modal="true"
        onClick={(ev) => ev.stopPropagation()}
        style={{
          maxWidth: 720,
          width: "min(720px, 92vw)",
          maxHeight: "86vh",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          overflow: "hidden",
        }}
      >
        <div className="row between" style={{ alignItems: "center" }}>
          <div className="col" style={{ gap: 4 }}>
            <h4 style={{ margin: 0 }}>Import design (Claude prototype / JSON / CSS / ZIP)</h4>
            <span className="text-3 fs-12">
              Validation runs right after upload. Insert into the editor is only allowed when the bundle has no errors.
              For Claude Code prototypes upload the <strong>full .zip</strong> — tokens are extracted from .css, .html, .tsx/.jsx too.
            </span>
          </div>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} onClick={() => onClose?.()}>
            Close
          </button>
        </div>

        <div
          onDragEnter={(ev) => {
            ev.preventDefault();
            setDragOver(true);
          }}
          onDragOver={(ev) => {
            ev.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="Choose file (JSON / CSS / HTML / JSX / TSX / ZIP)"
          style={{
            border: `1px dashed ${dragOver ? "var(--accent, oklch(0.72 0.18 295))" : "var(--border-subtle, oklch(1 0 0 / 0.18))"}`,
            background: dragOver ? "oklch(0.72 0.18 295 / 0.08)" : "oklch(1 0 0 / 0.02)",
            borderRadius: 14,
            padding: "22px 16px",
            textAlign: "center",
            cursor: "pointer",
            transition: "background 0.15s ease",
          }}
        >
          <strong style={{ display: "block", marginBottom: 4 }}>Drop here or click to choose</strong>
          <span className="text-3 fs-12">
            Accepts .json (Hermes schema or design tokens), .css/.scss/.less (`--var:` variables),
            .html / .tsx / .jsx / .ts / .js (extract `--var:` from markup), .zip (full prototype / Tailwind / Figma export).
            Limit 32 MB / max 400 relevant files / max 96 MB uncompressed.
            <br />
            <em>Tip:</em> If Claude Code gave you a folder, right-click → “Send to → Compressed (zip) folder” and upload that .zip.
          </span>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            style={{ display: "none" }}
            onChange={(ev) => {
              const f = ev.target.files?.[0];
              if (f) handleFile(f);
              ev.target.value = "";
            }}
          />
        </div>

        {filename ? (
          <div className="text-3 fs-12">
            <strong>File:</strong> {filename}
            {busy ? " · validating…" : null}
          </div>
        ) : null}

        {error ? (
          <div
            className="glass"
            style={{
              padding: 10,
              border: "1px solid oklch(0.65 0.2 25 / 0.55)",
              background: "oklch(0.65 0.2 25 / 0.08)",
            }}
          >
            <strong style={{ display: "block", marginBottom: 4 }}>Bundle rejected</strong>
            <span className="fs-13">{error}</span>
          </div>
        ) : null}

        {report ? (
          <div style={{ overflow: "auto", flex: 1, minHeight: 0 }}>
            <div className="row gap-2 fs-12" style={{ flexWrap: "wrap", marginBottom: 8 }}>
              <span
                className={`pill ${ok ? "pill-green" : "pill-red"}`}
                style={ok ? {} : { background: "oklch(0.65 0.2 25 / 0.18)", color: "oklch(0.85 0.05 25)" }}
              >
                {ok ? "Bundle OK" : "Bundle has errors"}
              </span>
              <span className="pill pill-gray">tokens: {tokens}</span>
              <span className="pill pill-gray">files: {report.stats?.total_files ?? 0}</span>
              <span className="pill pill-gray">JSON: {report.stats?.json_files ?? 0}</span>
              <span className="pill pill-gray">CSS: {report.stats?.css_files ?? 0}</span>
              <span className="pill pill-gray">skipped: {report.stats?.skipped ?? 0}</span>
              <span className="pill pill-amber">warnings: {warnCount}</span>
              <span
                className="pill"
                style={{
                  background: errorCount ? "oklch(0.65 0.2 25 / 0.18)" : "oklch(0.6 0.02 260 / 0.18)",
                  color: errorCount ? "oklch(0.85 0.05 25)" : "var(--text-2)",
                  border: "none",
                }}
              >
                errors: {errorCount}
              </span>
            </div>

            {report.errors?.length ? (
              <div className="glass" style={{ padding: 10, marginBottom: 10, border: "1px solid oklch(0.65 0.2 25 / 0.4)" }}>
                <strong style={{ display: "block", marginBottom: 6 }}>Errors</strong>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {report.errors.map((line, i) => (
                    <li key={`e-${i}`} className="fs-12" style={{ color: "oklch(0.85 0.05 25)" }}>
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {warnCount ? (
              <div className="glass" style={{ padding: 10, marginBottom: 10, border: "1px solid oklch(0.7 0.16 75 / 0.45)" }}>
                <strong style={{ display: "block", marginBottom: 6 }}>Warnings</strong>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {report.warnings.map((line, i) => (
                    <li key={`w-${i}`} className="fs-12">
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="glass" style={{ padding: 10 }}>
              <strong style={{ display: "block", marginBottom: 6 }}>Files</strong>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-3)" }}>
                    <th style={{ padding: "4px 6px" }}>Name</th>
                    <th style={{ padding: "4px 6px" }}>Status</th>
                    <th style={{ padding: "4px 6px" }}>Role</th>
                    <th style={{ padding: "4px 6px", textAlign: "right" }}>Tokens</th>
                    <th style={{ padding: "4px 6px", textAlign: "right" }}>Size</th>
                  </tr>
                </thead>
                <tbody>
                  {(report.files || []).map((row, i) => {
                    const g = statusGlyph(row.status);
                    return (
                      <tr key={`f-${i}`} style={{ borderTop: "1px solid oklch(1 0 0 / 0.06)" }}>
                        <td style={{ padding: "4px 6px", wordBreak: "break-all" }}>{row.name}</td>
                        <td style={{ padding: "4px 6px", color: g.color }}>{g.label}</td>
                        <td style={{ padding: "4px 6px" }}>{row.role || row.reason || "—"}</td>
                        <td style={{ padding: "4px 6px", textAlign: "right" }}>{row.extracted ?? "—"}</td>
                        <td style={{ padding: "4px 6px", textAlign: "right" }}>{fileSizeLabel(row.size)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <div className="row gap-2" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} onClick={() => onClose?.()}>
            Cancel
          </button>
          <button
            type="button"
            className="pill pill-violet"
            style={{ border: "none" }}
            disabled={!ok || busy}
            title={!ok ? "Upload must pass with no errors" : ""}
            onClick={onAcceptClick}
          >
            Insert into editor
          </button>
        </div>
      </div>
    </div>
  );
}
