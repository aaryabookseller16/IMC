"""
trader_v6.py — Adaptive ASH fair value + tighter passive quotes
────────────────────────────────────────────────────────────────
Local results versus trader_v5 on the bundled round 1 data:
  - Round 1 total: 292,428 vs 283,645
  - Day -1 total: 99,049 vs 96,379

Key change:
  - ASH_COATED_OSMIUM no longer anchors at a fixed 10_000 all day.
    It tracks a slow EMA of the mid while still inventory-skewing and
    using microprice to bias the quote centre.
"""

from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List
import jsonpickle
import math


LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
}


# ASH parameters
ASH_ANCHOR = 10000
ASH_EMA_ALPHA = 0.005
ASH_INV_SKEW = 0.06
ASH_INNER_EDGE = 1
ASH_OUTER_EDGE = 5
ASH_INNER_FRAC = 0.35
ASH_MICRO_W = 0.5
ASH_TAKE_PAD = 0.0

# IPR parameters
IPR_BUY_BUFFER = 5


class Trader:

    def run(self, state: TradingState):
        mem = jsonpickle.decode(state.traderData) if state.traderData else {
            "ash_ema": float(ASH_ANCHOR)
        }
        result: Dict[str, List[Order]] = {}

        for product, od in state.order_depths.items():
            if not od.sell_orders and not od.buy_orders:
                continue

            best_ask = min(od.sell_orders) if od.sell_orders else None
            best_bid = max(od.buy_orders) if od.buy_orders else None
            if best_ask is None and best_bid is None:
                continue

            pos = state.position.get(product, 0)
            limit = LIMITS.get(product, 80)
            orders: List[Order] = []

            if product == "INTARIAN_PEPPER_ROOT":
                can_buy = limit - pos

                if can_buy > 0 and best_ask is not None:
                    remaining = can_buy
                    for ask in sorted(od.sell_orders):
                        qty = min(abs(od.sell_orders[ask]), remaining)
                        orders.append(Order(product, ask, qty))
                        remaining -= qty
                        if remaining == 0:
                            break

                    if remaining > 0:
                        orders.append(Order(product, best_ask + IPR_BUY_BUFFER, remaining))

                result[product] = orders
                continue

            if product != "ASH_COATED_OSMIUM":
                continue

            buy_cap = limit - pos
            sell_cap = limit + pos
            fair = float(mem.get("ash_ema", ASH_ANCHOR))
            mid = fair

            if best_bid is not None and best_ask is not None:
                mid = (best_bid + best_ask) / 2
                fair += ASH_EMA_ALPHA * (mid - fair)
                mem["ash_ema"] = fair

            # Take only when the visible book is clearly better than our EMA fair.
            if od.sell_orders and buy_cap > 0:
                for ask in sorted(od.sell_orders):
                    if ask >= fair + ASH_TAKE_PAD:
                        break
                    qty = min(abs(od.sell_orders[ask]), buy_cap)
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    if buy_cap == 0:
                        break

            if od.buy_orders and sell_cap > 0:
                for bid in sorted(od.buy_orders, reverse=True):
                    if bid <= fair - ASH_TAKE_PAD:
                        break
                    qty = min(od.buy_orders[bid], sell_cap)
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    if sell_cap == 0:
                        break

            orig_pos = state.position.get(product, 0)
            est_pos = orig_pos + (limit - orig_pos - buy_cap) - (limit + orig_pos - sell_cap)
            centre = fair - est_pos * ASH_INV_SKEW

            if best_bid is not None and best_ask is not None:
                bid_vol = od.buy_orders[best_bid]
                ask_vol = abs(od.sell_orders[best_ask])
                if bid_vol + ask_vol > 0:
                    micro = (best_ask * bid_vol + best_bid * ask_vol) / (bid_vol + ask_vol)
                    centre += ASH_MICRO_W * (micro - mid)

            inner_buy = min(buy_cap, int(round(buy_cap * ASH_INNER_FRAC)))
            inner_sell = min(sell_cap, int(round(sell_cap * ASH_INNER_FRAC)))
            outer_buy = buy_cap - inner_buy
            outer_sell = sell_cap - inner_sell

            if inner_buy > 0:
                inner_bid = int(math.floor(centre)) - ASH_INNER_EDGE
                if best_bid is not None:
                    inner_bid = min(best_bid + 1, inner_bid)
                orders.append(Order(product, inner_bid, inner_buy))

            if inner_sell > 0:
                inner_ask = int(math.ceil(centre)) + ASH_INNER_EDGE
                if best_ask is not None:
                    inner_ask = max(best_ask - 1, inner_ask)
                orders.append(Order(product, inner_ask, -inner_sell))

            if outer_buy > 0:
                outer_bid = int(math.floor(centre)) - ASH_OUTER_EDGE
                orders.append(Order(product, outer_bid, outer_buy))

            if outer_sell > 0:
                outer_ask = int(math.ceil(centre)) + ASH_OUTER_EDGE
                orders.append(Order(product, outer_ask, -outer_sell))

            result[product] = orders

        return result, 0, jsonpickle.encode(mem)
