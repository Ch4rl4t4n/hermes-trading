import { useEffect, useMemo, useState } from "react";

export default function Confetti({ trigger, duration = 3000 }) {
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (!trigger) return undefined;
    setActive(true);
    const timer = setTimeout(() => setActive(false), duration);
    return () => clearTimeout(timer);
  }, [trigger, duration]);

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
        left: `${Math.random() * 100}%`,
        delay: `${Math.random() * 2}s`,
        duration: `${2 + Math.random() * 2}s`,
        size: `${6 + Math.random() * 8}px`,
        rotation: `${Math.random() * 360}deg`,
        circle: Math.random() > 0.5,
      })),
    [trigger],
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
