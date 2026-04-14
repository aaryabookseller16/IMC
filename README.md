# IMC Prosperity 4 — Team Setup

## Folder structure

```
prosperity4/
├── datamodel.py        ← official IMC classes (DO NOT EDIT — matches their grader)
├── trader.py           ← your bot  (EDIT THIS)
├── requirements.txt    ← pip dependencies
├── logs/               ← save log files from uploads / backtest runs here
├── data/               ← put the sample CSV files here (download from platform)
│   ├── prices_round_1_day_0.csv
│   └── trades_round_1_day_0.csv
├── scripts/            ← helper notebooks or analysis scripts
└── README.md           ← this file
```

---

## First-time setup (run once)

```bash
# 1. Create a virtual environment
python -m venv venv

# 2. Activate it
#    Mac / Linux:
source venv/bin/activate
#    Windows:
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Daily workflow

### Step 1 — Test locally (no upload needed)

```bash
# Quick sanity check — runs two fake iterations and prints your orders
python trader.py

# Full backtest against real round data (much better signal)
prosperity4btest trader.py 1            # all days in round 1
prosperity4btest trader.py 1-0          # round 1, day 0 only
prosperity4btest trader.py 1 --merge-pnl   # merged PnL across days
```

### Step 2 — Upload to IMC

1. Go to https://prosperity.imc.com
2. Navigate to the current round
3. Upload trader.py  ← the whole file, including datamodel is NOT needed (IMC provides it)
4. Wait ~60 seconds for the test run (1000 iterations on a sample day)
5. Download the log file → save to `logs/`

### Step 3 — Read the log

Your `print()` statements appear in the log. Look for:
- Negative PnL → your fair value is wrong, or spread too tight
- Zero trades  → your orders aren't crossing the book; check prices
- Position limit hits → you're breaching the limit; check `can_buy` / `can_sell` logic

### Step 4 — Iterate and re-upload

No limit on submissions. Only the LAST upload counts for scoring.
Submit early so you always have a working version as a fallback.

---

## Key rules (from the wiki)

| Rule | Detail |
|---|---|
| Position limits | RAINFOREST_RESIN: 50, KELP: 50, SQUID_INK: 50 (confirm on platform each round) |
| Order rejection | ALL orders for a product rejected if aggregated qty would breach limit |
| Runtime limit | run() must return in 900ms |
| State persistence | Use `traderData` + `jsonpickle`. Max 50,000 chars |
| Allowed libraries | pandas, numpy, statistics, math, typing, jsonpickle only |
| Scoring | 10,000 iterations on the actual round day. Your last submission is used. |
| Tiebreaker | Earlier final submission wins on equal score — submit early! |

---

## What to tune in trader.py

| Variable | What it does | When to change |
|---|---|---|
| `STATIC_FAIR_VALUES` | Hardcoded fair value for stable products | After analysing sample CSV |
| `SPREAD` | How far from fair value your MM quotes sit | Wider = safer but fewer fills |
| `MM_SIZE` | Units offered on each MM quote | Reduce if hitting limits often |
| `hist[-20:]` | Rolling window for dynamic fair value | Larger window = smoother, slower |

---

## Round 1 products (confirmed)
- **RAINFOREST_RESIN** — historically stable around 10,000. Market-make around this.
- **KELP** — dynamic price. Use rolling mid or EMA as fair value.
- **SQUID_INK** — dynamic price. Possibly mean-reverting — check sample data.

---

## Useful links

- Platform: https://prosperity.imc.com
- Wiki: https://imc-prosperity.notion.site
- Backtester: https://github.com/nabayansaha/imc-prosperity-4-backtester
- Discord: linked from the platform (search "Round 1" for community hints)
- Visualizer: https://jmerle.github.io/imc-prosperity-3-visualizer/ (compatible with P4 log format)
