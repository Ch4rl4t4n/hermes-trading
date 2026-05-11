import { useEffect, useRef, useState } from "react";
import { useCurrency } from "../contexts/CurrencyContext";

/**
 * Compact dropdown for picking the active display currency.
 * Sits in the top nav next to the notification bell.
 */
export default function CurrencySelector() {
  const { code, options, setCurrency } = useCurrency();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (ev) => {
      if (ref.current && !ref.current.contains(ev.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const active = options.find((o) => o.code === code) || options[0];

  return (
    <div className="hermes-currency" ref={ref}>
      <button
        type="button"
        className={`hermes-currency-trigger${open ? " is-open" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={`Display currency (${active.name})`}
      >
        <span className="hermes-currency-code">{active.code}</span>
        <span className="hermes-currency-chevron" aria-hidden="true">▾</span>
      </button>
      {open ? (
        <div className="hermes-currency-menu" role="menu">
          <div className="hermes-currency-menu-head">Display currency</div>
          {options.map((opt) => {
            const isActive = opt.code === code;
            return (
              <button
                key={opt.code}
                type="button"
                role="menuitem"
                className={`hermes-currency-item${isActive ? " is-active" : ""}`}
                onClick={() => {
                  setCurrency(opt.code);
                  setOpen(false);
                }}
              >
                <span className="hermes-currency-code-mono">{opt.code}</span>
                <span className="hermes-currency-name">{opt.name}</span>
                {isActive ? <span className="hermes-currency-tick" aria-hidden="true">✓</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
