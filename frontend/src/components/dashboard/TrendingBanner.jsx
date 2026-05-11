import { useEffect, useMemo, useRef, useState } from "react";
import client from "../../api/client";

/**
 * Most Trending banner — single full-width card that flips through the
 * top 5 traded assets on the platform. The card swaps every 6 seconds in
 * a randomised order (no consecutive repeats) with a subtle fade
 * transition.
 *
 * Data source: /api/leaderboard?period=weekly (top assets by 7-day P&L).
 *
 *   Props:
 *     onSelect — fired when a card is clicked (parent decides where to nav)
 *     onAdd    — fired when the card's "+ ADD" CTA is pressed
 */

const ROTATE_INTERVAL_MS = 6000;
const TOP_COUNT = 5;

const CATEGORY_GRADIENT = {
  crypto: "linear-gradient(135deg, rgba(167,139,250,.5), rgba(99,102,241,.4) 55%, rgba(34,211,238,.35))",
  stocks: "linear-gradient(135deg, rgba(34,197,94,.4), rgba(59,130,246,.4))",
  commodity: "linear-gradient(135deg, rgba(245,158,11,.45), rgba(239,68,68,.35))",
  forex: "linear-gradient(135deg, rgba(59,130,246,.42), rgba(139,92,246,.35))",
  default: "linear-gradient(135deg, rgba(99,102,241,.4), rgba(34,211,238,.35))",
};

const CATEGORY_LABEL = {
  crypto: "Crypto",
  stocks: "Stocks",
  commodity: "Commodities",
  forex: "Forex",
};

function fakeSparkFromPct(pct, len = 16) {
  const sign = pct >= 0 ? 1 : -1;
  const amp = Math.min(Math.abs(pct) / 25, 1) || 0.25;
  return Array.from({ length: len }, (_, i) => {
    const phase = (i / (len - 1)) * Math.PI * 2;
    const noise = Math.sin(phase * 1.6 + sign) * amp * 0.4;
    const trend = (i / (len - 1)) * sign * amp;
    return 0.5 + trend + noise * 0.25;
  });
}

function buildSparkPath(values, w = 120, h = 38) {
  if (!values || values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = w / (values.length - 1);
  return values
    .map((v, i) => {
      const x = (i * stepX).toFixed(1);
      const y = (h - ((v - min) / range) * h).toFixed(1);
      return `${i === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");
}

function categoryKey(cat) {
  const c = String(cat || "").toLowerCase();
  if (c.startsWith("crypto") || c === "btc" || c === "eth") return "crypto";
  if (c.startsWith("stock") || c === "equity") return "stocks";
  if (c.startsWith("commod")) return "commodity";
  if (c.startsWith("forex") || c === "fx") return "forex";
  return "default";
}

/**
 * Pick a random index in [0, total) that is not equal to `current`.
 * Falls back to (current + 1) % total if total < 2 to avoid infinite loops.
 */
function pickNextRandomIndex(current, total) {
  if (total <= 1) return 0;
  let next = current;
  // Loop is bounded — at most a few iterations because total is small (≤5).
  while (next === current) {
    next = Math.floor(Math.random() * total);
  }
  return next;
}

export default function TrendingBanner({ onSelect, onAdd }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeIdx, setActiveIdx] = useState(0);
  const [fadeKey, setFadeKey] = useState(0);
  const intervalRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    client
      .get("/api/leaderboard?period=weekly")
      .then(({ data }) => {
        if (cancelled) return;
        const list = Array.isArray(data?.leaderboard) ? data.leaderboard : [];
        setRows(list.slice(0, TOP_COUNT));
        setActiveIdx(0);
        setFadeKey((k) => k + 1);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Random rotation timer — restarts whenever the dataset changes or the
  // user manually picks a card so the next auto-flip is always 6 s away.
  useEffect(() => {
    if (rows.length < 2) return undefined;
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      setActiveIdx((current) => pickNextRandomIndex(current, rows.length));
      setFadeKey((k) => k + 1);
    }, ROTATE_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
    };
  }, [rows.length]);

  const currentRow = useMemo(() => {
    if (rows.length) return rows[activeIdx % rows.length] || rows[0];
    return null;
  }, [rows, activeIdx]);

  const goTo = (idx) => {
    setActiveIdx(idx);
    setFadeKey((k) => k + 1);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      if (rows.length >= 2) {
        intervalRef.current = setInterval(() => {
          setActiveIdx((current) => pickNextRandomIndex(current, rows.length));
          setFadeKey((k) => k + 1);
        }, ROTATE_INTERVAL_MS);
      }
    }
  };

  if (!loading && !rows.length) {
    return (
      <section className="hermes-trending hermes-trending--empty">
        <header className="hermes-trending-head">
          <div>
            <h2 className="hermes-trending-title">Most Trending</h2>
            <p className="hermes-trending-lead">Top assets traded across our platform</p>
          </div>
        </header>
        <p className="text-3 fs-12">Trending data will appear once the leaderboard is populated.</p>
      </section>
    );
  }

  if (loading || !currentRow) {
    return (
      <section className="hermes-trending" aria-label="Most trending agents">
        <header className="hermes-trending-head">
          <div>
            <h2 className="hermes-trending-title">Most Trending</h2>
            <p className="hermes-trending-lead">Top 5 assets traded on Hermes · 7-day P&amp;L</p>
          </div>
        </header>
        <div className="hermes-trending-track">
          <div className="hermes-trending-card is-skeleton" aria-hidden="true">
            <span className="hermes-trending-card-tag">Loading</span>
            <header className="hermes-trending-card-head">
              <strong className="hermes-trending-card-symbol">— — —</strong>
            </header>
            <div className="hermes-trending-card-stats"><span>—</span></div>
          </div>
        </div>
      </section>
    );
  }

  const cat = categoryKey(currentRow.category);
  const gradient = CATEGORY_GRADIENT[cat] || CATEGORY_GRADIENT.default;
  const positive = Number(currentRow.pnl_pct || 0) >= 0;
  const accent = positive ? "#10b981" : "#ef4444";
  const accentB = positive ? "#22d3ee" : "#f97316";
  const path = buildSparkPath(fakeSparkFromPct(currentRow.pnl_pct || 0));

  return (
    <section className="hermes-trending" aria-label="Most trending agents">
      <header className="hermes-trending-head">
        <div>
          <h2 className="hermes-trending-title">Most Trending</h2>
          <p className="hermes-trending-lead">
            Top {rows.length} assets traded on Hermes · 7-day P&amp;L
          </p>
        </div>
      </header>

      <div className="hermes-trending-track">
        <button
          key={`trending-${fadeKey}-${currentRow.agent_id}`}
          type="button"
          className="hermes-trending-card hermes-trending-card--solo is-fade-in"
          style={{ "--card-grad": gradient }}
          onClick={() => onSelect?.(currentRow)}
          title={`${currentRow.symbol} · ${currentRow.name}`}
        >
          <span className="hermes-trending-card-tag">Trending</span>
          <header className="hermes-trending-card-head">
            <strong className="hermes-trending-card-symbol">{currentRow.symbol}</strong>
            <span className="hermes-trending-card-cat">
              {CATEGORY_LABEL[cat] || currentRow.category || "Asset"}
            </span>
          </header>
          <div className="hermes-trending-card-name">{currentRow.name || currentRow.symbol}</div>
          <div className="hermes-trending-card-stats">
            <strong className="mono" style={{ color: accent }}>
              {positive ? "+" : ""}
              {Number(currentRow.pnl_pct || 0).toFixed(2)}%
            </strong>
            <span className="text-3 fs-12">7d return</span>
            <svg className="hermes-trending-card-spark" viewBox="0 0 120 38" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <linearGradient id={`tg-${currentRow.agent_id}-${fadeKey}`} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={accent} />
                  <stop offset="100%" stopColor={accentB} />
                </linearGradient>
              </defs>
              <path d={path} fill="none" stroke={`url(#tg-${currentRow.agent_id}-${fadeKey})`} strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <footer className="hermes-trending-card-foot">
            <span className="text-3 fs-12">
              Win {Math.round(Number(currentRow.win_rate || 0))}% · {Number(currentRow.trade_count || 0)} trades
            </span>
            <span
              className="hermes-trending-card-cta"
              onClick={(e) => {
                e.stopPropagation();
                onAdd?.(currentRow);
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  onAdd?.(currentRow);
                }
              }}
            >
              + ADD
            </span>
          </footer>
        </button>
      </div>

      {rows.length > 1 ? (
        <div className="hermes-trending-dots" role="tablist" aria-label="Trending assets">
          {rows.map((row, i) => (
            <button
              key={row.agent_id}
              type="button"
              role="tab"
              aria-label={`Show ${row.symbol}`}
              aria-selected={i === activeIdx}
              className={`hermes-trending-dot${i === activeIdx ? " is-active" : ""}`}
              onClick={() => goTo(i)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
