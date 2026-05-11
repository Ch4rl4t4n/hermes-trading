import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createCommunityPost,
  deleteCommunityPost,
  getCommunitySentiment,
  listCommunityPosts,
  toggleCommunityLike,
} from "../../api/community";

/**
 * CoinMarketCap-style community feed for the dashboard side column.
 *
 * Sections (top → bottom):
 *   1. Sentiment bar (24h bullish vs bearish from POSTed sentiment)
 *   2. Tabs: Top / Latest
 *   3. Scrollable post list (avatar, name, time, content, like + reply + share)
 *   4. Composer with sentiment toggle (Bullish / Bearish) + Post button
 */

const TAB_LATEST = "latest";
const TAB_TOP = "top";

function timeAgo(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "";
  const diff = Math.max(0, Date.now() - t);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}

function initialFromName(name) {
  return (name || "A").toString().trim().charAt(0).toUpperCase() || "A";
}

function PostIcon({ name }) {
  // Inline SVGs keep the bundle small and the visual cohesive with the rest of the app.
  switch (name) {
    case "heart":
      return (
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M8 13.4S2.5 9.8 2.5 6.4a2.9 2.9 0 0 1 5.5-1.3 2.9 2.9 0 0 1 5.5 1.3c0 3.4-5.5 7-5.5 7Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "heart-filled":
      return (
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M8 13.4S2.5 9.8 2.5 6.4a2.9 2.9 0 0 1 5.5-1.3 2.9 2.9 0 0 1 5.5 1.3c0 3.4-5.5 7-5.5 7Z"
            fill="currentColor"
          />
        </svg>
      );
    case "comment":
      return (
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M3 4h10a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H7l-3 2.5V11H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "share":
      return (
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M11 5l-7 3 7 3M11 5v6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "trash":
      return (
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M3.5 5.5h9M6 3.5h4M5 5.5l.6 7a1 1 0 0 0 1 .9h2.8a1 1 0 0 0 1-.9l.6-7"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      );
    case "bull":
      return (
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
          <path
            d="M3 11l3.2-3.2L8.5 10l4.5-4.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M11 5.5h2v2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "bear":
      return (
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
          <path
            d="M3 5l3.2 3.2L8.5 6l4.5 4.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M11 10.5h2v-2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    default:
      return null;
  }
}

const MAX_LEN = 600;

export default function CommunityFeed({ user, onToast }) {
  const [tab, setTab] = useState(TAB_LATEST);
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sentiment, setSentiment] = useState({ bullish_pct: 50, bearish_pct: 50, total_votes: 0 });
  const [draft, setDraft] = useState("");
  const [draftSentiment, setDraftSentiment] = useState(null); // 'bullish' | 'bearish' | null
  const [submitting, setSubmitting] = useState(false);

  const loadingTabRef = useRef(tab);

  const loadPosts = useCallback(async (currentTab) => {
    loadingTabRef.current = currentTab;
    setLoading(true);
    try {
      const { data } = await listCommunityPosts({ tab: currentTab, limit: 30 });
      // Guard against late responses
      if (loadingTabRef.current !== currentTab) return;
      setPosts(Array.isArray(data?.posts) ? data.posts : []);
    } catch {
      if (loadingTabRef.current !== currentTab) return;
      setPosts([]);
    } finally {
      if (loadingTabRef.current === currentTab) setLoading(false);
    }
  }, []);

  const loadSentiment = useCallback(async () => {
    try {
      const { data } = await getCommunitySentiment();
      setSentiment(data || { bullish_pct: 50, bearish_pct: 50, total_votes: 0 });
    } catch {
      setSentiment({ bullish_pct: 50, bearish_pct: 50, total_votes: 0 });
    }
  }, []);

  useEffect(() => {
    loadPosts(tab);
  }, [tab, loadPosts]);

  useEffect(() => {
    loadSentiment();
    const id = window.setInterval(loadSentiment, 60_000);
    return () => window.clearInterval(id);
  }, [loadSentiment]);

  const handleSubmit = async (e) => {
    e?.preventDefault?.();
    const content = draft.trim();
    if (!content) return;
    if (!user) {
      onToast?.("Sign in to post.");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await createCommunityPost({
        content,
        sentiment: draftSentiment || undefined,
      });
      if (data?.post) {
        setPosts((prev) => [data.post, ...prev]);
      }
      setDraft("");
      setDraftSentiment(null);
      loadSentiment();
      onToast?.("Posted.");
    } catch (err) {
      const msg = err?.response?.data?.error || "Could not post — please try again.";
      onToast?.(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLike = async (post) => {
    if (!user) {
      onToast?.("Sign in to react.");
      return;
    }
    // optimistic
    setPosts((prev) =>
      prev.map((p) =>
        p.id === post.id
          ? { ...p, is_liked: !p.is_liked, likes_count: Math.max(0, p.likes_count + (p.is_liked ? -1 : 1)) }
          : p,
      ),
    );
    try {
      const { data } = await toggleCommunityLike(post.id);
      setPosts((prev) =>
        prev.map((p) =>
          p.id === post.id
            ? { ...p, is_liked: !!data?.is_liked, likes_count: Number(data?.likes_count ?? p.likes_count) }
            : p,
        ),
      );
    } catch {
      // revert
      setPosts((prev) =>
        prev.map((p) =>
          p.id === post.id
            ? { ...p, is_liked: post.is_liked, likes_count: post.likes_count }
            : p,
        ),
      );
    }
  };

  const handleDelete = async (post) => {
    if (!window.confirm("Delete this post?")) return;
    try {
      await deleteCommunityPost(post.id);
      setPosts((prev) => prev.filter((p) => p.id !== post.id));
    } catch {
      onToast?.("Could not delete post.");
    }
  };

  const handleShare = async (post) => {
    const url = `${window.location.origin}/?post=${post.id}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "Hermes community", text: post.content, url });
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(`${post.content}\n${url}`);
        onToast?.("Link copied.");
      }
    } catch {
      /* user cancelled / not supported */
    }
  };

  const sentimentBars = useMemo(() => {
    const bull = Math.max(0, Math.min(100, Number(sentiment?.bullish_pct ?? 50)));
    const bear = 100 - bull;
    return { bull, bear };
  }, [sentiment]);

  const charCount = draft.length;
  const overLimit = charCount > MAX_LEN;
  const canSubmit = !!user && draft.trim().length >= 2 && !overLimit && !submitting;

  return (
    <aside className="hermes-side-panel hermes-feed">
      {/* Sentiment header */}
      <div className="hermes-feed-sentiment">
        <div className="hermes-feed-sentiment-head">
          <span className="hermes-feed-sentiment-title">Community sentiment</span>
          <span className="hermes-feed-sentiment-votes">
            {sentiment.total_votes
              ? `${sentiment.total_votes.toLocaleString()} votes · 24h`
              : "Be the first to vote · 24h"}
          </span>
        </div>
        <div className="hermes-feed-sentiment-bar" role="img" aria-label="bullish vs bearish">
          <div className="hermes-feed-sentiment-bull" style={{ width: `${sentimentBars.bull}%` }} />
          <div className="hermes-feed-sentiment-bear" style={{ width: `${sentimentBars.bear}%` }} />
        </div>
        <div className="hermes-feed-sentiment-legend">
          <span className="is-bull">
            <PostIcon name="bull" /> {sentimentBars.bull}%
          </span>
          <span className="is-bear">
            <PostIcon name="bear" /> {sentimentBars.bear}%
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div className="hermes-feed-tabs" role="tablist" aria-label="Feed sort">
        <button
          type="button"
          role="tab"
          aria-selected={tab === TAB_TOP}
          className={`hermes-feed-tab ${tab === TAB_TOP ? "is-active" : ""}`}
          onClick={() => setTab(TAB_TOP)}
        >
          Top
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === TAB_LATEST}
          className={`hermes-feed-tab ${tab === TAB_LATEST ? "is-active" : ""}`}
          onClick={() => setTab(TAB_LATEST)}
        >
          Latest
        </button>
      </div>

      {/* Scrollable list */}
      <div className="hermes-feed-list" role="feed" aria-busy={loading}>
        {loading ? (
          <div className="hermes-feed-empty">Loading feed…</div>
        ) : posts.length === 0 ? (
          <div className="hermes-feed-empty">
            <strong>No posts yet</strong>
            <span>Be the first to share what you think about today’s market.</span>
          </div>
        ) : (
          posts.map((p) => (
            <article key={p.id} className="hermes-feed-post">
              <header className="hermes-feed-post-head">
                <div
                  className="hermes-feed-post-avatar"
                  aria-hidden="true"
                  data-sentiment={p.sentiment || "neutral"}
                >
                  {initialFromName(p.username)}
                </div>
                <div className="hermes-feed-post-meta">
                  <span className="hermes-feed-post-name">@{p.username}</span>
                  <span className="hermes-feed-post-sub">
                    {p.symbol ? <span className="hermes-feed-post-symbol">${p.symbol}</span> : null}
                    {p.sentiment ? (
                      <span
                        className={`hermes-feed-post-sentiment is-${p.sentiment}`}
                        title={p.sentiment}
                      >
                        <PostIcon name={p.sentiment === "bullish" ? "bull" : "bear"} />
                        {p.sentiment}
                      </span>
                    ) : null}
                    <span className="hermes-feed-post-time">{timeAgo(p.created_at)}</span>
                  </span>
                </div>
                {p.is_own ? (
                  <button
                    type="button"
                    className="hermes-feed-post-del"
                    aria-label="Delete post"
                    onClick={() => handleDelete(p)}
                  >
                    <PostIcon name="trash" />
                  </button>
                ) : null}
              </header>
              <p className="hermes-feed-post-body">{p.content}</p>
              <footer className="hermes-feed-post-actions">
                <button
                  type="button"
                  className={`hermes-feed-post-action ${p.is_liked ? "is-active" : ""}`}
                  onClick={() => handleLike(p)}
                  aria-label={p.is_liked ? "Unlike" : "Like"}
                >
                  <PostIcon name={p.is_liked ? "heart-filled" : "heart"} />
                  <span>{p.likes_count}</span>
                </button>
                <button
                  type="button"
                  className="hermes-feed-post-action"
                  onClick={() => onToast?.("Replies coming soon.")}
                  aria-label="Reply"
                >
                  <PostIcon name="comment" />
                  <span>{p.comments_count || 0}</span>
                </button>
                <button
                  type="button"
                  className="hermes-feed-post-action"
                  onClick={() => handleShare(p)}
                  aria-label="Share"
                >
                  <PostIcon name="share" />
                </button>
              </footer>
            </article>
          ))
        )}
      </div>

      {/* Composer */}
      <form className="hermes-feed-composer" onSubmit={handleSubmit}>
        {!user ? (
          <div className="hermes-feed-composer-locked">Sign in to share your trading thoughts.</div>
        ) : (
          <>
            <textarea
              className="hermes-feed-composer-input"
              placeholder="$BTC How do you feel today?"
              maxLength={MAX_LEN + 50}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              aria-label="Write a post"
            />
            <div className="hermes-feed-composer-row">
              <div className="hermes-feed-sent-toggle" role="group" aria-label="Sentiment">
                <button
                  type="button"
                  className={`hermes-feed-sent-btn is-bull ${draftSentiment === "bullish" ? "is-on" : ""}`}
                  onClick={() => setDraftSentiment(draftSentiment === "bullish" ? null : "bullish")}
                >
                  <PostIcon name="bull" /> Bullish
                </button>
                <button
                  type="button"
                  className={`hermes-feed-sent-btn is-bear ${draftSentiment === "bearish" ? "is-on" : ""}`}
                  onClick={() => setDraftSentiment(draftSentiment === "bearish" ? null : "bearish")}
                >
                  <PostIcon name="bear" /> Bearish
                </button>
              </div>
              <div className="hermes-feed-composer-actions">
                <span
                  className={`hermes-feed-composer-counter ${overLimit ? "is-over" : ""}`}
                  aria-live="polite"
                >
                  {charCount}/{MAX_LEN}
                </span>
                <button
                  type="submit"
                  className="hermes-feed-post-btn"
                  disabled={!canSubmit}
                >
                  {submitting ? "Posting…" : "Post"}
                </button>
              </div>
            </div>
          </>
        )}
      </form>
    </aside>
  );
}
