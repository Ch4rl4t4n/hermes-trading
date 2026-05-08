import { memo } from "react";

function SparkLine({ points = [], color }) {
  if (!points.length) return null;

  const width = 120;
  const height = 38;
  const pad = 3;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = (width - pad * 2) / Math.max(points.length - 1, 1);

  const coords = points.map((value, idx) => {
    const x = pad + idx * step;
    const y = height - pad - ((value - min) / range) * (height - pad * 2);
    return { x, y };
  });

  const d = coords
    .map((p, i) => {
      if (i === 0) return `M ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
      const prev = coords[i - 1];
      const cx = ((prev.x + p.x) / 2).toFixed(2);
      return `Q ${cx} ${prev.y.toFixed(2)} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    })
    .join(" ");

  const positive = points[points.length - 1] >= points[0];
  const stroke = color || (positive ? "var(--color-green)" : "var(--color-red)");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export default memo(SparkLine);

