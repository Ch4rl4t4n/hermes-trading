import { useEffect, useMemo, useState } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

const COACH_MESSAGES = [
  "Every trader faces drawdowns. What matters is how you respond.",
  "Losses are tuition fees. Your agents are learning.",
  "The market tests patience. Stay disciplined.",
  "Even the best strategies have rough patches. Trust the process.",
];

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000;

function safeGetNumber(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function safeSetString(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore storage errors in private mode.
  }
}

export default function CoachMessage({ totalPnl }) {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState(COACH_MESSAGES[0]);

  const drawdownTriggered = useMemo(() => {
    const pnl = Number(totalPnl || 0);
    const peak = safeGetNumber(STORAGE_KEYS.COACH_PEAK_PNL, pnl);
    const nextPeak = Math.max(peak, pnl);
    safeSetString(STORAGE_KEYS.COACH_PEAK_PNL, String(nextPeak));

    // If peak is <= 0, fallback to absolute drop threshold.
    if (nextPeak <= 0) return pnl <= -5;
    return pnl <= nextPeak * 0.95;
  }, [totalPnl]);

  useEffect(() => {
    if (!drawdownTriggered) return;
    const lastShownRaw = safeGetNumber(STORAGE_KEYS.COACH_LAST_SHOWN, 0);
    const canShow = !lastShownRaw || Date.now() - lastShownRaw >= FOUR_HOURS_MS;
    if (!canShow) return;
    const pick = COACH_MESSAGES[Math.floor(Math.random() * COACH_MESSAGES.length)];
    const timer = setTimeout(() => {
      setMessage(pick);
      setVisible(true);
    }, 0);
    safeSetString(STORAGE_KEYS.COACH_LAST_SHOWN, String(Date.now()));
    return () => clearTimeout(timer);
  }, [drawdownTriggered]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") setVisible(false);
    };
    if (visible) window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visible]);

  if (!visible) return null;

  return (
    <aside className="coach-message" role="dialog" aria-label="Coach message">
      <div className="coach-header">
        <strong>🧘 Coach</strong>
        <button type="button" className="coach-close" onClick={() => setVisible(false)} aria-label="Dismiss coach message">
          ×
        </button>
      </div>
      <div className="coach-sep" />
      <p className="coach-body">{message}</p>
      <div className="coach-sep" />
      <div className="coach-actions">
        <button type="button" className="coach-btn coach-btn-muted" onClick={() => setVisible(false)}>
          💪 Got it
        </button>
        <button
          type="button"
          className="coach-btn coach-btn-accent"
          onClick={() => {
            window.location.href = "/trades";
          }}
        >
          📊 Review trades
        </button>
      </div>
    </aside>
  );
}
