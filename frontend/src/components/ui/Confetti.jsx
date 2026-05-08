import { useEffect, useMemo, useState } from "react";
import { sendNotification } from "../../utils/notifications";
import { sounds } from "../../utils/sounds";
import { useVoice } from "../../hooks/useVoice";
import { STORAGE_KEYS } from "../../utils/storageKeys";

function seeded(index, salt) {
  const value = Math.sin(index * 97.13 + salt * 31.7) * 10000;
  return value - Math.floor(value);
}

export default function Confetti({ trigger, duration = 3000 }) {
  const [active, setActive] = useState(false);
  const { speak, isSupported } = useVoice();

  useEffect(() => {
    if (!trigger) return undefined;
    const activateTimer = setTimeout(() => setActive(true), 0);
    sounds.profit();
    const voiceEnabledRaw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEYS.VOICE_ENABLED) : null;
    const voiceEnabled = voiceEnabledRaw === null ? true : voiceEnabledRaw === "true";
    if (voiceEnabled && isSupported.tts) {
      const messages = [
        "Trade closed in profit. Well done.",
        "Another win. Momentum is building.",
        "Profit secured. Agent performing well.",
        "Positive return achieved.",
        "Target reached. Excellent execution.",
      ];
      const msg = messages[Math.floor(Math.random() * messages.length)];
      speak(msg);
    }
    sendNotification("💰 Trade Closed", "Your agent secured a profit!");
    const timer = setTimeout(() => setActive(false), duration);
    return () => {
      clearTimeout(activateTimer);
      clearTimeout(timer);
    };
  }, [duration, isSupported.tts, speak, trigger]);

  const pieces = useMemo(
    () =>
      Array.from({ length: 60 }, (_, i) => ({
        id: i,
        color: [
          "oklch(0.72 0.18 155)",
          "oklch(0.72 0.18 295)",
          "oklch(0.82 0.14 75)",
          "oklch(0.65 0.2 25)",
          "oklch(0.85 0.15 200)",
        ][i % 5],
        left: `${seeded(i, 1) * 100}%`,
        delay: `${seeded(i, 2) * 2}s`,
        duration: `${2 + seeded(i, 3) * 2}s`,
        size: `${6 + seeded(i, 4) * 8}px`,
        rotation: `${seeded(i, 5) * 360}deg`,
        circle: seeded(i, 6) > 0.5,
      })),
    [],
  );

  if (!active) return null;

  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9999, overflow: "hidden" }}>
      {pieces.map((piece) => (
        <div
          key={piece.id}
          style={{
            position: "absolute",
            top: "-20px",
            left: piece.left,
            width: piece.size,
            height: piece.size,
            background: piece.color,
            borderRadius: piece.circle ? "50%" : "2px",
            transform: `rotate(${piece.rotation})`,
            animation: `confetti-fall ${piece.duration} ${piece.delay} ease-in forwards`,
          }}
        />
      ))}
      <style>{`
        @keyframes confetti-fall {
          0% { transform: translateY(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(110vh) rotate(720deg); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
