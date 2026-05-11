import { useEffect, useState } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

/**
 * 3-step welcome modal for new accounts (eToro-style intro carousel).
 * Triggered automatically the first time a user reaches the dashboard
 * without any active agents. Persists a "seen" flag in localStorage.
 */

const STEPS = [
  {
    id: "copy",
    title: "When agents trade, you trade.",
    description:
      "Subscribe to verified Hermes pro agents and mirror their trades automatically — no manual orders required.",
    cta: "Next",
    illustration: "copy",
  },
  {
    id: "time",
    title: "Make time work for you.",
    description:
      "Hermes runs 24/7 across crypto, stocks and commodities. Streamline decisions and stay focused on results.",
    cta: "Next",
    illustration: "time",
  },
  {
    id: "transparent",
    title: "Fully transparent.",
    description:
      "Every trade ships with a 'why' explanation, signal score and live P&L. Discover top performers aligned with your strategy and invest with confidence.",
    cta: "Get started",
    illustration: "transparent",
  },
];

function StepIllustration({ id }) {
  if (id === "copy") {
    return (
      <div className="hermes-onb-illustration">
        <div className="hermes-onb-card hermes-onb-card-1" style={{ background: "linear-gradient(135deg,#1f2937,#0f172a)" }}>
          <div className="hermes-onb-avatar" style={{ background: "linear-gradient(135deg,#a78bfa,#6366f1)" }}>A</div>
          <div className="col" style={{ gap: 2 }}>
            <strong>Aurora.AI</strong>
            <span className="text-3 fs-12" style={{ color: "#ef4444" }}>−5.4%</span>
          </div>
          <span className="text-3 fs-12" style={{ marginLeft: "auto" }}>10.3K</span>
        </div>
        <div className="hermes-onb-card hermes-onb-card-2" style={{ background: "linear-gradient(135deg,#0f172a,#1e293b)" }}>
          <div className="hermes-onb-avatar" style={{ background: "linear-gradient(135deg,#22c55e,#10b981)" }}>S</div>
          <div className="col" style={{ gap: 2 }}>
            <strong>Sentinel</strong>
            <span className="text-3 fs-12" style={{ color: "#22c55e" }}>+87.35%</span>
          </div>
        </div>
        <div className="hermes-onb-card hermes-onb-card-3" style={{ background: "linear-gradient(135deg,#1e293b,#0f172a)" }}>
          <div className="hermes-onb-avatar" style={{ background: "linear-gradient(135deg,#fbbf24,#f59e0b)" }}>M</div>
          <div className="col" style={{ gap: 2 }}>
            <strong>Momentum</strong>
            <span className="text-3 fs-12" style={{ color: "#22c55e" }}>+93.17%</span>
          </div>
          <span className="text-3 fs-12" style={{ marginLeft: "auto" }}>83.2K</span>
        </div>
        <svg className="hermes-onb-spark" viewBox="0 0 240 80" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0,60 L40,40 L80,55 L120,30 L160,38 L200,15 L240,22" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      </div>
    );
  }
  if (id === "time") {
    return (
      <div className="hermes-onb-illustration is-time">
        <div className="hermes-onb-time-graph">
          <svg viewBox="0 0 280 140" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="onb-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22c55e" stopOpacity=".4" />
                <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d="M0,90 C40,65 60,75 80,55 C100,35 120,55 150,40 C180,25 220,55 280,30 L280,140 L0,140 Z" fill="url(#onb-fill)" />
            <path d="M0,90 C40,65 60,75 80,55 C100,35 120,55 150,40 C180,25 220,55 280,30" fill="none" stroke="#22c55e" strokeWidth="2.4" />
          </svg>
          <span className="hermes-onb-bubble" style={{ left: "12%", top: "30%", background: "rgba(167,139,250,.92)" }}>Retail</span>
          <span className="hermes-onb-bubble" style={{ left: "58%", top: "10%", background: "rgba(34,211,238,.92)" }}>Crypto</span>
          <span className="hermes-onb-bubble is-pulse" style={{ left: "44%", top: "44%", background: "linear-gradient(135deg,#22c55e,#10b981)" }}>Indices</span>
          <span className="hermes-onb-bubble" style={{ left: "20%", top: "62%", background: "rgba(251,191,36,.92)" }}>Software</span>
          <span className="hermes-onb-bubble" style={{ left: "70%", top: "70%", background: "rgba(99,102,241,.92)" }}>Tech</span>
          <span className="hermes-onb-bubble" style={{ left: "0%", top: "44%", background: "rgba(244,114,182,.92)" }}>ETF</span>
        </div>
      </div>
    );
  }
  return (
    <div className="hermes-onb-illustration is-transparent">
      <div className="hermes-onb-portrait">
        <div className="hermes-onb-portrait-glow" />
        <div className="hermes-onb-portrait-icon">📱</div>
        <div className="hermes-onb-portrait-bubbles">
          <span className="hermes-onb-portrait-bubble" style={{ background: "linear-gradient(135deg,#a78bfa,#6366f1)", top: "10%", right: "5%" }}>1</span>
          <span className="hermes-onb-portrait-bubble" style={{ background: "linear-gradient(135deg,#22c55e,#10b981)", top: "30%", left: "5%" }}>2</span>
          <span className="hermes-onb-portrait-bubble" style={{ background: "linear-gradient(135deg,#fbbf24,#f59e0b)", bottom: "20%", right: "10%" }}>3</span>
          <span className="hermes-onb-portrait-bubble" style={{ background: "linear-gradient(135deg,#ef4444,#dc2626)", bottom: "5%", left: "10%" }}>4</span>
        </div>
      </div>
    </div>
  );
}

export default function OnboardingModal({ open, onClose, onComplete }) {
  const [step, setStep] = useState(0);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (ev) => {
      if (ev.key === "Escape") handleClose();
      if (ev.key === "ArrowRight") setStep((s) => Math.min(STEPS.length - 1, s + 1));
      if (ev.key === "ArrowLeft") setStep((s) => Math.max(0, s - 1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = () => {
    setClosing(true);
    setTimeout(() => {
      try {
        window.localStorage.setItem(STORAGE_KEYS.ONBOARDING_SEEN, "1");
      } catch {
        /* ignore */
      }
      onClose?.();
      setClosing(false);
      setStep(0);
    }, 180);
  };

  const handleNext = () => {
    if (step >= STEPS.length - 1) {
      try {
        window.localStorage.setItem(STORAGE_KEYS.ONBOARDING_SEEN, "1");
      } catch {
        /* ignore */
      }
      onComplete?.();
      onClose?.();
      setStep(0);
      return;
    }
    setStep((s) => s + 1);
  };

  if (!open) return null;
  const cur = STEPS[step];

  return (
    <div className={`hermes-onb-backdrop${closing ? " is-closing" : ""}`} role="dialog" aria-modal="true" aria-labelledby="hermes-onb-title">
      <div className="hermes-onb-shell">
        <header className="hermes-onb-head">
          <strong className="hermes-onb-tag">When they invest, you invest.</strong>
          <button type="button" className="hermes-onb-close" onClick={handleClose} aria-label="Close intro">
            ×
          </button>
        </header>

        <div className="hermes-onb-progress" aria-hidden="true">
          {STEPS.map((s, idx) => (
            <span key={s.id} className={`hermes-onb-progress-bar${idx === step ? " is-active" : ""}${idx < step ? " is-done" : ""}`} />
          ))}
        </div>

        <div className="hermes-onb-body">
          {step > 0 ? (
            <button type="button" className="hermes-onb-arrow is-prev" onClick={() => setStep((s) => Math.max(0, s - 1))} aria-label="Previous">‹</button>
          ) : null}
          {step < STEPS.length - 1 ? (
            <button type="button" className="hermes-onb-arrow is-next" onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))} aria-label="Next">›</button>
          ) : null}

          <StepIllustration id={cur.illustration} />

          <h3 id="hermes-onb-title" className="hermes-onb-title">{cur.title}</h3>
          <p className="hermes-onb-desc">{cur.description}</p>
        </div>

        <footer className="hermes-onb-foot">
          <button type="button" className="hermes-onb-cta" onClick={handleNext}>
            {cur.cta}
          </button>
        </footer>
      </div>
    </div>
  );
}
