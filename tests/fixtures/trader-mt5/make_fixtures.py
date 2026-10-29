"""Build the offline MetaTrader 5 fixtures: a demo server at GMT+3.

The numbers are synthetic but shaped like a real broker's: EURUSD, XAUUSD and
US500 with their own digits, tick values, lot ladders, stops levels, swaps and
filling modes, a 1:100 USD account, two sessions of 5-minute bars and two
closed trades.  Run it from this folder to regenerate:

    python3 make_fixtures.py

Nothing here is a prediction or a real quote.  The point is that every number
in the tests is repeatable on any machine, offline.
"""
import datetime
import json
import math
import random

OFFSET = 3.0                                   # server clock: GMT+3
UTC = datetime.timezone.utc


def epoch(y, m, d, hh=0, mm=0):
    return int(datetime.datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp())


def server_stamp(y, m, d, hh=0, mm=0):
    """MT5 hands out epoch seconds on the server clock, not UTC."""
    return epoch(y, m, d, hh, mm) + int(OFFSET * 3600)


def iso(z):
    return z.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_iso(y, m, d, hh, mm):
    return iso(datetime.datetime(y, m, d, hh, mm, tzinfo=UTC))


SYMBOLS = {
    "EURUSD": {
        "symbol": "EURUSD", "digits": 5, "point": 0.00001, "spread": 12,
        "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
        "trade_tick_size": 0.00001, "trade_tick_value": 1.0, "trade_contract_size": 100000.0,
        "trade_stops_level": 0, "trade_freeze_level": 0,
        "swap_long": -6.2, "swap_short": 1.1, "swap_mode": "points",
        "currency_base": "EUR", "currency_profit": "USD", "currency_margin": "EUR",
        "trade_mode": "full", "margin_initial": 0.0, "margin_rate": 0.0, "leverage_ratio": 100.0,
        "filling_modes": ["fok", "ioc", "return"], "sessions": [],
        "description": "Euro vs US Dollar", "path": "Forex\\Majors", "visible": True,
    },
    "XAUUSD": {
        "symbol": "XAUUSD", "digits": 2, "point": 0.01, "spread": 32,
        "volume_min": 0.01, "volume_max": 50.0, "volume_step": 0.01,
        "trade_tick_size": 0.01, "trade_tick_value": 1.0, "trade_contract_size": 100.0,
        "trade_stops_level": 50, "trade_freeze_level": 0,
        "swap_long": -35.4, "swap_short": 12.1, "swap_mode": "points",
        "currency_base": "XAU", "currency_profit": "USD", "currency_margin": "USD",
        "trade_mode": "full", "margin_initial": 0.0, "margin_rate": 1.0, "leverage_ratio": 100.0,
        "filling_modes": ["fok", "ioc", "return"], "sessions": [],
        "description": "Gold vs US Dollar", "path": "Metals", "visible": True,
    },
    "US500": {
        "symbol": "US500", "digits": 1, "point": 0.1, "spread": 20,
        "volume_min": 0.1, "volume_max": 50.0, "volume_step": 0.1,
        "trade_tick_size": 0.1, "trade_tick_value": 0.1, "trade_contract_size": 1.0,
        "trade_stops_level": 100, "trade_freeze_level": 20,
        "swap_long": -12.0, "swap_short": 2.0, "swap_mode": "points",
        "currency_base": "USD", "currency_profit": "USD", "currency_margin": "USD",
        "trade_mode": "full", "margin_initial": 0.0, "margin_rate": 0.5, "leverage_ratio": 200.0,
        "filling_modes": ["ioc", "return"], "sessions": [],
        "description": "S&P 500 index", "path": "Indices", "visible": True,
    },
}

QUOTES = {
    "EURUSD": {"bid": 1.08592, "ask": 1.08604, "time": utc_iso(2026, 10, 20, 13, 34),
               "spread_points": 12},
    "XAUUSD": {"bid": 2412.30, "ask": 2412.62, "time": utc_iso(2026, 10, 20, 13, 34),
               "spread_points": 32},
    "US500": {"bid": 5842.10, "ask": 5842.60, "time": utc_iso(2026, 10, 20, 13, 33),
              "spread_points": 5},
}

TERMINAL = {
    "connected": True, "trade_allowed": True, "tradeapi_disabled": False, "dlls_allowed": False,
    "build": 4620, "name": "MetaTrader 5", "company": "MetaQuotes Software Corp.",
    "path": "C:/Program Files/MetaTrader 5/terminal64.exe",
    "data_path": "C:/Users/trader/AppData/Roaming/MetaQuotes/Terminal/ABC123",
    "language": "English", "ping_last": 42,
}

ACCOUNT = {
    "login": 5001234, "name": "Demo Trader", "server": "Broker-Demo", "company": "Broker Ltd",
    "currency": "USD", "currency_digits": 2, "trade_mode": "demo", "leverage": 100,
    "balance": 5000.0, "equity": 5012.40, "profit": 12.40, "credit": 0.0,
    "margin": 0.0, "margin_free": 5012.40, "margin_level": 0.0,
    "margin_so_call": 100.0, "margin_so_so": 50.0,
    "trade_allowed": True, "trade_expert": True, "margin_mode": "hedging",
    "limit_orders": 0, "margin_initial": 0.0, "margin_maintenance": 0.0,
}


def bar(t, o, c, spread=0.00012, volume=None):
    hi = max(o, c) + abs(c - o) * 0.4 + 0.00002
    lo = min(o, c) - abs(c - o) * 0.4 - 0.00002
    return {"t": t, "o": round(o, 5), "h": round(hi, 5), "l": round(lo, 5), "c": round(c, 5),
            "v": volume if volume is not None else 140 + int(abs(c - o) * 200000) % 90,
            "spread": int(round(spread / 0.00001))}


def eurusd_bars():
    """Monday's chop around 1.0845, then Tuesday's slow climb to 1.0860.

    Tuesday opens at 03:00 New York (07:00 UTC) at 1.08500 and closes the
    fixture window at 09:30 New York near 1.08598, so the opening range is
    under the last price and the setup is a long breakout.
    """
    rnd = random.Random(20261020)
    bars = []
    price = 1.08480
    for i in range(288):
        pull = (1.08480 - price) * 0.05
        price = round(price + pull + rnd.gauss(0, 0.00009), 5)
        price = min(1.08620, max(1.08350, price))
        bars.append(bar(server_stamp(2026, 10, 19, 0, 0) + i * 300, bars[-1]["c"] if bars else 1.08480,
                        price))
    # Tuesday: a quiet pre-open, then a steady climb from 03:00 New York
    open_t = server_stamp(2026, 10, 20, 0, 0)
    open_price = price
    n = 162                                        # 00:00 to 13:30 UTC, 5 minutes each
    for i in range(n):
        utc_minutes = i * 5
        if utc_minutes < 7 * 60:                   # before 03:00 New York
            pull = (1.08490 - price) * 0.08
            nxt = price + pull + rnd.gauss(0, 0.00004)
        else:
            if utc_minutes == 7 * 60:
                open_price = price
            progress = (utc_minutes - 7 * 60) / float(n * 5 - 7 * 60)
            nxt = open_price + 0.00100 * progress + rnd.gauss(0, 0.00003)
        nxt = round(nxt, 5)
        bars.append(bar(open_t + i * 300, price, nxt))
        price = nxt
    return bars


def aggregate(bars, minutes):
    out, bucket = [], {}
    step = int(minutes) * 60
    for b in bars:
        key = b["t"] // step
        cur = bucket.get(key)
        if cur is None:
            bucket[key] = {"t": key * 3600, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                           "v": b["v"], "spread": b["spread"]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["v"] += b["v"]
    for key in sorted(bucket):
        out.append(bucket[key])
    return out


def deals():
    return [
        {"ticket": 7001, "position_id": 9001, "symbol": "EURUSD", "type": "buy", "entry": "in",
         "volume": 0.20, "price": 1.08500, "profit": 0.0, "commission": -0.70, "swap": 0.0,
         "fee": 0.0, "order": 6001, "time_utc": utc_iso(2026, 10, 20, 6, 10),
         "time": server_stamp(2026, 10, 20, 9, 10), "comment": "orb", "magic": 20261019},
        {"ticket": 7002, "position_id": 9001, "symbol": "EURUSD", "type": "sell", "entry": "out",
         "volume": 0.20, "price": 1.08300, "profit": -40.0, "commission": -0.70, "swap": 0.0,
         "fee": 0.0, "order": 6002, "time_utc": utc_iso(2026, 10, 20, 7, 40),
         "time": server_stamp(2026, 10, 20, 10, 40), "comment": "sl", "magic": 20261019},
        {"ticket": 7003, "position_id": 9002, "symbol": "EURUSD", "type": "buy", "entry": "in",
         "volume": 0.10, "price": 1.08600, "profit": 0.0, "commission": -0.35, "swap": 0.0,
         "fee": 0.0, "order": 6003, "time_utc": utc_iso(2026, 10, 20, 8, 0),
         "time": server_stamp(2026, 10, 20, 11, 0), "comment": "orb", "magic": 20261019},
        {"ticket": 7004, "position_id": 9002, "symbol": "EURUSD", "type": "sell", "entry": "out",
         "volume": 0.10, "price": 1.08850, "profit": 25.0, "commission": -0.35, "swap": 0.0,
         "fee": 0.0, "order": 6004, "time_utc": utc_iso(2026, 10, 20, 9, 30),
         "time": server_stamp(2026, 10, 20, 12, 30), "comment": "tp", "magic": 20261019},
    ]


def positions():
    return [
        {"ticket": 1001, "symbol": "EURUSD", "type": "buy", "volume": 0.20,
         "price_open": 1.08500, "price_current": 1.08592, "sl": 1.08300, "tp": 1.09000,
         "profit": 18.40, "swap": -0.40, "magic": 20261019, "comment": "orb",
         "time": server_stamp(2026, 10, 20, 9, 10), "time_utc": utc_iso(2026, 10, 20, 6, 10)},
        {"ticket": 1002, "symbol": "XAUUSD", "type": "sell", "volume": 0.10,
         "price_open": 2415.00, "price_current": 2412.30, "sl": 2418.50, "tp": 2408.00,
         "profit": 27.00, "swap": 0.0, "magic": 20261019, "comment": "orb",
         "time": server_stamp(2026, 10, 20, 9, 30), "time_utc": utc_iso(2026, 10, 20, 6, 30)},
    ]


def pending():
    return [
        {"ticket": 2001, "symbol": "EURUSD", "type": "buy_limit", "volume": 0.10,
         "price_open": 1.08400, "price_current": 1.08400, "sl": 1.08150, "tp": 1.08900,
         "magic": 20261019, "comment": "limit", "state": "placed", "type_time": "gtc",
         "expiration": None, "time": server_stamp(2026, 10, 20, 8, 0),
         "time_utc": utc_iso(2026, 10, 20, 5, 0)},
    ]


def base():
    bars = eurusd_bars()
    return {
        "created_by": "make_fixtures.py", "as_of": utc_iso(2026, 10, 20, 13, 35),
        "server_offset_hours": OFFSET, "terminal": TERMINAL, "account": ACCOUNT,
        "symbols": SYMBOLS, "quotes": QUOTES,
        "rates": {"EURUSD:M5": bars, "EURUSD:M15": aggregate(bars, 15),
                  "EURUSD:H1": aggregate(bars, 60), "EURUSD:H4": aggregate(bars, 240)},
        "positions": [], "orders": [], "deals": deals(),
        "send": [],
    }


def main():
    # compact: these files carry 450 bars each, and a reviewer does not need
    # 6,000 lines of pretty-printed OHLC to see the change
    flat = base()
    with open("context.json", "w") as fh:
        json.dump(flat, fh, separators=(",", ":"), sort_keys=False)
        fh.write("\n")

    live = base()
    live["positions"] = positions()
    live["orders"] = pending()
    with open("positions.json", "w") as fh:
        json.dump(live, fh, separators=(",", ":"), sort_keys=False)
        fh.write("\n")

    print("wrote context.json (%d bars) and positions.json" % len(flat["rates"]["EURUSD:M5"]))


if __name__ == "__main__":
    main()
