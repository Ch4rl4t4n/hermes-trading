import { useEffect, useMemo, useState } from "react";
import client from "../api/client";

/**
 * Rewards hub — gamification & loyalty page.
 *
 * Sections:
 *  1. Header summary card (current tier perks, referral bonus active, total points)
 *  2. Active rewards strip — pillstack of unlocked perks
 *  3. Achievements grid — earned vs locked badges (data: /api/agents/badges + BADGE_DEFINITIONS)
 *  4. Referral status — count, progress to next milestone, link to Invite page
 *  5. Quests / How to earn more — 4 actionable cards
 *
 * No new backend endpoint required: this page composes data already exposed by
 * /api/sharing/referral-info and /api/agents/badges. Future backend endpoint
 * /api/rewards/summary can replace these calls without UI changes.
 */

const ALL_BADGES = [
  { id: "top_gainer_24h", label: "Top Gainer", icon: "🔥", color: "#f97316", desc: "Top P&L gain in the last 24 hours" },
  { id: "hot_streak_3d", label: "Hot Streak", icon: "⚡", color: "#8b5cf6", desc: "3 consecutive days in the green" },
  { id: "steady_7d", label: "Steady", icon: "🛡", color: "#10b981", desc: "7 days without a losing day" },
  { id: "reliable", label: "Reliable", icon: "✓", color: "#6366f1", desc: "High uptime — agent rarely paused" },
];

const TIER_PERKS = {
  basic: [
    "3 marketplace agents",
    "30-day trade history",
    "Browser notifications",
  ],
  pro: [
    "10 marketplace agents",
    "365-day trade history",
    "Telegram & email alerts",
    "Weekly performance report",
  ],
  elite: [
    "Unlimited agents",
    "Full developer API access",
    "Priority Stripe support",
    "Live trading enabled",
    "Backtest export (PDF/CSV)",
  ],
  admin: ["All limits removed"],
};

const QUESTS = [
  {
    id: "first_clone",
    icon: "🚀",
    title: "Subscribe to your first agent",
    desc: "Pick any pro or community agent from the marketplace.",
    points: 50,
    cta: "Open marketplace",
    target: "marketplace",
  },
  {
    id: "first_invite",
    icon: "✉️",
    title: "Send your first invite",
    desc: "Share your referral link — earn +3 agent slots when a friend joins.",
    points: 100,
    cta: "Open invite page",
    target: "invite",
  },
  {
    id: "build_agent",
    icon: "🛠",
    title: "Build a custom agent",
    desc: "Use the no-code builder to ship your own strategy.",
    points: 150,
    cta: "Open builder",
    target: "builder",
  },
  {
    id: "go_pro",
    icon: "✨",
    title: "Upgrade to PRO",
    desc: "Unlock 10 agents, 365-day history and Telegram alerts.",
    points: 500,
    cta: "Compare plans",
    target: "pricing",
  },
];

function tierLabel(tier) {
  const t = String(tier || "basic").toLowerCase();
  if (t === "elite") return "ELITE";
  if (t === "pro") return "PRO";
  if (t === "admin") return "ADMIN";
  return "BASIC";
}

function loyaltyPoints({ referralCount = 0, earnedBadges = [], tier = "basic" }) {
  // Light gamification model — purely client-side until backend ships /api/rewards/summary.
  const tierPts = tier === "elite" ? 500 : tier === "pro" ? 200 : 0;
  return referralCount * 100 + earnedBadges.length * 50 + tierPts;
}

export default function Rewards({
  user,
  onNav,
  onToast,
  onboardingSteps = [],
  onOpenOnboarding,
}) {
  const [referralInfo, setReferralInfo] = useState(null);
  const [badgesByAgent, setBadgesByAgent] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [refRes, badgesRes] = await Promise.all([
          client.get("/api/sharing/referral-info").catch(() => null),
          client.get("/api/agents/badges").catch(() => null),
        ]);
        if (cancelled) return;
        if (refRes?.data && !refRes.data.error) setReferralInfo(refRes.data);
        if (badgesRes?.data) setBadgesByAgent(badgesRes.data || {});
      } catch (err) {
        onToast?.(err?.response?.data?.error || "Could not load rewards.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onToast]);

  const tierKey = String(user?.tier || "basic").toLowerCase();
  const perks = TIER_PERKS[tierKey] || TIER_PERKS.basic;

  const earnedBadgeIds = useMemo(() => {
    const set = new Set();
    Object.values(badgesByAgent || {}).forEach((arr) => {
      if (Array.isArray(arr)) arr.forEach((b) => set.add(b));
    });
    return Array.from(set);
  }, [badgesByAgent]);

  const referralCount = Number(referralInfo?.referral_count || 0);
  const bonusActive = Boolean(referralInfo?.bonus_active);
  const points = loyaltyPoints({ referralCount, earnedBadges: earnedBadgeIds, tier: tierKey });

  // Next referral milestone (every 3rd invite stacks a fresh +3-slot / 30-day window)
  const nextMilestone = Math.ceil((referralCount + 1) / 3) * 3;
  const milestoneProgress = Math.min(100, ((referralCount % 3) / 3) * 100 || (referralCount > 0 ? 0 : 0));

  return (
    <section className="page-content hermes-rewards col" style={{ gap: 22, maxWidth: 1080, margin: "0 auto" }}>
      <header className="hermes-page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="hermes-page-title">Rewards</h1>
          <p className="hermes-page-lead">Loyalty perks, achievements and referral bonuses — earned by using Hermes.</p>
        </div>
      </header>

      <article className="hermes-rewards-summary">
        <div className="hermes-rewards-summary-main">
          <span className="hermes-rewards-tier-pill">{tierLabel(user?.tier)} TIER</span>
          <strong className="hermes-rewards-points mono">
            {loading ? "—" : points.toLocaleString("en-US")}
            <span className="hermes-rewards-points-unit">pts</span>
          </strong>
          <p className="hermes-rewards-points-lead">
            Loyalty score combines tier perks, achievement badges and successful referrals.
          </p>
          <div className="hermes-rewards-summary-stats">
            <div className="hermes-rewards-stat">
              <strong className="mono">{loading ? "—" : earnedBadgeIds.length}</strong>
              <span className="text-3 fs-12">Badges earned</span>
            </div>
            <div className="hermes-rewards-stat">
              <strong className="mono">{loading ? "—" : referralCount}</strong>
              <span className="text-3 fs-12">Friends invited</span>
            </div>
            <div className="hermes-rewards-stat">
              <strong className="mono">{bonusActive ? "Active" : "—"}</strong>
              <span className="text-3 fs-12">Referral bonus</span>
            </div>
          </div>
        </div>
        <div className="hermes-rewards-perks">
          <h3 className="hermes-rewards-perks-title">Active tier perks</h3>
          <ul className="hermes-rewards-perk-list">
            {perks.map((p) => (
              <li key={p}>
                <span className="hermes-rewards-perk-check" aria-hidden="true">✓</span>
                {p}
              </li>
            ))}
          </ul>
          {tierKey !== "elite" && tierKey !== "admin" ? (
            <button type="button" className="hermes-cta-pill is-block" onClick={() => onNav?.("pricing")}>
              Unlock more perks
            </button>
          ) : null}
        </div>
      </article>

      {onboardingSteps.length > 0 ? (
        <article className="hermes-rewards-card hermes-onb-card">
          <div className="hermes-rewards-card-head">
            <h2>Onboarding progress</h2>
            <span className="text-3 fs-12">
              {(() => {
                const done = onboardingSteps.filter((s) => s.done).length;
                const total = onboardingSteps.length;
                return `${done} of ${total} steps complete`;
              })()}
            </span>
          </div>
          {(() => {
            const done = onboardingSteps.filter((s) => s.done).length;
            const total = onboardingSteps.length || 1;
            const pct = Math.round((done / total) * 100);
            return (
              <>
                <div className="hermes-onb-card-bar" aria-hidden="true">
                  <div className="hermes-onb-card-bar-fill" style={{ width: `${pct}%` }} />
                </div>
                <ul className="hermes-onb-card-list">
                  {onboardingSteps.map((s) => (
                    <li key={s.key} className={`hermes-onb-card-item${s.done ? " is-done" : ""}`}>
                      <span className="hermes-onb-card-check" aria-hidden="true">
                        {s.done ? "✓" : ""}
                      </span>
                      <div className="hermes-onb-card-body">
                        <strong>{s.label}</strong>
                        <span className="text-3 fs-12">{s.description}</span>
                      </div>
                      {!s.done && s.target ? (
                        <button
                          type="button"
                          className="hermes-onb-card-cta"
                          onClick={() => onNav?.(s.target)}
                        >
                          Open
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {pct < 100 ? (
                  <button
                    type="button"
                    className="hermes-cta-pill is-block"
                    onClick={() => onOpenOnboarding?.()}
                  >
                    Resume onboarding
                  </button>
                ) : (
                  <p className="text-3 fs-12 hermes-onb-card-done">All set — keep collecting trade badges below.</p>
                )}
              </>
            );
          })()}
        </article>
      ) : null}

      <article className="hermes-rewards-card">
        <div className="hermes-rewards-card-head">
          <h2>Achievements</h2>
          <span className="text-3 fs-12">
            {loading ? "Loading…" : `${earnedBadgeIds.length} of ${ALL_BADGES.length} unlocked`}
          </span>
        </div>
        <div className="hermes-rewards-badges-grid">
          {ALL_BADGES.map((b) => {
            const earned = earnedBadgeIds.includes(b.id);
            return (
              <div key={b.id} className={`hermes-rewards-badge${earned ? " is-earned" : " is-locked"}`}>
                <div
                  className="hermes-rewards-badge-icon"
                  style={{
                    background: earned ? `linear-gradient(135deg, ${b.color}, color-mix(in srgb, ${b.color} 50%, #0b0b14))` : "rgba(255,255,255,.04)",
                    color: earned ? "#fff" : "rgba(148,163,184,.5)",
                    boxShadow: earned ? `0 8px 22px ${b.color}55` : "none",
                  }}
                >
                  {b.icon}
                </div>
                <strong>{b.label}</strong>
                <span className="text-3 fs-12">{b.desc}</span>
                <span className={`hermes-rewards-badge-status${earned ? " is-earned" : ""}`}>
                  {earned ? "Earned · +50 pts" : "Locked"}
                </span>
              </div>
            );
          })}
        </div>
      </article>

      <article className="hermes-rewards-card">
        <div className="hermes-rewards-card-head">
          <h2>Referral progress</h2>
          <button type="button" className="hermes-rewards-link" onClick={() => onNav?.("invite")}>
            Open invite page →
          </button>
        </div>
        <div className="hermes-rewards-referral">
          <div className="hermes-rewards-referral-stat">
            <span className="text-3 fs-12">Friends invited</span>
            <strong className="mono">{loading ? "—" : referralCount}</strong>
          </div>
          <div className="hermes-rewards-referral-stat">
            <span className="text-3 fs-12">Next milestone</span>
            <strong className="mono">+3 slots / 30 days at {nextMilestone} invites</strong>
          </div>
          <div className="hermes-rewards-referral-stat">
            <span className="text-3 fs-12">Status</span>
            <strong className={bonusActive ? "is-pos" : ""}>
              {bonusActive ? "Bonus active" : "Idle"}
            </strong>
          </div>
        </div>
        <div className="hermes-rewards-progress">
          <div className="hermes-rewards-progress-fill" style={{ width: `${milestoneProgress}%` }} />
        </div>
        <p className="text-3 fs-12 hermes-rewards-referral-hint">
          Each completed invite stacks <strong>+3 marketplace agent slots for 30 days</strong>. Stackable with your tier.
        </p>
      </article>

      <article className="hermes-rewards-card">
        <div className="hermes-rewards-card-head">
          <h2>Earn more points</h2>
          <span className="text-3 fs-12">Quick wins to push your loyalty score</span>
        </div>
        <div className="hermes-rewards-quests">
          {QUESTS.map((q) => (
            <div key={q.id} className="hermes-rewards-quest">
              <span className="hermes-rewards-quest-icon" aria-hidden="true">{q.icon}</span>
              <div className="hermes-rewards-quest-body">
                <strong>{q.title}</strong>
                <span className="text-3 fs-12">{q.desc}</span>
              </div>
              <div className="hermes-rewards-quest-side">
                <span className="hermes-rewards-quest-points mono">+{q.points}</span>
                <button type="button" className="hermes-rewards-quest-cta" onClick={() => onNav?.(q.target)}>
                  {q.cta}
                </button>
              </div>
            </div>
          ))}
        </div>
      </article>

      <p className="text-3 fs-12 hermes-rewards-disclaimer">
        Loyalty points are a forward-looking score for visualizing engagement. Hermes does not currently exchange points for cash —
        a future update may introduce redemption (extra agent slots, marketplace credits, premium symbols).
      </p>
    </section>
  );
}
