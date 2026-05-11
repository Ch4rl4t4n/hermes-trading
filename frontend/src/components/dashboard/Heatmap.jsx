import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getHeatmap } from "../../api/heatmap";
import { useCurrency } from "../../contexts/CurrencyContext";

/**
 * 24-hour market heatmap (CoinMarketCap-style treemap).
 *
 * Tabs route to the backend `metric` param. Liquidation / Open Interest
 * data is not yet sourced — those tabs render a "Coming soon" empty state.
 *
 * Layout: binary-partition treemap. Items are sorted by value desc, the
 * canvas is recursively split along its longer side at the cumulative
 * 50%-of-value point. Renders absolutely-positioned tiles inside a
 * relatively-positioned container — no SVG, plain DOM for crisp text.
 */

const TABS = [
  { id: "volume", label: "Volume" },
  { id: "change", label: "Chg%" },
  { id: "liquidation", label: "Liquidation" },
  { id: "open_interest", label: "Open Interest" },
];

const REFRESH_MS = 60_000;

function pickValue(item, metric) {
  if (metric === "change") return Math.max(0.0001, Math.abs(Number(item.change_24h || 0)));
  if (metric === "market_cap") return Math.max(1, Number(item.market_cap || 0));
  return Math.max(1, Number(item.volume_24h || 0));
}

function binaryTreemap(items, rect) {
  if (!items.length) return [];
  if (items.length === 1) return [{ ...items[0], rect }];

  const sorted = [...items].sort((a, b) => b.__v - a.__v);
  const total = sorted.reduce((s, i) => s + i.__v, 0) || 1;
  const half = total / 2;

  let cum = 0;
  let splitIdx = 1;
  for (let i = 0; i < sorted.length; i += 1) {
    cum += sorted[i].__v;
    if (cum >= half) {
      splitIdx = i + 1;
      break;
    }
  }
  splitIdx = Math.max(1, Math.min(sorted.length - 1, splitIdx));

  const left = sorted.slice(0, splitIdx);
  const right = sorted.slice(splitIdx);
  const leftSum = left.reduce((s, i) => s + i.__v, 0);
  const ratio = leftSum / total;

  const horizontal = rect.w >= rect.h;
  const leftRect = horizontal
    ? { x: rect.x, y: rect.y, w: rect.w * ratio, h: rect.h }
    : { x: rect.x, y: rect.y, w: rect.w, h: rect.h * ratio };
  const rightRect = horizontal
    ? { x: rect.x + rect.w * ratio, y: rect.y, w: rect.w * (1 - ratio), h: rect.h }
    : { x: rect.x, y: rect.y + rect.h * ratio, w: rect.w, h: rect.h * (1 - ratio) };

  return [...binaryTreemap(left, leftRect), ...binaryTreemap(right, rightRect)];
}

function colorForChange(pct) {
  // Map -10..0..+10 into a red→neutral→green ramp; clamp at 12 for max saturation.
  const c = Math.max(-12, Math.min(12, Number(pct) || 0));
  if (c >= 0) {
    // Greens
    const intensity = c / 12; // 0..1
    const bg = `rgba(34, 197, 94, ${0.18 + intensity * 0.55})`;
    const border = `rgba(34, 197, 94, ${0.35 + intensity * 0.4})`;
    return { bg, border, text: "#ffffff" };
  }
  const intensity = -c / 12;
  const bg = `rgba(239, 68, 68, ${0.18 + intensity * 0.55})`;
  const border = `rgba(239, 68, 68, ${0.35 + intensity * 0.4})`;
  return { bg, border, text: "#ffffff" };
}

function formatBig(num) {
  const n = Number(num) || 0;
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(2);
}

export default function Heatmap() {
  const [metric, setMetric] = useState("volume");
  const [items, setItems] = useState([]);
  const [comingSoon, setComingSoon] = useState(false);
  const [loading, setLoading] = useState(true);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const containerRef = useRef(null);
  const { format } = useCurrency();

  const load = useCallback(async (currentMetric) => {
    setLoading(true);
    try {
      const { data } = await getHeatmap({ metric: currentMetric, limit: 20 });
      setItems(Array.isArray(data?.items) ? data.items : []);
      setComingSoon(Boolean(data?.coming_soon));
    } catch {
      setItems([]);
      setComingSoon(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(metric);
    if (metric === "liquidation" || metric === "open_interest") return undefined;
    const id = window.setInterval(() => load(metric), REFRESH_MS);
    return () => window.clearInterval(id);
  }, [metric, load]);

  // Track container dimensions for responsive treemap.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const update = () => {
      const r = el.getBoundingClientRect();
      setSize({ w: r.width, h: r.height });
    };
    update();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const tiles = useMemo(() => {
    if (!items.length || size.w < 50 || size.h < 50) return [];
    const enriched = items
      .map((it) => ({ ...it, __v: pickValue(it, metric) }))
      .filter((it) => it.__v > 0);
    if (!enriched.length) return [];
    return binaryTreemap(enriched, { x: 0, y: 0, w: size.w, h: size.h });
  }, [items, metric, size]);

  const renderTile = (t) => {
    const palette = colorForChange(t.change_24h);
    const area = t.rect.w * t.rect.h;
    // Type scale by tile area — keep readable on tiny tiles.
    let symbolFs = 12;
    let valueFs = 10;
    if (area > 80_000) {
      symbolFs = 56;
      valueFs = 22;
    } else if (area > 40_000) {
      symbolFs = 42;
      valueFs = 18;
    } else if (area > 20_000) {
      symbolFs = 28;
      valueFs = 14;
    } else if (area > 9000) {
      symbolFs = 20;
      valueFs = 12;
    } else if (area > 4000) {
      symbolFs = 14;
      valueFs = 10;
    }
    const showValue = area > 4000;
    const showSymbol = area > 1500;

    let valueLabel = "";
    if (metric === "volume") valueLabel = `$${formatBig(t.volume_24h)}`;
    else if (metric === "market_cap") valueLabel = `$${formatBig(t.market_cap)}`;
    else valueLabel = `${(Number(t.change_24h) || 0).toFixed(2)}%`;

    const title =
      `${t.symbol || t.name} · ${t.name}\n` +
      `Price: ${format(t.price || 0, { decimals: t.price >= 100 ? 2 : 4 })}\n` +
      `24h: ${(Number(t.change_24h) || 0).toFixed(2)}%\n` +
      `Vol: $${formatBig(t.volume_24h)}\n` +
      `MCap: $${formatBig(t.market_cap)}`;

    return (
      <div
        key={t.symbol || t.name}
        className="hermes-heatmap-tile"
        style={{
          left: `${t.rect.x}px`,
          top: `${t.rect.y}px`,
          width: `${t.rect.w}px`,
          height: `${t.rect.h}px`,
          background: palette.bg,
          borderColor: palette.border,
          color: palette.text,
        }}
        title={title}
      >
        {showSymbol ? (
          <span className="hermes-heatmap-tile-symbol" style={{ fontSize: `${symbolFs}px` }}>
            {t.symbol}
          </span>
        ) : null}
        {showValue ? (
          <span className="hermes-heatmap-tile-value" style={{ fontSize: `${valueFs}px` }}>
            {valueLabel}
          </span>
        ) : null}
      </div>
    );
  };

  return (
    <article className="glass hermes-heatmap">
      <header className="hermes-heatmap-head">
        <div className="hermes-heatmap-title">
          <h3>Heatmap</h3>
          <span className="hermes-heatmap-sub">24 hour</span>
        </div>
        <div className="hermes-heatmap-tabs" role="tablist" aria-label="Heatmap metric">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={metric === t.id}
              className={`hermes-heatmap-tab${metric === t.id ? " is-active" : ""}`}
              onClick={() => setMetric(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <div className="hermes-heatmap-canvas" ref={containerRef}>
        {loading && !items.length ? (
          <div className="hermes-heatmap-state">Loading market data…</div>
        ) : comingSoon ? (
          <div className="hermes-heatmap-state">
            <strong>Coming soon</strong>
            <span>{TABS.find((t) => t.id === metric)?.label} data is on the roadmap.</span>
          </div>
        ) : !tiles.length ? (
          <div className="hermes-heatmap-state">No data right now — try again in a minute.</div>
        ) : (
          tiles.map(renderTile)
        )}
      </div>
    </article>
  );
}
