# Hermes Trading Platform — Status (May 4, 2026)

## URLs

- Marketing: https://letagentscook.lol
- App: https://app.letagentscook.lol
- Server: 46.224.120.151 (Ubuntu 8GB, Hetzner)

## Stack

- Backend: Flask (Python) + PostgreSQL + Redis (plánované)
- Frontend: Single HTML template (**6882** riadkov) — `dashboard/templates/index.html`
- Auth: bcrypt + Google OAuth (Flask-Dance)
- Email: Gmail SMTP (App Password)
- Nginx: HTTPS + Let's Encrypt (app.letagentscook.lol + letagentscook.lol)
- Systemd services: hermes-dashboard, hermes-watcher, hermes-agents

## Admin credentials

**Nepište heslá do gitu.** Admin účet a heslá držte len v `.env`, secrets manageri alebo na serveri pri nasadení.

## Aktuálny stav

- Login/registrácia (manual + Google OAuth)
- Tier systém (basic/medium/pro/admin)
- 50 trading agentov v DB
- Marketplace API (`/api/marketplace/*`) vrátane `GET /api/marketplace/slots`
- Watcher agent (systemd, email alerty)
- HTTPS všade
- Email verifikácia (SMTP nakonfigurovaný)
- Dashboard s 3 kategóriami (Crypto / Akcie / Komodity), slots bar, sidebar P&L + tier
- Pozadie appky: canvas sieť so šípkami (full-screen `NeuralBackground` v `index.html`)

## Rozrobené (IN PROGRESS)

- Prípadné doladenie UI dashboardu (spacing, mobile)
- Samostatná „login page“ oproti modálnemu loginu (ak sa odlúči od SPA)
- Onboarding po registrácii

## Ďalší krok (NEXT)

1. Onboarding flow po registrácii
2. Prednastavení demo agenti pre nových používateľov
3. Retention / engagement metriky podľa roadmapy

## Roadmapa (5 fáz)

- **Fáza 1:** Prvý dojem & onboarding (teraz)
- **Fáza 2:** Retention & engagement
- **Fáza 3:** Biznis model & monetizácia
- **Fáza 4:** UX/UI & mobile
- **Fáza 5:** Pokročilé funkcie & škálovanie

## Dôležité súbory

- `/root/hermes/dashboard/app.py` — hlavný Flask app
- `/root/hermes/dashboard/templates/index.html` — frontend (single template)
- `/root/hermes/core/agent_marketplace.py` — marketplace logika + sloty
- `/root/hermes/core/watcher_agent.py` — monitoring agent
- `/root/hermes/.env` — secrets (SMTP, Google OAuth, DB); **nie v gite**
- `/root/hermes/dashboard/hermes.db` — stará SQLite (nepoužíva sa ak beží PostgreSQL)
- PostgreSQL je aktívna DB cez `DATABASE_URL` v `.env`

## API endpointy (výber)

- `GET  /api/auth/status`
- `POST /api/auth/login`
- `POST /api/auth/register`
- OAuth Google podľa nasadenia (`/oauth/google`, …)
- `GET  /api/marketplace/agents`
- `POST /api/marketplace/subscribe`
- `POST /api/marketplace/unsubscribe`
- `GET  /api/marketplace/my-agents`
- `GET  /api/marketplace/slots`
- `GET  /api/notifications`
- `POST /api/notifications/read` (ak je v app nasadený)
