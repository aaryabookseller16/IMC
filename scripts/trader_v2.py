"""
trader_v2.py — Strategy B
───────────────────────────
Same as v1 but with wider MM half-spread = 4 for both products.
Wider spread → fewer fills but more profit per fill.
Per-unit profit from passive MM: 2×spread = 8 per round trip.
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import math

LIMITS = {
    "ASH_COATED_OSMIUM":     80,
    "INTARIAN_PEPPER_ROOT":  80,
}

IPR_SLOPE        = 0.001
IPR_TAKE_EDGE    = 1
IPR_MM_SPREAD    = 4
IPR_INV_SKEW     = 0.10

ASH_FV           = 10000
ASH_TAKE_EDGE    = 0
ASH_MM_SPREAD    = 4
ASH_INV_SKEW     = 0.10


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
                mm_spread = ASH_MM_SPREAD
                inv_skew  = ASH_INV_SKEW
            elif product == "INTARIAN_PEPPER_ROOT":
                if "ipr_base" not in mem:
                    rough = mid - state.timestamp * IPR_SLOPE
                    mem["ipr_base"] = round(rough / 1000) * 1000
                fv        = mem["ipr_base"] + state.timestamp * IPR_SLOPE
                take_edge = IPR_TAKE_EDGE
                mm_spread = IPR_MM_SPREAD
                inv_skew  = IPR_INV_SKEW
            else:
                continue

            pos      = state.position.get(product, 0)
            limit    = LIMITS.get(product, 80)
            buy_cap  = limit - pos
            sell_cap = limit + pos
            orders: List[Order] = []

            # Aggressive arb
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

            # Passive MM — full remaining budget
            est_pos = pos + (limit - pos - buy_cap) - (limit + pos - sell_cap)
            skew    = -est_pos * inv_skew
            centre  = fv + skew

            mm_bid = int(math.floor(centre)) - mm_spread
            mm_ask = int(math.ceil(centre))  + mm_spread

            if buy_cap > 0:
                orders.append(Order(product, mm_bid,  buy_cap))
            if sell_cap > 0:
                orders.append(Order(product, mm_ask, -sell_cap))

            result[product] = orders

        return result, 0, jsonpickle.encode(mem)
