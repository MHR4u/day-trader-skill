#!/usr/bin/env python3
"""Lot sizing for MetaTrader 5 (trader-budget's MT5 half). Standard library
only, no network: it reads the terminal snapshot that `mt5.py snapshot` wrote,
or a saved spec and account for a dry run.

    python3 lots.py                                        # trader/plan.json + trader/mt5/context.json
    python3 lots.py --write                                # -> trader/orders.json (an MT5 order)
    python3 lots.py --at-market --write                    # fill at the quote, not at the plan's entry
    python3 lots.py --pending buy_stop --price 1.0910 --write
    python3 lots.py --symbol XAUUSD --entry 2412.50 --stop 2404.10 --target 2430.00 --risk 50
    python3 lots.py --partial --at-r 1 --pct 50            # the volume to close at 1R
    python3 lots.py --spec tests/fixtures/trader-mt5/context.json --json

How many lots. Whole steps of the symbol's volume_step, never a fraction MT5
would reject:

    lots = risk budget / (stop distance in money per lot + commission per lot)

      risk budget   the smallest of max_loss_per_trade_usd and
                    risk_pct_per_trade % of the account balance, times
                    --size-scale (default 1.0)
      stop distance the entry to the stop, in points, at the symbol's own
                    tick value (trade_tick_value), so XAUUSD, US500 and
                    USDJPY size correctly, plus the round-turn commission
      then          floor to volume_step, clamp to volume_min / volume_max
                    and max_lots_per_order, and shrink further while the
                    margin needed is over max_margin_use_pct of free margin

The entry it sizes at is the honest one: for a market buy the ASK from the
snapshot (the bid plus the spread), and never lower than the plan's entry, so
a price that ran up does not understate the risk. For a sell, the BID, and
never higher than the plan. For a pending order, the order's own price.

It refuses (and writes nothing) when:

  the stop is on the wrong side, or closer than the broker's stops level plus
  the spread, the symbol's minimum lot risks more than your budget, the
  reward:risk is under min_reward_risk, the spread is over max_spread_pips,
  the volume ladder has no step room, or the margin cap cannot be met.

Reads trader/config.json for the limits and the "mt5" block:
max_loss_per_trade_usd, risk_pct_per_trade, max_daily_loss_usd (reported),
max_lots_per_order, max_lots_per_symbol, max_margin_use_pct,
min_margin_level_pct, commission_per_lot, min_reward_risk, require_stop,
max_spread_pips, flat_by, and symbol_suffix.

The order it writes carries its own spec, quote and sizing numbers, so
trader-risk/check.py can check it offline and trader-broker/ticket.py can show
it without asking the terminal again.
"""

import argparse
import datetime
import json
import math
import os
import sys

DEFAULTS = {
    "max_loss_per_trade_usd": 50,
    "max_daily_loss_usd": 150,
    "max_trades_per_day": 3,
    "min_reward_risk": 1.0,
    "require_stop": True,
    "paper": True,
    "budget": None,
    "max_lots_per_order": 5.0,
    "max_lots_per_symbol": 5.0,
    "max_margin_use_pct": 40.0,
    "min_margin_level_pct": 300.0,
    "commission_per_lot": 0.0,
    "risk_pct_per_trade": None,
    "max_spread_pips": 2.0,
    "max_quote_age_sec": 300,
    "symbols": [],
    "magic": 20261019,
    "deviation": 20,
    "filling": "auto",
    "flat_by": "20:55",
}
PENDING = ("buy_limit", "sell_limit", "buy_stop", "sell_stop", "buy_stop_limit", "sell_stop_limit")
MAGIC = 20261019


class SizeError(Exception):
    pass


# ---------------------------------------------------------------- time

def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def eastern_offset(utc):
    y = utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def to_eastern(utc):
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=eastern_offset(utc))


def eastern_to_utc(local):
    for off in (-4, -5):
        utc = local - datetime.timedelta(hours=off)
        if eastern_offset(utc) == off:
            return utc
    return local + datetime.timedelta(hours=5)


def parse_now(text):
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = str(text).strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise SizeError("--now wants a time like \"2026-10-20 09:35\" (New York) or ...Z (UTC)")
    if dt.tzinfo is None:
        return eastern_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def parse_utc(text):
    if not text:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------- numbers

def _f(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def money(x):
    v = _f(x) or 0.0
    return ("-" if v < 0 else "") + "$" + "{:,.2f}".format(abs(v))


def num(x):
    v = _f(x)
    if v is None:
        return "?"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.8f" % v).rstrip("0").rstrip(".")


def price(x, d=5):
    v = _f(x)
    return "?" if v is None else ("%." + str(int(d)) + "f") % v


# ---------------------------------------------------------------- symbol maths

def point(spec):
    p = _f(spec.get("point"))
    if p and p > 0:
        return p
    d = spec.get("digits")
    return 10.0 ** (-int(d)) if d is not None else 0.00001


def digits(spec):
    d = spec.get("digits")
    return int(d) if d is not None else 5


def pip(spec):
    own = _f(spec.get("pip"))
    if own and own > 0:
        return own
    return point(spec) * 10.0 if digits(spec) >= 1 else point(spec)


def tick_size(spec):
    t = _f(spec.get("trade_tick_size") or spec.get("tick_size"))
    return t if t and t > 0 else point(spec)


def tick_value(spec):
    t = _f(spec.get("trade_tick_value") or spec.get("tick_value"))
    return t if t and t > 0 else None


def contract_size(spec):
    c = _f(spec.get("trade_contract_size") or spec.get("contract_size"))
    return c if c and c > 0 else 100000.0


def value_per_unit(spec):
    tv = tick_value(spec)
    return (tv / tick_size(spec)) if tv else contract_size(spec)


def distance_money(spec, distance, volume):
    d = _f(distance)
    v = _f(volume)
    if d is None or v is None:
        return None
    return abs(d) * value_per_unit(spec) * v


def volume_step(spec):
    s = _f(spec.get("volume_step"))
    return s if s and s > 0 else 0.01


def volume_min(spec):
    s = _f(spec.get("volume_min"))
    return s if s and s > 0 else 0.01


def volume_max(spec):
    s = _f(spec.get("volume_max"))
    return s if s and s > 0 else 100.0


def floor_volume(vol, spec):
    v = _f(vol)
    if v is None:
        return None
    step = volume_step(spec)
    n = math.floor(v / step + 1e-9)
    out = round(n * step, 8)
    return 0.0 if out < volume_min(spec) - 1e-12 else min(out, volume_max(spec))


def round_price(spec, p):
    v = _f(p)
    return None if v is None else round(v, digits(spec))


def spread_points(spec, bid, ask):
    if bid is None or ask is None:
        return None
    return (ask - bid) / point(spec)


def spread_pips(spec, bid, ask):
    if bid is None or ask is None:
        return None
    return (ask - bid) / pip(spec)


# ---------------------------------------------------------------- files

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise SizeError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise SizeError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def merged_config(cfg):
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (cfg or {}).items() if v is not None})
    block = cfg.get("mt5") if isinstance((cfg or {}).get("mt5"), dict) else {}
    c.update({k: v for k, v in block.items() if v is not None})
    for sub in ("session",):
        if isinstance(block.get(sub), dict):
            c[sub] = dict(block[sub])
    return c


# ---------------------------------------------------------------- inputs

def load_context(path):
    ctx = read_json(path, "MT5 snapshot (run mt5.py snapshot --write)", required=False) or {}
    if not isinstance(ctx, dict):
        raise SizeError("%s is not an MT5 snapshot" % path)
    return ctx


def resolve(a, plan, cfg, ctx):
    """Plan + snapshot + flags -> one dict with everything sizing needs."""
    symbols = {str(k).upper(): v for k, v in (ctx.get("symbols") or {}).items()}
    quotes = {str(k).upper(): v for k, v in (ctx.get("quotes") or {}).items()}
    acct = dict(ctx.get("account") or {})
    if a.account:
        extra = read_json(a.account, "account")
        if not isinstance(extra, dict):
            raise SizeError("%s is not an account" % a.account)
        acct.update(extra)
    if a.spec:
        spec_doc = read_json(a.spec, "spec")
        if not isinstance(spec_doc, dict):
            raise SizeError("%s is not a symbol spec" % a.spec)
        if "symbols" in spec_doc:
            symbols.update({str(k).upper(): v for k, v in spec_doc["symbols"].items()})
        else:
            sym = str(spec_doc.get("symbol") or a.symbol or plan.get("symbol") or "").upper()
            if not sym:
                raise SizeError("%s has no symbol" % a.spec)
            symbols[sym] = spec_doc
    # a bare --spec that is really a snapshot's account is handled above
    sym = str(a.symbol or plan.get("symbol") or "").strip().upper()
    if not sym:
        raise SizeError("no symbol: put one in the plan, or pass --symbol")
    suffix = str(cfg.get("symbol_suffix") or "")
    if suffix and sym in symbols:
        pass
    if sym not in symbols and (sym + suffix) in symbols:
        sym = sym + suffix
    spec = symbols.get(sym)
    if not spec:
        raise SizeError("%s is not in the snapshot; check the broker's symbol name (suffixes like .a, m, "
                        "or cash) with: mt5.py symbols --search %s" % (sym, sym[:3]))
    quote = dict(quotes.get(sym) or {})
    if quote.get("bid") is None or quote.get("ask") is None:
        quote.update(spec.get("tick") or {})
    if a.bid is not None:
        quote["bid"] = a.bid
    if a.ask is not None:
        quote["ask"] = a.ask
    if a.spread is not None and quote.get("bid") is not None:
        quote["ask"] = quote["bid"] + float(a.spread) * point(spec)
    bid, ask = _f(quote.get("bid")), _f(quote.get("ask"))
    if bid is None and a.entry is not None:
        bid = a.entry
        ask = a.entry if ask is None else ask
    side = str(a.side or plan.get("side") or "buy").strip().lower()
    if side in ("long",):
        side = "buy"
    if side in ("short",):
        side = "sell"
    if side not in ("buy", "sell"):
        raise SizeError("side must be buy or sell, got %r" % side)

    typ = str(a.type or plan.get("type") or "market").strip().lower()
    if typ not in ("market",) + PENDING:
        raise SizeError("type must be market or one of %s" % ", ".join(PENDING))
    if typ != "market" and str(typ).split("_")[0] != side:
        raise SizeError("a %s order is a %s order, but the side is %s" % (typ, typ.split("_")[0], side))

    entry_plan = _f(a.entry if a.entry is not None else plan.get("entry"))
    if typ == "market":
        ref = ask if side == "buy" else bid
        if ref is None:
            if entry_plan is None:
                raise SizeError("no quote in the snapshot and no --entry: nothing to size at")
            entry, entry_from = entry_plan, "the plan's entry (no quote)"
        elif a.at_market or entry_plan is None:
            entry, entry_from = ref, ("the ask" if side == "buy" else "the bid")
        elif side == "buy":
            entry, entry_from = max(ref, entry_plan), ("the ask" if ref >= entry_plan else "the plan's entry")
        else:
            entry, entry_from = min(ref, entry_plan), ("the bid" if ref <= entry_plan else "the plan's entry")
    else:
        entry = _f(a.price if a.price is not None else plan.get("price") or plan.get("entry"))
        if entry is None:
            raise SizeError("a %s order needs --price" % typ)
        entry_from = "the order's price"

    stop = _f(a.stop if a.stop is not None else plan.get("stop"))
    target = _f(a.target if a.target is not None else plan.get("target"))
    if stop is None and cfg.get("require_stop", True):
        raise SizeError("no stop: MT5 sizing needs one (put \"stop\" in the plan, or pass --stop). "
                        "Set require_stop false only if you know why you are trading blind")
    if stop is not None:
        if side == "buy" and stop >= entry:
            raise SizeError("a buy's stop (%s) must be under the entry (%s)" % (price(stop, digits(spec)),
                                                                               price(entry, digits(spec))))
        if side == "sell" and stop <= entry:
            raise SizeError("a sell's stop (%s) must be over the entry (%s)" % (price(stop, digits(spec)),
                                                                                price(entry, digits(spec))))
    if target is not None:
        if side == "buy" and target <= entry:
            raise SizeError("a buy's target (%s) must be over the entry (%s)" % (price(target, digits(spec)),
                                                                                 price(entry, digits(spec))))
        if side == "sell" and target >= entry:
            raise SizeError("a sell's target (%s) must be under the entry (%s)" % (price(target, digits(spec)),
                                                                                   price(entry, digits(spec))))
    return {"symbol": sym, "spec": spec, "quote": quote, "bid": bid, "ask": ask, "account": acct,
            "side": side, "type": typ, "entry": entry, "entry_from": entry_from,
            "stop": round_price(spec, stop) if stop is not None else None,
            "target": round_price(spec, target) if target is not None else None,
            "plan": plan, "cfg": cfg}


# ---------------------------------------------------------------- the sizing

def size(a, plan, cfg, ctx):
    r = resolve(a, plan, cfg, ctx)
    spec, acct = r["spec"], r["account"]
    side, typ, entry = r["side"], r["type"], r["entry"]
    stop, target = r["stop"], r["target"]
    bal = _f(acct.get("balance"))
    eq = _f(acct.get("equity"))
    base = eq if eq is not None else (bal or 0.0)
    free = _f(acct.get("margin_free"))
    if free is None:
        free = base - (_f(acct.get("margin")) or 0.0)
    currency = acct.get("currency") or "USD"
    warnings = []

    dist = abs(entry - stop) if stop is not None else None
    if dist is None:
        raise SizeError("no stop: cannot size without one")
    gap = max(_f(spec.get("trade_stops_level")) or 0.0, spread_points(spec, r["bid"], r["ask"]) or 0.0) * point(spec)
    if dist <= 0:
        raise SizeError("the entry and the stop are the same price")
    if gap and dist < gap - 1e-12:
        raise SizeError("the stop is %s points away but the broker needs %s (stops level plus spread): "
                        "widen the stop, then size again" % (num(dist / point(spec)), num(gap / point(spec))))
    if dist < 2 * pip(spec):
        warnings.append("the stop is under 2 pips away: the spread and the slippage can eat the whole edge")

    spread = spread_pips(spec, r["bid"], r["ask"])
    max_spread = _f(cfg.get("max_spread_pips"))
    if spread is not None and max_spread and spread > max_spread + 1e-9:
        raise SizeError("the spread is %s pips, over max_spread_pips (%s): wait for it to come back"
                        % (num(spread), num(max_spread)))

    budget = _f(a.risk)
    if budget is None:
        budget = _f(cfg.get("max_loss_per_trade_usd"))
    pct = _f(a.risk_pct) if a.risk_pct is not None else _f(cfg.get("risk_pct_per_trade"))
    if pct and base:
        by_pct = base * pct / 100.0
        if budget is None or by_pct < budget:
            budget = by_pct
    if not budget or budget <= 0:
        raise SizeError("no risk budget: set max_loss_per_trade_usd or risk_pct_per_trade in the config")
    budget *= (_f(a.size_scale) or 1.0)

    per_unit = value_per_unit(spec)
    per_lot_price = dist * per_unit
    comm = _f(cfg.get("commission_per_lot")) or 0.0
    per_lot = per_lot_price + comm
    if per_lot <= 0:
        raise SizeError("the risk per lot works out to zero: check the symbol's tick value and the stop")
    raw = budget / per_lot
    lots = floor_volume(raw, spec)
    why = "the risk budget"
    cap = _f(cfg.get("max_lots_per_order")) or 0.0
    if cap and lots > cap:
        lots = floor_volume(cap, spec)
        why = "max_lots_per_order"
    if lots <= 0:
        min_risk = distance_money(spec, dist, volume_min(spec)) + volume_min(spec) * comm
        raise SizeError("the risk budget (%s) is smaller than the symbol's minimum lot: %s lots at that stop "
                        "risks %s. Widen the budget or pick a quieter instrument"
                        % (money(budget), num(volume_min(spec)), money(min_risk)))

    cap_pct = _f(cfg.get("max_margin_use_pct")) or 0.0
    margin, mfrom = margin_of(r, lots)
    step = volume_step(spec)
    guard = 0
    while cap_pct and free > 0 and margin and margin > free * cap_pct / 100.0 + 0.005 and lots > volume_min(spec):
        lots = floor_volume(lots - step, spec)
        if lots <= 0:
            break
        margin, mfrom = margin_of(r, lots)
        guard += 1
        if guard > 1000:
            break
        why = "the margin cap (max_margin_use_pct)"
    if cap_pct and free > 0 and margin and margin > free * cap_pct / 100.0 + 0.005:
        raise SizeError("even the minimum lot needs %s of margin, over %s%% of free margin (%s)"
                        % (money(margin), num(cap_pct), money(free * cap_pct / 100.0)))
    if lots <= 0:
        raise SizeError("no volume fits the symbol's minimum: check volume_min and the stop distance")

    risk_price = distance_money(spec, dist, lots)
    commission = lots * comm
    risk = round((risk_price or 0.0) + commission, 2)
    if budget and risk > budget + 0.005:
        warnings.append("the money at risk (%s) is a hair over the budget (%s) after rounding to the lot step"
                        % (money(risk), money(budget)))
    if target is not None:
        reward = distance_money(spec, abs(target - entry), lots)
        rr = abs(target - entry) / dist
    else:
        reward, rr = None, None
    min_rr = _f(cfg.get("min_reward_risk"))
    if rr is not None and min_rr and rr < min_rr - 0.005:   # a half point of rounding
        raise SizeError("reward:risk is %.2f at this entry (%s) and target (%s), under min_reward_risk (%s): "
                        "move the target, or tighten the stop with trader-exit for a second look"
                        % (rr, price(entry, digits(spec)), price(target, digits(spec)), num(min_rr)))
    if rr is None:
        warnings.append("no target: reward:risk is unknown (trader-alerts can watch a price instead)")

    lvl_after = None
    used_after = (_f(acct.get("margin")) or 0.0) + (margin or 0.0)
    if used_after > 0 and base:
        lvl_after = base / used_after * 100.0
        floor = _f(cfg.get("min_margin_level_pct")) or 0.0
        if floor and lvl_after < floor:
            raise SizeError("margin level after the order would be %.0f%%, under min_margin_level_pct (%s): "
                            "smaller size or a bigger account" % (lvl_after, num(floor)))

    be_extra = ((spread or 0.0) * pip(spec) + (commission / per_unit if per_unit else 0.0))
    breakeven = entry + be_extra if side == "buy" else entry - be_extra
    if stop is not None:
        be_dist = abs(breakeven - entry)
        if be_dist >= dist:
            warnings.append("at this size the spread plus commission is %s points: a breakeven stop needs the "
                            "price to move that far first" % num(be_dist / point(spec)))

    return {
        "symbol": r["symbol"], "spec": spec, "quote": r["quote"], "account": acct, "plan": r["plan"],
        "side": side, "type": typ, "entry": round_price(spec, entry), "entry_from": r["entry_from"],
        "stop": stop, "target": target, "lots": lots, "lots_why": why,
        "raw_lots": round(raw, 5), "distance": dist,
        "pips_risk": round(dist / pip(spec), 1) if pip(spec) else None,
        "point_value": round(per_unit, 6), "per_lot_risk": round(per_lot, 2),
        "risk": risk, "risk_price": round(risk_price or 0.0, 2), "commission": round(commission, 4),
        "risk_pct": round(risk / base * 100.0, 2) if base else None,
        "reward": round(reward, 2) if reward is not None else None, "rr": round(rr, 3) if rr is not None else None,
        "margin": round(margin, 2) if margin is not None else None, "margin_from": mfrom,
        "margin_pct": round((margin or 0.0) / free * 100.0, 1) if free else None,
        "margin_level_after": round(lvl_after, 0) if lvl_after else None,
        "spread_pips": round(spread, 2) if spread is not None else None,
        "breakeven": round_price(spec, breakeven),
        "budget": round(budget, 2), "currency": currency, "warnings": warnings,
        "free_margin": round(free, 2), "balance": round(base, 2),
    }


def margin_of(r, lots):
    """(margin, where it came from) for a volume in the account currency."""
    spec, acct = r["spec"], r["account"]
    px = r["entry"]
    rate = _f(spec.get("margin_initial"))
    if rate is not None and rate > 0:
        return lots * contract_size(spec) * px * rate / 100.0, "the symbol's margin rate %s%%" % num(rate)
    lev = _f(acct.get("leverage")) or 100.0
    return lots * contract_size(spec) * px / lev, "leverage 1:%d" % int(lev)


# ---------------------------------------------------------------- output

def order_doc(r, a, cfg, now):
    spec, quote = r["spec"], r["quote"]
    order = {
        "venue": "mt5",
        "symbol": r["symbol"],
        "side": r["side"],
        "type": r["type"],
        "volume": num(r["lots"]),
        "deviation": int(_f(cfg.get("deviation")) or 20),
        "magic": int(_f(cfg.get("magic")) or MAGIC),
        "comment": (a.comment or ("%s %s" % (str(r["plan"].get("setup") or "orb"),
                                             now.strftime("%Y-%m-%d"))))[:26],
        "filling": str(a.filling or cfg.get("filling") or "auto").lower(),
        "time": str(a.time or cfg.get("time") or "gtc").lower(),
        "why": "%s on %s: %s lots, %s at risk (%s per lot over %s pips, plus %s commission)%s" % (
            str(r["plan"].get("setup_label") or r["plan"].get("setup") or "setup"), r["symbol"],
            num(r["lots"]), money(r["risk"]), money(r["per_lot_risk"]), num(r["pips_risk"]),
            money(r["commission"]),
            ", bound by %s" % r["lots_why"] if r["lots_why"] != "the risk budget" else ""),
        "plan": {k: v for k, v in (r["plan"] or {}).items() if k in
                 ("setup", "entry", "stop", "target", "risk_per_unit", "flat_by", "date", "stop_label",
                  "target_label", "venue", "symbol")},
        "spec": dict(spec, tick={"bid": quote.get("bid"), "ask": quote.get("ask"),
                                 "time": quote.get("time") or quote.get("time_utc")}),
        "quote": {k: quote.get(k) for k in ("bid", "ask", "time", "spread_points") if quote.get(k) is not None},
        "risk": {k: r[k] for k in ("risk", "risk_pct", "commission", "rr", "margin", "margin_pct",
                                   "margin_level_after", "pips_risk", "spread_pips", "breakeven",
                                   "point_value", "per_lot_risk", "budget", "currency")},
    }
    if r["stop"] is not None:
        order["sl"] = r["stop"]
    if r["target"] is not None:
        order["tp"] = r["target"]
    if r["type"] != "market":
        order["price"] = r["entry"]
        if a.expiration:
            order["time"] = "specified"
            order["expiration"] = a.expiration
    else:
        order["price"] = None
    for k in ("price", "expiration", "sl", "tp"):
        if order.get(k) is None:
            order.pop(k, None)
    return order


def report(r):
    spec = r["spec"]
    d = digits(spec)
    lines = []
    lines.append("SIZE %s %s lots of %s (%s order)" % (r["side"].upper(), num(r["lots"]), r["symbol"],
                                                       r["type"].replace("_", " ")))
    lines.append("  entry %s (%s), stop %s, target %s" % (
        price(r["entry"], d), r["entry_from"], price(r["stop"], d) if r["stop"] else "none",
        price(r["target"], d) if r["target"] else "none"))
    lines.append("  %s pips of risk, %s per lot: %s at risk (%s%% of %s)" % (
        ("%.1f" % r["pips_risk"]) if r["pips_risk"] is not None else "?", money(r["per_lot_risk"]),
        money(r["risk"]), num(r["risk_pct"]), money(r["balance"])))
    lines.append("  %s of a %s budget, rounded down to the symbol's %s lot step%s" % (
        money(r["budget"]), money(r["budget"]), num(volume_step(spec)),
        (", held back by " + r["lots_why"]) if r["lots_why"] != "the risk budget" else ""))
    if r["reward"] is not None:
        lines.append("  target pays %s, reward:risk %.2f" % (money(r["reward"]), r["rr"]))
    if r["margin"] is not None:
        lines.append("  margin %s (%s), %s of free margin%s" % (
            money(r["margin"]), r["margin_from"], ("%.1f%%" % r["margin_pct"]) if r["margin_pct"] is not None else "?",
            (", margin level %.0f%%" % r["margin_level_after"]) if r["margin_level_after"] else ""))
    if r["spread_pips"] is not None:
        lines.append("  spread %s pips; breakeven price about %s after the spread and commission" % (
            ("%.1f" % r["spread_pips"]), price(r["breakeven"], d)))
    for w in r["warnings"]:
        lines.append("  note: " + w)
    lines.append("Next: mt5.py snapshot --write, then trader-risk check.py, then trader-broker ticket.py show.")
    lines.append("Nothing is sent to the terminal until ticket.py records your yes and mt5.py execute runs.")
    return "\n".join(lines)


def partial_size(a, cfg, ctx):
    """The volume to close at R, for a partial take-profit."""
    if a.symbol is None or a.lots is None or a.at_r is None:
        raise SizeError("--partial wants --symbol, --lots (the open volume) and --at-r")
    spec = (ctx.get("symbols") or {}).get(a.symbol.upper()) if ctx else None
    if a.spec:
        doc = read_json(a.spec, "spec")
        if isinstance(doc, dict):
            spec = doc.get("symbols", {}).get(a.symbol.upper(), doc) if "symbols" in doc else doc
    spec = spec or {}
    total = _f(a.lots)
    pct = _f(a.pct) if a.pct is not None else 50.0
    raw = total * pct / 100.0
    vol = floor_volume(raw, spec) if spec else round(raw, 2)
    if not vol or vol <= 0:
        raise SizeError("%s%% of %s lots is under the symbol's minimum %s: take the whole position instead"
                        % (num(pct), num(total), num(volume_min(spec))))
    left = round(total - vol, 8)
    if left < volume_min(spec) - 1e-12:
        vol = floor_volume(total, spec)
        left = 0.0
    return {"symbol": a.symbol.upper(), "action": "partial_close", "total_lots": total, "volume": vol,
            "left": left, "at_r": _f(a.at_r), "pct": pct,
            "why": "partial take-profit at %.1fR: close %s of %s lots, leave %s running with the stop at "
                   "breakeven" % (_f(a.at_r) or 0, num(vol), num(total), num(left))}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Size an MT5 order to your budget (trader-budget). Writes nothing "
                                             "to the terminal.")
    ap.add_argument("--plan", default="trader/plan.json", help="the trade plan (trader-exit, or mt5.py setup)")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--context", default="trader/mt5/context.json", help="the snapshot from mt5.py snapshot")
    ap.add_argument("--account", help="a saved account JSON to use instead of the snapshot's")
    ap.add_argument("--spec", help="a saved symbol spec (or a snapshot) to use instead of the terminal's")
    ap.add_argument("--symbol")
    ap.add_argument("--side", choices=["buy", "sell", "long", "short"])
    ap.add_argument("--type", choices=["market"] + list(PENDING))
    ap.add_argument("--entry", type=float)
    ap.add_argument("--stop", type=float)
    ap.add_argument("--target", type=float)
    ap.add_argument("--price", type=float, help="the price of a pending order")
    ap.add_argument("--risk", type=float, help="the money to risk on this trade (default: the config's)")
    ap.add_argument("--risk-pct", type=float, help="risk this percentage of the account instead")
    ap.add_argument("--size-scale", type=float, default=1.0, help="scale the risk budget (0.5 = half size)")
    ap.add_argument("--at-market", action="store_true", help="fill at the quote, ignoring the plan's entry")
    ap.add_argument("--bid", type=float, help="override the quote's bid")
    ap.add_argument("--ask", type=float, help="override the quote's ask")
    ap.add_argument("--spread", type=float, help="override the spread, in points")
    ap.add_argument("--comment")
    ap.add_argument("--filling", choices=["auto", "fok", "ioc", "return", "boc"])
    ap.add_argument("--time", choices=["gtc", "day", "specified"])
    ap.add_argument("--expiration", help="YYYY-MM-DD HH:MM (server time)")
    ap.add_argument("--partial", action="store_true", help="the volume to close at R, not a new order")
    ap.add_argument("--lots", type=float, help="the open volume, for --partial")
    ap.add_argument("--at-r", dest="at_r", type=float, help="the R multiple, for --partial")
    ap.add_argument("--pct", type=float, help="the percentage to close, for --partial (default 50)")
    ap.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH",
                    help="write the order (default trader/orders.json)")
    ap.add_argument("--now", help='pretend it is this New York time, e.g. "2026-10-20 09:35"')
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = parse_now(a.now)
        cfg = merged_config(read_json(a.config, "config", required=False) or {})
        plan = read_json(a.plan, "plan (run trader-exit or mt5.py setup first)", required=False) or {}
        if not isinstance(plan, dict):
            raise SizeError("%s is not a plan" % a.plan)
        ctx = load_context(a.context)
        if a.partial:
            out = partial_size(a, cfg, ctx)
            print(json.dumps(out, indent=2) if a.json else
                  "PARTIAL %s: close %s of %s lots at %.1fR, leave %s running."
                  % (out["symbol"], num(out["volume"]), num(out["total_lots"]), out["at_r"], num(out["left"])))
            return 0
        r = size(a, plan, cfg, ctx)
        order = order_doc(r, a, cfg, now)
    except SizeError as e:
        print("lots.py: %s" % e, file=sys.stderr)
        return 1
    if a.write:
        old = read_json(a.write, "orders", required=False)
        replaced = len(old.get("orders", [])) if isinstance(old, dict) else 0
        doc = {"created_by": "trader-budget", "venue": "mt5",
               "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "proposed",
               "paper": bool(cfg.get("paper", True)),
               "note": "Proposals only. Nothing reaches the terminal until trader-risk passes this exact order, "
                       "you say yes in the chat, and mt5.py execute runs.",
               "source": "lots.py %s on %s" % (r["symbol"], now.strftime("%Y-%m-%d %H:%M")),
               "orders": [order]}
        write_json(a.write, doc)
    if a.json:
        print(json.dumps({"order": order, "size": {k: v for k, v in r.items() if k not in ("spec", "quote",
                                                                                           "account")}},
                         indent=2))
    else:
        print(report(r))
        if a.write:
            print("Wrote the order to %s%s." % (a.write, (" (it replaced %d earlier proposal%s)"
                                                        % (replaced, "" if replaced == 1 else "s")) if replaced else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
