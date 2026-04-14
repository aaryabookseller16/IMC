"""
IMC Prosperity 4 — Round 1 Trading Algorithm
Products: ASH_COATED_OSMIUM (position limit 80)
          INTARIAN_PEPPER_ROOT (position limit 80)
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Tuple
import jsonpickle
import math

# ── Position limits ──────────────────────────────────────────────────────────
LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
}

# ── Tunable parameters ──────────────────────────────────────────────────────

# Pepper Root (linear trend: fair = start + 0.001 * t)
PEPPER_SLOPE = 0.001
PEPPER_EMA_ALPHA = 0.4
PEPPER_TAKE_EDGE = 1
PEPPER_MM_HALF_SPREAD = 2
PEPPER_INV_SKEW = 0.15

# Osmium (mean-revert around ~10000, slow wave)
OSMIUM_ANCHOR = 10000
OSMIUM_EMA_ALPHA = 0.005
OSMIUM_TAKE_EDGE = 0
OSMIUM_MM_HALF_SPREAD = 2
OSMIUM_INV_SKEW = 0.08


class Trader:

    def __init__(self) -> None:
        self.pepper_fair = None
        self.pepper_last_ts = None
        self.osmium_ema = float(OSMIUM_ANCHOR)

    def bid(self):
        """Placeholder for Round 2 auction. Ignored in other rounds."""
        return 0

    # ─────────────────────────────────────────────────────────────────────
    #  MAIN ENTRY
    # ─────────────────────────────────────────────────────────────────────
    def run(self, state: TradingState):
        result = {}

        # Restore persisted state
        if state.traderData:
            try:
                saved = jsonpickle.decode(state.traderData)
                self.pepper_fair = saved.get("pf")
                self.pepper_last_ts = saved.get("pt")
                self.osmium_ema = saved.get("oe", float(OSMIUM_ANCHOR))
            except Exception:
                pass

        for product in state.order_depths:
            if product == "INTARIAN_PEPPER_ROOT":
                result[product] = self._trade_pepper(state, product)
            elif product == "ASH_COATED_OSMIUM":
                result[product] = self._trade_osmium(state, product)
            else:
                result[product] = []

        trader_data = jsonpickle.encode({
            "pf": self.pepper_fair,
            "pt": self.pepper_last_ts,
            "oe": self.osmium_ema,
        })
        conversions = 0
        return result, conversions, trader_data

    # ─────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def _mid(od: OrderDepth):
        bb = max(od.buy_orders) if od.buy_orders else None
        ba = min(od.sell_orders) if od.sell_orders else None
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        return bb if bb is not None else ba

    # ─────────────────────────────────────────────────────────────────────
    #  INTARIAN_PEPPER_ROOT — Linear trend + market making
    # ─────────────────────────────────────────────────────────────────────
    def _trade_pepper(self, state: TradingState, product: str) -> List[Order]:
        orders = []
        od = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = LIMITS[product]
        ts = state.timestamp

        mid = self._mid(od)
        if mid is None:
            return orders

        # Update linear fair-value estimate
        if self.pepper_fair is None or self.pepper_last_ts is None:
            self.pepper_fair = mid
            self.pepper_last_ts = ts
        else:
            dt = ts - self.pepper_last_ts
            self.pepper_fair += PEPPER_SLOPE * dt
            self.pepper_last_ts = ts
            self.pepper_fair += PEPPER_EMA_ALPHA * (mid - self.pepper_fair)

        fair = self.pepper_fair

        # ── Budget: track buy/sell capacity independently ────────────────
        # Exchange rejects ALL orders if aggregate buy (or sell) exceeds limit
        max_buy = limit - position      # total units we can buy
        max_sell = limit + position     # total units we can sell
        buy_budget = max_buy
        sell_budget = max_sell

        # ── Phase 1: Take mispriced asks ─────────────────────────────────
        if od.sell_orders:
            for ask_px in sorted(od.sell_orders.keys()):
                if ask_px < fair - PEPPER_TAKE_EDGE and buy_budget > 0:
                    vol = -od.sell_orders[ask_px]    # sell_orders values are negative
                    qty = min(vol, buy_budget)
                    if qty > 0:
                        orders.append(Order(product, ask_px, qty))
                        buy_budget -= qty
                else:
                    break

        # ── Phase 1: Take mispriced bids ─────────────────────────────────
        if od.buy_orders:
            for bid_px in sorted(od.buy_orders.keys(), reverse=True):
                if bid_px > fair + PEPPER_TAKE_EDGE and sell_budget > 0:
                    vol = od.buy_orders[bid_px]
                    qty = min(vol, sell_budget)
                    if qty > 0:
                        orders.append(Order(product, bid_px, -qty))
                        sell_budget -= qty
                else:
                    break

        # ── Phase 2: Market-make with remaining budget ───────────────────
        # Estimate where position will end up after takes fill
        est_pos = position + (max_buy - buy_budget) - (max_sell - sell_budget)
        skew = -est_pos * PEPPER_INV_SKEW
        adj_fair = fair + skew

        buy_px = int(math.floor(adj_fair)) - PEPPER_MM_HALF_SPREAD
        sell_px = int(math.ceil(adj_fair)) + PEPPER_MM_HALF_SPREAD

        if buy_budget > 0:
            orders.append(Order(product, buy_px, buy_budget))
        if sell_budget > 0:
            orders.append(Order(product, sell_px, -sell_budget))

        return orders

    # ─────────────────────────────────────────────────────────────────────
    #  ASH_COATED_OSMIUM — Slow-wave EMA + aggressive market making
    # ─────────────────────────────────────────────────────────────────────
    def _trade_osmium(self, state: TradingState, product: str) -> List[Order]:
        orders = []
        od = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = LIMITS[product]

        mid = self._mid(od)
        if mid is None:
            return orders

        # Track slow-moving wave with EMA
        self.osmium_ema += OSMIUM_EMA_ALPHA * (mid - self.osmium_ema)
        fair = self.osmium_ema

        # ── Budget: track buy/sell capacity independently ────────────────
        max_buy = limit - position
        max_sell = limit + position
        buy_budget = max_buy
        sell_budget = max_sell

        # ── Phase 1: Take mispriced asks (below fair) ────────────────────
        if od.sell_orders:
            for ask_px in sorted(od.sell_orders.keys()):
                if ask_px < fair - OSMIUM_TAKE_EDGE and buy_budget > 0:
                    vol = -od.sell_orders[ask_px]
                    qty = min(vol, buy_budget)
                    if qty > 0:
                        orders.append(Order(product, ask_px, qty))
                        buy_budget -= qty
                elif ask_px <= fair and position < 0 and buy_budget > 0:
                    # At/near fair: buy to flatten a short
                    vol = -od.sell_orders[ask_px]
                    qty = min(vol, min(-position, buy_budget))
                    if qty > 0:
                        orders.append(Order(product, ask_px, qty))
                        buy_budget -= qty
                else:
                    break

        # ── Phase 1: Take mispriced bids (above fair) ────────────────────
        if od.buy_orders:
            for bid_px in sorted(od.buy_orders.keys(), reverse=True):
                if bid_px > fair + OSMIUM_TAKE_EDGE and sell_budget > 0:
                    vol = od.buy_orders[bid_px]
                    qty = min(vol, sell_budget)
                    if qty > 0:
                        orders.append(Order(product, bid_px, -qty))
                        sell_budget -= qty
                elif bid_px >= fair and position > 0 and sell_budget > 0:
                    # At/near fair: sell to flatten a long
                    vol = od.buy_orders[bid_px]
                    qty = min(vol, min(position, sell_budget))
                    if qty > 0:
                        orders.append(Order(product, bid_px, -qty))
                        sell_budget -= qty
                else:
                    break

        # ── Phase 2: Market-make with remaining budget ───────────────────
        est_pos = position + (max_buy - buy_budget) - (max_sell - sell_budget)
        skew = -est_pos * OSMIUM_INV_SKEW
        adj_fair = fair + skew

        buy_px = int(math.floor(adj_fair)) - OSMIUM_MM_HALF_SPREAD
        sell_px = int(math.ceil(adj_fair)) + OSMIUM_MM_HALF_SPREAD

        # Keep quotes from drifting too far from the anchor
        buy_px = min(buy_px, OSMIUM_ANCHOR - 1)
        sell_px = max(sell_px, OSMIUM_ANCHOR + 1)

        if buy_budget > 0:
            orders.append(Order(product, buy_px, buy_budget))
        if sell_budget > 0:
            orders.append(Order(product, sell_px, -sell_budget))

        return orders
