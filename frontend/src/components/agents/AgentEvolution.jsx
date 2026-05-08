import { useEffect, useMemo, useState } from "react";

import {
  calculateXP,
  getLevel,
  getStoredEvolution,
  getUnlockedPersonalities,
  getUnlockedSkins,
  saveStoredEvolution,
} from "../../utils/agentXP";
import AgentAvatar from "./AgentAvatar";
import MemoryVault from "../MemoryVault";

const SKIN_META = {
  basic: { label: "Basic Core", style: "basic" },
  neon: { label: "Neon Robot", style: "neon" },
  meme_cat: { label: "Meme Cat", style: "meme_cat" },
  wolf: { label: "Wall Street Wolf", style: "wolf" },
  cosmic: { label: "Cosmic Agent", style: "cosmic" },
};

const PERSONALITY_META = {
  zen_monk: {
    label: "Zen DCA Monk",
    short: "🧘 Steady and patient",
    description: "Calm, patient, and low-risk focused with smooth position sizing.",
  },
  aggressive: {
    label: "Aggressive Meme Trader",
    short: "🚀 To the moon!",
    description: "High energy and momentum-chasing with fast execution.",
  },
  wall_street: {
    label: "Wall Street Pro",
    short: "📊 Analyzing market conditions",
    description: "Formal, data-driven style focused on structure and risk-adjusted return.",
  },
  degen: {
    label: "Degen Gambler",
    short: "💀 All in or nothing",
    description: "Chaotic, high-risk decision bias for maximum volatility.",
  },
};

export default function AgentEvolution({ agent, open, onClose, onChange }) {
  const xp = useMemo(() => calculateXP(agent || {}), [agent]);
  const levelMeta = useMemo(() => getLevel(xp), [xp]);
  const unlockedSkins = useMemo(() => getUnlockedSkins(levelMeta.level), [levelMeta.level]);
  const unlockedPersonalities = useMemo(() => getUnlockedPersonalities(levelMeta.level), [levelMeta.level]);
  const [skin, setSkin] = useState("basic");
  const [personality, setPersonality] = useState("zen_monk");

  useEffect(() => {
    if (!agent) return;
    const saved = getStoredEvolution(agent, levelMeta.level);
    const timer = window.setTimeout(() => {
      setSkin(unlockedSkins.includes(saved.skin) ? saved.skin : unlockedSkins[0]);
      setPersonality(unlockedPersonalities.includes(saved.personality) ? saved.personality : unlockedPersonalities[0]);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [agent, levelMeta.level, unlockedPersonalities, unlockedSkins]);

  if (!open || !agent) return null;

  const nextXP = levelMeta.next;
  const currentThreshold = levelMeta.level === 1 ? 0 : levelMeta.level === 2 ? 500 : levelMeta.level === 3 ? 2000 : levelMeta.level === 4 ? 5000 : 10000;
  const progressPct = nextXP ? Math.max(0, Math.min(100, ((xp - currentThreshold) / (nextXP - currentThreshold)) * 100)) : 100;
  const totalPnl = Number(agent.pnlUsd ?? agent.pnl ?? 0);
  const winStreak = Math.max(1, Math.round((Number(agent.winRate) || 50) / 11));
  const bestTrade = ((totalPnl / Math.max(1, Number(agent.trades) || 1)) * 2.2).toFixed(2);
  const ageDays = Math.max(1, Math.round((Number(agent.trades) || 0) * 1.8 + 4));
  const personalityMeta = PERSONALITY_META[personality] || PERSONALITY_META.zen_monk;

  const updateEvolution = (nextValue) => {
    const merged = { skin, personality, ...nextValue };
    saveStoredEvolution(agent, merged);
    setSkin(merged.skin);
    setPersonality(merged.personality);
    onChange?.(agent, merged);
  };

  return (
    <div className="agent-evo-overlay" onClick={onClose} role="presentation">
      <div className="agent-evo-modal glass" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="row between">
          <h3>Agent Evolution</h3>
          <button className="btn btn-ghost btn-sm" type="button" onClick={onClose}>Close</button>
        </div>

        <div className="agent-evo-head">
          <AgentAvatar name={agent.name} level={levelMeta.level} skin={skin} size="lg" />
          <div className="col gap-2">
            <strong style={{ fontSize: 18 }}>{agent.name}</strong>
            <span className="pill pill-violet">{`Lv.${levelMeta.level} ${levelMeta.title.toUpperCase()}`}</span>
            <span className="fs-12 text-2">{nextXP ? `${xp.toLocaleString()} / ${nextXP.toLocaleString()} XP to next level` : `${xp.toLocaleString()} XP (MAX)`}</span>
          </div>
        </div>

        <div className="progress agent-evo-progress">
          <div className="progress-fill agent-evo-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>

        <div className="agent-evo-section glass-2">
          <div className="fs-12 text-3">Current personality</div>
          <strong>{personalityMeta.label}</strong>
          <div className="fs-13">{personalityMeta.short}</div>
          <div className="fs-12 text-2">{personalityMeta.description}</div>
        </div>

        <div className="agent-evo-section glass-2">
          <div className="fs-12 text-3">Current skin</div>
          <strong>{SKIN_META[skin]?.label || "Basic Core"}</strong>
        </div>

        <div className="agent-evo-grid-title">Unlocked skins</div>
        <div className="agent-evo-skins-grid">
          {Object.entries(SKIN_META).map(([key, meta]) => {
            const unlocked = unlockedSkins.includes(key);
            return (
              <button
                key={key}
                type="button"
                className={`agent-evo-skin-card ${skin === key ? "active" : ""}`}
                onClick={() => unlocked && updateEvolution({ skin: key })}
                disabled={!unlocked}
              >
                <AgentAvatar name={agent.name} level={levelMeta.level} skin={unlocked ? key : "basic"} size="md" />
                <span>{meta.label}</span>
                {!unlocked ? <span className="agent-evo-locked">Locked</span> : null}
              </button>
            );
          })}
        </div>

        <div className="agent-evo-grid-title">Personality selector</div>
        <div className="agent-evo-personality-grid">
          {Object.entries(PERSONALITY_META).map(([key, meta]) => {
            const unlocked = unlockedPersonalities.includes(key);
            return (
              <button
                key={key}
                type="button"
                className={`agent-evo-personality ${personality === key ? "active" : ""}`}
                disabled={!unlocked}
                onClick={() => unlocked && updateEvolution({ personality: key })}
              >
                <div>{meta.label}</div>
                <small>{unlocked ? meta.short : "Locked"}</small>
              </button>
            );
          })}
        </div>

        <div className="agent-evo-grid-title">Stats</div>
        <div className="agent-evo-stats-grid">
          <div><span>Win streak</span><strong>{winStreak}</strong></div>
          <div><span>Best trade</span><strong>{bestTrade}</strong></div>
          <div><span>Total PnL</span><strong>{`${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}`}</strong></div>
          <div><span>Age</span><strong>{`${ageDays} days`}</strong></div>
        </div>

        <MemoryVault agentId={agent.id} />
      </div>
    </div>
  );
}
