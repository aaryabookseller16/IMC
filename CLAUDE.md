# CLAUDE.md — IMC Prosperity 4

## Competition
5-round algo trading, April 14–30 2026. Write Python `Trader` class. Currency: XIRECs. Round 1 goal: 200k+ XIRECs.

## Round 1 Products

**INTARIAN_PEPPER_ROOT** (limit: 80)
- Linear fair value: `fair(t) = start_price + 0.001 * t` (residual std ~1.1, ~+1000/day)
- Spread 11–14, autocorrelation ≈ -0.50
- Strategy: linear trend + EMA correction + MM with inventory skew

**ASH_COATED_OSMIUM** (limit: 80)
- Mean-reverts around 10,000, range 9988–10013 (R² ≈ 0.21)
- Spread ~16, autocorrelation ≈ -0.50
- Strategy: slow EMA (α=0.005) + aggressive taking + MM

## Submission Format
```python
from datamodel import OrderDepth, TradingState, Order
class Trader:
    def bid(self): return 0
    def run(self, state: TradingState):
        result = {}       # Dict[str, List[Order]]
        conversions = 0
        traderData = ""   # max 50k chars
        return result, conversions, traderData
```

## Critical Rules
- Position breach → exchange cancels ALL orders for that product. Track buy/sell budgets separately.
- `sell_orders` values are **negative** in OrderDepth
- Order prices must be `int`
- Imports: pandas, numpy, statistics, math, typing, jsonpickle + stdlib
- Timeout: 900ms. State via `traderData` (jsonpickle) — Lambda is stateless.
- Test: 1k iterations. Final eval: 10k iterations.

## Performance (1k iterations)
| Product | PnL | Buys | Sells |
|---|---|---|---|
| ASH_COATED_OSMIUM | ~1,443 | 268 @ 9997.3 | 297 @ 10002.7 |
| INTARIAN_PEPPER_ROOT | ~1,120 | 93 @ 12046.9 | 99 @ 12061.4 |
| **Total** | **~2,563** → ~25k projected | | |

## Known Issues
- Pepper Root: EMA warmup lag → undertrading early
- Osmium: inventory drifts to -29 → flatten more aggressively
- MM spreads possibly too wide; try adaptive spread from book

## Files
- `prices_round_1_day_{-2,-1,0}.csv` — order book snapshots (semicolon-delimited)
- `trades_round_1_day_{-2,-1,0}.csv` — market trades
- `scripts/trader-vinny.py` — active Round 1 submission
- `scripts/datamodel.py` — official IMC classes (do not edit)

## Backtester
```bash
pip install -r requirements.txt          # installs prosperity4btest
prosperity4btest trader.py 1             # all round 1 data
prosperity4btest trader.py 1-0           # day 0 only
prosperity4btest trader.py 1 --vis       # with visualizer
```
Repo: https://github.com/nabayansaha/imc-prosperity-4-backtester

---

## Prior Winners — Frankfurt Hedgehogs (P3, 2nd / 12k teams)
Source: https://github.com/TimoDiehm/imc-prosperity-3

**Philosophy**
- Market microstructure puzzle, not ML — simple beats overfitted.
- Validate autocorrelation before betting on mean reversion.
- Prefer flat parameter regions over peak-optimized values.

**Fair Value — Wall Mid**
- `fair = (bid_wall + ask_wall) / 2` — more stable than raw mid or EMA.
- Bid/ask walls = deep-liquidity levels in the book.

**Mean Reversion**
- Confirm negative autocorrelation vs. random-normal baseline.
- Fixed entry/exit thresholds outperform dynamic z-scores.

**Backtesting**
- Don't optimize for website score alone — overfits to simulation noise.
- Open-source backtester for sweeps; official site for bot-dependent strategies.

**Risk**
- Tiebreaker = earlier submission at equal score → submit early, often.
- Tighter spreads = more fills; wider = safer. Tune via grid search.
