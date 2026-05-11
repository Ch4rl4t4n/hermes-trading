/**
 * Slot summary cards — Crypto / Akcie / Komodity with progress dots, prototype-style.
 */

const CATEGORIES = [
  {
    key: "crypto",
    label: "Crypto slots",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M9 8h6M9 12h6M9 16h6" />
      </svg>
    ),
  },
  {
    key: "stocks",
    label: "Stock slots",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="m7 14 4-4 3 3 5-6" />
      </svg>
    ),
  },
  {
    key: "commodity",
    label: "Commodity slots",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2 4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6z" />
      </svg>
    ),
  },
];

function dots(used, max) {
  const out = [];
  for (let i = 0; i < max; i += 1) {
    const filled = i < used;
    out.push(
      <span
        key={i}
        className={`hermes-slot-dot${filled ? " is-filled" : ""}`}
        aria-hidden="true"
      />,
    );
  }
  return out;
}

export default function SlotsHeader({ counts }) {
  return (
    <div className="hermes-slots">
      {CATEGORIES.map((c) => {
        const data = counts[c.key] || { used: 0, max: 0 };
        return (
          <article key={c.key} className="hermes-slot-card glass">
            <div className="hermes-slot-icon" aria-hidden="true">{c.icon}</div>
            <div className="hermes-slot-body">
              <span className="hermes-slot-label">{c.label}</span>
              <div className="hermes-slot-progress">
                <strong className="mono">{data.used}/{data.max}</strong>
                <span className="hermes-slot-dots">{dots(data.used, data.max)}</span>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
