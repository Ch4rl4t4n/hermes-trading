import { useEffect } from "react";

export default function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(onClose, 2400);
    return () => clearTimeout(id);
  }, [toast, onClose]);

  if (!toast) return null;

  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        bottom: "calc(78px + env(safe-area-inset-bottom))",
        transform: "translateX(-50%)",
        zIndex: 999,
        animation: "toastSlideUp .24s ease-out",
      }}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div
        className="glass row gap-2"
        style={{ padding: "11px 14px", borderRadius: 12, minWidth: 220, maxWidth: 340 }}
      >
        <span className="dot dot-live" />
        <span className="fs-13">{toast.message}</span>
      </div>
    </div>
  );
}

