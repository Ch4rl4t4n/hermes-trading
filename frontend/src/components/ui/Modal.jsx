import { createPortal } from "react-dom";
import { useEffect, useId, useRef } from "react";

export default function Modal({ open, title, children, onClose, className = "" }) {
  const closeBtnRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const prevActive = document.activeElement;
    closeBtnRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (prevActive && typeof prevActive.focus === "function") prevActive.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div className={`modal-overlay active ${className}`.trim()} onClick={onClose}>
      <div className="modal modal-auth" onClick={(e) => e.stopPropagation()}>
        <button ref={closeBtnRef} type="button" className="modal-close" onClick={onClose} aria-label="Zavrieť modal">
          ×
        </button>
        <div role="dialog" aria-modal="true" aria-labelledby={title ? titleId : undefined}>
          {title ? <div id={titleId} className="modal-title">{title}</div> : null}
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
