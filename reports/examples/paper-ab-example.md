# Paper A/B report (M8)

- **ab_mode:** `both`
- **cycles:** 6
- **seed:** 42
- **started_at:** 2026-10-17T18:34:07.296951+00:00
- **finished_at:** 2026-10-17T18:34:07.297306+00:00
- **MODE remains:** `paper` (live_enabled=False)

## Arm metrics

### `rules_only`

```
arm=rules_only
trades=5
expectancy_R=0.9200
max_DD_pct=0.50%
net_return_pct=2.31%
R:R=1.400
bad_JSON_rate=0.00% (0/0)
equity_end=10231.46
```

### `rules_plus_ai`

```
arm=rules_plus_ai
trades=3
expectancy_R=1.4667
max_DD_pct=0.00%
net_return_pct=2.22%
R:R=1.467
bad_JSON_rate=20.00% (1/5)
equity_end=10221.54
```

## §13 gate check

**Overall:** `FAIL`

| Check | Arm | Result | Detail |
|---|---|---|---|
| `min_sample` | `rules_plus_ai` | **FAIL** | trades=3 (need>=80) OR weeks=0.15 (need>=12); arm=rules_plus_ai |
| `max_drawdown` | `rules_only` | **PASS** | max_DD=0.50% (limit<=8.0%) |
| `net_return` | `rules_only` | **PASS** | net_return=2.31% (need>0.0%) |
| `expectancy` | `rules_only` | **PASS** | expectancy_R=0.9200 (need>0.0) |
| `reward_risk` | `rules_only` | **PASS** | avg_win/avg_loss_R=1.400 (need>=1.0) |
| `max_drawdown` | `rules_plus_ai` | **PASS** | max_DD=0.00% (limit<=8.0%) |
| `net_return` | `rules_plus_ai` | **PASS** | net_return=2.22% (need>0.0%) |
| `expectancy` | `rules_plus_ai` | **PASS** | expectancy_R=1.4667 (need>0.0) |
| `reward_risk` | `rules_plus_ai` | **PASS** | avg_win/avg_loss_R=1.467 (need>=1.0) |
| `bad_json_rate` | `rules_plus_ai` | **FAIL** | bad_JSON=20.00% (1/5 Agent4 calls; limit<=3.0%) |
| `ab_drawdown` | `ab` | **PASS** | rules+AI DD=0.00pp vs rules-only=0.50pp (limit <= rules-only + 1.0pp = 1.50pp) |
| `ab_expectancy` | `ab` | **PASS** | rules+AI expectancy_R=1.4667 vs rules-only=0.9200 (need >= rules-only) |

§13 paper criteria FAILED — remain on MODE=paper; do not go live.

## Notes

- This harness runs **synthetic/mock cycles** for CI and local comparison — it is **not** a substitute for the full §13 paper window on Exness MT5 demo.
- A gate **PASS** here still leaves **`MODE=paper`**. Live capital requires explicit human approval after a documented paper window.
