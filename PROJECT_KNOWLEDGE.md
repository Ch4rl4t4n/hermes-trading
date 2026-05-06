# Hermes Trading Platform — Project Knowledge Base

## URLs & Server
- Marketing: https://letagentscook.lol
- App: https://app.letagentscook.lol
- Server: 46.224.120.151 (Ubuntu 8GB, Hetzner)
- Telegram bot: @Let_Agents_Cook_bot

## Stack
- Backend: Flask (Python) + PostgreSQL + Redis (plánované)
- Frontend: /root/hermes/dashboard/templates/index.html (~6900 riadkov, single file)
- Auth: bcrypt + Google OAuth (Flask-Dance)
- Email: Gmail SMTP
- Nginx: HTTPS + Let's Encrypt
- Systemd: hermes-dashboard, hermes-watcher, hermes-agents
- Payments: Stripe (test mode)

## Dôležité súbory
- /root/hermes/dashboard/app.py — hlavný Flask app
- /root/hermes/dashboard/templates/index.html — celý frontend
- /root/hermes/core/agent_marketplace.py — marketplace + record_paper_trade()
- /root/hermes/core/watcher_agent.py — monitoring + alerts + weekly report + telegram polling
- /root/hermes/core/telegram_bot.py — Telegram bot logika
- /root/hermes/core/trade_reasons.py — generate_trade_reason()
- /root/hermes/core/leaderboard.py — compute_leaderboard_cache()
- /root/hermes/scripts/ — seed a utility skripty
- /root/hermes/.env — všetky secrets

## DB Tabuľky (PostgreSQL)
- users — id, email, tier, stripe_customer_id, stripe_subscription_id, telegram_chat_id, weekly_report_enabled, unsubscribe_token
- trading_agents — id, name, symbol, category, strategy, win_rate, total_trades, show_in_leaderboard
- user_subscriptions — user_id, agent_id, mode, is_active
- paper_trades — id, user_id, agent_id, symbol, action, price, quantity, pnl, reason, signals (jsonb), confidence, timestamp
- trade_explanations — trade_id, explanation, signals, generated_at
- agent_pnl_snapshots — agent_id, user_id, snapshot_date, pnl_usd, pnl_pct, equity, trade_count, win_count
- agent_leaderboard_cache — agent_id, period, rank, pnl_pct, pnl_usd, win_rate, trade_count, subscriber_count
- alert_rules — user_id, agent_id, alert_type, threshold, is_enabled, last_triggered_at
- notifications — user_id, type, title, message, is_read
- system_events — event_type, severity, message, details

## API Endpointy
- GET/POST /api/auth/status|login|register
- GET /api/marketplace/agents|slots
- POST /api/marketplace/subscribe|unsubscribe
- GET /api/marketplace/my-agents
- GET /api/agents/pnl
- GET /api/agents/badges
- GET /api/trades/history
- GET /api/leaderboard?period=weekly|monthly|alltime
- GET/POST /api/alerts/rules
- GET /api/notifications + POST /api/notifications/read
- POST /api/stripe/create-checkout-session|create-portal-session|webhook
- POST /api/telegram/connect-token|disconnect|webhook
- GET /api/settings/weekly-report + POST
- GET /unsubscribe/<token>
- POST /api/admin/assign-demo-agents

## Tier Systém
- basic: 3 agenti, 3 alerty, view-only leaderboard, no telegram
- pro: 10 agentov, 15 alertov, plný leaderboard, telegram — 19€/mes
- elite: unlimited — 49€/mes
- admin: unlimited všetko

## Stripe Ceny (test mode)
- STRIPE_PRICE_PRO_MONTHLY, STRIPE_PRICE_PRO_YEARLY
- STRIPE_PRICE_ELITE_MONTHLY, STRIPE_PRICE_ELITE_YEARLY
(hodnoty v .env po spustení create_stripe_products.py)

## Hotové funkcie (Fáza 1 + 2 + začiatok 3)
✅ Login/registrácia (manual + Google OAuth)
✅ Tier systém (basic/pro/admin)
✅ 50 trading agentov v DB
✅ Marketplace API
✅ Onboarding (empty states, checklist ONB, contextual tooltips)
✅ Demo agenti pre nových userov (assign_demo_agents)
✅ Live P&L dashboard (agent_pnl_snapshots, auto-refresh 30s)
✅ Performance badges (top_gainer, hot_streak, steady, reliable)
✅ Alert systém (pnl_drop + agent_inactive, modal UI, email + telegram)
✅ Weekly email report (HTML, opt-out, pondelok 8:00 UTC)
✅ Leaderboard agentov (weekly/monthly/alltime, cache 6h)
✅ "Why?" vysvetlenia pre trades (reason, signals jsonb, confidence)
✅ Telegram bot @Let_Agents_Cook_bot (príkazy: /start /pnl /status /help /stop)
✅ Stripe integrácia (checkout, portal, webhooky, tier enforcement)

## Roadmapa — zostatok
### Fáza 3 (Biznis model) — v procese:
⬜ No-code agent builder (conversational AI)
⬜ Social sharing ("Môj agent +12%")

### Fáza 4 (UX/UI & Mobile):
⬜ Mobile responsiveness
⬜ PWA / mobile app
⬜ Dark/light mode toggle
⬜ Accessibility

### Fáza 5 (Pokročilé funkcie):
⬜ Agent marketplace (user-created agents)
⬜ Backtesting engine
⬜ API prístup pre Elite tier
⬜ Custom watcher nastavenia
⬜ CSV/PDF export

## Pracovný štýl
- Jeden bod naraz — ty dáš analýzu, Claude napíše Cursor prompt
- Cursor prompt = kompletné zadanie bez otázok
- Všetky DB queries cez SQLAlchemy text()
- Alembic pre migrácie: cd /root/hermes && venv/bin/alembic upgrade head
- Deploy: systemctl restart hermes-dashboard hermes-watcher
