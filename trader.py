"""
IMC Prosperity 4 — Round 1 Submission
──────────────────────────────────────
INTARIAN_PEPPER_ROOT:
  Price rises exactly +1000/day (slope 0.001/timestamp).
  Buy max position (80) immediately, hold all day.
  Profit ≈ 80 × 990 ≈ 79,200 per day from trend alone.

ASH_COATED_OSMIUM:
  Stationary at FV=10000.
  Aggressive arb (take all asks<10000 / bids>10000) +
  passive MM at FV±7 with inventory skew.
  Spread=7 maximises fill_rate × profit_per_unit empirically.

Backtested: 267,585 total over 3 days (target: 200,000).
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import math

LIMITS = {
    "ASH_COATED_OSMIUM":     80,
    "INTARIAN_PEPPER_ROOT":  80,
}

# ASH parameters
ASH_FV        = 10000
ASH_TAKE_EDGE = 0      # take all asks < 10000, sell all bids > 10000
ASH_MM_SPREAD = 7      # ±7 optimal from trade distribution analysis
ASH_INV_SKEW  = 0.08   # shift centre by 0.08 per unit held (speeds turnover)

# IPR: bid above best ask so we fill from both book and market trades
IPR_BUY_BUFFER = 5     # bid this many ticks above best ask


class Trader:

    def run(self, state: TradingState):
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}
        result: Dict[str, List[Order]] = {}

        for product, od in state.order_depths.items():
            if not od.sell_orders and not od.buy_orders:
                continue

            best_ask = min(od.sell_orders) if od.sell_orders else None
            best_bid = max(od.buy_orders)  if od.buy_orders  else None
            if best_ask is None and best_bid is None:
                continue

            pos   = state.position.get(product, 0)
            limit = LIMITS.get(product, 80)
            orders: List[Order] = []

            # ── INTARIAN_PEPPER_ROOT: buy & hold the trend ─────────────────
            if product == "INTARIAN_PEPPER_ROOT":
                can_buy = limit - pos

                if can_buy > 0 and best_ask is not None:
                    # Sweep all ask levels aggressively
                    remaining = can_buy
                    for ask in sorted(od.sell_orders):
                        qty = min(abs(od.sell_orders[ask]), remaining)
                        orders.append(Order(product, ask, qty))
                        remaining -= qty
                        if remaining == 0:
                            break

                    # Passive bid above best ask to also catch market trades
                    if remaining > 0:
                        orders.append(Order(product, best_ask + IPR_BUY_BUFFER, remaining))

                # Never sell — MTM accounting captures the full trend gain
                result[product] = orders
                continue

            # ── ASH_COATED_OSMIUM: aggressive arb + passive MM ─────────────
            if product != "ASH_COATED_OSMIUM":
                continue

            fv       = float(ASH_FV)
            buy_cap  = limit - pos
            sell_cap = limit + pos

            # Aggressive: take all asks strictly below FV
            if od.sell_orders and buy_cap > 0:
                for ask in sorted(od.sell_orders):
                    if ask >= fv - ASH_TAKE_EDGE:
                        break
                    qty = min(abs(od.sell_orders[ask]), buy_cap)
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    if buy_cap == 0:
                        break

            # Aggressive: take all bids strictly above FV
            if od.buy_orders and sell_cap > 0:
                for bid in sorted(od.buy_orders, reverse=True):
                    if bid <= fv + ASH_TAKE_EDGE:
                        break
                    qty = min(od.buy_orders[bid], sell_cap)
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    if sell_cap == 0:
                        break

            # Passive MM — full remaining budget, skewed toward inventory reversal
            est_pos = pos + (limit - pos - buy_cap) - (limit + pos - sell_cap)
            skew    = -est_pos * ASH_INV_SKEW
            centre  = fv + skew

            mm_bid = int(math.floor(centre)) - ASH_MM_SPREAD
            mm_ask = int(math.ceil(centre))  + ASH_MM_SPREAD

            if buy_cap > 0:
                orders.append(Order(product, mm_bid,  buy_cap))
            if sell_cap > 0:
                orders.append(Order(product, mm_ask, -sell_cap))

            result[product] = orders

        return result, 0, jsonpickle.encode(mem)
