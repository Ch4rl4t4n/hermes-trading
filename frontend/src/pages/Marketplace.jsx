import { useCallback, useEffect, useMemo, useState } from "react";

import client from "../api/client";
import { getCommunityAgents, getMyCommunityAgents } from "../api/community";
import SubmitAgentModal from "../components/SubmitAgentModal";
import { useBreakpoint } from "../hooks/useBreakpoint";

const communityCategories = ["all", "crypto", "stocks", "commodities"];

export default function Marketplace({ agents = [], user, onToast }) {
  const { isMobile, isDesktop } = useBreakpoint();
  const [tab, setTab] = useState("system");
  const [systemAgents, setSystemAgents] = useState([]);
  const [subscribedIds, setSubscribedIds] = useState(new Set());
  const [communityAgents, setCommunityAgents] = useState([]);
  const [mySubmissions, setMySubmissions] = useState([]);
  const [communityCategory, setCommunityCategory] = useState("all");
  const [communitySort, setCommunitySort] = useState("newest");
  const [loadingSystem, setLoadingSystem] = useState(true);
  const [loadingCommunity, setLoadingCommunity] = useState(true);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [showMySubmissions, setShowMySubmissions] = useState(true);

  const tier = String(user?.tier || "basic").toLowerCase();
  const canSubmit = tier === "pro" || tier === "elite" || tier === "admin";

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
    const listResult = await getCommunityAgents({ category: communityCategory, sort: communitySort });
    const mineResult = await getMyCommunityAgents();
    setCommunityAgents(listResult.data || []);
    setMySubmissions(mineResult.data || []);
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
      onToast?.(`Subscribed to ${agent.name}`);
      await loadSystemAgents();
    } catch {
      onToast?.("Subscribe failed");
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

  const renderAgentCard = (agent, isCommunity = false) => (
    <article key={`${isCommunity ? "community" : "system"}-${agent.id}`} className="mp-card agent-card marketplace-card">
      <div className="mp-card-inner">
        <div className="agent-card-header">
          <span className="agent-name" style={{ fontSize: 14, fontWeight: 600 }}>{agent.name}</span>
        </div>
        <div className="mp-meta row gap-2" style={{ marginTop: 6 }}>
          <span className={`pill ${cardCategoryClass(agent.category)}`}>{agent.category || "Unknown"}</span>
          <span className="pill pill-gray">{agent.strategy || "strategy"}</span>
          {isCommunity ? <span className="pill pill-amber">COMMUNITY</span> : null}
        </div>
        {isCommunity ? (
          <div className="text-3 fs-12" style={{ marginTop: 8 }}>
            by @{agent.author_handle || "agent_author"}
          </div>
        ) : null}
        <div className="row gap-2 fs-12 text-2" style={{ marginTop: 8 }}>
          <span className="pill pill-gray">Win {Number(agent.win_rate ?? agent.winRate ?? 0).toFixed(2)}%</span>
          <span className="pill pill-green">
            {Number(agent.total_return ?? agent.pnlPct ?? 0) >= 0 ? "+" : ""}
            {Number(agent.total_return ?? agent.pnlPct ?? 0).toFixed(2)}%
          </span>
        </div>
        <div className="mp-meta" style={{ marginTop: 8 }}>
          👥 {Number(agent.subscribers || 0)} subscribers
        </div>
        {isCommunity ? (
          <div className="mp-meta" style={{ marginTop: 6, fontWeight: 600 }}>
            {Number(agent.price_monthly || 0) > 0 ? `$${Number(agent.price_monthly).toFixed(2)}/month` : "Free"}
          </div>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => subscribeSystemAgent(agent)}
        style={{
          border: "none",
          width: "100%",
          borderRadius: 8,
          padding: "10px 12px",
          background: "oklch(0.72 0.18 295)",
          color: "#fff",
          fontWeight: 600,
          marginTop: 10,
        }}
      >
        Subscribe
      </button>
    </article>
  );

  return (
    <section className="page-content marketplace-page">
      <div className="row gap-2" style={{ flexWrap: "wrap", marginBottom: 12 }}>
        <button type="button" className={`pill ${tab === "system" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setTab("system")}>
          System agents · {systemAgents.length || 50}
        </button>
        <button type="button" className={`pill ${tab === "community" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setTab("community")}>
          Community · {communityAgents.length}
        </button>
        <button type="button" className={`pill ${tab === "subscribed" ? "pill-violet" : "pill-gray"}`} style={{ border: "none" }} onClick={() => setTab("subscribed")}>
          Subscribed
        </button>
      </div>

      {tab === "community" ? (
        <article className="glass" style={{ padding: 12, marginBottom: 12 }}>
          <div className="row between" style={{ alignItems: "center", marginBottom: 12, gap: 10, flexWrap: "wrap" }}>
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              {communityCategories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  className={`pill ${communityCategory === cat ? "pill-violet" : "pill-gray"}`}
                  style={{ border: "none" }}
                  onClick={() => setCommunityCategory(cat)}
                >
                  {cat[0].toUpperCase() + cat.slice(1)}
                </button>
              ))}
            </div>
            <div className="row gap-2" style={{ alignItems: "center" }}>
              <select className="bt-field" value={communitySort} onChange={(event) => setCommunitySort(event.target.value)} style={{ marginBottom: 0 }}>
                <option value="newest">Newest</option>
                <option value="top">Top Win</option>
                <option value="popular">Popular</option>
              </select>
              <button
                type="button"
                className="pill pill-violet"
                style={{ border: "none" }}
                disabled={!canSubmit}
                title={!canSubmit ? "Pro or Elite required" : ""}
                onClick={() => setShowSubmitModal(true)}
              >
                Submit Agent
              </button>
            </div>
          </div>

          {mySubmissions.length > 0 ? (
            <details open={showMySubmissions} onToggle={(event) => setShowMySubmissions(event.currentTarget.open)}>
              <summary style={{ cursor: "pointer", marginBottom: 10, fontWeight: 600 }}>My Submissions</summary>
              <div className="community-submissions">
                {mySubmissions.map((submission) => (
                  <div key={submission.id} className="community-submission-item">
                    <div className="col">
                      <strong>{submission.name}</strong>
                      <span className="text-3 fs-12">{submission.symbol} · {submission.strategy}</span>
                    </div>
                    <div className="row gap-2" style={{ alignItems: "center", flexWrap: "wrap" }}>
                      <span className={statusBadge(submission.status)} title={submission.reject_reason || ""}>{String(submission.status || "pending").toUpperCase()}</span>
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
                          View in Marketplace
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

      <div className={`marketplace-grid ${isDesktop ? "desktop" : isMobile ? "mobile" : "tablet"}`}>
        {tab === "system" ? systemAgents.map((agent) => renderAgentCard(agent, false)) : null}
        {tab === "community" ? communityAgents.map((agent) => renderAgentCard(agent, true)) : null}
        {tab === "subscribed" ? subscribedAgents.map((agent) => renderAgentCard(agent, false)) : null}
        {(tab === "system" && loadingSystem) || (tab === "community" && loadingCommunity) ? (
          <div className="text-3">Loading...</div>
        ) : null}
      </div>

      <SubmitAgentModal
        open={showSubmitModal}
        onClose={() => setShowSubmitModal(false)}
        onToast={onToast}
        onSubmitted={loadCommunityAgents}
      />
    </section>
  );
}

