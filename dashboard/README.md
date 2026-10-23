# AutoTrader ops dashboard

Read-only web UI for **ght.systems** — engine status, paper PnL, recent trades, decisions, signals, system events (heartbeats), and a kill-switch view.

The **Python trading engine** (Windows + MT5) remains the source of truth. This app:

- **Does not** place, modify, or cancel MT5 orders
- **Has no** `/api/order`, `/api/execute`, or similar endpoints
- Reads the same SQL tables the engine writes when a server-side database env var is set

## Stack

- Next.js (App Router) + TypeScript + Tailwind CSS
- Deploy target: **Vercel** (root directory = `dashboard/`)
- Domain: **`ght.systems`**

## Data source

| Server env | What the page shows |
|---|---|
| `DATABASE_URL` = Postgres URI (Supabase **transaction** pooler, port **6543**) | Live rows via `postgres` (prepared statements off, SSL required) |
| or `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (only if `DATABASE_URL` is empty) | Live rows via the service role. Never `NEXT_PUBLIC_` |
| Neither, and the app is on Vercel | **Database not configured** — empty tables, no sample trades |
| Neither, local `next dev` | Sample journal (`DASHBOARD_DATA_MODE` defaults to demo off Vercel) |

Query failures stay on an error state. They do not fall back to sample trades.

Tables read: `trades`, `decisions`, `signals`, `system_events` (heartbeat / engine_up / engine_down), `kill_switch_state`. Paper PnL is `sum(trades.pnl)` for rows that are not `open`.

The Windows engine should use the **session** pooler (port **5432**) in its own `DATABASE_URL`. Do not point the long-running process at port 6543.

## Required / optional env

See `.env.example`. Names only — no secrets in git.

| Variable | Required | Notes |
|---|---|---|
| `DASHBOARD_PASSWORD` | Recommended in production | Middleware password gate; empty = open access (local/dev) |
| `DASHBOARD_SESSION_SECRET` | Optional | HMAC pepper; defaults to password |
| `DATABASE_URL` | For live data | Transaction pooler URI, port 6543, server-only |
| `SUPABASE_URL` | Alternative | Project URL, server-only |
| `SUPABASE_SERVICE_ROLE_KEY` | Alternative | Service role, server-only, bypasses RLS |
| `DASHBOARD_DATA_MODE` | Optional | Local `demo` sample data. Ignored on Vercel when no database env is set |

## Local run

```bash
cd dashboard
cp .env.example .env.local
# set DASHBOARD_PASSWORD=... for gated access
npm install
npm run dev
# → http://localhost:3000
```

```bash
npm run build    # production build (CI gate)
npm run start    # serve build
npm run test:smoke
```

## API surface (intentionally small)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Public liveness (`placesOrders: false`, `dataMode`) |
| `POST` | `/api/auth/login` | Set session cookie |
| `POST` | `/api/auth/logout` | Clear session |
| `GET` | `/api/journal` | Read-only journal snapshot |
| `GET` | `/api/kill-switch` | Read the local demo flag (not the engine row) |
| `POST` | `/api/kill-switch` | Local demo flag only. Live mode does not write the engine kill switch |

## Vercel

1. Root Directory = `dashboard`.
2. Env (Production): `DASHBOARD_PASSWORD`, and `DATABASE_URL` **or** `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
3. Redeploy after env changes. Until `DATABASE_URL` / Supabase keys exist, production shows **Database not configured**.

### CLI (when `VERCEL_TOKEN` is available)

```bash
cd dashboard
npx vercel --token "$VERCEL_TOKEN" --prod --yes
```

## Hard rules

- `MODE=paper` engine remains default; dashboard is monitoring-only.
- Never commit secrets (`.env.local`, Vercel secrets stay out of git).
- No place-order endpoints — enforced by design and smoke test.
