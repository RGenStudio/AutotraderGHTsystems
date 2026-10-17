# AutoTrader (ght.systems)

Paper-first Forex trading engine for **EURUSD** / **USDJPY** (H1 entry, H4 trend).  
M0 scaffold: project layout, config, `MODE`, risk defaults, and a passing test suite — **no secrets in the repo**.

Canonical repo: [RGenStudio/AutotraderGHTsystems](https://github.com/RGenStudio/AutotraderGHTsystems)

## Hard rules (this phase)

- Default **`MODE=paper`**. Do not enable `live` until §13 paper criteria pass and a human approves.
- Risk Engine defaults (code): **0.5%** per trade · **2%** daily loss · **5%** weekly drawdown · **max 2** open positions.
- Broker credentials and API keys live only in a local `.env` on the Windows PC (or later Windows VPS) — never in chat or git.
- MetaTrader5 Python package + terminal require **Windows**. Cloud Linux cannot host the live engine.

## Quick start (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check src tests
python -m autotrader          # prints MODE=paper
```

Copy `.env.example` → `.env` on the operator Windows PC and fill values locally.

## Layout

```
config/config.yaml     # non-secret defaults (risk, symbols, windows)
src/autotrader/        # engine package
tests/                 # pytest
.env.example           # empty template only
```

## Disclaimer

Not financial advice. Trading can lose all capital — paper/demo first.
