#!/usr/bin/env python3
"""Pre-trade risk rules for MetaTrader 5 orders. Standard library only, no
network. This is trader-risk's MT5 half and trader-budget's arithmetic, in one
place, so an MT5 order is checked with the same care as an Alpaca one.

It is a pure function over files. `mt5.py snapshot` writes the terminal's
state to trader/mt5/context.json (account, symbol specs, quotes, open
positions, pending orders, today's closed deals). Open orders
(trader/orders.json, written by trader-budget/lots.py or mt5.py) carry
everything the check needs: volume, sl, tp, the spec and the sizing numbers.
So the check runs offline, is repeatable, and can be tested without a
terminal, which is the whole point.

    from mt5rules import check_orders
    res = check_orders([(1, order)], cfg, ctx, state, today, now_utc)

What blocks an MT5 order:

  format      no symbol or side, unknown type, volume not a positive number,
              a market order that also carries a price, a pending order with
              no price, a non-integer magic, an unknown filling mode
  venue       not an MT5 order, or the symbol is not in the terminal's
              snapshot (check the suffix: EURUSD.a, XAUUSDm ...)
  symbol      blocked list, symbol hidden or trade mode disabled, close-only,
              long-only / short-only against the side
  session     outside the symbol's trading session, the broker's rollover
              window, before no_entries_before or after no_entries_after
              (New York time), or a weekend
  size        under volume_min, over volume_max, not a multiple of
              volume_step, over max_lots_per_order / max_lots_per_symbol
  exposure    over max_open_positions or max_positions_per_symbol, or a
              duplicate pending order / an entry already placed today
  stop        no sl while require_stop is true, sl or tp on the wrong side,
              sl closer than the broker's stops level plus the current spread
  spread      current spread over max_spread_pips, or the quote is stale
  risk        money at risk (price distance + commission) over
              max_loss_per_trade_usd or risk_pct_per_trade, over what is left
              of max_daily_loss_usd after today's closed losses and today's
              entries, or a reward:risk under min_reward_risk
  margin      margin over max_margin_use_pct of free margin, or the margin
              level after the order under min_margin_level_pct
  account     terminal not connected, trading not allowed, or a REAL account
              while allow_live is false (demo accounts are paper: that is fine)
  daily       max_trades_per_day entries or max_orders_per_day orders placed
              today (trader/state/broker.json, the same log as Alpaca)

An EXIT (a sell that closes a long, a buy that closes a short, a close) is
checked for format, symbol and risk-to-account only: getting out is never
blocked by the entry window, the spread or the daily limits.

Exit codes and the trader-risk verdict file are handled by
trader-risk/check.py, which loads this module by path (the skill folder names
have hyphens, so a normal import is not possible).
"""

import datetime
import hashlib
import json
import math

# ---------------------------------------------------------------- config

DEFAULTS = {
    "max_loss_per_trade_usd": 50,
    "max_daily_loss_usd": 150,
    "max_trades_per_day": 3,
    "max_orders_per_day": 10,
    "min_reward_risk": 1.0,
    "require_stop": True,
    "blocked": [],
    "paper": True,
    "allow_short": False,
    "allow_options": False,
    "allow_margin": False,
    "budget": None,
}

MT5_DEFAULTS = {
    "venue": "mt5",
    "allow_live": False,
    "magic": 20261019,
    "deviation": 20,
    "symbol_suffix": "",
    "symbols": [],                     # empty = any symbol the terminal knows
    "max_spread_pips": 2.0,
    "max_quote_age_sec": 60,
    "max_lots_per_order": 2.0,
    "max_lots_per_symbol": 2.0,
    "max_open_positions": 3,
    "max_positions_per_symbol": 1,
    "max_margin_use_pct": 40.0,
    "min_margin_level_pct": 300.0,
    "commission_per_lot": 7.0,        # round turn, per lot: set your broker's
    "risk_pct_per_trade": 1.0,
    "allow_pending": True,
    "filling": "auto",
    "guard": {
        "enabled": False,
        "breakeven_at_r": 1.0,
        "trail_at_r": 1.0,
        "trail_points": 150,
        "partial_at_r": 1.0,
        "partial_pct": 50,
    },
    "session": {
        "open": "03:00",              # New York: the London session
        "no_entries_before": "03:05",
        "no_entries_after": "19:00",
        "flat_by": "20:55",
        "rollover": "23:55",
        "rollover_minutes": 15,
        "days": [0, 1, 2, 3, 4],       # 0 = Monday, New York time
    },
}

MT5_FIELDS = ("venue", "symbol", "side", "type", "volume", "price", "sl", "tp",
              "deviation", "magic", "comment", "filling", "time", "expiration")
VENUES = ("mt5", "metatrader", "metatrader5", "mt5-demo", "mt5-live")
MARKET = "market"
PENDING = ("buy_limit", "sell_limit", "buy_stop", "sell_stop", "buy_stop_limit", "sell_stop_limit")
TYPES = (MARKET,) + PENDING
FILLINGS = ("auto", "fok", "ioc", "return", "boc")
TIME_POLICIES = ("gtc", "day", "specified", "specified_day")
ACTIONS = {"market": "deal", "buy_limit": "pending", "sell_limit": "pending",
           "buy_stop": "pending", "sell_stop": "pending",
           "buy_stop_limit": "pending", "sell_stop_limit": "pending"}


class RuleError(Exception):
    pass


def mt5_config(cfg):
    """The config's "mt5" block over the defaults, plus the shared limits.
    Both flat and nested layouts work: {"max_loss_per_trade_usd": 50} next to
    {"mt5": {"max_lots_per_order": 5}}. It is also idempotent: a config that
    already went through this function (everything flat) keeps its values."""
    cfg = cfg or {}
    c = dict(DEFAULTS)
    c.update(cfg)
    if isinstance(cfg.get("mt5"), dict):
        block = cfg["mt5"]
    else:
        block = {k: cfg[k] for k in MT5_DEFAULTS if k in cfg}
        for sub in ("session", "guard"):
            if isinstance(cfg.get(sub), dict):
                block[sub] = cfg[sub]
    merged = dict(MT5_DEFAULTS)
    merged.update({k: v for k, v in block.items() if v is not None})
    for sub in ("session", "guard"):
        s = dict(MT5_DEFAULTS[sub])
        s.update(block.get(sub) or {})
        merged[sub] = s
    for k in ("max_loss_per_trade_usd", "max_daily_loss_usd", "max_trades_per_day", "max_orders_per_day",
              "min_reward_risk", "require_stop", "blocked", "paper", "allow_short", "budget"):
        if c.get(k) is not None:
            merged[k] = c[k]
    merged["_config"] = c
    return merged


def merge_cfg(cfg):
    """The full config with the MT5 defaults filled in (for mt5.py, lots.py
    and check.py to agree on one number)."""
    c = mt5_config(cfg)
    flat = dict(c)
    flat.pop("_config", None)
    out = dict(c["_config"])
    out.update(flat)
    out["mt5"] = {k: v for k, v in c.items() if k != "_config"}
    return out


# ---------------------------------------------------------------- time (New York, no tz files)

def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def eastern_offset(utc):
    """Hours from UTC for New York: -4 in daylight time, -5 otherwise."""
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
    """ISO time -> naive UTC. A time without an offset is New York time."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = str(text).strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise RuleError("--now wants a time like \"2026-10-19 10:15\" (New York) or ...Z (UTC)")
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


def ny_iso(utc):
    return to_eastern(utc).strftime("%Y-%m-%dT%H:%M:%S") + ("-04:00" if eastern_offset(utc) == -4 else "-05:00")


def server_to_ny(server_dt, offset_hours):
    """MT5 server time (a broker clock, usually UTC+2/+3) -> New York wall time."""
    utc = server_dt - datetime.timedelta(hours=float(offset_hours))
    return to_eastern(utc)


def ny_to_server(ny_dt, offset_hours):
    return eastern_to_utc(ny_dt) + datetime.timedelta(hours=float(offset_hours))


def hhmm(text, what="time"):
    if text in (None, "", False):
        return None
    try:
        h, m = str(text).strip().split(":")[:2]
        return datetime.time(int(h), int(m))
    except (ValueError, TypeError):
        raise RuleError("%s must be an HH:MM time, got %r" % (what, text))


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


def price(x, digits=5):
    v = _f(x)
    if v is None:
        return "?"
    return ("%." + str(int(digits)) + "f") % v


# ---------------------------------------------------------------- symbol maths

def point(spec):
    p = _f(spec.get("point"))
    if p and p > 0:
        return p
    d = spec.get("digits")
    return 10.0 ** (-int(d)) if d is not None else 0.00001


def pip(spec):
    """A pip in price terms. 5-digit and 3-digit FX: 10 points (0.0001,
    0.01). 2-digit gold and 1-digit indices: 10 points too (0.10, 1.0).
    0-digit instruments: one point. Override with the spec's own "pip"."""
    own = _f(spec.get("pip"))
    if own and own > 0:
        return own
    d = spec.get("digits")
    d = int(d) if d is not None else 5
    return point(spec) * 10.0 if d >= 1 else point(spec)


def digits(spec):
    d = spec.get("digits")
    return int(d) if d is not None else 5


def tick_size(spec):
    t = _f(spec.get("trade_tick_size") or spec.get("tick_size"))
    if t and t > 0:
        return t
    return point(spec)


def tick_value(spec):
    """Account-currency value of one tick for 1.00 lot."""
    t = _f(spec.get("trade_tick_value") or spec.get("tick_value"))
    if t and t > 0:
        return t
    return None


def contract_size(spec):
    c = _f(spec.get("trade_contract_size") or spec.get("contract_size"))
    return c if c and c > 0 else 100000.0


def value_per_unit(spec):
    """Money per 1.00 price unit for 1.00 lot, in the account currency."""
    tv = tick_value(spec)
    if tv:
        return tv / tick_size(spec)
    # Fallback: contract size, assuming the profit currency is the account's.
    return contract_size(spec)


def money_per_pip(spec):
    return pip(spec) * value_per_unit(spec)


def distance_money(spec, distance, volume):
    """Money made or lost over a price distance for a volume, at 1:1."""
    d = _f(distance)
    v = _f(volume)
    if d is None or v is None:
        return None
    return abs(d) * value_per_unit(spec) * v


def round_price(spec, p):
    v = _f(p)
    if v is None:
        return None
    return round(v, digits(spec))


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
    """Round a volume DOWN to the symbol's step and clamp to min / max."""
    v = _f(vol)
    if v is None:
        return None
    step = volume_step(spec)
    n = math.floor(v / step + 1e-9)
    out = round(n * step, 8)
    if out < volume_min(spec):
        return 0.0
    return min(out, volume_max(spec))


def volume_fits(vol, spec):
    """(ok, why). MT5 rejects anything off the step ladder."""
    v = _f(vol)
    if v is None or v <= 0:
        return False, "volume must be a positive number"
    lo, hi, step = volume_min(spec), volume_max(spec), volume_step(spec)
    if v < lo - 1e-9:
        return False, "volume %s is under the symbol's minimum %s" % (num(v), num(lo))
    if v > hi + 1e-9:
        return False, "volume %s is over the symbol's maximum %s" % (num(v), num(hi))
    n = (v - lo) / step
    if abs(n - round(n)) > 1e-6:
        return False, "volume %s is not a multiple of the symbol's step %s" % (num(v), num(step))
    return True, ""


def _stamp(value, offset_hours=0.0):
    """A quote time: ISO text, or MT5's epoch seconds on the server clock."""
    if value in (None, ""):
        return None
    text = parse_utc(value)
    if text is not None:
        return text
    epoch = _f(value)
    if epoch is None:
        return None
    utc = datetime.datetime(1970, 1, 1) + datetime.timedelta(
        seconds=epoch - (offset_hours or 0.0) * 3600.0)
    return utc


def quote_of(spec, quotes=None, sym=None, offset_hours=0.0):
    """(bid, ask, time, spread_points) from the snapshot: the quote block, else
    the spec's own tick, else None."""
    q = (quotes or {}).get(sym or spec.get("symbol") or "") or {}
    src = q if (q.get("bid") is not None and q.get("ask") is not None) else (spec.get("tick") or {})
    bid, ask = _f(src.get("bid")), _f(src.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None, None, None, None
    p = point(spec)
    spread = (ask - bid) / p if p else None
    return bid, ask, _stamp(src.get("time_utc") or src.get("time"), offset_hours), spread


def spread_pips(spec, bid, ask):
    if bid is None or ask is None:
        return None
    return (ask - bid) / pip(spec)


def entry_price(order, spec, quote):
    """The price the risk is measured from: the ask for a market buy, the bid
    for a market sell, the order's own price for a pending order."""
    typ = str(order.get("type") or MARKET).lower()
    bid, ask = (quote[0], quote[1]) if quote else (None, None)
    side = str(order.get("side") or type_side(typ)).lower()
    if typ != MARKET:
        return _f(order.get("price"))
    return ask if side == "buy" else bid


def type_side(typ):
    typ = str(typ or MARKET).lower()
    if typ.startswith("buy"):
        return "buy"
    if typ.startswith("sell"):
        return "sell"
    return "buy"


def side_of(order):
    return str(order.get("side") or type_side(order.get("type"))).strip().lower()


def venue_of(order):
    return str(order.get("venue") or order.get("platform") or "").strip().lower()


def is_mt5(order):
    return venue_of(order) in VENUES


def kind_of(order, positions=None):
    """entry or exit. A sell that only closes a long (or a buy that only closes
    a short) is an exit; so is an order that says so."""
    verdict = str(order.get("intent") or order.get("kind") or "").lower()
    if verdict in ("entry", "exit"):
        return verdict
    side = side_of(order)
    vol = _f(order.get("volume")) or 0.0
    net = 0.0
    for p in positions or []:
        if str(p.get("symbol", "")).upper() != str(order.get("symbol", "")).upper():
            continue
        pv = _f(p.get("volume")) or 0.0
        net += pv if str(p.get("type", "buy")).lower() == "buy" else -pv
    if side == "sell" and net > 1e-9:
        return "exit"
    if side == "buy" and net < -1e-9:
        return "exit"
    return "entry"


def fingerprint(order):
    """The exact order that was checked. Same function in trader-broker/ticket.py."""
    core = {}
    for k in MT5_FIELDS:
        v = order.get(k)
        if v is None:
            continue
        if k in ("volume", "price", "sl", "tp"):
            f = _f(v)
            v = num(f) if f is not None else str(v)
        elif k in ("deviation", "magic"):
            f = _f(v)
            v = int(f) if f is not None else str(v)
        core[k] = v
    core["venue"] = "mt5"
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def account_balance(ctx):
    """Equity when the snapshot has it (risk is measured against what is
    actually there), else the balance."""
    a = (ctx or {}).get("account") or {}
    eq = _f(a.get("equity"))
    bal = _f(a.get("balance"))
    return (eq if eq is not None else bal) or 0.0


def account_balance_only(ctx):
    a = (ctx or {}).get("account") or {}
    return _f(a.get("balance")) or account_balance(ctx)


def resolve_filling(spec, want):
    """"auto" -> the first mode the symbol actually allows (FOK, then IOC,
    then RETURN), the same choice mt5lib makes at send time."""
    want = str(want or "auto").lower()
    if want != "auto":
        return want
    modes = [str(m).lower() for m in ((spec or {}).get("filling_modes") or ["fok", "ioc", "return"])]
    for m in ("fok", "ioc", "return"):
        if m in modes:
            return m
    return modes[0] if modes else "return"


def account_free(ctx):
    a = (ctx or {}).get("account") or {}
    free = _f(a.get("margin_free"))
    if free is not None:
        return free
    eq = account_balance(ctx)
    margin = _f(a.get("margin")) or 0.0
    return eq - margin


def margin_level(ctx):
    a = (ctx or {}).get("account") or {}
    lvl = _f(a.get("margin_level"))
    if lvl:
        return lvl
    margin = _f(a.get("margin")) or 0.0
    return (account_balance(ctx) / margin * 100.0) if margin > 0 else None


def margin_for(order, spec, ctx, quote):
    """Margin for the order in the account currency. The order's own number
    (order_calc_margin from the terminal) wins; else the broker's margin rate;
    else the account's leverage."""
    stored = _f(order.get("margin"))
    if stored and stored > 0:
        return stored, "the terminal's order_calc_margin"
    acct = (ctx or {}).get("account") or {}
    vol = _f(order.get("volume")) or 0.0
    px = entry_price(order, spec, quote)
    if not px:
        return None, "no price"
    rate = _f(spec.get("margin_initial"))
    if rate is not None and rate > 0:
        return vol * contract_size(spec) * px * rate / 100.0, "the symbol's margin rate %s%%" % num(rate)
    leverage = _f(acct.get("leverage")) or 100.0
    return vol * contract_size(spec) * px / leverage, "leverage 1:%d" % int(leverage)


def risk_of(order, spec, ctx, quote, commission_per_lot=0.0):
    """(money at risk, details) with the entry, the stop distance, commission."""
    side = side_of(order)
    vol = _f(order.get("volume")) or 0.0
    ent = entry_price(order, spec, quote)
    sl = _f(order.get("sl"))
    tp = _f(order.get("tp"))
    det = {"entry": ent, "volume": vol, "sl": sl, "tp": tp,
           "entry_from": ("ask" if side == "buy" else "bid") if str(order.get("type") or MARKET) == MARKET
           else "the order's price"}
    if not ent or not sl:
        return None, det
    dist = (ent - sl) if side == "buy" else (sl - ent)
    det["distance"] = dist
    det["pips"] = dist / pip(spec) if dist else None
    if dist <= 0:
        return None, det
    per_lot = distance_money(spec, dist, 1.0)
    det["per_lot"] = per_lot
    det["price"] = distance_money(spec, dist, vol)
    det["commission"] = round(vol * (commission_per_lot or 0.0), 4)
    det["risk"] = round((det["price"] or 0.0) + det["commission"], 2)
    if tp:
        rew = (tp - ent) if side == "buy" else (ent - tp)
        det["reward_money"] = round(distance_money(spec, rew, vol) or 0.0, 2)
        det["rr"] = round(rew / dist, 3) if dist else None
    return det["risk"], det


def realized_today(ctx, today):
    """Today's closed result in the account currency: profit + swap +
    commission + fee, on the New York date, including the opening commission
    of any position closed today (that commission is part of the trade)."""
    deals = (ctx or {}).get("deals") or []
    closed_today = set()
    for d in deals:
        when = parse_utc(d.get("time_utc") or d.get("time"))
        if when is None or to_eastern(when).date().isoformat() != str(today):
            continue
        if str(d.get("entry", "")).lower() in ("out", "out_by"):
            closed_today.add(d.get("position_id"))
    total = 0.0
    n = 0
    for d in deals:
        when = parse_utc(d.get("time_utc") or d.get("time"))
        if when is None or to_eastern(when).date().isoformat() != str(today):
            continue
        entry = str(d.get("entry", "")).lower()
        if entry in ("out", "out_by") or d.get("position_id") in closed_today:
            total += sum(_f(d.get(k)) or 0.0 for k in ("profit", "swap", "commission", "fee"))
            if entry in ("out", "out_by"):
                n += 1
    return round(total, 2), n


def rec_day(rec):
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


def placed_today(state, today):
    return [r for r in ((state or {}).get("orders") or []) if rec_day(r) == str(today)]


def rec_is_entry(rec):
    kind = str(rec.get("kind") or "").lower()
    if kind in ("entry", "exit"):
        return kind == "entry"
    return str(rec.get("side", "")).lower() == "buy"


def open_net(positions, symbol):
    net = 0.0
    for p in positions or []:
        if str(p.get("symbol", "")).upper() != str(symbol).upper():
            continue
        v = _f(p.get("volume")) or 0.0
        net += v if str(p.get("type", "buy")).lower() == "buy" else -v
    return net


def open_lots(positions, symbol):
    return sum(_f(p.get("volume")) or 0.0 for p in positions or []
               if str(p.get("symbol", "")).upper() == str(symbol).upper())


# ---------------------------------------------------------------- sessions

def in_window(now_ny, start, end):
    """Is the wall-clock time inside start..end? Handles a window that crosses
    midnight (22:00 to 02:00)."""
    if start is None and end is None:
        return True
    t = now_ny.time().replace(second=0, microsecond=0)
    if start is None:
        return t < end
    if end is None:
        return t >= start
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def rollover_window(cfg, ctx, now_utc=None):
    """The broker's rollover window in New York time, from the server's own
    clock: "rollover": "23:55" server time plus "rollover_minutes": 15.
    The dates matter: New York's daylight offset is read for the day the
    snapshot was made, not for some fixed date."""
    sess = cfg.get("session") or {}
    off = _f((ctx or {}).get("server_offset_hours"))
    start_srv = hhmm(sess.get("rollover") or "23:55", "mt5.session.rollover")
    span = int(_f(sess.get("rollover_minutes")) or 0)
    day = to_eastern(now_utc or parse_now(None)).date()
    base = datetime.datetime.combine(day, start_srv)
    if off is None:
        return start_srv, (base + datetime.timedelta(minutes=span)).time()
    start = server_to_ny(base, off).time()
    end = server_to_ny(base + datetime.timedelta(minutes=span), off).time()
    return start, end


def symbol_sessions(spec):
    """The symbol's own sessions, if the snapshot has them: a list of
    {"day": 0-6 (server), "from": "HH:MM", "to": "HH:MM"} in server time.
    Empty means the default Mon-Fri, all day."""
    out = []
    for s in spec.get("sessions") or spec.get("session") or []:
        if not isinstance(s, dict):
            continue
        try:
            out.append((int(s.get("day")), hhmm(s.get("from"), "session.from"),
                        hhmm(s.get("to"), "session.to")))
        except (RuleError, TypeError):
            continue
    return out


def symbol_open(spec, now_srv):
    """(open, why). A symbol with sessions of its own is checked against them;
    otherwise Mon-Fri, all day, with a weekend closed."""
    sessions = symbol_sessions(spec)
    if sessions:
        for day, start, end in sessions:
            if day != now_srv.weekday():
                continue
            if end < start:          # a session over midnight
                if now_srv.time() >= start or now_srv.time() < end:
                    return True, ""
                continue
            if start <= now_srv.time() < end:
                return True, ""
        return False, "outside the symbol's trading session (%s server time)" % now_srv.strftime("%a %H:%M")
    if now_srv.weekday() >= 5:
        return False, "the market is closed for the weekend (%s server time)" % now_srv.strftime("%a %H:%M")
    return True, ""


def session_state(cfg, ctx, now_utc):
    """Everything the checks need about the clock, in one dict."""
    off = _f((ctx or {}).get("server_offset_hours"))
    off = 0.0 if off is None else off
    now_ny = to_eastern(now_utc)
    now_srv = now_utc + datetime.timedelta(hours=off)
    sess = cfg.get("session") or {}
    days = sess.get("days")
    days = list(range(5)) if days is None else [int(d) for d in days]
    return {"now_utc": now_utc, "now_ny": now_ny, "now_server": now_srv, "offset": off, "days": days,
            "rollover": rollover_window(cfg, ctx, now_utc),
            "before": hhmm(sess.get("no_entries_before"), "mt5.session.no_entries_before"),
            "after": hhmm(sess.get("no_entries_after"), "mt5.session.no_entries_after"),
            "flat_by": hhmm(sess.get("flat_by"), "mt5.session.flat_by")}


def session_reasons(st, cfg, spec, is_exit=False):
    """Reasons an ENTRY cannot be opened now, plus warnings. Exits skip all of
    this: getting out is always allowed."""
    if is_exit:
        return [], []
    reasons, warns = [], []
    if st["now_ny"].weekday() not in st["days"]:
        reasons.append("session: the desk is closed on %s New York (mt5.session.days)"
                       % st["now_ny"].strftime("%A"))
        return reasons, warns
    ok, why = symbol_open(spec, st["now_server"])
    if not ok:
        reasons.append("session: " + why)
    start, end = st["rollover"]
    if in_window(st["now_ny"], start, end):
        reasons.append("session: the broker's rollover window (%s to %s New York): spreads widen and stops slip"
                       % (start.strftime("%H:%M"), end.strftime("%H:%M")))
    if st["before"] is not None and st["now_ny"].time() < st["before"]:
        reasons.append("session: no new entries before %s New York (it is %s)"
                       % (st["before"].strftime("%H:%M"), st["now_ny"].strftime("%H:%M")))
    if st["after"] is not None and st["now_ny"].time() > st["after"]:
        reasons.append("session: no new entries after %s New York (it is %s)"
                       % (st["after"].strftime("%H:%M"), st["now_ny"].strftime("%H:%M")))
    if st["flat_by"] is not None:
        warns.append("flat by %s New York: an intraday trade is closed before the session ends"
                     % st["flat_by"].strftime("%H:%M"))
    return reasons, warns


# ---------------------------------------------------------------- the check

def check_orders(pairs, cfg, ctx, state=None, today=None, now=None):
    """Check [(index, order), ...] of MT5 orders against the rules.

    cfg    the config (flat limits plus the "mt5" block)
    ctx    the snapshot from mt5.py snapshot (account, symbols, quotes, positions,
           orders, deals, server_offset_hours); {} means "no terminal": the
           checks then fall over to the order's own spec, with warnings
    state  trader/state/broker.json, for today's entries and duplicates
    now    naive UTC (default: the real clock)

    Returns {"results": [...], "account": {...}, "venue": "mt5",
             "loss_today": ..., "realized_today": ...}. Each result has the
    same shape as trader-risk's, plus MT5 numbers (volume, margin, spread,
    pips, rr, risk_pct)."""
    c = mt5_config(cfg)
    ctx = ctx or {}
    now_utc = now or parse_now(None)
    ny = to_eastern(now_utc)
    today = str(today or ny.date().isoformat())
    st = session_state(c, ctx, now_utc)
    acct = ctx.get("account") or {}
    symbols = {str(k).upper(): v for k, v in (ctx.get("symbols") or {}).items()}
    quotes = {str(k).upper(): v for k, v in (ctx.get("quotes") or {}).items()}
    positions = ctx.get("positions") or []
    pending = ctx.get("orders") or []
    trades = c.get("max_trades_per_day")
    max_orders = c.get("max_orders_per_day")
    blocked = {str(b).upper() for b in (c.get("blocked") or [])}
    allow = {str(s).upper() for s in (c.get("symbols") or [])}
    done = placed_today(state, today)
    count_today = len(done)
    entries_done = [r for r in done if rec_is_entry(r)]
    loss_logged = 0.0
    warns_top = []
    for r in entries_done:
        ml = _f(r.get("max_loss"))
        if ml is None:
            warns_top.append("an entry placed today (%s %s) has no max loss in the log; not counted in "
                             "the daily loss" % (r.get("side"), r.get("symbol")))
        else:
            loss_logged += ml
    realized, nd = realized_today(ctx, today)
    loss_closed = max(0.0, -realized)
    balance = account_balance(ctx)
    balance_only = account_balance_only(ctx)
    free = account_free(ctx)
    lvl_before = margin_level(ctx)
    live = str(acct.get("trade_mode") or "demo").lower() in ("real", "live")
    if live and not c.get("allow_live"):
        warns_top.append("this is a REAL-money account and \"mt5.allow_live\" is false: entries are blocked "
                         "until you change that on purpose")
    if not c.get("paper", True):
        warns_top.append("LIVE mode (\"paper\": false): these orders use real money")
    if not ctx:
        warns_top.append("no terminal snapshot: run mt5.py snapshot --write first (checks fall back to the "
                         "order's own spec and figures)")
    off = _f(ctx.get("server_offset_hours"))
    if off is None:
        warns_top.append("the snapshot has no server time offset: sessions and rollover are read as New York "
                         "time (mt5.py snapshot records the real one)")
    results = []
    entries_batch, loss_batch = 0, 0.0
    used_symbols = {}

    for idx, o in pairs:
        reasons, warns, info = [], [], []
        o = o or {}
        sym = str(o.get("symbol") or "").strip().upper()
        typ = str(o.get("type") or MARKET).strip().lower()
        side = side_of(o)
        vol = _f(o.get("volume"))
        spec = symbols.get(sym) or (o.get("spec") if isinstance(o.get("spec"), dict) else {}) or {}
        quote = quote_of(spec, quotes, sym, _f(ctx.get("server_offset_hours")) or 0.0) if spec \
            else (None, None, None, None)
        bid, ask, qtime, qspread = quote
        kind = kind_of(o, positions)
        is_exit = kind == "exit"

        # ---- format
        if not sym:
            reasons.append("format: no symbol")
        if side not in ("buy", "sell"):
            reasons.append("format: side must be buy or sell, got %r" % o.get("side"))
        if typ not in TYPES:
            reasons.append("format: unknown order type %r (market, %s)" % (typ, ", ".join(PENDING)))
        if vol is None or vol <= 0:
            reasons.append("format: volume must be a positive number of lots, got %r" % o.get("volume"))
        if typ != MARKET and _f(o.get("price")) is None:
            reasons.append("format: a %s order needs a price" % typ)
        if typ == MARKET and _f(o.get("price")) is not None:
            warns.append("a market order carries a price: the terminal fills at the market, the price is ignored")
        for k in ("deviation", "magic"):
            if o.get(k) is not None and _f(o.get(k)) is None:
                reasons.append("format: %s must be a whole number" % k)
        fill = str(o.get("filling") or c.get("filling") or "auto").lower()
        if fill not in FILLINGS:
            reasons.append("format: unknown filling mode %r (auto, fok, ioc, return)" % o.get("filling"))
        fill = resolve_filling(spec, fill)
        policy = str(o.get("time") or "gtc").lower()
        if policy not in TIME_POLICIES:
            reasons.append("format: unknown time policy %r (gtc, day, specified)" % o.get("time"))
        if policy in ("specified", "specified_day") and not o.get("expiration"):
            reasons.append("format: a specified time policy needs an expiration time")
        if typ == MARKET and policy in ("specified", "specified_day"):
            reasons.append("format: a market order cannot expire; use a day or gtc policy")
        if o.get("tp") is not None and _f(o.get("tp")) is not None and o.get("tp") == o.get("sl"):
            reasons.append("format: sl and tp are the same price")
        if not spec:
            reasons.append("symbol: %s is not in the terminal snapshot; check the broker's suffix "
                           "(EURUSD.a, XAUUSDm, US500.cash ...)" % (sym or "?"))

        # ---- symbol
        if spec and allow and sym not in allow:
            reasons.append("symbol: %s is not on your mt5.symbols list" % sym)
        if sym and sym in blocked:
            reasons.append("symbol: %s is on your blocked list" % sym)
        if spec:
            mode = str(spec.get("trade_mode") or "full").lower()
            if mode in ("disabled", "close_only", "closeonly"):
                reasons.append("symbol: %s is %s at the broker right now"
                               % (sym, "disabled" if mode == "disabled" else "close-only"))
            elif mode in ("long_only", "longonly") and side == "sell":
                reasons.append("symbol: %s is long-only at the broker right now" % sym)
            elif mode in ("short_only", "shortonly") and side == "buy":
                reasons.append("symbol: %s is short-only at the broker right now" % sym)
        if side == "sell" and not is_exit and not c.get("allow_short", False):
            reasons.append("short: selling %s would open a short, and \"allow_short\" is false" % (sym or "?"))
        if is_exit and side == "sell":
            held = open_net(positions, sym)
            if held <= 1e-9 and vol is not None:
                reasons.append("exit: no %s position to close (the terminal holds %s lots)" % (sym, num(max(held, 0))))
            elif held > 1e-9 and vol is not None and vol > held + 1e-9:
                reasons.append("exit: closing %s lots but the terminal holds %s lots" % (num(vol), num(held)))

        # ---- terminal and account
        term = ctx.get("terminal") or {}
        if not ctx and not is_exit:
            reasons.append("terminal: no MT5 snapshot (run mt5.py snapshot --write): without it the account, "
                           "margin, positions, sessions and spreads cannot be checked")
        if ctx and term.get("connected") is False:
            reasons.append("account: the terminal is not connected to the broker")
        if ctx and term.get("trade_allowed") is False and not is_exit:
            reasons.append("account: trading is disabled in the terminal (Tools > Options > Expert Advisors, "
                           "or the terminal's AutoTrading button)")
        if ctx and acct.get("trade_allowed") is False and not is_exit:
            reasons.append("account: this login cannot trade (account_info.trade_allowed is false)")
        if ctx and acct.get("trade_expert") is False and not is_exit:
            reasons.append("account: the account's \"algo trading\" flag is off")
        if live and not c.get("allow_live") and not is_exit:
            reasons.append("account: REAL-money account while \"mt5.allow_live\" is false")
        if not is_exit and c.get("paper", True) and live:
            warns.append("the config says paper, this account is real: set \"paper\": false if that is the plan")

        # ---- clock
        s_reasons, s_warns = session_reasons(st, c, spec, is_exit)
        reasons.extend(s_reasons)
        warns.extend(s_warns)

        # ---- volume and size
        if spec and vol is not None and vol > 0:
            ok, why = volume_fits(vol, spec)
            if not ok:
                reasons.append("size: " + why)
        if vol is not None and vol > 0:
            if vol > (_f(c.get("max_lots_per_order")) or 0) + 1e-9:
                reasons.append("size: %s lots is over max_lots_per_order (%s)"
                               % (num(vol), num(c.get("max_lots_per_order"))))
            already = open_lots(positions, sym) + sum(_f(p.get("volume")) or 0 for p in pending
                                                      if str(p.get("symbol", "")).upper() == sym)
            if not is_exit and already + vol > (_f(c.get("max_lots_per_symbol")) or 0) + 1e-9:
                reasons.append("size: %s lots on %s after this order is over max_lots_per_symbol (%s)"
                               % (num(already + vol), sym, num(c.get("max_lots_per_symbol"))))
            if already > 0 and not is_exit:
                warns.append("%s already has %s lots open or pending" % (sym, num(already)))

        # ---- exposure
        if not is_exit:
            held = [p for p in positions if str(p.get("symbol", "")).upper() == sym]
            per_sym = (_f(c.get("max_positions_per_symbol")) or 0)
            if per_sym and per_sym > 0:
                have = len(held) + len([p for p in pending if str(p.get("symbol", "")).upper() == sym])
                if have >= int(per_sym):
                    reasons.append("exposure: %s already has %d position(s)/order(s), the limit is %d"
                                   % (sym, have, int(per_sym)))
            max_open = (_f(c.get("max_open_positions")) or 0)
            if max_open and len(positions) + len(pending) >= int(max_open):
                reasons.append("exposure: %d open positions and pending orders, the limit is %d"
                               % (len(positions) + len(pending), int(max_open)))
            net = open_net(positions, sym)
            hedging = bool(acct.get("hedge", True))
            if net > 1e-9 and side == "sell":
                if hedging:
                    reasons.append("exposure: a sell would hedge the %s long (netting accounts would close it); "
                                   "close it on purpose instead" % sym)
            elif net < -1e-9 and side == "buy":
                if hedging:
                    reasons.append("exposure: a buy would hedge the %s short" % sym)
            mine = [p for p in pending if str(p.get("symbol", "")).upper() == sym
                    and str(p.get("type", "")).lower() == typ and abs((_f(p.get("volume")) or 0) - (vol or 0)) < 1e-9
                    and abs((_f(p.get("price")) or 0) - (_f(o.get("price")) or 0)) < 1e-9]
            if mine:
                reasons.append("duplicate: the terminal already has that pending order on %s" % sym)
            same = [r for r in entries_done if str(r.get("symbol", "")).upper() == sym
                    and str(r.get("side", "")).lower() == side]
            if same:
                reasons.append("duplicate: an entry on %s %s was already placed today at %s"
                               % (sym, side, same[-1].get("at", "?")))
            if trades and len(entries_done) + entries_batch >= int(trades) and not is_exit:
                reasons.append("daily: %d entries placed today, the limit is %d"
                               % (len(entries_done) + entries_batch, int(trades)))
            if max_orders and count_today + entries_batch >= int(max_orders) and not is_exit:
                reasons.append("daily: %d orders placed today, the limit is %d"
                               % (count_today + entries_batch, int(max_orders)))
            if not c.get("allow_pending", True) and typ != MARKET:
                reasons.append("size: pending orders are off (\"mt5.allow_pending\": false)")

        # ---- spread and quote
        spread = spread_pips(spec, bid, ask) if spec else None
        max_spread = _f(c.get("max_spread_pips"))
        if is_exit:
            if bid is None:
                warns.append("no quote in the snapshot: the terminal fills the close at the market")
        else:
            if spec and bid is None:
                reasons.append("spread: no quote for %s in the snapshot (run mt5.py snapshot --write)" % sym)
            elif spread is not None and max_spread and spread > max_spread + 1e-9:
                reasons.append("spread: %s pips is over max_spread_pips (%s); wait for the spread to come back"
                               % (round(spread, 1), num(max_spread)))
            if qtime is not None and not is_exit:
                age = (now_utc - qtime).total_seconds()
                maxage = _f(c.get("max_quote_age_sec")) or 60
                if age > maxage:
                    reasons.append("spread: the quote is %d seconds old (max_quote_age_sec is %d); refresh the "
                                   "snapshot" % (int(age), int(maxage)))
                elif age < -60:
                    warns.append("the quote's time is %d seconds in the future: check the server offset" % int(-age))

        # ---- stops
        ent = entry_price(o, spec, quote) if spec else _f(o.get("price"))
        sl, tp = _f(o.get("sl")), _f(o.get("tp"))
        stop_level = _f(spec.get("trade_stops_level")) or 0.0

        def min_gap():
            return max(stop_level, (qspread or 0.0)) * point(spec) if spec else 0.0

        if not is_exit:
            if c.get("require_stop", True) and sl is None:
                reasons.append("stop: no stop-loss, and \"require_stop\" is true")
            if sl is not None and ent is not None:
                if side == "buy" and sl >= ent:
                    reasons.append("stop: a buy's stop-loss (%s) must be under the entry (%s)"
                                   % (price(sl, digits(spec)), price(ent, digits(spec))))
                if side == "sell" and sl <= ent:
                    reasons.append("stop: a sell's stop-loss (%s) must be over the entry (%s)"
                                   % (price(sl, digits(spec)), price(ent, digits(spec))))
                gap = abs(ent - sl)
                if gap < min_gap() - 1e-12 and gap > 0:
                    reasons.append("stop: the stop is %s points from the entry, the broker needs at least %s "
                                   "(stops level %s plus the spread %s)"
                                   % (num(gap / point(spec)), num(min_gap() / point(spec)), num(stop_level),
                                      num(qspread or 0)))
            if tp is not None and ent is not None:
                if side == "buy" and tp <= ent:
                    reasons.append("stop: a buy's take-profit (%s) must be over the entry (%s)"
                                   % (price(tp, digits(spec)), price(ent, digits(spec))))
                if side == "sell" and tp >= ent:
                    reasons.append("stop: a sell's take-profit (%s) must be under the entry (%s)"
                                   % (price(tp, digits(spec)), price(ent, digits(spec))))
                if abs(tp - ent) < min_gap() - 1e-12:
                    reasons.append("stop: the take-profit is inside the broker's stops level")
            if sl is not None and tp is not None and spec:
                for leg, name in ((sl, "stop-loss"), (tp, "take-profit")):
                    if leg <= 0:
                        reasons.append("stop: the %s is not a positive price" % name)
                    if abs(leg / point(spec) - round(leg / point(spec))) > 1e-4:
                        warns.append("the %s is not on the symbol's point grid (%s digits)"
                                     % (name, digits(spec)))

        # ---- money at risk
        risk_money, det = None, {}
        if spec and vol and ent and sl and not is_exit:
            risk_money, det = risk_of(o, spec, ctx, quote, _f(c.get("commission_per_lot")) or 0.0)
            per_trade = _f(c.get("max_loss_per_trade_usd"))
            pct = _f(c.get("risk_pct_per_trade"))
            if risk_money is None:
                reasons.append("risk: cannot work out the money at risk (no entry price or no stop)")
            else:
                if per_trade and risk_money > per_trade + 0.005:
                    reasons.append("risk: %s at risk is over max_loss_per_trade_usd (%s)"
                                   % (money(risk_money), money(per_trade)))
                if pct and balance and risk_money > balance * pct / 100.0 + 0.005:
                    reasons.append("risk: %s at risk is over risk_pct_per_trade (%s%% of %s = %s)"
                                   % (money(risk_money), num(pct), money(balance),
                                      money(balance * pct / 100.0)))
                used = loss_logged + loss_closed + loss_batch + risk_money
                daily = _f(c.get("max_daily_loss_usd"))
                if daily and used > daily + 0.005:
                    reasons.append("risk: %s at risk today (today's losses %s + entries at their stops %s + "
                                   "this one) is over max_daily_loss_usd (%s)"
                                   % (money(used), money(loss_closed), money(loss_logged + loss_batch),
                                      money(daily)))
                rr = det.get("rr")
                if tp is None:
                    warns.append("no take-profit: reward:risk cannot be measured; "
                                 "trader-alerts can watch the target instead")
                elif rr is not None and rr < (_f(c.get("min_reward_risk")) or 0) - 1e-9:
                    reasons.append("risk: reward:risk is %.2f, under min_reward_risk (%s)"
                                   % (rr, num(c.get("min_reward_risk"))))

        # ---- margin
        margin, mfrom = None, ""
        if spec and vol and not is_exit:
            margin, mfrom = margin_for(o, spec, ctx, quote)
            cap = _f(c.get("max_margin_use_pct")) or 0
            if margin is not None and free:
                if cap and margin > free * cap / 100.0 + 0.005:
                    reasons.append("margin: %s needed is over %s%% of free margin (%s)"
                                   % (money(margin), num(cap), money(free * cap / 100.0)))
                used_after = (_f(acct.get("margin")) or 0.0) + margin
                eq_after = account_balance(ctx)
                if used_after > 0 and lvl_before is not None:
                    level_after = eq_after / used_after * 100.0
                    floor = _f(c.get("min_margin_level_pct")) or 0
                    if floor and level_after < floor:
                        reasons.append("margin: margin level would be %.0f%%, under min_margin_level_pct (%s)"
                                       % (level_after, num(floor)))
                if cap and margin > free:
                    reasons.append("margin: the order needs %s but only %s is free" % (money(margin), money(free)))
        elif spec and is_exit:
            warns.append("closing frees margin; the terminal's own margin check runs at send time")

        # ---- the yes gate and the numbers a ticket shows
        info.append("%s %s lots of %s at %s, stop %s, target %s" % (
            side.upper(), num(vol), sym or "?", price(ent, digits(spec)) if ent else "?",
            price(sl, digits(spec)) if sl else "none", price(tp, digits(spec)) if tp else "none"))
        if det.get("pips") is not None:
            info.append("stop distance %.1f pips (%s per lot, %s for %s lots)" % (
                det["pips"], money(det.get("per_lot")), money(det.get("price")), num(vol)))
        if risk_money is not None:
            info.append("money at risk %s%s%s" % (
                money(risk_money), (" including %s commission" % money(det.get("commission")))
                if det.get("commission") else "",
                (" = %.2f%% of the account" % (risk_money / balance * 100.0)) if balance else ""))
        if spread is not None:
            info.append("spread %s pips (%s points); filling %s" % (
                ("%.1f" % spread), num(qspread), str(fill)))
        if margin is not None:
            info.append("margin %s (%s); free margin %s" % (money(margin), mfrom, money(free)))
        if qtime is not None:
            info.append("quote at %s New York" % to_eastern(qtime).strftime("%H:%M:%S"))
        info.append("terminal server time %s (UTC%+d), New York %s" % (
            st["now_server"].strftime("%a %H:%M"), int(st["offset"]),
            st["now_ny"].strftime("%a %H:%M")))
        warns.extend(warns_top)

        if not reasons and kind == "entry":
            entries_batch += 1
            loss_batch += risk_money or 0.0
        verdict = "BLOCK" if reasons else "PASS"
        res = {
            "index": idx, "symbol": sym, "side": side, "kind": kind,
            "venue": "mt5",
            "amount": "%s lots" % num(vol if vol is not None else 0),
            "value_usd": None,
            "entry_ref": round(ent, digits(spec)) if ent else None,
            "entry_ref_from": det.get("entry_from", ""),
            "stop": round(sl, digits(spec)) if sl else None,
            "target": round(tp, digits(spec)) if tp else None,
            "risk_per_share": None, "risk_per_unit": det.get("distance"),
            "max_loss": round(risk_money, 2) if risk_money is not None else None,
            "reward_risk": det.get("rr"),
            "volume": vol, "margin": round(margin, 2) if margin is not None else None,
            "spread_pips": round(spread, 2) if spread is not None else None,
            "pips_risk": round(det["pips"], 1) if det.get("pips") is not None else None,
            "commission": det.get("commission"),
            "risk_pct": round(risk_money / balance * 100.0, 2) if (risk_money is not None and balance) else None,
            "fingerprint": fingerprint(o),
            "verdict": verdict, "reasons": reasons, "warnings": warns, "info": info,
        }
        results.append(res)

    margin_used = sum((r.get("margin") or 0.0) for r in results if r["verdict"] == "PASS")
    return {
        "venue": "mt5",
        "results": results,
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "block": sum(1 for r in results if r["verdict"] == "BLOCK"),
        "account": {"login": acct.get("login"), "server": acct.get("server"),
                    "currency": acct.get("currency", "USD"), "balance": round(balance_only, 2),
                    "equity": round(_f(acct.get("equity")) or balance, 2),
                    "free_margin": round(free, 2),
                    "free_margin_after": round(max(0.0, free - margin_used), 2),
                    "margin_used_by_passed": round(margin_used, 2),
                    "margin_level": round(lvl_before, 1) if lvl_before else None,
                    "leverage": acct.get("leverage"), "trade_mode": acct.get("trade_mode", "demo"),
                    "hedge": acct.get("hedge")},
        "loss_today": round(loss_closed + loss_logged, 2),
        "realized_today": realized,
        "closed_today": nd,
        "warnings": warns_top,
        "server_offset_hours": off,
        "now_new_york": st["now_ny"].strftime("%Y-%m-%d %H:%M"),
        "now_server": st["now_server"].strftime("%Y-%m-%d %H:%M"),
        "rollover_window_ny": [st["rollover"][0].strftime("%H:%M"), st["rollover"][1].strftime("%H:%M")],
    }


def summary(res):
    """A short block of MT5 facts, for the report under the verdicts."""
    a = res.get("account") or {}
    lines = ["MT5 %s account %s on %s: balance %s, equity %s, free margin %s%s" % (
        str(a.get("trade_mode", "demo")).upper(), a.get("login") or "?",
        a.get("server") or "?", money(a.get("balance")), money(a.get("equity")),
        money(a.get("free_margin")),
        (", margin level %.0f%%" % a["margin_level"]) if a.get("margin_level") else "")]
    if res.get("closed_today"):
        lines.append("today's closed trades: %d, %s" % (res["closed_today"], money(res.get("realized_today"))))
    if res.get("loss_today"):
        lines.append("counted against the daily loss: %s" % money(res["loss_today"]))
    if res.get("rollover_window_ny"):
        lines.append("broker rollover %s to %s New York; terminal time %s (UTC%+d)" % (
            res["rollover_window_ny"][0], res["rollover_window_ny"][1], res.get("now_server"),
            int(res.get("server_offset_hours") or 0)))
    return "\n".join(lines)
