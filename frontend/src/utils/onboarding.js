/**
 * Compute onboarding step progress from real user state.
 *
 * Returned shape (always 4 steps in this order):
 *   [{ key, label, description, done, target }]
 *
 * `target` is a navigation page id consumed by `onNav(id)`.
 *
 * Heuristics:
 *   1. agent_added       — user has at least one subscribed/built agent
 *   2. alert_configured  — agents.length > 0 (proxy until per-user alert count is exposed)
 *   3. telegram_connected — user.telegram_chat_id is set
 *   4. first_backtest    — user.first_backtest_at flag (falls back to false)
 *
 * Demo agents (whole array === demoAgents reference) are not counted as real.
 */
export function deriveOnboardingSteps(user, agents, options = {}) {
  const { demoAgentsRef } = options;
  const isDemo = Array.isArray(agents) && demoAgentsRef && agents === demoAgentsRef;
  const realAgents = !isDemo && Array.isArray(agents) ? agents : [];
  const hasAgents = realAgents.length > 0;
  const hasTelegram = Boolean(
    user?.telegram_chat_id ||
      user?.telegramConnected ||
      user?.telegram_connected,
  );
  const hasBacktest = Boolean(
    user?.first_backtest_at ||
      user?.firstBacktestAt ||
      (typeof window !== "undefined" &&
        window.localStorage?.getItem?.("hermes_first_backtest_done") === "1"),
  );
  const hasAlert = Boolean(
    user?.alert_rules_count != null
      ? Number(user.alert_rules_count) > 0
      : hasAgents,
  );

  return [
    {
      key: "agent_added",
      label: "Add your first agent",
      description: "Subscribe in the marketplace or build a custom one.",
      done: hasAgents,
      target: "marketplace",
    },
    {
      key: "alert_configured",
      label: "Configure alerts",
      description: "Get notified when an agent moves out of plan.",
      done: hasAlert,
      target: "alerts",
    },
    {
      key: "telegram_connected",
      label: "Connect Telegram",
      description: "Receive trade pings on your phone.",
      done: hasTelegram,
      target: "settings",
    },
    {
      key: "first_backtest",
      label: "Run your first backtest",
      description: "Validate a strategy on historical data.",
      done: hasBacktest,
      target: "backtest",
    },
  ];
}

export function onboardingPercent(steps) {
  if (!Array.isArray(steps) || steps.length === 0) return 0;
  const done = steps.filter((s) => s?.done).length;
  return Math.round((done / steps.length) * 100);
}
