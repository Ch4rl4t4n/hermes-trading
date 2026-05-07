import { createPortal } from "react-dom";

export default function Modal({ open, title, children, onClose, className = "" }) {
  if (!open) return null;
  return createPortal(
    <div className={`modal-overlay active ${className}`.trim()} onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal modal-auth" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        {title ? <div className="modal-title">{title}</div> : null}
        {children}
      </div>
    </div>,
    document.body,
  );
}
