"""
trader_v3.py — Strategy C: Tiered MM
──────────────────────────────────────
- Exact FV for both products
- TIERED passive market making: multiple bid/ask levels
  • Tight inner tier (spread=2): catches high-frequency fills
  • Wide outer tier (spread=5): catches big price swings, high profit per unit
- Stronger inventory skewing
- Separate skew for each tier (outer tier skews more aggressively)
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import math

LIMITS = {
    "ASH_COATED_OSMIUM":     80,
    "INTARIAN_PEPPER_ROOT":  80,
}

IPR_SLOPE     = 0.001
IPR_TAKE_EDGE = 1
IPR_INV_SKEW  = 0.12

ASH_FV        = 10000
ASH_TAKE_EDGE = 0
ASH_INV_SKEW  = 0.12

# Tiers: (half_spread, fraction_of_remaining_budget)
# Fractions must sum to ≤ 1.0. Remaining goes to the widest tier.
TIERS = [
    (2, 0.25),   # inner tier: 25% of capacity at spread ±2
    (5, 0.75),   # outer tier: 75% of capacity at spread ±5
]


class Trader:

    def run(self, state: TradingState):
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}
        result: Dict[str, List[Order]] = {}

        for product, od in state.order_depths.items():
            if not od.sell_orders and not od.buy_orders:
                continue

            best_ask = min(od.sell_orders) if od.sell_orders else None
            best_bid = max(od.buy_orders)  if od.buy_orders  else None
            if best_ask is None or best_bid is None:
                continue
            mid = (best_ask + best_bid) / 2.0

            if product == "ASH_COATED_OSMIUM":
                fv        = float(ASH_FV)
                take_edge = ASH_TAKE_EDGE
                inv_skew  = ASH_INV_SKEW
            elif product == "INTARIAN_PEPPER_ROOT":
                if "ipr_base" not in mem:
                    rough = mid - state.timestamp * IPR_SLOPE
                    mem["ipr_base"] = round(rough / 1000) * 1000
                fv        = mem["ipr_base"] + state.timestamp * IPR_SLOPE
                take_edge = IPR_TAKE_EDGE
                inv_skew  = IPR_INV_SKEW
            else:
                continue

            pos      = state.position.get(product, 0)
            limit    = LIMITS.get(product, 80)
            buy_cap  = limit - pos
            sell_cap = limit + pos
            orders: List[Order] = []

            # ── Aggressive arb ────────────────────────────────────────────
            if od.sell_orders and buy_cap > 0:
                for ask in sorted(od.sell_orders):
                    if ask >= fv - take_edge:
                        break
                    qty = min(abs(od.sell_orders[ask]), buy_cap)
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    if buy_cap == 0:
                        break

            if od.buy_orders and sell_cap > 0:
                for bid in sorted(od.buy_orders, reverse=True):
                    if bid <= fv + take_edge:
                        break
                    qty = min(od.buy_orders[bid], sell_cap)
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    if sell_cap == 0:
                        break

            # ── Inventory skew ────────────────────────────────────────────
            est_pos  = pos + (limit - pos - buy_cap) - (limit + pos - sell_cap)
            skew     = -est_pos * inv_skew
            centre   = fv + skew

            # ── Tiered passive MM ─────────────────────────────────────────
            total_buy  = buy_cap
            total_sell = sell_cap

            for i, (spread, frac) in enumerate(TIERS):
                is_last = (i == len(TIERS) - 1)

                if is_last:
                    tier_buy  = buy_cap
                    tier_sell = sell_cap
                else:
                    tier_buy  = max(1, int(round(total_buy  * frac)))
                    tier_sell = max(1, int(round(total_sell * frac)))
                    tier_buy  = min(tier_buy,  buy_cap)
                    tier_sell = min(tier_sell, sell_cap)

                mm_bid = int(math.floor(centre)) - spread
                mm_ask = int(math.ceil(centre))  + spread

                if tier_buy > 0:
                    orders.append(Order(product, mm_bid,  tier_buy))
                    buy_cap  -= tier_buy
                if tier_sell > 0:
                    orders.append(Order(product, mm_ask, -tier_sell))
                    sell_cap -= tier_sell

            result[product] = orders

        return result, 0, jsonpickle.encode(mem)
