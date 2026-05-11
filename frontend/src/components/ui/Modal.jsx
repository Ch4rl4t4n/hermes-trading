import { createPortal } from "react-dom";
import { useEffect, useId, useRef } from "react";

function collectFocusable(root) {
  if (!root) return [];
  const sel =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  return [...root.querySelectorAll(sel)].filter((el) => !el.hasAttribute("disabled"));
}

export default function Modal({ open, title, children, onClose, className = "" }) {
  const modalRef = useRef(null);
  const closeBtnRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const prevActive = document.activeElement;
    closeBtnRef.current?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose?.();
        return;
      }
      if (event.key !== "Tab") return;
      const node = modalRef.current;
      const focusables = collectFocusable(node);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey) {
        if (document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (prevActive && typeof prevActive.focus === "function") prevActive.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div
      className={`modal-overlay active ${className}`.trim()}
      role="presentation"
      onClick={onClose}
    >
      <div
        ref={modalRef}
        className="modal modal-auth"
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <button ref={closeBtnRef} type="button" className="modal-close" onClick={onClose} aria-label="Close modal">
          ×
        </button>
        {title ? (
          <h2 id={titleId} className="modal-title">
            {title}
          </h2>
        ) : null}
        {children}
      </div>
    </div>,
    document.body,
  );
}
