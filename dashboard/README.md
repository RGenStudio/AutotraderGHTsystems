# AutoTrader ops dashboard (M7)

Read-only web UI for **ght.systems** — recent decisions, trades, system events, and a **kill switch** control.

The **Python trading engine** (Windows + MT5) remains the source of truth. This app:

- **Does not** place, modify, or cancel MT5 orders
- **Has no** `/api/order`, `/api/execute`, or similar endpoints
- Ships with **demo data** suitable for Vercel serverless (SQLite on the engine host does not persist on Vercel)

## Stack

- Next.js (App Router) + TypeScript + Tailwind CSS
- Deploy target: **Vercel** (root directory = `dashboard/`)
- Domain intent: **`ght.systems`**

## Data modes

| `DASHBOARD_DATA_MODE` | Behavior |
|---|---|
| `demo` (default) | Static demo journal JSON + local/ephemeral kill-switch file |
| `api` | `GET` `ENGINE_JOURNAL_URL` for live JSON; falls back to demo on failure |

**Production journal sync** (engine SQLite → Supabase → dashboard) is a later milestone. On Vercel, prefer `demo` until that exists.

Kill-switch POST writes a flag file (`.data/kill-switch.json` locally, `/tmp` on Vercel). It is **not** automatically mirrored into the Windows engine until shared store sync lands.

## Required / optional env

See `.env.example`.

| Variable | Required | Notes |
|---|---|---|
| `DASHBOARD_PASSWORD` | Recommended in production | Middleware password gate; empty = open access (local/dev) |
| `DASHBOARD_SESSION_SECRET` | Optional | HMAC pepper; defaults to password |
| `DASHBOARD_DATA_MODE` | Optional | `demo` \| `api` (default `demo`) |
| `ENGINE_JOURNAL_URL` | Only for `api` | HTTPS JSON feed |
| `DASHBOARD_KILL_SWITCH_PATH` | Optional | Override kill-switch JSON path |

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
| `GET` | `/api/health` | Public liveness (`placesOrders: false`) |
| `POST` | `/api/auth/login` | Set session cookie |
| `POST` | `/api/auth/logout` | Clear session |
| `GET` | `/api/journal` | Read-only decisions / trades / events |
| `GET` | `/api/kill-switch` | Read kill-switch state |
| `POST` | `/api/kill-switch` | `{ "action": "engage"\|"clear", "reason": "…" }` |

## Vercel deploy

### Project settings

1. Import **RGenStudio/AutotraderGHTsystems** in Vercel.
2. Set **Root Directory** to `dashboard`.
3. Framework preset: Next.js.
4. Env vars: at least `DASHBOARD_PASSWORD`, `DASHBOARD_DATA_MODE=demo`.

### CLI (when `VERCEL_TOKEN` is available)

```bash
cd dashboard
npx vercel --token "$VERCEL_TOKEN" --prod --yes
# Optional if org/project known:
# VERCEL_ORG_ID=… VERCEL_PROJECT_ID=… npx vercel --prod --yes --token "$VERCEL_TOKEN"
```

### Custom domain `ght.systems`

In Vercel → Project → Settings → Domains → add `ght.systems` (and `www` if desired).

DNS at the registrar (exact records Vercel shows; typically):

| Type | Name | Value |
|---|---|---|
| `A` | `@` | `76.76.21.21` (confirm in Vercel UI) |
| `CNAME` | `www` | `cname.vercel-dns.com` (confirm in Vercel UI) |

Bartender: add GitHub/Actions or Cursor secret **`VERCEL_TOKEN`** (and optionally `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID`) so agents can deploy without inventing credentials.

## Hard rules

- `MODE=paper` engine remains default; dashboard is monitoring-only.
- Never commit secrets (`.env.local`, Vercel secrets stay out of git).
- No place-order endpoints — enforced by design and smoke test.
