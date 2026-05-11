import { useCallback, useEffect, useMemo, useState } from "react";

import client from "../api/client";
import { getCommunityAgents, getMyCommunityAgents } from "../api/community";
import { cloneMarketplaceListing, getMarketplaceUserAgentListings } from "../api/marketplaceListings";
import { listBuilderAgents } from "../api/watcherSettings";
import { unpublishUserAgent } from "../api/userAgentMarketplace";
import MarketplaceCard from "../components/marketplace/MarketplaceCard";
import PublishBuilderAgentModal from "../components/PublishBuilderAgentModal";
import SubmitAgentModal from "../components/SubmitAgentModal";
import { useBreakpoint } from "../hooks/useBreakpoint";

const communityCategories = ["all", "crypto", "stocks", "commodities"];

function inferListingCategory(symbol) {
  const raw = String(symbol || "").toUpperCase().trim();
  const base = raw.split(/[/\-]/)[0] || raw;
  const crypto = new Set(["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE", "LINK", "AVAX", "MATIC", "DOT"]);
  if (crypto.has(base)) return "crypto";
  if (["GLD", "USO", "XAU", "UNG", "SLV", "DBC"].includes(base)) return "commodities";
  return "stocks";
}

function normalizeBuilderListing(l) {
  return {
    kind: "builder_listing",
    cardKey: `bl-${l.public_id}`,
    public_id: l.public_id,
    name: l.name,
    symbol: l.symbol,
    category: inferListingCategory(l.symbol),
    strategy: l.strategy_type,
    author_handle: l.author_handle || "author",
    win_rate: Number(l.win_rate ?? 0),
    total_return: Number(l.pnl_pct_week ?? 0),
    subscribers: Number(l.clone_count ?? 0),
    price_monthly: 0,
    user_has_clone: Boolean(l.user_has_clone),
    sortCreatedAt: l.published_at ? Date.parse(l.published_at) || 0 : 0,
  };
}

function normalizeLegacyCommunity(a) {
  return {
    kind: "legacy_community",
    cardKey: `lc-${a.id}`,
    id: a.id,
    name: a.name,
    symbol: a.symbol,
    category: String(a.category || "crypto").toLowerCase(),
    strategy: a.strategy,
    author_handle: a.author_handle,
    win_rate: Number(a.win_rate ?? 0),
    total_return: Number(a.total_return ?? 0),
    subscribers: Number(a.subscribers ?? 0),
    price_monthly: Number(a.price_monthly ?? 0),
    sortCreatedAt: a.created_at ? Date.parse(a.created_at) || 0 : 0,
  };
}

function mergeAndSortCommunityRows(builderRows, legacyRows, category, sort) {
  let rows = [...builderRows, ...legacyRows];
  if (category !== "all") {
    rows = rows.filter((r) => String(r.category || "").toLowerCase() === category);
  }
  if (sort === "top") {
    rows.sort((a, b) => b.win_rate - a.win_rate);
  } else if (sort === "popular") {
    rows.sort((a, b) => b.subscribers - a.subscribers);
  } else {
    rows.sort((a, b) => b.sortCreatedAt - a.sortCreatedAt);
  }
  return rows;
}

function marketplaceStatusLabel(ms) {
  const m = String(ms || "").toLowerCase();
  if (m === "pending") return "Pending review";
  if (m === "approved") return "Approved in marketplace";
  if (m === "rejected") return "Rejected";
  return "Not published";
}

export default function Marketplace({ agents = [], user, onToast, onNav }) {
  const { isMobile, isDesktop } = useBreakpoint();
  const [tab, setTab] = useState("system");
  const [searchTerm, setSearchTerm] = useState("");
  const [systemAgents, setSystemAgents] = useState([]);
  const [subscribedIds, setSubscribedIds] = useState(new Set());
  const [legacyCommunityAgents, setLegacyCommunityAgents] = useState([]);
  const [builderListingRaw, setBuilderListingRaw] = useState([]);
  const [myBuilderAgents, setMyBuilderAgents] = useState([]);
  const [mySubmissions, setMySubmissions] = useState([]);
  const [communityCategory, setCommunityCategory] = useState("all");
  const [communitySort, setCommunitySort] = useState("newest");
  const [loadingSystem, setLoadingSystem] = useState(true);
  const [loadingCommunity, setLoadingCommunity] = useState(true);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [showMySubmissions, setShowMySubmissions] = useState(true);
  const [publishModalAgent, setPublishModalAgent] = useState(null);
  const [unpublishingId, setUnpublishingId] = useState(null);

  const tier = String(user?.tier || "basic").toLowerCase();
  const canSubmit = tier === "pro" || tier === "elite" || tier === "admin";

  const mergedCommunityRows = useMemo(() => {
    const b = builderListingRaw.map(normalizeBuilderListing);
    const l = legacyCommunityAgents.map(normalizeLegacyCommunity);
    return mergeAndSortCommunityRows(b, l, communityCategory, communitySort);
  }, [builderListingRaw, legacyCommunityAgents, communityCategory, communitySort]);

  const loadSystemAgents = useCallback(async () => {
    setLoadingSystem(true);
    try {
      const { data } = await client.get("/api/marketplace/agents", { params: { category: "all" } });
      const rows = Array.isArray(data?.agents) ? data.agents : [];
      setSystemAgents(rows);
      setSubscribedIds(new Set(rows.filter((row) => row.subscribed).map((row) => row.id)));
    } catch {
      setSystemAgents(Array.isArray(agents) ? agents : []);
      setSubscribedIds(new Set());
    } finally {
      setLoadingSystem(false);
    }
  }, [agents]);

  const loadCommunityAgents = useCallback(async () => {
    setLoadingCommunity(true);
    const [listResult, mineResult, listingsResult, mineAgentsResult] = await Promise.all([
      getCommunityAgents({ category: communityCategory, sort: communitySort }),
      getMyCommunityAgents(),
      getMarketplaceUserAgentListings({ sort: communitySort, limit: 80 }),
      listBuilderAgents(),
    ]);
    setLegacyCommunityAgents(listResult.data || []);
    setMySubmissions(mineResult.data || []);
    setBuilderListingRaw(listingsResult.listings || []);
    setMyBuilderAgents(mineAgentsResult.agents || []);
    setLoadingCommunity(false);
  }, [communityCategory, communitySort]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadSystemAgents();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadSystemAgents]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadCommunityAgents();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadCommunityAgents]);

  const subscribedAgents = useMemo(
    () => systemAgents.filter((agent) => subscribedIds.has(agent.id)),
    [systemAgents, subscribedIds],
  );

  const subscribeSystemAgent = async (agent) => {
    try {
      const { data } = await client.post("/api/marketplace/subscribe", { agent_id: agent.id, mode: "paper" });
      if (!data?.success) throw new Error(data?.message || "subscribe failed");
      onToast?.(`Subscribed: ${agent.name}`);
      await loadSystemAgents();
    } catch {
      onToast?.("System agent subscription failed.");
    }
  };

  const onSubscribeCommunityCard = async (agent) => {
    if (agent.kind === "builder_listing") {
      if (agent.user_has_clone) {
        onToast?.("You already cloned this agent.");
        return;
      }
      try {
        const { data, error } = await cloneMarketplaceListing(agent.public_id);
        if (error || data?.success === false) {
          const msg = data?.message || error?.response?.data?.message || error?.response?.data?.error || "";
          throw new Error(msg || "clone failed");
        }
        onToast?.("Agent cloned to your account.");
        await loadCommunityAgents();
      } catch {
        onToast?.("Clone failed — plan limits or you already own a copy.");
      }
      return;
    }
    onToast?.("Legacy community form listings can’t be added directly — use an approved Agent Builder listing.");
  };

  const onUnpublishBuilder = async (agentId) => {
    if (!window.confirm("Unpublish this agent from the public marketplace?")) return;
    setUnpublishingId(agentId);
    try {
      const { data, error } = await unpublishUserAgent(agentId);
      if (error || data?.success === false) {
        const msg = data?.message || error?.response?.data?.message || error?.response?.data?.error || "";
        onToast?.(msg || "Operation failed.");
      } else {
        onToast?.("Agent unpublished from marketplace.");
        await loadCommunityAgents();
      }
    } finally {
      setUnpublishingId(null);
    }
  };

  const statusBadge = (status) => {
    const normalized = String(status || "pending").toUpperCase();
    if (normalized === "APPROVED") return "pill pill-green";
    if (normalized === "REJECTED") return "pill pill-red";
    return "pill pill-amber";
  };

  const cardCategoryClass = (category) => {
    const lower = String(category || "").toLowerCase();
    if (lower === "crypto") return "pill-violet";
    if (lower === "stocks") return "pill-green";
    if (lower === "commodities") return "pill-amber";
    return "pill-gray";
  };

  const filterBySearch = (rows) => {
    const t = String(searchTerm || "").trim().toLowerCase();
    if (!t) return rows;
    return rows.filter((row) => {
      const hay = [row.name, row.symbol, row.strategy, row.author_handle, row.category]
        .map((v) => String(v || "").toLowerCase())
        .join(" ");
      return hay.includes(t);
    });
  };

  const renderAgentCard = (agent, isCommunity = false) => (
    <MarketplaceCard
      key={isCommunity ? agent.cardKey : `system-${agent.id}`}
      agent={agent}
      isCommunity={isCommunity}
      onSubscribe={() => (isCommunity ? onSubscribeCommunityCard(agent) : subscribeSystemAgent(agent))}
      onPause={() => onToast?.(`${agent.name || agent.symbol}: already cloned or subscribed.`)}
    />
  );

  const _legacyCategoryClass = cardCategoryClass; // keep referenced for future use
  void _legacyCategoryClass;

  return (
    <section className="page-content hermes-marketplace">
      <header className="hermes-marketplace-head">
        <div>
          <h1 className="hermes-page-title">Marketplace</h1>
          <p className="hermes-page-lead">Subscribe to vetted AI agents or discover strategies from the community</p>
        </div>
        <button type="button" className="hermes-cta-pill" onClick={() => onNav?.("builder")}>
          + Create your own
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7M9 7h8v8" /></svg>
        </button>
      </header>

      <nav className="hermes-tabs" role="tablist" aria-label="Marketplace tabs">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "system"}
          className={`hermes-tab${tab === "system" ? " is-active" : ""}`}
          onClick={() => setTab("system")}
        >
          System agents · {systemAgents.length || 50}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "community"}
          className={`hermes-tab${tab === "community" ? " is-active" : ""}`}
          onClick={() => setTab("community")}
        >
          Community · {mergedCommunityRows.length}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "subscribed"}
          className={`hermes-tab${tab === "subscribed" ? " is-active" : ""}`}
          onClick={() => setTab("subscribed")}
        >
          My subscriptions · {subscribedAgents.length}
        </button>
      </nav>

      <div className="hermes-marketplace-toolbar">
        <div className="hermes-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="search"
            placeholder="Search agents, symbols, authors…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="Search marketplace"
          />
        </div>
        <div className="hermes-filter-pills" role="tablist" aria-label="Categories">
          {communityCategories.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`hermes-filter-pill${communityCategory === cat ? " is-active" : ""}`}
              onClick={() => setCommunityCategory(cat)}
            >
              {cat === "all" ? "ALL" : cat.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {tab === "community" ? (
        <article className="glass hermes-community-tools" style={{ padding: 14, marginBottom: 16 }}>
          <div className="row between" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div className="row gap-2" style={{ alignItems: "center" }}>
              <span className="text-3 fs-12">Sort by:</span>
              <select className="bt-field" value={communitySort} onChange={(event) => setCommunitySort(event.target.value)} style={{ marginBottom: 0 }}>
                <option value="newest">Newest</option>
                <option value="top">Top win rate</option>
                <option value="popular">Popularity</option>
              </select>
            </div>
            <button
              type="button"
              className="hermes-cta-pill is-secondary"
              disabled={!canSubmit}
              title={!canSubmit ? "Requires Pro or Elite" : ""}
              onClick={() => setShowSubmitModal(true)}
            >
              Submit agent (form)
            </button>
          </div>

          {myBuilderAgents.length > 0 ? (
            <details style={{ marginBottom: 14 }}>
              <summary style={{ cursor: "pointer", marginBottom: 10, fontWeight: 600 }}>Publish from Agent Builder</summary>
              <p className="text-3 fs-12" style={{ marginTop: 0 }}>
                From Pro tier you can submit your own active agent for review — once approved it appears in the BUILDER list and others can clone it.
              </p>
              <div className="community-submissions">
                {myBuilderAgents.map((a) => {
                  const ms = String(a.marketplace_status || "").toLowerCase();
                  const active = String(a.status || "").toLowerCase() === "active";
                  const showPublish =
                    canSubmit &&
                    active &&
                    ms !== "pending" &&
                    ms !== "approved";
                  return (
                    <div key={a.id} className="community-submission-item">
                      <div className="col">
                        <strong>{a.name}</strong>
                        <span className="text-3 fs-12">
                          {a.symbol} · {a.strategy_type || "—"} · {marketplaceStatusLabel(a.marketplace_status)}
                        </span>
                        {a.marketplace_reject_reason ? (
                          <span className="publish-req-bad fs-12">{String(a.marketplace_reject_reason)}</span>
                        ) : null}
                      </div>
                      <div className="row gap-2" style={{ alignItems: "center", flexWrap: "wrap" }}>
                        {ms === "approved" ? (
                          <>
                            <span className="pill pill-green">Approved</span>
                            <button
                              type="button"
                              className="pill pill-gray"
                              style={{ border: "none" }}
                              disabled={unpublishingId === a.id}
                              onClick={() => onUnpublishBuilder(a.id)}
                            >
                              {unpublishingId === a.id ? "…" : "Unpublish"}
                            </button>
                          </>
                        ) : null}
                        {showPublish ? (
                          <button type="button" className="pill pill-violet" style={{ border: "none" }} onClick={() => setPublishModalAgent(a)}>
                            Publish
                          </button>
                        ) : null}
                        {!canSubmit ? <span className="text-3 fs-12">Pro+ required to publish</span> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </details>
          ) : null}

          {mySubmissions.length > 0 ? (
            <details open={showMySubmissions} onToggle={(event) => setShowMySubmissions(event.currentTarget.open)}>
              <summary style={{ cursor: "pointer", marginBottom: 10, fontWeight: 600 }}>My requests (legacy form)</summary>
              <div className="community-submissions">
                {mySubmissions.map((submission) => (
                  <div key={submission.id} className="community-submission-item">
                    <div className="col">
                      <strong>{submission.name}</strong>
                      <span className="text-3 fs-12">
                        {submission.symbol} · {submission.strategy}
                      </span>
                    </div>
                    <div className="row gap-2" style={{ alignItems: "center", flexWrap: "wrap" }}>
                      <span className={statusBadge(submission.status)} title={submission.reject_reason || ""}>
                        {String(submission.status || "pending").toUpperCase()}
                      </span>
                      {String(submission.status || "").toLowerCase() === "approved" ? (
                        <button
                          type="button"
                          className="pill pill-gray"
                          style={{ border: "none" }}
                          onClick={() => {
                            setCommunityCategory("all");
                            setCommunitySort("newest");
                          }}
                        >
                          View in marketplace
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </article>
      ) : null}

      <div className={`hermes-marketplace-grid ${isDesktop ? "is-desktop" : isMobile ? "is-mobile" : "is-tablet"}`}>
        {tab === "system" ? filterBySearch(systemAgents).map((agent) => renderAgentCard(agent, false)) : null}
        {tab === "community" ? filterBySearch(mergedCommunityRows).map((agent) => renderAgentCard(agent, true)) : null}
        {tab === "subscribed" ? filterBySearch(subscribedAgents).map((agent) => renderAgentCard(agent, false)) : null}
        {(tab === "system" && loadingSystem) || (tab === "community" && loadingCommunity) ? (
          <div className="text-3" style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40 }}>Loading…</div>
        ) : null}
        {tab === "subscribed" && !loadingSystem && subscribedAgents.length === 0 ? (
          <div className="text-3" style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40 }}>
            No subscriptions yet. Open the <strong>System agents</strong> or <strong>Community</strong> tab and add your first one.
          </div>
        ) : null}
      </div>

      <SubmitAgentModal
        open={showSubmitModal}
        onClose={() => setShowSubmitModal(false)}
        onToast={onToast}
        onSubmitted={loadCommunityAgents}
      />

      <PublishBuilderAgentModal
        agent={publishModalAgent}
        open={Boolean(publishModalAgent)}
        onClose={() => setPublishModalAgent(null)}
        onToast={onToast}
        onPublished={loadCommunityAgents}
      />
    </section>
  );
}
