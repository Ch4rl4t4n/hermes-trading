import { useState } from "react";
import client from "../api/client";

/**
 * Hermes Club tier comparison page — aligned with the Hermes roadmap and
 * business plan defined in CLAUDE.md.
 *
 *   BASIC   — free starter (3 marketplace agents, 1 user-built agent, 30-day history)
 *   PRO     — 19€/mo (10 mkt agents, 5 builder agents, 15 alerts, Telegram, live trading, 365-day history)
 *   ELITE   — 49€/mo (unlimited everything, Developer API, advanced backtesting, custom watcher)
 *
 * Sections:
 *  1. Hero (brand + headline + subline)
 *  2. Plan card row with billing toggle (yearly = save 20%) + 2 priced cards (PRO / ELITE)
 *     BASIC stays as a free-tier note above the cards.
 *  3. Top benefits at a glance — 3 columns (BASIC / PRO / ELITE) with real platform limits
 *  4. Other Hermes advantages — features actually shipped or shipping next
 *  5. Footer disclosure
 */

const PLANS = {
  pro: {
    id: "pro",
    name: "PRO",
    monthly: 19,
    yearly: 15.2, // 19 * 0.8 = 20% discount when billed yearly
    yearlyTotal: 182.4,
    blurb: "For active paper traders ready to scale beyond the starter portfolio.",
    cta: "Start 7-day free trial",
  },
  elite: {
    id: "elite",
    name: "ELITE",
    monthly: 49,
    yearly: 39.2, // 49 * 0.8
    yearlyTotal: 470.4,
    blurb: "Everything in PRO + unlimited agents, Developer API and advanced backtesting.",
    cta: "Start 7-day free trial",
    bestValue: true,
  },
};

/**
 * Top benefits (3 columns BASIC / PRO / ELITE).
 * Values mirror the official tier table in CLAUDE.md so the marketing
 * promise can never drift away from what the backend actually enforces.
 */
const BENEFITS = [
  {
    icon: "agents",
    title: "Marketplace agents",
    desc: "Pre-built AI agents you can subscribe to from the marketplace.",
    basic: "3",
    pro: "10",
    elite: "Unlimited",
    elitePremium: true,
  },
  {
    icon: "builder",
    title: "Custom agents (Builder)",
    desc: "No-code agent builder — your own strategies running 24/7.",
    basic: "1",
    pro: "5",
    elite: "Unlimited",
    elitePremium: true,
  },
  {
    icon: "wallet",
    title: "Symbol coverage",
    desc: "Tradable instruments your agents can scan and execute on.",
    basic: "BTC · ETH · SOL",
    pro: "All 99 symbols",
    elite: "All 99 symbols",
  },
  {
    icon: "history",
    title: "Trade history",
    desc: "How far back you can drill into your own paper / live trades.",
    basic: "30 days",
    pro: "365 days",
    elite: "Unlimited",
  },
  {
    icon: "alerts",
    title: "Smart alert rules",
    desc: "P&L drop, inactivity, entry/exit and custom conditions.",
    basic: "3 rules",
    pro: "15 rules",
    elite: "Unlimited",
    elitePremium: true,
  },
  {
    icon: "telegram",
    title: "Telegram bot & email",
    desc: "Push alerts to Telegram + weekly summary email.",
    basic: "Email only",
    pro: "Included",
    elite: "Included",
  },
  {
    icon: "live",
    title: "Live trading",
    desc: "Switch your top agents from paper to a real broker connection.",
    basic: "—",
    pro: "Active",
    elite: "Active",
  },
  {
    icon: "backtest",
    title: "Backtesting engine",
    desc: "Replay strategies on historical data with detailed equity curves.",
    basic: "—",
    pro: "Included",
    elite: "Multi-symbol & multi-period",
    elitePremium: true,
  },
  {
    icon: "api",
    title: "Developer API",
    desc: "Programmatic REST + WebSocket access to your agents and trades.",
    basic: "—",
    pro: "—",
    elite: "Included",
    elitePremium: true,
  },
  {
    icon: "export",
    title: "CSV / PDF export",
    desc: "Download your full trade history for accounting or research.",
    basic: "—",
    pro: "Included",
    elite: "Included",
  },
];

/**
 * Other Hermes advantages — features actually shipped (per CLAUDE.md
 * "Hotové features" list) or imminent on the roadmap.
 */
const ADVANTAGES = [
  {
    icon: "spark",
    title: "Why It's Moving",
    desc: "Every trade gets an AI-generated explanation — signals, confidence and the on-chain / news context behind it.",
  },
  {
    icon: "live",
    title: "Real-time P&L dashboard",
    desc: "Live agent monitoring with auto-refresh every 30 s and per-agent P&L breakdown across all categories.",
  },
  {
    icon: "delta",
    title: "Performance badges",
    desc: "Gamified achievements — Top Gainer, Hot Streak, Steady and Reliable — earned automatically from your trade record.",
  },
  {
    icon: "builder",
    title: "AI Agent Builder",
    desc: "4-step no-code wizard with AI-generated strategy summary. Pick a symbol, a strategy, your risk and the watcher takes care of the rest.",
  },
  {
    icon: "telegram",
    title: "Telegram bot",
    desc: "Connect /start, /pnl, /status, /help and /stop commands directly to your agents — full account control from your phone.",
  },
  {
    icon: "research",
    title: "Live leaderboard",
    desc: "Weekly, monthly and all-time rankings of every public agent. Subscribe to the top performers with a single tap.",
  },
  {
    icon: "shield",
    title: "Performance cards & sharing",
    desc: "Generate beautiful, shareable performance cards for any agent — embed P&L, win-rate and a sparkline in one click.",
  },
  {
    icon: "key",
    title: "Referral program",
    desc: "Invite a friend — both of you earn +3 bonus marketplace slots for 30 days. Stack referrals to scale faster.",
  },
  {
    icon: "manager",
    title: "Custom watcher rules",
    desc: "Define your own monitoring rules on price, P&L delta, agent inactivity and webhook triggers (Elite).",
  },
  {
    icon: "course",
    title: "Early access",
    desc: "First look at new swarms, agents and AI models before they ship to the rest of the platform.",
  },
];

function Icon({ name }) {
  const c = "currentColor";
  switch (name) {
    case "agents":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="8" r="3.4" />
          <path d="M5 21c.5-3.6 3.5-5.6 7-5.6S18.5 17.4 19 21" />
          <circle cx="18.5" cy="6.5" r="1.5" />
        </svg>
      );
    case "builder":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 6 6 14a3 3 0 0 0 0 4 3 3 0 0 0 4 0l8-8" />
          <path d="m13 7 4 4" />
          <path d="M19 3a3 3 0 0 0-2 5l-2 2 2 2 2-2a3 3 0 0 0 0-7Z" />
        </svg>
      );
    case "wallet":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="6.5" width="18" height="13" rx="2.6" />
          <path d="M3 10h18" />
          <circle cx="16.5" cy="14.5" r="1.2" />
        </svg>
      );
    case "alerts":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
          <path d="M10.4 20a2.1 2.1 0 0 0 3.2 0" />
        </svg>
      );
    case "history":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3.2 2" />
        </svg>
      );
    case "telegram":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 10.5 21 4l-3 16-6-3-3 4-1-6Z" />
        </svg>
      );
    case "api":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="m9 18-6-6 6-6" />
          <path d="m15 6 6 6-6 6" />
        </svg>
      );
    case "live":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M5.5 5.5a9 9 0 0 0 0 13M18.5 5.5a9 9 0 0 1 0 13M8 8a5 5 0 0 0 0 8M16 8a5 5 0 0 1 0 8" />
        </svg>
      );
    case "spark":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 17 9 11l4 4 8-9" />
          <path d="M17 6h4v4" />
        </svg>
      );
    case "research":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 21h18" />
          <path d="M5 21V11M10 21V7M15 21V13M20 21V4" />
        </svg>
      );
    case "delta":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 4 4 20h16Z" />
        </svg>
      );
    case "backtest":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 12 8 8l4 4 5-5 4 4" />
          <path d="M3 18h18" />
        </svg>
      );
    case "export":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      );
    case "shield":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 3 4 6v6c0 5 3.5 8.5 8 9 4.5-.5 8-4 8-9V6Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
    case "key":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="8" cy="14" r="4" />
          <path d="m11 11 9-9 3 3-3 3-2-2-2 2-2-2" />
        </svg>
      );
    case "course":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="m3 6 9 4 9-4-9-4Z" />
          <path d="M3 6v8l9 4 9-4V6" />
        </svg>
      );
    case "manager":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
        </svg>
      );
    default:
      return null;
  }
}

function BenefitValue({ value }) {
  if (value === "Included") {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m5 12 5 5L20 6" />
      </svg>
    );
  }
  if (value === "—" || value === "" || value == null) {
    return <span className="hermes-club-benefit-dash" aria-hidden="true">—</span>;
  }
  return <span>{value}</span>;
}

export default function Tiers({ user, onToast, onNav }) {
  const [billing, setBilling] = useState("yearly");
  const [busyPlan, setBusyPlan] = useState(null);
  const isYearly = billing === "yearly";
  const currentTier = String(user?.tier || "basic").toLowerCase();

  const startCheckout = async (planId) => {
    if (!user) {
      onNav?.("login");
      return;
    }
    setBusyPlan(planId);
    try {
      const { data } = await client.post("/api/stripe/create-checkout-session", {
        tier: planId,
        billing: isYearly ? "yearly" : "monthly",
      });
      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      onToast?.(data?.error || "Stripe checkout is not configured yet.");
    } catch (err) {
      onToast?.(err?.response?.data?.error || "Could not start checkout.");
    } finally {
      setBusyPlan(null);
    }
  };

  const renderPriceBlock = (plan) => {
    if (isYearly) {
      const original = plan.monthly;
      return (
        <>
          <span className="hermes-club-price-strike">€{original.toFixed(2)}</span>
          <strong className="hermes-club-price">
            <span className="hermes-club-price-currency">€</span>
            {plan.yearly.toFixed(2)}
            <span className="hermes-club-price-period">/month</span>
          </strong>
          <span className="hermes-club-price-billed">(billed €{plan.yearlyTotal.toFixed(2)} annually)</span>
        </>
      );
    }
    return (
      <>
        <strong className="hermes-club-price">
          <span className="hermes-club-price-currency">€</span>
          {plan.monthly.toFixed(2)}
          <span className="hermes-club-price-period">/month</span>
        </strong>
        <span className="hermes-club-price-billed">billed monthly</span>
      </>
    );
  };

  return (
    <section className="page-content hermes-club">
      <div className="hermes-club-hero">
        <div className="hermes-club-brandmark">
          <span className="hermes-club-brand-mark" aria-hidden="true">⌂</span>
          <span className="hermes-club-brand-name">HERMES</span>
        </div>
        <h1 className="hermes-club-title">Club</h1>
        <h2 className="hermes-club-headline">Scale your AI trading desk</h2>
        <p className="hermes-club-sub">
          Subscribe to unlock more agents, the Developer API, advanced backtesting and live trading.
        </p>
        <p className="hermes-club-fineprint">
          Optional subscription. Core paper-trading, marketplace browsing, P&amp;L dashboard, badges and the leaderboard
          remain free for every Hermes account.
        </p>
      </div>

      <div className="hermes-club-card">
        <div className="hermes-club-toolbar">
          <div className="hermes-club-billing-label">Billing plan</div>
          <button
            type="button"
            className={`hermes-club-toggle${isYearly ? " is-yearly" : ""}`}
            role="switch"
            aria-checked={isYearly}
            onClick={() => setBilling(isYearly ? "monthly" : "yearly")}
          >
            <span className="hermes-club-toggle-knob" aria-hidden="true" />
            <span className="hermes-club-toggle-text">
              {isYearly ? "Pay yearly (save 20%)" : "Pay monthly"}
            </span>
          </button>
        </div>

        <div className="hermes-club-plans-grid">
          <div className="hermes-club-plans-spacer" aria-hidden="true">
            <p className="text-3 fs-12">
              Already on the free <strong>BASIC</strong> tier — 3 marketplace agents, 1 builder agent,
              30-day history and weekly email summary.
            </p>
          </div>

          {[PLANS.pro, PLANS.elite].map((plan) => {
            const isCurrent = currentTier === plan.id;
            return (
              <div
                key={plan.id}
                className={`hermes-club-plan${plan.bestValue ? " is-best" : ""}${isCurrent ? " is-current" : ""}`}
              >
                {plan.bestValue ? <span className="hermes-club-best-pill">Best value</span> : null}
                <h3 className={`hermes-club-plan-name${plan.bestValue ? " is-elite" : " is-pro"}`}>
                  {plan.name}
                </h3>
                <div className="hermes-club-plan-price">{renderPriceBlock(plan)}</div>
                <button
                  type="button"
                  className={`hermes-club-cta${plan.bestValue ? " is-best" : ""}${isCurrent ? " is-current" : ""}`}
                  disabled={Boolean(busyPlan) || isCurrent}
                  onClick={() => startCheckout(plan.id)}
                >
                  {isCurrent ? "Current plan" : busyPlan === plan.id ? "Loading…" : plan.cta}
                </button>
              </div>
            );
          })}
        </div>

        <h4 className="hermes-club-section-heading">Top benefits at a glance</h4>

        <div className="hermes-club-benefits is-three-col">
          <div className="hermes-club-benefit-row hermes-club-benefit-head">
            <div className="hermes-club-benefit-info">
              <span className="hermes-club-benefit-head-label">Feature</span>
            </div>
            <div className="hermes-club-benefit-value">
              <span className="hermes-club-benefit-head-tier">BASIC</span>
            </div>
            <div className="hermes-club-benefit-value">
              <span className="hermes-club-benefit-head-tier is-pro">PRO</span>
            </div>
            <div className="hermes-club-benefit-value">
              <span className="hermes-club-benefit-head-tier is-elite">ELITE</span>
            </div>
          </div>

          {BENEFITS.map((b) => (
            <div key={b.title} className="hermes-club-benefit-row">
              <div className="hermes-club-benefit-info">
                <span className="hermes-club-benefit-icon" aria-hidden="true">
                  <Icon name={b.icon} />
                </span>
                <div className="hermes-club-benefit-copy">
                  <strong>{b.title}</strong>
                  <span className="text-3 fs-12">{b.desc}</span>
                </div>
              </div>
              <div className="hermes-club-benefit-value is-basic">
                <BenefitValue value={b.basic} />
              </div>
              <div className="hermes-club-benefit-value">
                <BenefitValue value={b.pro} />
              </div>
              <div className={`hermes-club-benefit-value is-elite${b.elitePremium ? " is-emph" : ""}`}>
                <BenefitValue value={b.elite} />
              </div>
            </div>
          ))}
        </div>

        <div className="hermes-club-asterisk text-3 fs-12">
          * Live trading and Developer API require a verified, KYC-approved account. ELITE-only features ship gradually
          across Phase 4 and Phase 5 of the Hermes roadmap.
        </div>

        <div className="hermes-club-cta-row">
          <button
            type="button"
            className="hermes-club-cta is-outline"
            disabled={Boolean(busyPlan) || currentTier === "pro"}
            onClick={() => startCheckout("pro")}
          >
            {currentTier === "pro" ? "Current plan" : "Start 7-day free trial"}
          </button>
          <button
            type="button"
            className="hermes-club-cta is-best"
            disabled={Boolean(busyPlan) || currentTier === "elite"}
            onClick={() => startCheckout("elite")}
          >
            {currentTier === "elite" ? "Current plan" : "Start 7-day free trial"}
          </button>
        </div>
      </div>

      <h2 className="hermes-club-advantages-heading">Other Hermes advantages</h2>
      <p className="hermes-club-advantages-lead text-3 fs-12">
        These features are part of every paid plan — built and maintained by the Hermes team.
      </p>
      <div className="hermes-club-advantages">
        {ADVANTAGES.map((a) => (
          <div key={a.title} className="hermes-club-advantage">
            <span className="hermes-club-advantage-icon" aria-hidden="true">
              <Icon name={a.icon} />
            </span>
            <div className="hermes-club-advantage-copy">
              <strong>{a.title}</strong>
              <p className="text-3 fs-12">{a.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <p className="hermes-club-disclaimer text-3 fs-12">
        Subscriptions billed via Stripe and managed inside your account. Cancel anytime from{" "}
        <a href="#" onClick={(e) => { e.preventDefault(); onNav?.("settings"); }}>Settings → Subscription</a>.
        By proceeding you accept the <a href="/terms">Terms &amp; Conditions</a> of Hermes Trading Labs and confirm you
        have reviewed the <a href="/privacy">Privacy Policy</a>.
      </p>
    </section>
  );
}
