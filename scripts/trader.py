from scripts.datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import statistics

# =============================================================================
#  KNOWN ROUND 1 PRODUCTS & POSITION LIMITS
#  (check the Rounds section of the wiki to confirm / update each round)
# =============================================================================
LIMITS: Dict[str, int] = {
    "RAINFOREST_RESIN":      50,
    "KELP":                  50,
    "SQUID_INK":             50,
    # add new products here each round
}

# =============================================================================
#  KNOWN FAIR VALUES
#  Stable products have a fixed fair value you find by analysing the sample CSV.
#  Dynamic products (KELP, SQUID_INK) don't have one — use rolling mid instead.
# =============================================================================
STATIC_FAIR_VALUES: Dict[str, float] = {
    "RAINFOREST_RESIN": 10000,   # historically stable — confirm from sample data
}


class Trader:

    def run(self, state: TradingState):
        # ── 1. RESTORE PERSISTENT STATE ──────────────────────────────────────
        if state.traderData:
            mem = jsonpickle.decode(state.traderData)
        else:
            mem = {
                "iteration": 0,
                "price_history": {},   # product → list[float]  (last 50 mids)
            }

        mem["iteration"] += 1

        # ── 2. DEBUG LOG (shows up in the log file after uploading) ───────────
        print(f"\n=== iter {mem['iteration']} | t={state.timestamp} ===")
        for prod, pos in state.position.items():
            print(f"  pos {prod}: {pos}")

        # ── 3. TRADE LOGIC ────────────────────────────────────────────────────
        result: Dict[str, List[Order]] = {}

        for product, depth in state.order_depths.items():

            if not depth.sell_orders or not depth.buy_orders:
                continue   # one-sided book — skip

            # ── Market prices ─────────────────────────────────────────────────
            best_ask = min(depth.sell_orders)
            best_bid = max(depth.buy_orders)
            mid      = (best_ask + best_bid) / 2

            # ── Price history (for rolling fair value) ────────────────────────
            hist = mem["price_history"].setdefault(product, [])
            hist.append(mid)
            if len(hist) > 50:
                hist.pop(0)

            # ── Fair value ────────────────────────────────────────────────────
            if product in STATIC_FAIR_VALUES:
                fv = STATIC_FAIR_VALUES[product]
            elif len(hist) >= 10:
                fv = statistics.mean(hist[-20:])
            else:
                fv = mid   # not enough history yet

            # ── Position headroom ─────────────────────────────────────────────
            pos    = state.position.get(product, 0)
            limit  = LIMITS.get(product, 20)
            can_buy  = limit - pos
            can_sell = limit + pos

            print(f"  {product}: bid={best_bid} ask={best_ask} fv={fv:.1f} pos={pos}")

            orders: List[Order] = []

            # ── STRATEGY A: take mispriced orders immediately ─────────────────
            #   Buy from bots who are selling BELOW fair value
            if can_buy > 0:
                for ask in sorted(depth.sell_orders):
                    if ask >= fv:
                        break
                    qty = min(abs(depth.sell_orders[ask]), can_buy)
                    orders.append(Order(product, ask, qty))
                    can_buy -= qty
                    if can_buy == 0:
                        break

            #   Sell to bots who are buying ABOVE fair value
            if can_sell > 0:
                for bid in sorted(depth.buy_orders, reverse=True):
                    if bid <= fv:
                        break
                    qty = min(depth.buy_orders[bid], can_sell)
                    orders.append(Order(product, bid, -qty))
                    can_sell -= qty
                    if can_sell == 0:
                        break

            # ── STRATEGY B: passive market-making quotes ──────────────────────
            #   Post resting orders around fair value to earn the spread.
            #   Tune SPREAD up if you're getting filled too aggressively,
            #   down if you're not getting filled at all.
            SPREAD     = 2
            MM_SIZE    = 5
            mm_bid     = round(fv) - SPREAD
            mm_ask     = round(fv) + SPREAD

            if can_buy >= MM_SIZE:
                orders.append(Order(product, mm_bid,  MM_SIZE))
            if can_sell >= MM_SIZE:
                orders.append(Order(product, mm_ask, -MM_SIZE))

            result[product] = orders

        # ── 4. RETURN ─────────────────────────────────────────────────────────
        trader_data_str = jsonpickle.encode(mem)
        return result, 0, trader_data_str


# =============================================================================
#  LOCAL TEST — simulates two iterations so you can run  python trader.py
#  and see what orders your bot would place without uploading anything.
# =============================================================================
if __name__ == "__main__":
    from scripts.datamodel import OrderDepth, TradingState, Trade

    def make_state(trader_data="", position=None, timestamp=0):
        """Build a fake TradingState for local testing."""
        if position is None:
            position = {}

        resin = OrderDepth()
        resin.sell_orders = {10002: -4, 10003: -2}
        resin.buy_orders  = {9998: 3, 9997: 5}

        kelp = OrderDepth()
        kelp.sell_orders = {1523: -3, 1524: -2}
        kelp.buy_orders  = {1519: 4, 1518: 6}

        return TradingState(
            traderData   = trader_data,
            timestamp    = timestamp,
            listings     = {},
            order_depths = {
                "RAINFOREST_RESIN": resin,
                "KELP":             kelp,
            },
            own_trades   = {},
            market_trades= {},
            position     = position,
            observations = None,
        )

    trader = Trader()

    print("=" * 55)
    print("  ITERATION 1 — no position, no history")
    print("=" * 55)
    state1 = make_state(timestamp=0, position={})
    orders1, _, saved1 = trader.run(state1)
    print("\n-- ORDERS --")
    for prod, ol in orders1.items():
        for o in ol:
            side = "BUY " if o.quantity > 0 else "SELL"
            print(f"  {side} {abs(o.quantity):>3}x  {prod}  @ {o.price}")

    print("\n" + "=" * 55)
    print("  ITERATION 2 — resin position = +7, state carried over")
    print("=" * 55)
    state2 = make_state(
        trader_data = saved1,
        timestamp   = 100,
        position    = {"RAINFOREST_RESIN": 7, "KELP": -3},
    )
    orders2, _, saved2 = trader.run(state2)
    print("\n-- ORDERS --")
    for prod, ol in orders2.items():
        for o in ol:
            side = "BUY " if o.quantity > 0 else "SELL"
            print(f"  {side} {abs(o.quantity):>3}x  {prod}  @ {o.price}")
