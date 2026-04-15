"""
trader_v4.py — Strategy D: Trend-ride + ASH MM
────────────────────────────────────────────────
KEY INSIGHT:
  INTARIAN_PEPPER_ROOT rises exactly +1000 per day (slope 0.001/ts).
  Holding +80 units for a full day earns ~79,200 from the trend alone
  (buy at ~10010, price rises to ~11000, profit ≈ 80 × 990 per day).

  ASH_COATED_OSMIUM is stationary at FV=10000 — pure market making.
  Optimal passive MM spread is ±5 (maximises fill_rate × profit_per_unit
  from empirical trade distribution: 498 trades at ≤9995, 503 at ≥10005).
  Aggressive arb (ask<10000 or bid>10000) + passive MM share the budget.
  Inventory skew shifts quotes toward mean-reversion when position builds.

Strategy:
  IPR  → build max long position ASAP, hold, never voluntarily sell
  ASH  → aggressive arb (take_edge=0) + passive MM at FV±5, skew=0.08
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
ASH_TAKE_EDGE = 0       # buy all asks < 10000, sell all bids > 10000
ASH_MM_SPREAD = 7       # ±7 maximises fill_rate × profit_per_unit empirically
ASH_INV_SKEW  = 0.08    # shift centre by 0.08 per unit held (speeds turnover)

# IPR: buy-and-hold via aggressive cross of the spread
# We post a buy at ASK + buffer so we always fill quickly from book + market trades
IPR_BUY_BUFFER = 5      # how far above best ask we're willing to bid


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

            pos    = state.position.get(product, 0)
            limit  = LIMITS.get(product, 80)
            orders: List[Order] = []

            # ══════════════════════════════════════════════════════════════
            #  INTARIAN_PEPPER_ROOT — buy & hold the trend
            # ══════════════════════════════════════════════════════════════
            if product == "INTARIAN_PEPPER_ROOT":
                can_buy = limit - pos

                if can_buy > 0 and best_ask is not None:
                    # Sweep all available ask levels (aggressive cross)
                    remaining = can_buy
                    for ask in sorted(od.sell_orders):
                        qty = min(abs(od.sell_orders[ask]), remaining)
                        orders.append(Order(product, ask, qty))
                        remaining -= qty
                        if remaining == 0:
                            break

                    # Post a passive bid above the current best ask so we
                    # fill against market trades as well (fills at our price)
                    if remaining > 0:
                        passive_bid = best_ask + IPR_BUY_BUFFER
                        orders.append(Order(product, passive_bid, remaining))

                # Never sell IPR — the trend does the work (MTM captures it)
                result[product] = orders
                continue

            # ══════════════════════════════════════════════════════════════
            #  ASH_COATED_OSMIUM — aggressive arb + passive MM
            # ══════════════════════════════════════════════════════════════
            if product != "ASH_COATED_OSMIUM":
                continue  # skip unknown products

            fv        = float(ASH_FV)
            buy_cap   = limit - pos
            sell_cap  = limit + pos

            # Aggressive arb: take all asks below FV
            if od.sell_orders and buy_cap > 0:
                for ask in sorted(od.sell_orders):
                    if ask >= fv - ASH_TAKE_EDGE:
                        break
                    qty = min(abs(od.sell_orders[ask]), buy_cap)
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    if buy_cap == 0:
                        break

            # Aggressive arb: take all bids above FV
            if od.buy_orders and sell_cap > 0:
                for bid in sorted(od.buy_orders, reverse=True):
                    if bid <= fv + ASH_TAKE_EDGE:
                        break
                    qty = min(od.buy_orders[bid], sell_cap)
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    if sell_cap == 0:
                        break

            # Passive MM — full remaining budget with inventory skew
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
