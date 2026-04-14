# CLAUDE.md

## Project: IMC Prosperity 4 — Round 1 Trading Algorithm

### Competition Overview
IMC Prosperity 4 is a 5-round algorithmic trading competition (April 14–30, 2026). Teams write Python `Trader` classes that trade against bots on a simulated exchange. Currency is XIRECs. Round 1 goal: earn 200,000+ XIRECs before the third trading day.

### Round 1 Products

**INTARIAN_PEPPER_ROOT** (position limit: 80)
- "Steady, slow-growing root" — fair value follows a perfectly linear trend
- Formula: `fair(t) = start_price + 0.001 * t` (exact slope from data, residual std ~1.1)
- Each day starts where the previous ended (~+1000/day)
- Spread typically 11–14, mean-reverting (autocorrelation ≈ -0.50)
- Strategy: linear trend tracker + EMA correction + market making with inventory skew

**ASH_COATED_OSMIUM** (position limit: 80)
- "Volatile with hidden pattern" — oscillates slowly around 10,000
- Smoothed range: 9988–10013, no clean sine pattern (best R² ≈ 0.21)
- Spread typically 16, mean-reverting (autocorrelation ≈ -0.50)
- Strategy: slow EMA (α=0.005) fair value tracker + aggressive taking + market making

### Algorithm Structure (submission format)
```python
from datamodel import OrderDepth, TradingState, Order
class Trader:
    def bid(self): return 0          # Round 2 only, placeholder for now
    def run(self, state: TradingState):
        result = {}                  # Dict[str, List[Order]]
        conversions = 0
        traderData = ""              # serialized state string (max 50k chars)
        return result, conversions, traderData
```

### Critical Rules
- **Position limits**: Exchange cancels ALL orders for a product if aggregate buy qty > (limit - position) OR aggregate sell qty > (limit + position). Track buy/sell budgets independently.
- **sell_orders values are NEGATIVE** in OrderDepth
- **Order prices must be int**
- **Allowed imports**: pandas, numpy, statistics, math, typing, jsonpickle + stdlib
- **Timeout**: 900ms per `run()` call
- **State persistence**: Use `traderData` string (serialized via jsonpickle). AWS Lambda is stateless — class/global variables may not persist between calls.
- **Test runs**: 1,000 iterations. Final eval: 10,000 iterations.

### Current Performance (test run, 1k iterations)
- ASH_COATED_OSMIUM: ~1,443 XIRECs (268 buys @ 9997.3, 297 sells @ 10002.7)
- INTARIAN_PEPPER_ROOT: ~1,120 XIRECs (93 buys @ 12046.9, 99 sells @ 12061.4)
- Total: ~2,563 XIRECs → projected ~25k at 10k iterations
- No errors, no log warnings

### Known Improvement Areas
- Pepper Root undertrading early (EMA warmup lag) — consider tighter spread and lower take edge
- Osmium inventory drifts to -29 by end — flatten more aggressively
- Market-making spreads may be too wide — test tightening to capture more fills
- Consider adaptive spread based on current book spread

### Data Files
- `prices_round_1_day_{-2,-1,0}.csv` — order book snapshots (semicolon-delimited)
- `trades_round_1_day_{-2,-1,0}.csv` — market trades (semicolon-delimited)
- `.circ` files — Prosperity submission logs (zip archives containing .log, .py, .json)

### Backtester
Install the community backtester for local testing:
```bash
pip install -U prosperity4btest
prosperity4btest trader.py 1        # run on all round 1 data
prosperity4btest trader.py 1-0      # run on round 1 day 0 only
prosperity4btest trader.py 1 --vis  # auto-open visualizer
```
Repo: https://github.com/nabayansaha/imc-prosperity-4-backtester

**TODO: Add the backtester as a dev dependency or submodule in this repo.**

### Key File
- `trader.py` — the submission algorithm (this is what gets uploaded to prosperity.imc.com)
