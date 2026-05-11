import { useEffect } from "react";
import { onboardingPercent } from "../utils/onboarding";
import { STORAGE_KEYS } from "../utils/storageKeys";

/**
 * Onboarding "checklist" popup. Replaces the static dashboard widget.
 *
 * Triggers (handled by App.jsx):
 *   - For new users with onboarding < 100% (24h cooldown via localStorage)
 *   - Manually re-opened from the Rewards page
 *
 * Each step is a clickable row: clicking it dismisses the modal and
 * navigates to the related page (marketplace, alerts, settings, backtest).
 *
 * No DB writes — completion state is derived from real user data
 * (see `utils/onboarding.js`).
 */

function CheckIcon({ done }) {
  if (done) {
    return (
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        <path
          d="M3.5 8.5l3 3 6-7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.45" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
      <path
        d="M5 3l5 5-5 5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function OnboardingProgressModal({
  open,
  steps = [],
  onClose,
  onNavigate,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (ev) => {
      if (ev.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const pct = onboardingPercent(steps);
  const done = steps.filter((s) => s.done).length;
  const total = steps.length || 1;
  const isComplete = done >= total;

  const handleStepClick = (step) => {
    if (!step?.target) {
      onClose?.();
      return;
    }
    onClose?.();
    onNavigate?.(step.target);
  };

  const handleDismiss = () => {
    try {
      window.localStorage.setItem(
        STORAGE_KEYS.ONBOARDING_PROGRESS_DISMISSED,
        String(Date.now()),
      );
    } catch {
      /* ignore */
    }
    onClose?.();
  };

  return (
    <div
      className="hermes-onb-progress-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="hermes-onb-progress-title"
    >
      <div className="hermes-onb-progress-shell">
        <button
          type="button"
          className="hermes-onb-progress-close"
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>

        <header className="hermes-onb-progress-head">
          <span className="hermes-onb-progress-eyebrow">Onboarding</span>
          <h2 id="hermes-onb-progress-title" className="hermes-onb-progress-title">
            {isComplete
              ? "You're all set."
              : "Finish setting up Hermes."}
          </h2>
          <p className="hermes-onb-progress-lead">
            {isComplete
              ? "Every milestone unlocked. Keep an eye on Rewards for new badges."
              : `${done} of ${total} steps complete — pick up where you left off.`}
          </p>
        </header>

        <div className="hermes-onb-progress-bar" aria-hidden="true">
          <div
            className="hermes-onb-progress-bar-fill"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="hermes-onb-progress-pct">{pct}%</span>

        <ul className="hermes-onb-progress-list">
          {steps.map((step) => (
            <li key={step.key}>
              <button
                type="button"
                className={`hermes-onb-progress-item${step.done ? " is-done" : ""}`}
                onClick={() => handleStepClick(step)}
                disabled={step.done}
                aria-label={`${step.label} — ${step.done ? "complete" : "open"}`}
              >
                <span
                  className={`hermes-onb-progress-check${step.done ? " is-on" : ""}`}
                  aria-hidden="true"
                >
                  <CheckIcon done={step.done} />
                </span>
                <span className="hermes-onb-progress-item-body">
                  <strong>{step.label}</strong>
                  <span>{step.description}</span>
                </span>
                {step.done ? (
                  <span className="hermes-onb-progress-item-status is-done">Done</span>
                ) : (
                  <span className="hermes-onb-progress-item-status">
                    Open <ArrowIcon />
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>

        <footer className="hermes-onb-progress-foot">
          <button
            type="button"
            className="hermes-onb-progress-secondary"
            onClick={handleDismiss}
          >
            {isComplete ? "Close" : "Maybe later"}
          </button>
          {!isComplete ? (
            <button
              type="button"
              className="hermes-onb-progress-primary"
              onClick={() => {
                const next = steps.find((s) => !s.done);
                if (next) handleStepClick(next);
                else onClose?.();
              }}
            >
              Continue setup
            </button>
          ) : (
            <button
              type="button"
              className="hermes-onb-progress-primary"
              onClick={() => {
                onClose?.();
                onNavigate?.("rewards");
              }}
            >
              View rewards
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
