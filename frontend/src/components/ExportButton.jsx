import { useEffect, useRef, useState } from "react";

export default function ExportButton({ className = "" }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    const onDocClick = (event) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  return (
    <div className={`export-menu ${className}`.trim()} ref={rootRef}>
      <button type="button" className="btn btn-ghost export-menu-trigger" onClick={() => setOpen((v) => !v)}>
        <span aria-hidden="true">📥</span>
        <span>Export</span>
      </button>
      {open ? (
        <div className="glass export-menu-dropdown">
          <button
            type="button"
            className="export-menu-item"
            onClick={() => {
              window.open("/api/export/trades.csv", "_blank", "noopener,noreferrer");
              setOpen(false);
            }}
          >
            📥 Export CSV
          </button>
          <button
            type="button"
            className="export-menu-item"
            onClick={() => {
              window.open("/api/export/report.pdf", "_blank", "noopener,noreferrer");
              setOpen(false);
            }}
          >
            📄 Export PDF Report
          </button>
        </div>
      ) : null}
    </div>
  );
}
