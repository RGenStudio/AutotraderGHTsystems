# AutoTrader (ght.systems)

Paper-first Forex trading engine for **EURUSD** / **USDJPY** (H1 entry, H4 trend).  
**M6:** Orchestrator H1 cycle + Telegram alerts + heartbeat/`system_events`.  
**M7:** Read-only ops [dashboard](./dashboard/) (Next.js) — decisions / trades / events + kill switch; Vercel deploy for **ght.systems**.  
**M8:** Paper A/B harness — **rules-only vs rules+AI** on synthetic/mock cycles + §13 gate checker (does **not** enable live).  
Default **`MODE=paper`** — no live trading; LLM defaults to **mock** (no API keys required in CI).

Canonical repo: [RGenStudio/AutotraderGHTsystems](https://github.com/RGenStudio/AutotraderGHTsystems)

## Hard rules (this phase)

- Default **`MODE=paper`**. Do not enable `live` until §13 paper criteria pass and a human approves. The CLI / execution factory **refuse** `MODE=live`.
- Risk Engine defaults (code): **0.5%** per trade · **2%** daily loss · **5%** weekly drawdown · **max 2** open positions (at most one per symbol).
- **Active window (UTC):** default **00:00–24:00 every day** (effectively 24h while the engine is up) — narrow `active_window` in config if you want operator-hours only. Outside a narrowed window the engine must **not** open new entries. Kill switch / risk rules are unchanged.
- Bad Decision Maker JSON / LLM failure ≡ **do not trade**. Kill switch checked every Risk Engine cycle.
- Strategy Engine creates **candidate entries in code only** — AI filters/sizes; it does not invent signals.
- Agents propose only; **Risk Engine (code) is authority**. Agent 3 cannot raise risk ceilings.
- Telegram alerts soft-fail: if Telegram is down, the cycle **logs and continues** (never hard-fails).
- Web dashboard is **read-only + kill switch** — **no** place-order / execution endpoints; the Python engine remains source of truth for MT5.
- Broker credentials and API keys live only in a local `.env` on the Windows PC (or later Windows VPS) — never in chat or git.
- MetaTrader5 Python package + terminal require **Windows**. Cloud Linux / CI uses the **mock** data backend, **mock** LLM, and **paper** execution (no MT5 `order_send`).

## Quick start (dev / Linux CI)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check src tests
python -m autotrader                     # smoke: MODE=paper + execution + database + llm + ab_mode + telegram
python -m autotrader run --once          # one H1 orchestrator cycle (mock data / mock LLM)
python -m autotrader paper-ab --cycles 50   # M8 paper A/B harness (synthetic cycles)
autotrader run --once --at 2026-10-14T15:00:00+00:00
```

On Linux, `create_market_data_provider()` automatically selects the **mock/fixture** backend, `create_llm_client()` uses the **mock** LLM, and `create_execution_backend()` returns the **paper** backend so tests pass without MetaTrader5 or API keys.

## LLMClient + Agents 1–4 (M5)

All model calls go through **`LLMClient`** (HTTP wrapper + pydantic schema validation + timeout). CI uses `MockLLMBackend` — no real API keys.

| Agent | Role | Model slot (config) | Default model id | Env key |
|---|---|---|---|---|
| 1 Technical Analyst | Structure vs signal; **no** size/order | `llm.models.technical` | `deepseek-chat` | `DEEPSEEK_API_KEY` |
| 2 News | Calendar + high-impact **±30 min** no-trade flag | `llm.models.news` | `deepseek-chat` | `DEEPSEEK_API_KEY` |
| 3 Risk Manager | Propose size / SL / TP only | `llm.models.risk_manager` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| 4 Decision Maker | Final JSON action; invalid schema ⇒ no trade | `llm.models.decision_maker` | `claude-sonnet-4-5` | `ANTHROPIC_API_KEY` |

Default `llm.backend` is **`http`**. Brief principle: cheap models filter first; Claude decides last. CI / missing key for that agent soft-falls to mock (loop continues).

### Enable real LLM (paper / Windows)

1. Put keys in local `.env` for the agents you want live: `DEEPSEEK_API_KEY` (1–2), `OPENAI_API_KEY` (3), `ANTHROPIC_API_KEY` (4).
2. Optional: `LLM_BACKEND=http` (YAML default) or `LLM_BACKEND=mock` to force mock.
3. Routing by model id: `deepseek-*` → DeepSeek (`https://api.deepseek.com`) · `gpt-*` → OpenAI (`https://api.openai.com/v1`, override with `LLM_BASE_URL`) · `claude-*` → Anthropic **Messages** API (`https://api.anthropic.com/v1/messages`).
4. Model ids default as in the table above (`config/config.yaml`).
5. Run: `python -m autotrader run --once` (add `--mt5-data` on Windows with `MT5_*` filled for live demo candles). Execution stays **paper** (no MT5 `order_send`).

`LLM_BACKEND=mock` always forces mock. Missing key for a model’s provider → soft mock for that call only (logged).

### API credit low alert (Telegram)

When the orchestrator runs (including `--loop`), it best-effort probes remaining provider credit. If remaining USD &lt; `API_CREDIT_WARN_USD` (default **1.0**), it sends Telegram **once per 6h cooldown**.

- DeepSeek: `GET /user/balance` when `DEEPSEEK_API_KEY` is set.
- OpenAI: tries known credit-grants endpoints; **most API keys cannot read prepaid balance** — set optional manual `OPENAI_CREDIT_USD` (update when you top up).
- Anthropic: skipped (no simple remaining-balance API).
- Never logs full API keys.

```python
from datetime import UTC, datetime
from autotrader.agents.pipeline import build_agent_pipeline
from autotrader.agents.calendar import StubNewsCalendar
from autotrader.journal import open_trade_journal
from autotrader.llm import MockLLMBackend, LLMClient

journal = open_trade_journal()  # or temp sqlite URL in tests
backend = MockLLMBackend()
# enqueue Agent1..4 JSON dicts / strings for deterministic tests
pipe = build_agent_pipeline(journal=journal, force_mock=True)
# Or: AgentPipeline(LLMClient(backend), journal=journal, calendar=StubNewsCalendar(events=[]))

result = pipe.run(
    {"symbol": "EURUSD", "side": "long", "entry_price": 1.085, "strategy": "A"},
    now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
    symbol="EURUSD",
    idempotency_key="signal-2026-10-14-h1",
)
if result.trade_allowed and result.risk_payload:
    # Pass result.risk_payload to RiskEngine.evaluate(..., raw_json=...)
    ...
else:
    # reason: news_blackout | bad_json | llm_or_schema_fail | decision_skip | ...
    ...
```

**Agent 2 calendar:** set `NEWS_CALENDAR_URL` in local `.env` to a structured JSON feed (adapter: `UrlNewsCalendar`). Tests use `StubNewsCalendar`. Blackout is **±30 minutes** around High-impact **USD/EUR/JPY** events for the symbol’s currencies (code-enforced).

**Costs:** each agent call is written to `agent_calls`; estimated USD usage goes to `costs` (`kind=llm_api`).

Agents 1∥2 run in **parallel** inside the pipeline (Agents 3 → 4 stay sequential).

## Orchestrator + Telegram (M6)

One H1 cycle:

`data → indicators → strategy pre-filter → (if signal) Agents 1∥2 → 3 → 4 → Risk Engine → paper execution stub → journal`

Gates every cycle: **`MODE=paper`**, **kill switch**, **active_window** (no new entries outside). Heartbeat / engine up-down are written to `system_events`.

```bash
# Single cycle (default: mock market data + mock LLM; Telegram optional from .env)
python -m autotrader run --once
python -m autotrader run --once --at 2026-10-14T15:00:00+00:00

# Windows + Exness demo candles (still MODE=paper execution):
python -m autotrader run --once --mt5-data

# Scheduler hook (tests use a fake clock; production can loop with sleep)
python -m autotrader run --loop --max-cycles 1
```

There is **no** separate `forward-test` CLI. Closest ops path: **`MODE=paper`** + `run --once --mt5-data` (forward/demo candles) while orders stay on the paper execution backend.

```python
from datetime import UTC, datetime, timedelta
from autotrader.orchestrator import build_orchestrator, SimpleIntervalScheduler
from autotrader.journal import open_trade_journal

journal = open_trade_journal()  # or temp sqlite URL in tests
orch = build_orchestrator(journal=journal, force_mock_data=True, force_mock_llm=True)
orch.heartbeat.mark_up(message="engine started")
result = orch.run_cycle(now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC))
# result.status / result.symbol_results — approve | reject | no_signal | skipped

sched = SimpleIntervalScheduler(orchestrator=orch, interval=timedelta(hours=1), sleep=lambda _s: None)
sched.run_until(
    start=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
    stop_at=datetime(2026, 10, 14, 18, 0, tzinfo=UTC),
)
orch.heartbeat.mark_down(message="engine stopped")
```

**Telegram:** set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in local `.env` to enable alerts on **approve / reject / kill / errors**. Unset → no-op notifier (CI default). HTTP is mockable in tests; failures are logged and the cycle continues. Failed-send logs redact `bot<token>` from API URLs (never log the full token). If a token was ever logged or pasted in chat, **revoke it** with [@BotFather](https://t.me/BotFather) and put a new value in `.env`.

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## Paper A/B harness (M8)

Compare **rules-only** (Strategy Engine → Risk Engine, no LLM) vs **rules+AI** (Agents 1–4 filter) on **N synthetic/mock cycles**. This is a CI/local harness — **not** a multi-week Exness demo run.

Config (`config/config.yaml` → `paper_ab`):

| Key | Values |
|---|---|
| `ab_mode` | `rules_only` \| `rules_plus_ai` \| `both` |
| `cycles` | default `50` |
| `gates.*` | §13 thresholds (80 trades **or** 2 weeks, DD≤8%, expectancy>0, bad-JSON≤3%, A/B DD/expectancy). `min_weeks=2` is weaker statistically — Bartender accepted. |

```bash
# Both arms, 50 synthetic cycles → markdown + JSON under reports/ (gitignored except examples/)
python -m autotrader paper-ab --cycles 50
python -m autotrader paper-ab --cycles 50 --ab-mode rules_only
python -m autotrader.paper_ab --cycles 20 --seed 7

# Fixture-driven (tests / reproducible demo)
python -m autotrader paper-ab --cycles 6 --fixture tests/fixtures/paper_ab_cycles.json

# Console script alias
autotrader-paper-ab --cycles 50
```

Metrics per arm: **trades**, **expectancy (R)**, **max DD**, **bad-JSON rate** (Agent 4 / rules+AI).  
§13 gate checker prints **PASS/FAIL** and writes it into the report — it **never** sets `MODE=live` (`live_enabled=false` always).

Example committed sample: [`reports/examples/paper-ab-example.md`](./reports/examples/paper-ab-example.md).

### Run paper A/B on Windows with MT5 later

The harness itself needs **no MT5** (synthetic cycles work on Linux CI and Windows). When you later compare arms against a real Exness **demo** journal:

1. Keep **`MODE=paper`** / demo account — never live until §13 passes **and** a human approves.
2. On the Windows PC with Exness MT5 installed:

   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e ".[dev,mt5]"
   copy .env.example .env
   rem fill MT5_* locally; leave MODE=paper
   python -m autotrader paper-ab --cycles 50
   ```

3. Use the orchestrator for live-demo H1 cycles (`python -m autotrader run --once --mt5-data`) while the A/B harness remains the **offline comparator** + gate checker.
4. Document closed trades / weeks in the trade journal; promote to small live capital only after human review — this CLI will not flip `MODE` for you.

## Trade journal (SQLite / M4)

Every Risk Engine decision (with **reason**), paper fill, and kill-switch change can be written to a local SQLite database (WAL mode) via SQLAlchemy.

**Where the DB file lives**

| Setting | Location |
|---|---|
| Default (no `DATABASE_URL`) | `data/autotrader.db` under the **repo root** |
| Override | Set `DATABASE_URL` in local `.env` (e.g. `sqlite:///C:/path/to/data/autotrader.db`) |

The `data/` directory is gitignored (along with `*.db`). Tests always use a **temp** SQLite file — they never touch the default path.

**Inspect the journal**

```bash
# After the engine has written rows (or from a Python shell):
python -c "
from autotrader.journal import open_trade_journal
j = open_trade_journal()  # or open_trade_journal('sqlite:///data/autotrader.db')
for d in j.query_decisions(symbol='EURUSD'):
    print(d.id, d.created_at, d.allowed, d.reason)
"

# Or with the sqlite3 CLI:
sqlite3 data/autotrader.db \"SELECT id, symbol, allowed, reason, created_at FROM decisions ORDER BY id;\"
```

```python
from datetime import UTC, datetime
from autotrader.journal import open_trade_journal, persist_risk_outcome, persist_execution_outcome
from autotrader.risk import CandidateOrder, RiskContext, RiskEngine, default_risk_limits
from autotrader.execution import ApprovedOrder, create_execution_backend
from autotrader.config import Mode

journal = open_trade_journal()  # creates tables if needed
engine = RiskEngine(limits=default_risk_limits())
backend = create_execution_backend(mode=Mode.PAPER)
candidate = CandidateOrder(
    symbol="EURUSD", side="long", requested_risk_pct=0.5,
    stop_distance_price=0.0010, entry_price=1.10,
    idempotency_key="signal-2026-10-17-h1",
)
ctx = RiskContext(equity=10_000, now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC))
decision = engine.evaluate(candidate, ctx)
decision_id = persist_risk_outcome(journal, decision, candidate=candidate, context=ctx)
if decision.allowed:
    approved = ApprovedOrder(
        symbol=candidate.symbol, side=candidate.side, volume=0.1,
        entry_price=candidate.entry_price, stop_price=1.0990, take_profit=None,
        idempotency_key=candidate.idempotency_key, risk_pct=0.5,
    )
    result = backend.send_order(approved)
    persist_execution_outcome(journal, approved, result, decision_id=decision_id)
```

Tables (brief M4+M5): `signals`, `agent_calls`, `decisions`, `orders`, `trades`, `costs`, `system_events`, plus `kill_switch_state`.

## Risk Engine + execution (M3)

Every candidate order must pass the **Risk Engine** before any send:

| Check | On fail |
|---|---|
| Kill switch active | reject (`kill_switch_active`) |
| `MODE=live` (this phase) | reject (`live_mode_forbidden`) |
| Bad / invalid Decision JSON | reject (`bad_json`) |
| Outside active window | reject (`outside_active_window`) |
| Risk % > 0.5 | reject |
| Daily loss ≥ 2% (UTC day) | reject |
| Weekly DD ≥ 5% | reject + **engage kill switch** |
| Open positions ≥ 2 or symbol already open | reject |

```python
from datetime import UTC, datetime
from autotrader.risk import CandidateOrder, RiskContext, RiskEngine, default_risk_limits
from autotrader.kill_switch import KillSwitch
from autotrader.execution import ApprovedOrder, create_execution_backend
from autotrader.reconcile import reconcile_positions
from autotrader.config import Mode

ks = KillSwitch()
engine = RiskEngine(limits=default_risk_limits(), kill_switch=ks)
backend = create_execution_backend(mode=Mode.PAPER)  # never hits real MT5 order_send

candidate = CandidateOrder(
    symbol="EURUSD",
    side="long",
    requested_risk_pct=0.5,
    stop_distance_price=0.0010,
    entry_price=1.10,
    idempotency_key="signal-2026-10-17-h1",
)
ctx = RiskContext(equity=10_000, now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC))
decision = engine.evaluate(candidate, ctx)
if decision.allowed:
    backend.send_order(
        ApprovedOrder(
            symbol=candidate.symbol,
            side=candidate.side,
            volume=0.1,
            entry_price=candidate.entry_price,
            stop_price=1.0990,
            take_profit=None,
            idempotency_key=candidate.idempotency_key,
            risk_pct=candidate.requested_risk_pct,
        )
    )
# Replaying the same idempotency_key returns DUPLICATE — no second fill.
```

**Startup reconcile:** compare local journal vs backend positions; mismatch → kill switch / pause until human clear:

```python
from autotrader.reconcile import reconcile_positions
result = reconcile_positions(local=[], remote=backend.list_open_positions(), kill_switch=ks)
# result.paused is True on mismatch
```

Windows MT5 `order_send` is stubbed behind the `ExecutionBackend` protocol (`mt5_stub`) for later wiring — CI always uses paper.

## Run a backtest (no MT5)

Closed-bar only (no look-ahead). Reports win rate, R:R, max drawdown, and expectancy. Spread / slippage / fees are configurable.

```bash
# Synthetic OHLC (default mixed scenario) — works on Linux CI
python -m autotrader.backtest
python -m autotrader.backtest --strategy A --scenario trend --bars 800
python -m autotrader.backtest --strategy C --scenario range --spread 0.00015 --slippage 0.00005

# Optional: your own closed OHLC CSV (columns: time,open,high,low,close[,volume])
python -m autotrader.backtest --csv path/to/ohlc.csv --strategy all

# Console script alias
autotrader-backtest --strategy B --bars 600
```

Example output lines: `trades=…`, `win_rate=…`, `R:R=…`, `expectancy_R=…`, `max_DD=…`.

Strategies follow the brief ADX regime: **ADX>25 → A or B**, **ADX<20 → C**, **ADX 20–25 → no trade**.

## Run against Exness MT5 demo (Windows PC)

The live MT5 **data** path only works on a **Windows** machine with the Exness MT5 terminal installed and logged in. **Order send** remains paper/stub in M3 — do not send live orders.

**Login ≠ rates.** A successful `MT5 initialize` / login only proves the terminal accepted credentials. `copy_rates_from_pos` can still return `None` with `(-1, 'Call failed')` when the symbol is not in Market Watch or the name does not match the broker (common on Exness). Treat those as separate failures.

### Exness symbol suffixes (exact casing)

Exness often exposes pairs as `EURUSDm` / `USDJPYm` (and similar), not bare `EURUSD`. **Casing is significant** — `EURUSDm` ≠ `EURUSDM`. The adapter keeps config spelling as-is (no `.upper()` on trading symbols), calls `symbol_select(symbol, True)`, and retries `copy_rates` once. Connect logs show the exact Market Watch names.

Configure one of:

1. **Broker-native `symbols`** — set Market Watch names in `config/config.yaml` with **exact** broker casing:

   ```yaml
   symbols:
     - EURUSDm
     - USDJPYm
   ```

2. **`symbol_map`** — keep logical app names and map to wire names (values keep broker casing):

   ```yaml
   symbols:
     - EURUSD
     - USDJPY
   symbol_map:
     EURUSD: EURUSDm
     USDJPY: USDJPYm
   ```

If rates still fail, the error lists visible/matching symbols from `symbols_get` and calls out case mismatches when `symbol_select` fails (e.g. config `EURUSDM` vs broker `EURUSDm`).

### Pull updates without losing local config

Local `config/config.yaml` edits (Exness symbols, LLM models, etc.) can conflict with `git pull`. Before pulling on the Windows PC:

```bat
git stash push -u -m "local config" -- config
git pull
git stash pop
```

Or copy `config\config.yaml` aside, pull, then copy your symbols / `symbol_map` back. Keep `.env` local (never commit).

1. Install **Exness MetaTrader 5** and log in to your **demo** account (EA/algo trading enabled). Prefer Standard MT5 demo, USD.
2. Clone this repo on that Windows PC.
3. Create a venv and install (include the optional MT5 extra):

   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e ".[dev,mt5]"
   ```

4. Copy `.env.example` → `.env` and fill **locally** (never commit):

   ```env
   MODE=paper
   MT5_LOGIN=your_demo_login
   MT5_PASSWORD=your_demo_password
   MT5_SERVER=your_exness_demo_server
   MT5_PATH=C:/Path/To/terminal64.exe
   ```

   Prefer **forward slashes** in `MT5_PATH`. A Windows backslash before `terminal64`
   (`...\MetaTrader 5\terminal64.exe`) can be mis-read as a tab escape (`\t`),
   yielding a broken path like `...5erminal64.exe`. The adapter detects that pattern
   and rewrites it, but setting `C:/.../terminal64.exe` avoids the footgun.

   Leave `MT5_PATH` empty if the terminal is already running and discoverable.

5. Align **`symbols` / `symbol_map`** with Market Watch (see above), keep MT5 open and logged in, then from the repo:

   ```bat
   python -c "from autotrader.data import create_market_data_provider, Timeframe; p=create_market_data_provider(); print(len(p.fetch_candles('EURUSD', Timeframe.H1, count=10)))"
   ```

   With `MT5_LOGIN` set on Windows, the factory selects the **MetaTrader5** backend. Without credentials (or on Linux) it stays on the mock backend.

6. Default `active_window` is **00:00–24:00 UTC every day** (new entries whenever the engine is up). Narrow it in `config/config.yaml` if you want operator-hours only. Prefer flat before shutdown. On engine start, run reconcile; clear kill switch only after human review if mismatched.

See also project docs: local-run rules (pre-VPS) and project context in the Cursor project store.

## Ops dashboard (M7)

Read-only Next.js app under [`dashboard/`](./dashboard/) — demo journal data on Vercel (SQLite does not persist on serverless) + password gate + kill-switch POST. Full run/deploy notes: [`dashboard/README.md`](./dashboard/README.md).

```bash
cd dashboard
npm install
npm run build
npm run test:smoke
npm run dev   # http://localhost:3000
```

Env: `DASHBOARD_PASSWORD`, `DASHBOARD_DATA_MODE=demo|api` (see `dashboard/.env.example`). Domain intent: **ght.systems** on Vercel (Root Directory = `dashboard`).

## Layout

```
dashboard/                  # M7 Next.js ops UI (Vercel root directory)
config/config.yaml          # non-secret defaults (risk, symbols, active_window, llm, paper_ab, database)
src/autotrader/
  active_window.py          # is_within_active_window(now)
  risk.py                   # RiskEngine — approve/reject candidate orders
  kill_switch.py            # in-memory kill switch (checked every cycle)
  reconcile.py              # startup local vs remote position reconcile
  orchestrator/             # H1 cycle + scheduler hook + heartbeat
  telegram/                 # Telegram notifier (soft-fail; TELEGRAM_* from env)
  paper_ab/                 # M8 rules-only vs rules+AI harness + §13 gates + reports
  db/                       # SQLAlchemy engine (SQLite WAL) + ORM tables
  journal/                  # TradeJournal API + persist helpers + PersistentKillSwitch
  llm/                      # LLMClient + mock/HTTP backends + cost hook
  agents/                   # Agents 1–4 + calendar adapter + pipeline (1∥2)
  execution/                # paper backend + MT5 stub protocol (no CI order_send)
  data/                     # MarketDataProvider + MT5 / mock adapters
  indicators/               # EMA, RSI, ATR, ADX, Bollinger
  strategy/                 # A trend · B breakout · C mean reversion + ADX regime
  backtest/                 # closed-bar engine, costs, metrics, CLI
data/autotrader.db          # default journal file (created at runtime; gitignored)
reports/                    # runtime A/B reports (gitignored); examples/ committed
tests/
  fixtures/sample_ohlc.csv  # tiny CSV smoke fixture
  fixtures/paper_ab_cycles.json
.env.example                # empty template only (LLM / Telegram keys listed)
```

## Disclaimer

Not financial advice. Trading can lose all capital — paper/demo first.
