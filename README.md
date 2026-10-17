# AutoTrader (ght.systems)

Paper-first Forex trading engine for **EURUSD** / **USDJPY** (H1 entry, H4 trend).  
**M2:** Strategy Engine A/B/C (code signals) + closed-bar backtester.  
Default **`MODE=paper`** — no live trading, no AI agents yet.

Canonical repo: [RGenStudio/AutotraderGHTsystems](https://github.com/RGenStudio/AutotraderGHTsystems)

## Hard rules (this phase)

- Default **`MODE=paper`**. Do not enable `live` until §13 paper criteria pass and a human approves.
- Risk Engine defaults (code): **0.5%** per trade · **2%** daily loss · **5%** weekly drawdown · **max 2** open positions.
- **Active window (UTC):** weekdays **12:00–21:00** by default — outside the window the engine must **not** open new entries.
- Strategy Engine creates **candidate entries in code only** — AI does not invent signals (agents come later).
- Broker credentials and API keys live only in a local `.env` on the Windows PC (or later Windows VPS) — never in chat or git.
- MetaTrader5 Python package + terminal require **Windows**. Cloud Linux / CI uses the **mock** data backend (no MT5 credentials required).

## Quick start (dev / Linux CI)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check src tests
python -m autotrader          # prints MODE=paper
```

On Linux, `create_market_data_provider()` automatically selects the **mock/fixture** backend so tests pass without MetaTrader5.

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

The live MT5 data path only works on a **Windows** machine with the Exness MT5 terminal installed and logged in.

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
   MT5_PATH=C:\Path\To\terminal64.exe
   ```

   Leave `MT5_PATH` empty if the terminal is already running and discoverable.

5. Keep MT5 open and logged in, then from the repo:

   ```bat
   python -c "from autotrader.data import create_market_data_provider, Timeframe; p=create_market_data_provider(); print(len(p.fetch_candles('EURUSD', Timeframe.H1, count=10)))"
   ```

   With `MT5_LOGIN` set on Windows, the factory selects the **MetaTrader5** backend. Without credentials (or on Linux) it stays on the mock backend.

6. Respect **operator hours**: configure `active_window` in `config/config.yaml` (default weekdays 12:00–21:00 UTC). Outside that window, do not open new entries. Prefer flat before shutdown.

See also project docs: local-run rules (pre-VPS) and project context in the Cursor project store.

## Layout

```
config/config.yaml          # non-secret defaults (risk, symbols, active_window, backtest costs)
src/autotrader/
  active_window.py          # is_within_active_window(now)
  data/                     # MarketDataProvider + MT5 / mock adapters
  indicators/               # EMA, RSI, ATR, ADX, Bollinger
  strategy/                 # A trend · B breakout · C mean reversion + ADX regime
  backtest/                 # closed-bar engine, costs, metrics, CLI
tests/
  fixtures/sample_ohlc.csv  # tiny CSV smoke fixture
.env.example                # empty template only
```

## Disclaimer

Not financial advice. Trading can lose all capital — paper/demo first.
