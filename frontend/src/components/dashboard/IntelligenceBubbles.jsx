import { useCallback, useEffect, useRef, useState } from "react";
import { listIntelligence } from "../../api/intelligence";

/**
 * Horizontal news ticker rendered below the Trending Banner.
 *
 * Each bubble represents a small piece of "agent intelligence" —
 * a news headline, AI-generated question, alert hint or insight pushed
 * by an agent (or admin) into `intelligence_news`. Clicking a bubble
 * opens its `url` (when present) in a new tab.
 *
 * Auto-refresh every 60s. Mouse wheel scrolls horizontally over the row.
 */

const REFRESH_MS = 60_000;

function PillIcon({ icon, accent, kind }) {
  // If author supplied an emoji/icon use it; otherwise render a coloured dot.
  if (icon && icon.length <= 4) {
    return <span className="hermes-news-pill-icon" aria-hidden="true">{icon}</span>;
  }
  return (
    <span
      className={`hermes-news-pill-dot is-${accent || "neutral"}`}
      data-kind={kind}
      aria-hidden="true"
    />
  );
}

export default function IntelligenceBubbles() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const railRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await listIntelligence({ limit: 12 });
      setItems(Array.isArray(data?.items) ? data.items : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  // Convert vertical wheel into horizontal scroll for natural trackpad/mouse UX.
  useEffect(() => {
    const el = railRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        el.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const handleClick = (item) => {
    if (!item?.url) return;
    try {
      window.open(item.url, "_blank", "noopener,noreferrer");
    } catch {
      /* ignore */
    }
  };

  if (!loading && !items.length) return null;

  return (
    <div className="hermes-news-rail" aria-label="Latest intelligence">
      <div className="hermes-news-rail-track" ref={railRef}>
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            className={`hermes-news-pill is-${it.accent || "neutral"}`}
            onClick={() => handleClick(it)}
            disabled={!it.url}
            title={it.source ? `${it.source}` : undefined}
          >
            <PillIcon icon={it.icon} accent={it.accent} kind={it.kind} />
            <span className="hermes-news-pill-text">{it.title}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
