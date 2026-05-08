import { memo } from "react";

import SparkLine from "../ui/SparkLine";
import PerformanceBadge from "../ui/PerformanceBadge";
import AgentAvatar from "./AgentAvatar";
import { calculateXP, getLevel } from "../../utils/agentXP";

function AgentCard({
  agent,
  onToggle,
  onDetails,
  onOpenEvolution,
  onShare,
  personalityTag,
  evolutionSkin = "basic",
}) {
  const positive = agent.pnlUsd >= 0;
  const statusClass = agent.status === "live" ? "dot-live" : "dot-paused";
  const xp = calculateXP(agent);
  const levelInfo = getLevel(xp);
  const floor = levelInfo.level === 1 ? 0 : levelInfo.level === 2 ? 500 : levelInfo.level === 3 ? 2000 : levelInfo.level === 4 ? 5000 : 10000;
  const xpProgress = levelInfo.next ? Math.max(0, Math.min(100, ((xp - floor) / (levelInfo.next - floor)) * 100)) : 100;
  const handleToggle = () => onToggle?.();
  const handleDetails = () => onDetails?.();
  const handleOpenEvolution = () => onOpenEvolution?.(agent);
  const handleShare = () => onShare?.(agent);

  return (
    <div className="glass" style={{ padding: "16px", marginBottom: "12px" }}>
      <article className="agent-card" onClick={handleOpenEvolution} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && handleOpenEvolution()}>
        <div className="agent-card-header">
          <div className="row gap-2">
            <AgentAvatar name={agent.name} level={levelInfo.level} skin={evolutionSkin} size="sm" />
            <span className="agent-name">{agent.name}</span>
          </div>
          <div className="row gap-2">
            <span className={`pill pill-violet`} style={{ padding: "2px 8px", fontSize: 10 }}>{`Lv.${levelInfo.level}`}</span>
            <button
              type="button"
              className="agent-share-btn"
              aria-label="share"
              onClick={(e) => { e.stopPropagation(); handleShare(); }}
              title="Share performance"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7" />
                <path d="M12 3v12" />
                <path d="m7 8 5-5 5 5" />
              </svg>
            </button>
            <span className={`dot ${statusClass}`} />
          </div>
        </div>
        <div className="mp-meta">
          <span className="pill pill-gray">{agent.symbol}</span> ·{" "}
          <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".06em" }}>{agent.category}</span>
        </div>

        <div className="row between" style={{ marginTop: 8, alignItems: "center" }}>
          <div className="mono pnl-number" style={{ fontSize: 20, color: positive ? "oklch(0.72 0.18 155)" : "oklch(0.65 0.2 25)" }}>
            {positive ? "+" : ""}
            {agent.pnlUsd.toFixed(2)}
          </div>
          <SparkLine points={agent.spark} color={positive ? "oklch(0.72 0.18 155)" : "oklch(0.65 0.2 25)"} />
        </div>

        <div className="mp-meta" style={{ marginTop: 8 }}>
          Win rate {agent.winRate}%
          <div className="progress" style={{ marginTop: 6 }}>
            <div className="progress-fill" style={{ width: `${agent.winRate}%` }} />
          </div>
          <div className="progress" style={{ marginTop: 6, height: 4 }}>
            <div className="progress-fill" style={{ width: `${xpProgress}%`, background: "oklch(0.82 0.14 75)" }} />
          </div>
          <div className="fs-12 text-3" style={{ marginTop: 4 }}>{`${xp.toLocaleString()} XP`}</div>
          {personalityTag ? (
            <div className="pill pill-gray" style={{ marginTop: 6, width: "fit-content", fontSize: 10 }}>
              {personalityTag}
            </div>
          ) : null}
        </div>

        {agent.badges?.length ? (
          <div className="agent-badges" style={{ marginTop: 8 }}>
            {agent.badges.map((badge) => (
              <PerformanceBadge key={badge.label} label={badge.label} icon={badge.icon} />
            ))}
          </div>
        ) : null}

        <div className="mp-actions" style={{ marginTop: 10 }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); handleToggle(); }} aria-label="toggle">
            {agent.status === "live" ? (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <rect x="6" y="4" width="4" height="16" />
                <rect x="14" y="4" width="4" height="16" />
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <polygon points="5,3 19,12 5,21" />
              </svg>
            )}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); handleDetails(); }} aria-label="details">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </article>
    </div>
  );
}

export default memo(AgentCard);

