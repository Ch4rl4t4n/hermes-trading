import { useCallback, useEffect, useMemo, useState } from "react";
import client from "../api/client";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "news", label: "News" },
  { id: "trend", label: "Trends" },
  { id: "summary", label: "Summaries" },
];

function formatAgo(value) {
  if (!value) return "n/a";
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return "n/a";
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

function sentimentClass(sentiment) {
  const key = String(sentiment || "neutral").toLowerCase();
  if (key === "positive") return "intel-dot-positive";
  if (key === "negative") return "intel-dot-negative";
  return "intel-dot-neutral";
}

function scorePct(score) {
  const value = Number(score || 0);
  const normalized = Math.max(-1, Math.min(1, value));
  return Math.round(((normalized + 1) / 2) * 100);
}

export default function IntelligenceFeed() {
  const [activeType, setActiveType] = useState("all");
  const [feed, setFeed] = useState([]);
  const [sentiment, setSentiment] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [feedRes, sentimentRes] = await Promise.all([
        client.get(`/api/intelligence/feed?limit=20&type=${encodeURIComponent(activeType)}`),
        client.get("/api/intelligence/sentiment"),
      ]);
      setFeed(Array.isArray(feedRes.data) ? feedRes.data : []);
      setSentiment(Array.isArray(sentimentRes.data) ? sentimentRes.data : []);
    } catch (err) {
      setError(err?.response?.data?.error || "Unable to load intelligence feed");
    } finally {
      setLoading(false);
    }
  }, [activeType]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchFeed().catch(() => {});
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchFeed]);

  useEffect(() => {
    const timer = setInterval(() => {
      fetchFeed().catch(() => {});
    }, 60000);
    return () => clearInterval(timer);
  }, [fetchFeed]);

  const sentimentChips = useMemo(() => sentiment.slice(0, 6), [sentiment]);

  return (
    <article className="glass intelligence-feed">
      <div className="row between" style={{ alignItems: "center" }}>
        <div className="section-title" style={{ margin: 0 }}>Market Intelligence</div>
        <button type="button" className="share-btn" onClick={() => fetchFeed().catch(() => {})}>🔄 refresh</button>
      </div>

      <div className="intel-sentiment-grid">
        {sentimentChips.map((item) => (
          <div key={item.symbol} className="intel-sentiment-chip">
            <div className="row between">
              <strong>{item.symbol}</strong>
              <span className={Number(item.avg_score || 0) >= 0 ? "intel-score-positive" : "intel-score-negative"}>
                {Number(item.avg_score || 0) >= 0 ? "+" : ""}{Number(item.avg_score || 0).toFixed(2)}
              </span>
            </div>
            <div className="intel-score-meter"><i style={{ width: `${scorePct(item.avg_score)}%` }} /></div>
          </div>
        ))}
      </div>

      <div className="row gap-2" style={{ flexWrap: "wrap" }}>
        {FILTERS.map((filter) => (
          <button
            key={filter.id}
            type="button"
            className={`pill ${activeType === filter.id ? "pill-violet" : "pill-gray"}`}
            onClick={() => setActiveType(filter.id)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {error ? <div className="text-3 fs-12" style={{ marginTop: 8 }}>{error}</div> : null}
      {loading ? <div className="text-3 fs-12" style={{ marginTop: 8 }}>Loading...</div> : null}

      <div className="intel-feed-list">
        {feed.map((item) => (
          <article key={item.id} className="intel-feed-row">
            <div className="row gap-2" style={{ alignItems: "center" }}>
              <span className={`intel-dot ${sentimentClass(item.sentiment)}`} />
              <strong>{item.title || "Untitled report"}</strong>
            </div>
            <div className="row between fs-12 text-3" style={{ marginTop: 4 }}>
              <span>{item.source || "Unknown source"} · {item.agent_id || "intel"}</span>
              <span>{item.symbol || "MARKET"} · {formatAgo(item.created_at)}</span>
            </div>
          </article>
        ))}
        {feed.length === 0 && !loading ? <div className="text-3 fs-12">No intelligence reports yet.</div> : null}
      </div>
    </article>
  );
}
