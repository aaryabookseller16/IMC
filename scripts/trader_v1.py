"""
trader_v1.py — Strategy A
───────────────────────────
- Exact linear FV for INTARIAN_PEPPER_ROOT (base + ts * 0.001)
- Fixed FV=10000 for ASH_COATED_OSMIUM
- Full remaining budget for passive MM (key driver)
- Inventory skewing to speed up position turnover
- MM half-spread = 2 for both products (same as vinny, but exact FV)
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import math

LIMITS = {
    "ASH_COATED_OSMIUM":     80,
    "INTARIAN_PEPPER_ROOT":  80,
}

# ── INTARIAN: exact linear trend ────────────────────────────────────────────
IPR_SLOPE        = 0.001   # price rises by 0.001 per timestamp unit
IPR_TAKE_EDGE    = 1       # buy ask when ask < FV - 1, sell bid when bid > FV + 1
IPR_MM_SPREAD    = 2       # passive MM half-spread
IPR_INV_SKEW     = 0.10   # inventory skew (centre shift per unit held)

# ── ASH: stationary at 10000 ────────────────────────────────────────────────
ASH_FV           = 10000
ASH_TAKE_EDGE    = 0       # buy any ask < 10000, sell any bid > 10000
ASH_MM_SPREAD    = 2
ASH_INV_SKEW     = 0.10


class Trader:

    def run(self, state: TradingState):
        # ── restore state ─────────────────────────────────────────────────
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

            # ── fair value ─────────────────────────────────────────────────
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
                continue  # skip unknown products

            # ── position headroom ─────────────────────────────────────────
            pos      = state.position.get(product, 0)
            limit    = LIMITS.get(product, 80)
            buy_cap  = limit - pos     # remaining buy capacity
            sell_cap = limit + pos     # remaining sell capacity

            orders: List[Order] = []

            # ── STRATEGY A: aggressive arb (take mispriced orders) ─────────
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

            # ── STRATEGY B: passive market-making with full remaining budget
            # Skew centre toward zero inventory to accelerate position turnover
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
