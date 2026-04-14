"""
scripts/analyse_data.py
───────────────────────
Analyse and plot IMC Prosperity price / trade CSVs.

Usage (single file):
    python scripts/analyse_data.py ROUND1/prices_round_1_day_0.csv

Usage (whole round directory — plots all days together):
    python scripts/analyse_data.py ROUND1/
    python scripts/analyse_data.py          # defaults to ROUND1/
"""

import sys
import os
import glob
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
#  I/O helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_prices(filepath: str) -> pd.DataFrame:
    """Load a single semicolon-delimited IMC prices CSV."""
    df = pd.read_csv(filepath, sep=";")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def load_trades(filepath: str) -> pd.DataFrame:
    """Load a single semicolon-delimited IMC trades CSV."""
    df = pd.read_csv(filepath, sep=";")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def load_round_prices(data_dir: str) -> pd.DataFrame:
    """Load and concatenate all prices_*.csv files found in data_dir."""
    pattern = os.path.join(data_dir, "prices_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No prices_*.csv files found in {data_dir!r}")
    frames = [load_prices(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    # add a continuous x-axis: each day is 1_000_000 timestamps wide
    df["abs_timestamp"] = df["day"] * 1_000_000 + df["timestamp"]
    return df


def load_round_trades(data_dir: str) -> pd.DataFrame:
    """Load and concatenate all trades_*.csv files found in data_dir."""
    pattern = os.path.join(data_dir, "trades_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        t = load_trades(f)
        # infer day from filename  e.g. trades_round_1_day_-2.csv → day=-2
        base = os.path.basename(f)
        try:
            day_str = base.split("_day_")[1].replace(".csv", "")
            t["day"] = int(day_str)
        except (IndexError, ValueError):
            t["day"] = 0
        frames.append(t)
    df = pd.concat(frames, ignore_index=True)
    df["abs_timestamp"] = df["day"] * 1_000_000 + df["timestamp"]
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Stats summary
# ─────────────────────────────────────────────────────────────────────────────

def summarise(df: pd.DataFrame):
    products = df["product"].unique()
    print(f"\n{'='*60}")
    print(f"  {len(products)} product(s): {', '.join(products)}")
    print(f"{'='*60}")

    for prod in products:
        sub = df[df["product"] == prod]["mid_price"].dropna()
        mean = sub.mean()
        std  = sub.std()
        mn   = sub.min()
        mx   = sub.max()
        cv   = std / mean * 100

        stability = (
            "STABLE  → use static fair value"
            if cv < 0.5 else
            "DYNAMIC → use rolling mean / EMA"
        )
        print(f"\n  {prod}")
        print(f"    mean:  {mean:.2f}")
        print(f"    std:   {std:.4f}  (CV: {cv:.3f}%)")
        print(f"    range: {mn:.0f} – {mx:.0f}")
        print(f"    → {stability}")


# ─────────────────────────────────────────────────────────────────────────────
#  Plotting
# ─────────────────────────────────────────────────────────────────────────────

def plot_prices(df: pd.DataFrame, title_suffix: str = ""):
    """
    Quick plot for a single prices DataFrame.
    Shows mid_price and spread per product.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        print("\n[plot] matplotlib not installed — pip install matplotlib")
        return

    # compute spread if we have bid/ask columns
    if "bid_price_1" in df.columns and "ask_price_1" in df.columns:
        df = df.copy()
        df["spread"] = df["ask_price_1"] - df["bid_price_1"]
        show_spread = True
    else:
        show_spread = False

    products = df["product"].unique()
    cols = 2 if show_spread else 1
    fig, axes = plt.subplots(len(products), cols,
                             figsize=(7 * cols, 4 * len(products)),
                             squeeze=False)

    x_col = "abs_timestamp" if "abs_timestamp" in df.columns else "timestamp"

    for row, prod in enumerate(products):
        sub = df[df["product"] == prod].sort_values(x_col)

        ax_price = axes[row][0]
        ax_price.plot(sub[x_col], sub["mid_price"], lw=0.8, color="steelblue")
        ax_price.set_title(f"{prod} — mid price{title_suffix}")
        ax_price.set_xlabel("timestamp")
        ax_price.set_ylabel("price")
        ax_price.grid(alpha=0.3)

        if show_spread:
            ax_spread = axes[row][1]
            ax_spread.plot(sub[x_col], sub["spread"], lw=0.8, color="darkorange")
            ax_spread.set_title(f"{prod} — spread (ask₁ − bid₁){title_suffix}")
            ax_spread.set_xlabel("timestamp")
            ax_spread.set_ylabel("spread")
            ax_spread.grid(alpha=0.3)

    plt.tight_layout()
    out = _save_fig(fig, "price_analysis")
    plt.show()


def plot_round1(data_dir: str = "ROUND1", overlay_trades: bool = True):
    """
    Load all prices (and optionally trades) CSVs from data_dir and produce:

      Per product:
        • Panel 1 — mid_price across all days (day boundaries marked)
        • Panel 2 — bid/ask spread across all days
        • Panel 3 — trade execution prices (if overlay_trades=True and data exists)

    Saves the figure to logs/round1_overview.png and shows it interactively.

    Parameters
    ----------
    data_dir : str
        Path to the directory containing prices_*.csv and trades_*.csv files.
        Defaults to "ROUND1" (relative to the project root).
    overlay_trades : bool
        Whether to load and plot trade prices alongside mid_price.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("\n[plot] matplotlib not installed — pip install matplotlib")
        return

    # ── load data ──────────────────────────────────────────────────────────
    print(f"[plot_round1] loading prices from {data_dir!r} ...")
    prices = load_round_prices(data_dir)

    trades = pd.DataFrame()
    if overlay_trades:
        try:
            trades = load_round_trades(data_dir)
            if not trades.empty:
                print(f"[plot_round1] loaded {len(trades)} trade records")
        except Exception as e:
            print(f"[plot_round1] could not load trades: {e}")

    products   = sorted(prices["product"].unique())
    days       = sorted(prices["day"].unique())
    n_products = len(products)

    # ── figure layout ──────────────────────────────────────────────────────
    n_rows = n_products
    n_cols = 2  # col 0 = mid price (+trades), col 1 = spread
    fig, axes = plt.subplots(n_rows, n_cols,
                             figsize=(16, 5 * n_rows),
                             squeeze=False)
    fig.suptitle(f"IMC Prosperity — Round 1 overview  (days {days})",
                 fontsize=14, fontweight="bold", y=1.01)

    # day boundary x positions
    day_boundaries = {d: d * 1_000_000 for d in days}

    # colours for day shading
    day_colours = ["#f0f4ff", "#fff8f0", "#f0fff4", "#fff0f4"]

    for row, prod in enumerate(products):

        # ── price sub-frame ────────────────────────────────────────────────
        p = prices[prices["product"] == prod].sort_values("abs_timestamp").copy()
        if "bid_price_1" in p.columns and "ask_price_1" in p.columns:
            p["spread"] = p["ask_price_1"] - p["bid_price_1"]
        else:
            p["spread"] = None

        # ── trade sub-frame ────────────────────────────────────────────────
        if not trades.empty and "symbol" in trades.columns:
            t = trades[trades["symbol"] == prod].sort_values("abs_timestamp").copy()
        else:
            t = pd.DataFrame()

        # ── Panel 0: mid price ─────────────────────────────────────────────
        ax0 = axes[row][0]
        _shade_days(ax0, days, day_colours, day_boundaries, p)

        ax0.plot(p["abs_timestamp"], p["mid_price"],
                 lw=0.9, color="steelblue", label="mid price", zorder=3)

        if not t.empty and "price" in t.columns:
            ax0.scatter(t["abs_timestamp"], t["price"],
                        s=12, color="crimson", alpha=0.6,
                        label="trades", zorder=4)

        ax0.set_title(f"{prod} — mid price", fontweight="bold")
        ax0.set_ylabel("price")
        ax0.set_xlabel("timestamp (abs)")
        ax0.legend(fontsize=8)
        ax0.grid(alpha=0.25)
        _add_day_lines(ax0, days, day_boundaries)

        # ── Panel 1: spread ────────────────────────────────────────────────
        ax1 = axes[row][1]
        _shade_days(ax1, days, day_colours, day_boundaries, p)

        if p["spread"].notna().any():
            ax1.plot(p["abs_timestamp"], p["spread"],
                     lw=0.8, color="darkorange", label="spread (ask₁ − bid₁)")
        else:
            ax1.text(0.5, 0.5, "spread data not available",
                     transform=ax1.transAxes, ha="center", va="center",
                     color="grey")

        ax1.set_title(f"{prod} — bid/ask spread", fontweight="bold")
        ax1.set_ylabel("spread")
        ax1.set_xlabel("timestamp (abs)")
        ax1.legend(fontsize=8)
        ax1.grid(alpha=0.25)
        _add_day_lines(ax1, days, day_boundaries)

    plt.tight_layout()
    out = _save_fig(fig, "round1_overview")
    print(f"[plot_round1] saved → {out}")
    plt.show()


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _shade_days(ax, days, colours, boundaries, price_df):
    """Shade alternating day bands on an axes."""
    sorted_days = sorted(days)
    x_min = price_df["abs_timestamp"].min()
    x_max = price_df["abs_timestamp"].max()

    for i, d in enumerate(sorted_days):
        x0 = boundaries[d]
        x1 = boundaries[sorted_days[i + 1]] if i + 1 < len(sorted_days) else x_max + 1
        ax.axvspan(x0, x1, color=colours[i % len(colours)], alpha=0.4, zorder=0)


def _add_day_lines(ax, days, boundaries):
    """Draw vertical lines at each day boundary."""
    for i, d in enumerate(sorted(days)):
        if i == 0:
            continue
        ax.axvline(boundaries[d], color="grey", lw=0.8, ls="--", zorder=2)


def _save_fig(fig, stem: str) -> str:
    """Save figure to logs/ (creates dir if needed), return path."""
    import matplotlib.pyplot as plt
    logs_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs"
    )
    os.makedirs(logs_dir, exist_ok=True)
    out = os.path.join(logs_dir, f"{stem}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "ROUND1"

    if os.path.isdir(target):
        # directory → full round overview
        df = load_round_prices(target)
        summarise(df)
        plot_round1(target)
    else:
        # single file → quick single-day view
        print(f"Loading {target}...")
        df = load_prices(target)
        summarise(df)
        plot_prices(df, title_suffix=f"  ({os.path.basename(target)})")
