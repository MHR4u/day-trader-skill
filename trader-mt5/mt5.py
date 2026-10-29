#!/usr/bin/env python3
"""MetaTrader 5 for the day-trader pack: the terminal, the data, the orders
and the position management, in one command line. Standard library only when
it replays a saved snapshot; the real terminal needs the Windows-only
MetaTrader5 package (python -m pip install MetaTrader5) and a running,
logged-in MetaTrader 5.

    python3 mt5.py doctor                                  # can we talk to the terminal?
    python3 mt5.py init --write                            # a trader/config.json with the MT5 block
    python3 mt5.py account                                 # balance, equity, margin, free margin
    python3 mt5.py symbols --search EUR --limit 20          # the broker's real names (suffixes!)
    python3 mt5.py spec EURUSD.a                           # digits, tick value, lot ladder, stops level
    python3 mt5.py quote EURUSD XAUUSD --write             # quotes -> trader/prices.json
    python3 mt5.py bars EURUSD --tf M5 --count 500 --write --csv --yahoo
    python3 mt5.py levels EURUSD --tf M5 --or-minutes 60   # opening range, ATR, pivots, prev day H/L
    python3 mt5.py setup EURUSD --write-plan               # a plan.json trader-budget can size
    python3 mt5.py session EURUSD                          # server time, New York time, rollover, flat-by
    python3 mt5.py snapshot --write                        # -> trader/mt5/context.json (risk + sizing)
    python3 mt5.py positions                               # open trades, with risk at the stop
    python3 mt5.py orders                                  # pending orders
    python3 mt5.py history --days 30 --write               # journal: wins, expectancy, drawdown
    python3 mt5.py margin --symbol EURUSD --volume 0.35
    python3 mt5.py execute --index 1                       # the third gate: send the approved order
    python3 mt5.py manage trail --symbol EURUSD            # risk-reducing management
    python3 mt5.py manage close --symbol EURUSD --yes "yes"
    python3 mt5.py guard show|on|off|run                   # pre-authorized protective automation
    python3 mt5.py backtest EURUSD --tf M5 --count 5000    # honest stats from the bars you have

--replay PATH reads a saved snapshot instead of the terminal, which is how the
tests run and how you can look at everything on macOS or Linux. Add
--now "2026-10-20 10:00" to pin the clock (New York time).

The three gates before an order reaches the market are unchanged, they are
only spelled in MT5 words:

  1. trader-risk/check.py passed this exact order (fingerprint, today)
  2. trader-broker/ticket.py recorded your explicit yes for it, today
  3. mt5.py execute runs, on a demo account or with "mt5.allow_live": true

No order is ever sent from a yes alone, and no tool here treats "ok" or "sure"
as a yes. Orders that only close or tighten (manage close, trail, breakeven,
partial) cannot add risk; they need your yes too unless the guard file that
you turned on with an explicit yes covers them.

MT5 is Windows-only. On macOS or Linux use --replay with a snapshot copied
from the Windows machine, or run the pack on a Windows VPS next to the
terminal. "doctor" says exactly what is missing.
"""

import argparse
import datetime
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import mt5lib as L
except ImportError as e:                                   # pragma: no cover
    print("mt5.py: cannot load mt5lib.py next to it (%s)" % e, file=sys.stderr)
    raise

try:
    import mt5rules as R
except ImportError as e:                                   # pragma: no cover
    print("mt5.py: cannot load mt5rules.py next to it (%s)" % e, file=sys.stderr)
    raise

VERSION = "2.1"
MAGIC = 20261019
YES_WORDS = ("yes", "y")
DOUBT = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later", "hold",
         "unless", "if", "all", "every", "everything", "rest", "both", "them", "each"}
GUARD_ACTIONS = ("breakeven", "trail", "partial")


# ---------------------------------------------------------------- small helpers

def cfg_and_block(a):
    cfg = L.read_json(a.config, "config", required=False) or {}
    block = cfg.get("mt5") if isinstance(cfg.get("mt5"), dict) else {}
    merged = dict(R.MT5_DEFAULTS)
    merged.update({k: v for k, v in block.items() if v is not None})
    for sub in ("session", "guard"):
        s = dict(R.MT5_DEFAULTS[sub])
        s.update(block.get(sub) or {})
        merged[sub] = s
    for k in ("max_loss_per_trade_usd", "max_daily_loss_usd", "max_trades_per_day",
              "min_reward_risk", "require_stop", "blocked", "paper"):
        if cfg.get(k) is not None:
            merged[k] = cfg[k]
    return cfg, merged


def open_terminal(a, cfg):
    block = (cfg.get("mt5") if isinstance(cfg.get("mt5"), dict) else {}) or {}
    replay = a.replay or os.environ.get("MT5_REPLAY")
    merged = dict(cfg)
    merged["mt5"] = block
    term = L.Terminal(merged, replay=replay)
    return term


def now_of(a):
    return R.parse_now(getattr(a, "now", None))


def today_of(a, now):
    return R.to_eastern(now).date().isoformat()


def out_json(a):
    return bool(getattr(a, "json", False))


def warn(text):
    print(text, file=sys.stderr)


def plain_yes(reply, action_desc):
    """(ok, why). The same strict rule as trader-broker: starts with yes,
    names no batch, carries no condition."""
    raw = (reply or "").strip()
    if not raw:
        return False, "no reply"
    if "?" in raw:
        return False, "that is a question, not a yes"
    words = [w for w in raw.lower().replace(",", " ").split() if w]
    if not words or words[0] not in YES_WORDS:
        return False, "only a reply that starts with yes counts (not ok, sure, go, do it)"
    if DOUBT & set(words):
        return False, "the reply has a condition, a doubt or a batch word in it"
    return True, "explicit yes for %s" % action_desc


def require_yes(a, action_desc, guard_ok=False):
    """Raises unless the user's own words said yes, or the guard covers it."""
    if guard_ok and guard_enabled(a) and guard_allows(a, action_desc.split(":")[0].strip()):
        print("The guard file you enabled with a yes covers this protective action.")
        return
    ok, why = plain_yes(getattr(a, "yes", None), action_desc)
    if not ok:
        raise L.Mt5Error("nothing was sent: %s. Ask the user again, in plain words, for this one action, "
                         "and pass their reply with --yes \"...\"" % why)


def guard_path(a):
    return getattr(a, "guard", None) or "trader/mt5/guard.json"


def guard_doc(a):
    return L.read_json(guard_path(a), "guard file", required=False) or {"enabled": False, "actions": []}


def guard_enabled(a):
    return bool(guard_doc(a).get("enabled"))


def guard_allows(a, action):
    doc = guard_doc(a)
    if not doc.get("enabled"):
        return False
    actions = doc.get("actions") or list(GUARD_ACTIONS)
    return action in actions


def guard_state_path(a):
    """Next to the guard file, so a test or a second config cannot share it."""
    own = getattr(a, "guard_state", None)
    if own:
        return own
    guard = getattr(a, "guard", None)
    if guard:
        return os.path.join(os.path.dirname(os.path.abspath(guard)), "guard-state.json")
    return "trader/mt5/guard-state.json"


def guard_state(a):
    return L.read_json(guard_state_path(a), "guard state", required=False) or {"positions": {}}


def guard_mark(a, ticket, action):
    """Only the guard keeps a ledger. A hand-run manage command does not write
    one: nothing is automated there, so nothing needs de-duplicating."""
    if not os.path.exists(guard_path(a)):
        return
    st = guard_state(a)
    st.setdefault("positions", {}).setdefault(str(ticket), {})[action] = True
    L.write_json(guard_state_path(a), st)


def guard_done(a, ticket, action):
    return bool((guard_state(a).get("positions") or {}).get(str(ticket), {}).get(action))


def record_state(a, rec):
    state = L.read_json(a.state, "broker state", required=False) or {"orders": []}
    state.setdefault("orders", []).append(rec)
    L.write_json(a.state, state)
    return state


def risk_pass(a, order, today):
    """The fingerprint of this exact order, PASSED today, from trader-risk."""
    risk = L.read_json(a.risk, "risk check", required=False)
    fp = R.fingerprint(order)
    if not risk:
        raise L.Mt5Error("trader-risk has not checked this order: run check.py first (nothing was sent)")
    if risk.get("date") != today:
        raise L.Mt5Error("the risk check is from %s, not today: run check.py again (nothing was sent)"
                         % risk.get("date"))
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            if r.get("verdict") != "PASS":
                raise L.Mt5Error("trader-risk BLOCKED this order: %s (nothing was sent)"
                                 % "; ".join(r.get("reasons") or ["blocked"]))
            return r
    raise L.Mt5Error("this exact order is not in the last risk check (it changed or is new): run check.py "
                     "again (nothing was sent)")


def approval(a, order, today):
    """Your recorded yes for this exact order, today."""
    state = L.read_json(a.state, "broker state", required=False) or {"orders": []}
    fp = R.fingerprint(order)
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and R.rec_day(rec) == today:
            found = rec
    if not found:
        raise L.Mt5Error("no yes recorded for this order today. Show it with ticket.py show, ask the user, "
                         "record their reply with ticket.py approve --index N --reply \"...\", then run "
                         "execute again (nothing was sent)")
    if found.get("status") == "approved":
        return found
    raise L.Mt5Error("order already recorded as %s at %s: nothing to send. A new order needs a new check and "
                     "a new yes (nothing was sent)" % (found.get("status"), found.get("at")))


def account_guard(term, block, action="trade"):
    """A REAL account needs allow_live: true, on purpose, in the config."""
    acct = term.account() or {}
    mode = str(acct.get("trade_mode") or "demo").lower()
    if mode in ("real", "live") and not block.get("allow_live", False):
        raise L.Mt5Error("nothing was sent: this is a REAL-money account and \"mt5.allow_live\" is false. "
                         "Change it in trader/config.json on purpose, or use the demo account")
    term_info = term.terminal_info() or {}
    if term_info.get("trade_allowed") is False:
        raise L.Mt5Error("nothing was sent: trading is off in the terminal (Tools > Options > Expert Advisors, "
                         "and the AutoTrading button)")
    if acct.get("trade_allowed") is False:
        raise L.Mt5Error("nothing was sent: this login is not allowed to trade")
    return acct


def order_of(a):
    doc = L.read_json(a.orders, "orders file (run trader-budget lots.py first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise L.Mt5Error("no orders in %s" % a.orders)
    idx = a.index
    if idx is None:
        if len(orders) != 1:
            raise L.Mt5Error("%d orders in %s: say which one with --index N" % (len(orders), a.orders))
        idx = 1
    if not 1 <= idx <= len(orders):
        raise L.Mt5Error("there is no order %d (there are %d)" % (idx, len(orders)))
    order = orders[idx - 1]
    if not R.is_mt5(order):
        raise L.Mt5Error("order %d is not an MT5 order (venue %r): use trader-broker/ticket.py for Alpaca or "
                         "IBKR" % (idx, order.get("venue")))
    return idx, order


def position_of(term, a):
    positions = term.positions()
    if not positions:
        raise L.Mt5Error("no open positions: nothing to manage")
    if getattr(a, "ticket", None):
        for p in positions:
            if int(p.get("ticket") or 0) == int(a.ticket):
                return p
        raise L.Mt5Error("no position with ticket %s" % a.ticket)
    if not getattr(a, "symbol", None):
        if len(positions) == 1:
            return positions[0]
        raise L.Mt5Error("say which position: --symbol EURUSD or --ticket 123456")
    sym = str(a.symbol).upper()
    mine = [p for p in positions if str(p.get("symbol", "")).upper() == sym]
    if not mine:
        raise L.Mt5Error("no open %s position" % sym)
    if len(mine) > 1:
        raise L.Mt5Error("%d %s positions: say which ticket" % (len(mine), sym))
    return mine[0]


def fill_volume(spec, vol, want=None):
    """A partial close volume that MT5 will accept."""
    total = _f(vol) or 0.0
    if want is None or want <= 0:
        return total
    v = L._f(want) or 0.0
    step = _f(spec.get("volume_step")) or 0.01
    v = math.floor(v / step + 1e-9) * step
    v = round(v, 8)
    lo = _f(spec.get("volume_min")) or 0.01
    if v >= total - 1e-9:
        return total
    if v < lo - 1e-12:
        raise L.Mt5Error("closing %s lots is under the symbol's minimum %s: close the whole position instead"
                         % (L.num(v), L.num(lo)))
    if total - v < lo - 1e-12:
        return total
    return v


def _f(x):
    return L._f(x)


# ---------------------------------------------------------------- reports

def print_account(acct, term=None, block=None):
    if not acct:
        print("No account: the terminal is not connected.")
        return
    mode = str(acct.get("trade_mode") or "demo").upper()
    print("MT5 %s account %s on %s (%s)" % (mode, acct.get("login"), acct.get("server"), acct.get("company")))
    print("  balance %s, equity %s, floating %s" % (L.money(acct.get("balance")), L.money(acct.get("equity")),
                                                     L.money(acct.get("profit"))))
    lvl = acct.get("margin_level") or 0
    print("  margin used %s of %s, free %s, margin level %s" % (
        L.money(acct.get("margin")), L.money(acct.get("equity")), L.money(acct.get("margin_free")),
        ("%.0f%%" % lvl) if lvl else "n/a (nothing open)"))
    print("  leverage 1:%s, %s margin, trading %s, algo trading %s" % (
        L.num(acct.get("leverage")), acct.get("margin_mode") or "?",
        "allowed" if acct.get("trade_allowed") else "NOT allowed",
        "allowed" if acct.get("trade_expert") else "NOT allowed"))
    if mode in ("REAL", "LIVE"):
        print("  THIS IS REAL MONEY. Entries stay blocked unless \"mt5.allow_live\": true.")
    elif str(acct.get("trade_mode")) == "contest":
        print("  contest account: real prices, virtual money.")


def _margin_words(spec):
    """How much margin one lot takes, in the words a trader uses."""
    if _f(spec.get("margin_initial")):
        return "%s%% of the notional" % L.num(spec.get("margin_initial"))
    if _f(spec.get("leverage_ratio")):
        return "1:%s (the broker's leverage for this symbol)" % L.num(spec.get("leverage_ratio"))
    return "the account's leverage"


def print_spec(sym_doc):
    sym = sym_doc.get("symbol") or "?"
    p = _f(sym_doc.get("point")) or 0.0
    pip = (p * 10) if (int(sym_doc.get("digits") or 5) >= 1) else p
    tv = _f(sym_doc.get("trade_tick_value")) or 0.0
    ts = _f(sym_doc.get("trade_tick_size")) or p
    per_pip = (pip / ts) * tv if ts else 0.0
    print("%s %s" % (sym, ("(" + sym_doc.get("description") + ")") if sym_doc.get("description") else ""))
    print("  digits %s, point %s, pip %s, contract %s %s" % (
        sym_doc.get("digits"), L.num(p), L.num(pip), L.num(sym_doc.get("trade_contract_size")),
        sym_doc.get("currency_base") or ""))
    print("  tick size %s, tick value %s, one pip is about %s per 1.00 lot" % (
        L.num(ts), L.money(tv), L.money(per_pip)))
    print("  volume %s to %s in steps of %s" % (L.num(sym_doc.get("volume_min")),
                                                L.num(sym_doc.get("volume_max")),
                                                L.num(sym_doc.get("volume_step"))))
    print("  spread %s points, stops level %s points, freeze level %s points" % (
        L.num(sym_doc.get("spread")), L.num(sym_doc.get("trade_stops_level")),
        L.num(sym_doc.get("trade_freeze_level"))))
    print("  margin %s, swap long %s / short %s (%s), trade mode %s" % (
        _margin_words(sym_doc), L.num(sym_doc.get("swap_long")), L.num(sym_doc.get("swap_short")),
        sym_doc.get("swap_mode") or "?", sym_doc.get("trade_mode")))
    print("  filling %s, profit currency %s" % (", ".join(sym_doc.get("filling_modes") or []),
                                                 sym_doc.get("currency_profit")))
    for s in sym_doc.get("sessions") or []:
        print("  session day %s: %s to %s (server time)" % (s.get("day"), s.get("from"), s.get("to")))


def print_quote(sym, q, spec, offset=0.0):
    if not q or q.get("bid") is None:
        print("%s: no quote (is the symbol in Market Watch?)" % sym)
        return
    p = _f((spec or {}).get("point")) or 0.00001
    d = int((spec or {}).get("digits") or 5)
    spread_points = (q["ask"] - q["bid"]) / p if p else 0
    pip = p * 10 if d >= 1 else p
    stamp = q.get("time_utc") or q.get("time")
    if isinstance(stamp, (int, float)):
        stamp = L.iso(stamp, offset)
    print("%s  bid %s  ask %s  spread %s points (%.1f pips)  %s" % (
        sym, L.price(q["bid"], d), L.price(q["ask"], d), L.num(spread_points),
        spread_points * p / pip if pip else 0, stamp or "time unknown"))


def print_positions(term, positions):
    if not positions:
        print("No open positions.")
        return
    total = 0.0
    for p in positions:
        spec = term.symbol(p.get("symbol")) or {}
        d = int(spec.get("digits") or 5)
        pips = None
        if spec:
            pip = (_f(spec.get("point")) or 0.00001) * 10
            pips = (p["price_current"] - p["price_open"]) / pip if p["type"] == "buy" else \
                (p["price_open"] - p["price_current"]) / pip
        risk = None
        if p.get("sl"):
            per_unit = (_f(spec.get("trade_tick_value")) or 0.0) / (_f(spec.get("trade_tick_size")) or
                                                                   (_f(spec.get("point")) or 1e-9))
            risk = abs(p["price_open"] - p["sl"]) * per_unit * (_f(p.get("volume")) or 0.0)
        total += _f(p.get("profit")) or 0.0
        print("#%s %s %s %s lots at %s, now %s, sl %s, tp %s" % (
            p.get("ticket"), p["type"].upper(), p.get("symbol"), L.num(p.get("volume")),
            L.price(p.get("price_open"), d), L.price(p.get("price_current"), d),
            L.price(p.get("sl"), d) if p.get("sl") else "none", L.price(p.get("tp"), d) if p.get("tp") else "none"))
        print("    profit %s, swap %s%s%s" % (
            L.money(p.get("profit")), L.money(p.get("swap")),
            (" (%s pips)" % ("%.1f" % pips)) if pips is not None else "",
            (", risk at the stop %s" % L.money(risk)) if risk else ", NO STOP"))
    print("Floating now: %s" % L.money(total))


def print_orders(term, orders):
    if not orders:
        print("No pending orders.")
        return
    for o in orders:
        spec = term.symbol(o.get("symbol")) or {}
        d = int(spec.get("digits") or 5)
        print("#%s %s %s %s lots at %s, sl %s, tp %s, %s, %s" % (
            o.get("ticket"), str(o.get("type", "")).replace("_", " ").upper(), o.get("symbol"),
            L.num(o.get("volume")), L.price(o.get("price"), d),
            L.price(o.get("sl"), d) if o.get("sl") else "none",
            L.price(o.get("tp"), d) if o.get("tp") else "none",
            o.get("type_time") or "?", ("expires " + str(o.get("expiration"))) if o.get("expiration") else "no expiry"))


def session_lines(term, block, symbol=None, now=None):
    acct = term.account() or {}
    term_info = term.terminal_info() or {}
    now_utc = now or R.parse_now(None)
    off = term.offset if term.offset is not None else 0.0
    st = R.session_state(dict(block, session=block.get("session") or {}), {"account": acct,
                                                                          "server_offset_hours": off}, now_utc)
    lines = ["Terminal: %s (%s), connected %s, trading %s, build %s" % (
        term_info.get("name") or "?", term_info.get("company") or "?", "yes" if term_info.get("connected") else "NO",
        "allowed" if term_info.get("trade_allowed") else "OFF", term_info.get("build") or "?")]
    lines.append("Server time %s (UTC%+d), New York %s, UTC %s" % (
        st["now_server"].strftime("%a %Y-%m-%d %H:%M"), int(off), st["now_ny"].strftime("%a %H:%M"),
        now_utc.strftime("%H:%M")))
    start, end = st["rollover"]
    lines.append("Broker rollover %s to %s New York: no new entries, spreads widen" % (
        start.strftime("%H:%M"), end.strftime("%H:%M")))
    sess = block.get("session") or {}
    lines.append("Entry window %s to %s New York, flat by %s; open %s" % (
        sess.get("no_entries_before") or "off", sess.get("no_entries_after") or "off",
        sess.get("flat_by") or "off", st["now_ny"].strftime("%A")))
    if symbol:
        spec = term.symbol(symbol) or {}
        q = term.quote(spec.get("symbol") or symbol) or {}
        if not spec:
            lines.append("%s: the terminal does not know that symbol; check the suffix with: mt5.py symbols "
                         "--search %s" % (symbol, symbol[:3]))
        else:
            open_now, why = R.symbol_open(spec, st["now_server"])
            lines.append("%s: %s%s" % (spec.get("symbol"), "open for trading" if open_now else "closed",
                                       (" (" + why + ")") if why else ""))
            print_quote(spec.get("symbol"), q, spec, term.offset)
            lines.append("time to flat-by: %s" % _until(st["now_ny"], sess.get("flat_by")))
    return "\n".join(lines)


def _until(now_ny, hhmm_text):
    if not hhmm_text:
        return "not set"
    try:
        h, m = [int(x) for x in str(hhmm_text).split(":")[:2]]
    except ValueError:
        return "not set"
    target = now_ny.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now_ny:
        target += datetime.timedelta(days=1)
    mins = int((target - now_ny).total_seconds() // 60)
    return "%d h %02d min" % (mins // 60, mins % 60)


# ---------------------------------------------------------------- snapshot

def build_snapshot(term, cfg, block, paths, extra_symbols=(), days=2, now=None):
    now_utc = now or R.parse_now(None)
    acct = term.account() or {}
    term_info = term.terminal_info() or {}
    wanted = []
    for name in list(extra_symbols) + list(block.get("symbols") or []) + list(block.get("watchlist") or []):
        if name:
            wanted.append(str(name).upper())
    for key in ("plan", "orders"):
        doc = L.read_json(paths.get(key), "%s file" % key, required=False) or {}
        if isinstance(doc, dict):
            if doc.get("symbol"):
                wanted.append(str(doc["symbol"]).upper())
            for o in doc.get("orders") or []:
                if o.get("symbol"):
                    wanted.append(str(o["symbol"]).upper())
    wanted += [str(p.get("symbol", "")).upper() for p in term.positions() if p.get("symbol")]
    wanted += [str(p.get("symbol", "")).upper() for p in term.orders() if p.get("symbol")]
    wanted = [s for s in dict.fromkeys(wanted) if s]
    if not wanted:
        # nothing named yet: snapshot the watchlist, so lots.py and check.py
        # have a spec and a quote to work with
        try:
            visible = [str(s.get("symbol") or "") for s in term.symbols() if s.get("visible", True)]
        except L.Mt5Error:
            visible = []
        wanted = [s for s in dict.fromkeys(visible) if s][:25]
        fallback = True
    else:
        fallback = False
    symbols, quotes, missing = {}, {}, []
    for name in wanted:
        real = term.spec_with_suffix(name)
        spec = term.symbol(real)
        if not spec:
            missing.append(name)
            continue
        # the spec carries its own tick, so risk checks work even when the
        # quotes block is trimmed later
        tick = term.quote(real) or {}
        spec = dict(spec)
        spec["tick"] = {k: tick.get(k) for k in ("bid", "ask", "time", "time_utc") if tick.get(k) is not None}
        if tick.get("bid") is not None and tick.get("ask") is not None:
            tick = dict(tick)
            tick["time_utc"] = tick.get("time_utc") or L.iso(tick.get("time"), term.offset or 0)
            p = _f(spec.get("point")) or 1.0
            tick["spread_points"] = round((tick["ask"] - tick["bid"]) / p, 1)
            quotes[real] = tick
        symbols[real] = spec
    deals = term.deals(days=days, end=now_utc)
    return {
        "created_by": "trader-mt5", "version": VERSION,
        "as_of": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server_offset_hours": term.offset or 0.0,
        "terminal": term_info, "account": acct,
        "symbols": symbols, "quotes": quotes,
        "positions": term.positions(), "orders": term.orders(),
        "deals": deals, "missing": missing, "from_watchlist": fallback,
        "note": "Read-only snapshot of MetaTrader 5. trader-risk and trader-budget read it; nothing here "
                "places an order.",
    }


# ---------------------------------------------------------------- journal

def journal(deals, days=30):
    """Closed trades and the honest numbers, from the terminal's own deals."""
    by_pos = {}
    for d in deals or []:
        if str(d.get("entry")) in ("in", "out", "inout", "out_by") and d.get("position_id"):
            by_pos.setdefault(d["position_id"], []).append(d)
    trades = []
    for pid, ds in by_pos.items():
        ds.sort(key=lambda x: str(x.get("time_utc") or ""))
        opens = [d for d in ds if str(d.get("entry")) == "in"]
        closes = [d for d in ds if str(d.get("entry")) in ("out", "out_by")]
        if not closes:
            continue
        volume = sum(_f(d.get("volume")) or 0 for d in closes)
        result = sum(sum(_f(d.get(k)) or 0 for k in ("profit", "swap", "commission", "fee")) for d in ds)
        trades.append({
            "position_id": pid, "symbol": (closes[0].get("symbol") or ""),
            "volume": round(volume, 8), "profit": round(result, 2),
            "open_time": opens[0].get("time_utc") if opens else None,
            "close_time": closes[-1].get("time_utc"),
            "commission": round(sum(_f(d.get("commission")) or 0 for d in ds), 2),
            "swap": round(sum(_f(d.get("swap")) or 0 for d in ds), 2),
            "deals": len(ds),
        })
    trades.sort(key=lambda t: str(t.get("close_time") or ""))
    wins = [t for t in trades if t["profit"] > 0]
    losses = [t for t in trades if t["profit"] < 0]
    gross_win = sum(t["profit"] for t in wins)
    gross_loss = sum(-t["profit"] for t in losses)
    curve, peak, dd, dd_abs = 0.0, 0.0, 0.0, 0.0
    for t in trades:
        curve += t["profit"]
        peak = max(peak, curve)
        dd_abs = max(dd_abs, peak - curve)
        if peak > 0:
            dd = max(dd, (peak - curve) / peak * 100.0)
    per_symbol, per_day = {}, {}
    for t in trades:
        s = per_symbol.setdefault(t["symbol"] or "?", {"trades": 0, "profit": 0.0})
        s["trades"] += 1
        s["profit"] += t["profit"]
        day = str(t.get("close_time") or "")[:10]
        if day:
            per_day[day] = round(per_day.get(day, 0.0) + t["profit"], 2)
    total = sum(t["profit"] for t in trades)
    n = len(trades)
    return {
        "from": (deals[0].get("time_utc") if deals else None),
        "to": (deals[-1].get("time_utc") if deals else None),
        "closed_trades": n, "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(len(wins) / n * 100.0, 1) if n else None,
        "net_profit": round(total, 2), "gross_win": round(gross_win, 2), "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "expectancy": round(total / n, 2) if n else None,
        "best": max((t["profit"] for t in trades), default=None),
        "worst": min((t["profit"] for t in trades), default=None),
        "max_drawdown": round(dd_abs, 2), "max_drawdown_pct": round(dd, 1) if dd else None,
        "commission": round(sum(t["commission"] for t in trades), 2),
        "swap": round(sum(t["swap"] for t in trades), 2),
        "per_symbol": per_symbol, "per_day": per_day,
        "trades": trades,
    }


def print_journal(j):
    if not j["closed_trades"]:
        print("No closed trades in the terminal's history for that window.")
        return
    print("Closed trades %d: %d wins, %d losses (%s%% win rate)" % (
        j["closed_trades"], j["wins"], j["losses"], L.num(j["win_rate_pct"])))
    print("Net %s, gross win %s, gross loss %s, profit factor %s" % (
        L.money(j["net_profit"]), L.money(j["gross_win"]), L.money(j["gross_loss"]), L.num(j["profit_factor"])))
    print("Average win %s, average loss %s, expectancy %s per trade" % (
        L.money(j["avg_win"]), L.money(j["avg_loss"]), L.money(j["expectancy"])))
    print("Best %s, worst %s, max drawdown %s%s" % (
        L.money(j["best"]), L.money(j["worst"]), L.money(j["max_drawdown"]),
        (" (%s%% of the peak)" % L.num(j["max_drawdown_pct"])) if j.get("max_drawdown_pct") else ""))
    print("Commission %s, swap %s" % (L.money(j["commission"]), L.money(j["swap"])))
    if j.get("per_symbol"):
        print("By symbol: " + ", ".join("%s %s (%d)" % (s, L.money(v["profit"]), v["trades"])
                                       for s, v in sorted(j["per_symbol"].items(),
                                                          key=lambda kv: -kv[1]["profit"])))
    days = sorted(j.get("per_day", {}).items())[-7:]
    if days:
        print("By day: " + ", ".join("%s %s" % (d, L.money(p)) for d, p in days))
    print("This is your own realised history, not a prediction. Education and tooling, not financial advice.")


# ---------------------------------------------------------------- levels, setup

def bars_by_session(bars, offset=0.0):
    """Group bars by New York date, using the server offset."""
    out = {}
    for b in bars:
        ny = R.to_eastern(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=b["t"] - (offset or 0) * 3600))
        out.setdefault(ny.date().isoformat(), []).append(b)
    return out


def atr(bars, n=14):
    if len(bars) < 2:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    use = trs[-n:] if len(trs) >= n else trs
    return sum(use) / len(use)


def ema(values, n):
    if not values:
        return []
    k = 2.0 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def bar_ny(bar, offset):
    return R.to_eastern(datetime.datetime(1970, 1, 1) +
                        datetime.timedelta(seconds=bar["t"] - (offset or 0) * 3600))


def levels(sym, spec, bars, tf, or_minutes, block, offset=0.0):
    if not bars:
        raise L.Mt5Error("no bars for %s: is the symbol in Market View and the market open?" % sym)
    d = int(spec.get("digits") or 5)
    day = bars_by_session(bars, offset)
    last_day = sorted(day)[-1]
    per_bar_min = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}.get(tf, 5)
    n_or = max(1, int(round(or_minutes / per_bar_min)))
    sess_open = R.hhmm((block.get("session") or {}).get("open") or "00:00", "mt5.session.open")
    today_bars = [b for b in day[last_day] if bar_ny(b, offset).time() >= sess_open] or day[last_day]
    or_bars = today_bars[:n_or]
    prev_days = sorted(day)[:-1]
    prev = [b for b in (day[prev_days[-1]] if prev_days else [])
            if bar_ny(b, offset).time() >= sess_open] or (day[prev_days[-1]] if prev_days else [])
    out = {
        "symbol": sym, "timeframe": tf, "day": last_day, "offset_hours": offset,
        "session_open": sess_open.strftime("%H:%M"),
        "session_open_bar": L.iso(or_bars[0]["t"], offset) if or_bars else None,
        "opening_range": {"high": max(b["h"] for b in or_bars), "low": min(b["l"] for b in or_bars),
                          "mid": (max(b["h"] for b in or_bars) + min(b["l"] for b in or_bars)) / 2.0,
                          "minutes": or_minutes, "bars": len(or_bars)} if or_bars else None,
        "day": last_day,
        "day_high": max(b["h"] for b in today_bars), "day_low": min(b["l"] for b in today_bars),
        "last": bars[-1]["c"], "atr": atr(bars),
        "prev_day": {"high": max(b["h"] for b in prev), "low": min(b["l"] for b in prev),
                     "close": prev[-1]["c"], "open": prev[0]["o"]} if prev else None,
        "bars": len(bars), "last_bar": L.iso(bars[-1]["t"], offset),
    }
    if out["prev_day"]:
        h, l, c = out["prev_day"]["high"], out["prev_day"]["low"], out["prev_day"]["close"]
        p = (h + l + c) / 3.0
        out["pivots"] = {"pivot": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + (h - l),
                         "s2": p - (h - l), "r3": h + 2 * (p - l), "s3": l - 2 * (h - p)}
    for k in ("opening_range", "prev_day", "pivots"):
        if k in out and out[k]:
            out[k] = {kk: (round(vv, d) if isinstance(vv, float) else vv) for kk, vv in out[k].items()}
    for k in ("day_high", "day_low", "last", "atr"):
        if out.get(k) is not None:
            out[k] = round(out[k], d)
    return out


def setup(sym, spec, bars, tf, block, quote, lv, rr, or_minutes):
    """A plan from what the chart shows: trend filter, the opening range, an
    ATR stop, a target at RR. Honest and simple: it says wait when there is
    nothing to trade."""
    if not bars or len(bars) < 30:
        raise L.Mt5Error("not enough bars for a setup on %s: fetch at least 200 with mt5.py bars" % sym)
    d = int(spec.get("digits") or 5)
    closes = [b["c"] for b in bars]
    e_fast, e_slow = ema(closes, 50)[-1], ema(closes, 200)[-1] if len(closes) >= 200 else ema(closes, 100)[-1]
    a = lv.get("atr") or atr(bars) or 0.0
    last = bars[-1]["c"]
    bid = quote.get("bid") or last
    ask = quote.get("ask") or last
    or_high = lv["opening_range"]["high"]
    or_low = lv["opening_range"]["low"]
    or_mid = lv["opening_range"]["mid"]
    trend = "up" if e_fast > e_slow else "down"
    spread_pips = (ask - bid) / ((_f(spec.get("point")) or 1e-5) * 10)
    checks = [
        "trend on %s: EMA50 %s EMA200 %s, so %s" % (tf, L.price(e_fast, d), L.price(e_slow, d), trend),
        "last %s, opening range %s to %s (%s minutes)" % (L.price(last, d), L.price(or_low, d),
                                                          L.price(or_high, d), or_minutes),
        "ATR(14) %s (%s pips), spread %.1f pips" % (L.price(a, d), L.num(a / ((_f(spec.get("point")) or 1e-5) * 10))
                                                    if a else "?", spread_pips),
    ]
    verdict, why = "wait", []
    side = None
    if trend == "up" and last > or_high:
        side, verdict = "buy", "ready"
        why.append("price closed over the opening range high while the trend is up")
    elif trend == "down" and last < or_low:
        side, verdict = "sell", "ready"
        why.append("price closed under the opening range low while the trend is down")
    else:
        why.append("no close outside the opening range in the trend's direction yet")
    if lv.get("prev_day"):
        pdh, pdl = lv["prev_day"]["high"], lv["prev_day"]["low"]
        if last > pdh * 0.9995:
            checks.append("price is at or above yesterday's high %s: a breakout needs volume" % L.price(pdh, d))
        elif last < pdl * 1.0005:
            checks.append("price is at or below yesterday's low %s" % L.price(pdl, d))
    if spread_pips and spread_pips > (_f(block.get("max_spread_pips")) or 2.0):
        verdict = "wait"
        why.append("the spread is %.1f pips, over the limit" % spread_pips)
    entry = ask if side == "buy" else bid
    stop = None
    if side and a:
        # half an ATR behind the entry, but never tighter than the range's mid:
        # the calmer of the two stops, then the target is that R multiple of it
        if side == "buy":
            stop = min(entry - 0.5 * a, or_mid)
        else:
            stop = max(entry + 0.5 * a, or_mid)
        stop = round(stop, d)
        # the target is rounded away from the entry, so the plan's own reward
        # to risk is never a hair under the RR it promises
        span = abs(entry - stop) * rr
        step = 10 ** (-d)
        if side == "buy":
            target = math.ceil((entry + span) / step) * step
        else:
            target = math.floor((entry - span) / step) * step
        target = round(target, d)
    plan = {
        "created_by": "trader-mt5", "venue": "mt5", "symbol": spec.get("symbol") or sym, "side": side or "buy",
        "date": lv["day"], "setup": "orb", "setup_label": "opening-range breakout with an ATR stop",
        "interval": tf, "entry": round(entry, d) if entry else None, "entry_time": None,
        "opening_range": {"high": or_high, "low": or_low, "mid": or_mid, "minutes": or_minutes},
        "stop": stop if side else None, "stop_rule": "or_mid/atr", "stop_label": "half an ATR, behind the range mid",
        "target": target if side else None, "target_r": rr, "target_label": "%sR" % L.num(rr),
        "risk_per_unit": round(abs(entry - stop), d) if (side and stop) else None,
        "reward_risk": rr if side else None,
        "flat_by": (block.get("session") or {}).get("flat_by"),
        "verdict": verdict, "checks": checks + why, "trend": trend,
        "atr": round(a, d) if a else None, "spread_pips": round(spread_pips, 1) if spread_pips else None,
        "quote_time": quote.get("time_utc"),
    }
    return plan


def print_levels(lv):
    sym = lv["symbol"]
    print("%s %s, day %s (server offset UTC%+d)" % (sym, lv["timeframe"], lv["day"], int(lv["offset_hours"])))
    if lv.get("opening_range"):
        r = lv["opening_range"]
        print("  opening range (%s min): high %s, low %s, mid %s" % (
            r["minutes"], L.num(r["high"]), L.num(r["low"]), L.num(r["mid"])))
    print("  day high %s, day low %s, last %s" % (L.num(lv["day_high"]), L.num(lv["day_low"]), L.num(lv["last"])))
    if lv.get("atr"):
        print("  ATR(14) %s" % L.num(lv["atr"]))
    if lv.get("prev_day"):
        p = lv["prev_day"]
        print("  yesterday: high %s, low %s, close %s" % (L.num(p["high"]), L.num(p["low"]), L.num(p["close"])))
    if lv.get("pivots"):
        q = lv["pivots"]
        print("  pivots: R3 %s R2 %s R1 %s P %s S1 %s S2 %s S3 %s" % tuple(
            L.num(q[k]) for k in ("r3", "r2", "r1", "pivot", "s1", "s2", "s3")))
    print("  %d bars, last %s" % (lv["bars"], lv.get("last_bar")))


def print_setup(plan):
    print("SETUP %s %s: %s" % (plan["symbol"], plan["side"].upper(), plan["verdict"].upper()))
    for c in plan["checks"]:
        print("  - " + c)
    if plan.get("stop"):
        print("  entry %s, stop %s (%s), target %s (%s)" % (
            L.num(plan["entry"]), L.num(plan["stop"]), plan["stop_label"], L.num(plan["target"]),
            plan["target_label"]))
        print("  flat by %s New York" % (plan.get("flat_by") or "the session end"))
    print("Next: lots.py --write, check.py, ticket.py show, then mt5.py execute. Nothing is sent until then.")


# ---------------------------------------------------------------- backtest

def backtest(sym, spec, bars, tf, offset, rr=2.0, or_minutes=60, stop_mode="or", atr_mult=1.0,
             spread_points=0.0, commission_per_lot=0.0, allow_short=True, flat_by="20:55",
             session_open="03:00"):
    """One simple rule, no lookahead, costs included:

      at the session open, take the opening range (or_minutes); the first bar
      that CLOSES outside it is the entry (that bar's close, plus the spread
      for a buy, minus it for a sell); the stop is the range's far side or
      half an ATR; the target is rr times that risk; whichever comes first
      wins, and a bar that touches both is counted as the stop filling first.
      Anything still open at flat_by is closed at its close.

    It returns the trades and the stats. A small sample is a small sample:
    print how few trades there are, always."""
    if len(bars) < 30:
        raise L.Mt5Error("not enough bars to backtest: fetch more with mt5.py bars --count 5000")
    d = int(spec.get("digits") or 5)
    pt = _f(spec.get("point")) or 10.0 ** (-d)
    pip = pt * 10 if d >= 1 else pt
    per_unit = (_f(spec.get("trade_tick_value")) or 0.0) / (_f(spec.get("trade_tick_size")) or pt)
    if not per_unit:
        per_unit = _f(spec.get("trade_contract_size")) or 100000.0
    per_bar = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}.get(tf, 5)
    n_or = max(1, int(round(or_minutes / per_bar)))
    groups = bars_by_session(bars, offset)
    hh, mm = [int(x) for x in str(flat_by or "20:55").split(":")[:2]]
    so = R.hhmm(session_open, "session_open")
    trades = []
    for day in sorted(groups):
        day_bars = [b for b in groups[day] if bar_ny(b, offset).time() >= so]
        if len(day_bars) < n_or + 3:
            continue
        or_bars = day_bars[:n_or]
        hi = max(b["h"] for b in or_bars)
        lo = min(b["l"] for b in or_bars)
        mid = (hi + lo) / 2.0
        a = atr(or_bars, n_or) or (hi - lo)
        side, entry, stop, idx = None, None, None, None
        for i in range(n_or, len(day_bars)):
            b = day_bars[i]
            if b["c"] > hi and allow_short is not None:
                side, entry, stop, idx = "buy", b["c"] + spread_points * pt, None, i
                break
            if b["c"] < lo and allow_short:
                side, entry, stop, idx = "sell", b["c"] - spread_points * pt, None, i
                break
        if side is None:
            continue
        if stop_mode == "atr":
            stop = entry - atr_mult * a if side == "buy" else entry + atr_mult * a
        elif stop_mode == "mid":
            stop = mid
        else:
            stop = lo if side == "buy" else hi
        risk = abs(entry - stop)
        if risk <= pt * 2:
            continue
        target = entry + rr * risk if side == "buy" else entry - rr * risk
        exit_price, exit_time, why = None, None, None
        for b in day_bars[idx + 1:]:
            t = R.to_eastern(datetime.datetime(1970, 1, 1) + datetime.timedelta(
                seconds=b["t"] - (offset or 0) * 3600))
            if t.time() >= datetime.time(hh, mm):
                exit_price, exit_time, why = b["c"], t, "flat by %s" % flat_by
                break
            if side == "buy":
                if b["l"] <= stop:
                    exit_price, exit_time, why = stop, t, "stop"
                    break
                if b["h"] >= target:
                    exit_price, exit_time, why = target, t, "target"
                    break
            else:
                if b["h"] >= stop:
                    exit_price, exit_time, why = stop, t, "stop"
                    break
                if b["l"] <= target:
                    exit_price, exit_time, why = target, t, "target"
                    break
        if exit_price is None:
            b = day_bars[-1]
            exit_price, exit_time, why = b["c"], None, "session end"
        gross = (exit_price - entry) if side == "buy" else (entry - exit_price)
        r = gross / risk
        commission_r = (commission_per_lot / per_unit) / risk if per_unit else 0.0
        r_net = r - commission_r
        trades.append({"day": day, "side": side, "entry": round(entry, d), "stop": round(stop, d),
                       "target": round(target, d), "exit": round(exit_price, d), "why": why,
                       "risk_price": round(risk, d), "pips_risk": round(risk / pip, 1),
                       "r": round(r, 3), "r_net": round(r_net, 3),
                       "close_time": exit_time.strftime("%H:%M") if exit_time else None})
    n = len(trades)
    wins = [t for t in trades if t["r_net"] > 0]
    losses = [t for t in trades if t["r_net"] < 0]
    expectancy = sum(t["r_net"] for t in trades) / n if n else 0.0
    curve, peak, dd = 0.0, 0.0, 0.0
    for t in trades:
        curve += t["r_net"]
        peak = max(peak, curve)
        dd = max(dd, peak - curve)
    return {"symbol": sym, "timeframe": tf, "rule": "opening range (%d min), %s stop, %sR target, flat by %s" % (
        or_minutes, stop_mode, L.num(rr), flat_by),
        "trades": n, "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(len(wins) / n * 100.0, 1) if n else None,
        "expectancy_r": round(expectancy, 3), "total_r": round(sum(t["r_net"] for t in trades), 2),
        "avg_win_r": round(sum(t["r_net"] for t in wins) / len(wins), 2) if wins else None,
        "avg_loss_r": round(sum(t["r_net"] for t in losses) / len(losses), 2) if losses else None,
        "max_drawdown_r": round(dd, 2),
        "exits": {k: sum(1 for t in trades if t["why"].startswith(k)) for k in ("target", "stop", "flat", "session")},
        "sessions": len(groups), "bars": len(bars),
        "costs": {"spread_points": spread_points, "commission_per_lot": commission_per_lot},
        "detail": trades, "small_sample": n < 30,
        "note": "A backtest over one rule and one instrument is a reality check, not a promise."}


def print_backtest(bt):
    print("BACKTEST %s %s: %s" % (bt["symbol"], bt["timeframe"], bt["rule"]))
    if not bt["trades"]:
        print("  no trades: the rule never fired in these bars. Try another session window or more bars.")
        return
    print("  %d trades over %d sessions: %d wins, %d losses (%s%%), expectancy %sR per trade" % (
        bt["trades"], bt["sessions"], bt["wins"], bt["losses"], L.num(bt["win_rate_pct"]),
        L.num(bt["expectancy_r"])))
    print("  total %sR, average win %sR, average loss %sR, max drawdown %sR" % (
        L.num(bt["total_r"]), L.num(bt["avg_win_r"]), L.num(bt["avg_loss_r"]), L.num(bt["max_drawdown_r"])))
    print("  exits: %s" % ", ".join("%s %d" % (k, v) for k, v in bt["exits"].items() if v))
    if bt["small_sample"]:
        print("  WARNING: under 30 trades. That is not a sample you can trust.")
    print("  " + bt["note"])


# ---------------------------------------------------------------- commands

def cmd_doctor(a):
    cfg, block = cfg_and_block(a)
    lines = ["trader-mt5 %s" % VERSION]
    lines.append("python %s" % sys.version.split()[0])
    lines.append("platform %s" % sys.platform)
    if sys.platform.startswith("win"):
        lines.append("Windows: the MetaTrader5 package can run here.")
    else:
        lines.append("Not Windows: the real MetaTrader5 package will not load. Use --replay with a snapshot, "
                     "or run this on the Windows machine next to the terminal.")
    try:
        import MetaTrader5 as mt5          # noqa: F401
        lines.append("MetaTrader5 package: installed")
    except Exception as e:
        lines.append("MetaTrader5 package: NOT available (%s)" % str(e)[:80])
        lines.append("  install: python -m pip install MetaTrader5   (Windows only)")
    lines.append("config: %s %s" % (a.config, "found" if os.path.exists(a.config) else "missing (mt5.py init --write)"))
    lines.append("terminal path: %s" % (block.get("terminal_path") or os.environ.get("MT5_PATH") or
                                       "(auto: the last terminal the package found)"))
    lines.append("allow_live: %s, paper: %s, magic: %s" % (
        block.get("allow_live"), block.get("paper", cfg.get("paper", True)), block.get("magic")))
    try:
        term = open_terminal(a, cfg)
    except L.Mt5Error as e:
        lines.append("terminal: NOT usable")
        lines.append(str(e))
        print("\n".join(lines))
        return 1
    try:
        acct = term.account() or {}
        info = term.terminal_info() or {}
        lines.append("terminal: %s %s, build %s, connected %s, trading %s, dlls %s" % (
            info.get("name"), info.get("company"), info.get("build"),
            info.get("connected"), info.get("trade_allowed"), info.get("dlls_allowed")))
        lines.append("account: %s %s on %s, balance %s %s" % (
            acct.get("login"), str(acct.get("trade_mode", "")).upper(), acct.get("server"),
            L.num(acct.get("balance")), acct.get("currency")))
        lines.append("server offset: UTC%+d (detected from a tick)" % int(term.offset or 0))
        try:
            names = term.symbol_names()
            lines.append("symbols visible: %d" % len(names))
        except L.Mt5Error as e:
            lines.append("symbols: %s" % e)
        lines.append("account trading allowed: %s, algo trading: %s" % (
            acct.get("trade_allowed"), acct.get("trade_expert")))
        if str(acct.get("trade_mode")) in ("real", "live") and not block.get("allow_live"):
            lines.append("REAL account and allow_live is false: entries will be blocked on purpose.")
        lines.append("")
        lines.append("Everything reads: account, symbols, spec, quote, bars, levels, session, positions, "
                     "orders, history, margin, backtest.")
        lines.append("Every write needs: a passing risk check today, your recorded yes, and this terminal.")
    finally:
        term.close()
    print("\n".join(lines))
    return 0


def cmd_init(a):
    cfg = L.read_json(a.config, "config", required=False) or {}
    cfg.setdefault("budget", 5000)
    cfg.setdefault("paper", True)
    cfg.setdefault("max_loss_per_trade_usd", 50)
    cfg.setdefault("max_daily_loss_usd", 150)
    cfg.setdefault("max_trades_per_day", 3)
    cfg.setdefault("min_reward_risk", 1.5)
    cfg.setdefault("require_stop", True)
    cfg.setdefault("blocked", [])
    mt5 = cfg.get("mt5") if isinstance(cfg.get("mt5"), dict) else {}
    for k, v in R.MT5_DEFAULTS.items():
        if k not in ("session", "guard"):
            mt5.setdefault(k, v)
    mt5["allow_live"] = bool(mt5.get("allow_live", False))
    mt5["paper"] = cfg["paper"]
    sess = dict(R.MT5_DEFAULTS["session"])
    sess.update(mt5.get("session") or {})
    mt5["session"] = sess
    guard = dict(R.MT5_DEFAULTS["guard"])
    guard.update(mt5.get("guard") or {})
    mt5["guard"] = guard
    cfg["mt5"] = mt5
    if a.write:
        L.write_json(a.write, cfg)
        print("Wrote %s. Paper first, live blocked: \"mt5.allow_live\" is false." % a.write)
    else:
        print(json.dumps(cfg, indent=2))
    print("Next: open MetaTrader 5, log in to the DEMO account, turn on Tools > Options > Expert Advisors > "
          "Allow algorithmic trading, then: python3 mt5.py doctor")
    return 0


def cmd_account(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        acct = term.account() or {}
        if out_json(a):
            print(json.dumps(acct, indent=2))
        else:
            print_account(acct, term, block)
    finally:
        term.close()
    return 0


def cmd_symbols(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        names = term.symbol_names(a.group)
        search = (a.search or "").upper()
        found = [n for n in names if search in n.upper()] if search else names
        if a.limit:
            found = found[: a.limit]
        if out_json(a):
            print(json.dumps(found, indent=2))
        else:
            print("%d symbols%s%s" % (len(found), " matching " + search if search else "",
                                      " (of %d)" % len(names) if len(found) != len(names) else ""))
            for n in found:
                spec = term.symbol(n) or {}
                print("  %-14s %-28s %s digits, lots %s to %s / %s, spread %s" % (
                    n, (spec.get("description") or "")[:28], spec.get("digits"),
                    L.num(spec.get("volume_min")), L.num(spec.get("volume_max")),
                    L.num(spec.get("volume_step")), L.num(spec.get("spread"))))
            if not found:
                print("  none: try --search EUR, --search XAU, or list the broker's Market Watch")
    finally:
        term.close()
    return 0


def cmd_spec(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        real = term.spec_with_suffix(a.symbol)
        spec = term.symbol(real)
        if not spec:
            raise L.Mt5Error("the terminal does not know %r. The broker's names often carry a suffix; find it "
                             "with: mt5.py symbols --search %s" % (a.symbol, str(a.symbol)[:3].upper()))
        q = term.quote(real)
        if out_json(a):
            spec = dict(spec)
            spec["quote"] = q
            print(json.dumps(spec, indent=2))
        else:
            print_spec(spec)
            print_quote(real, q, spec, term.offset)
    finally:
        term.close()
    return 0


def cmd_quote(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        quotes = {}
        for name in a.symbols:
            real = term.spec_with_suffix(name)
            q = term.quote(real) or {}
            spec = term.symbol(real) or {}
            if not q:
                warn("%s: no quote" % real)
                continue
            q = dict(q)
            q["time_utc"] = q.get("time_utc") or L.iso(q.get("time"), term.offset or 0)
            quotes[real] = q
            if not out_json(a):
                print_quote(real, q, spec, term.offset)
        if a.write:
            doc = L.prices_doc(quotes, now_of(a), term.offset or 0)
            L.write_json(a.write, doc)
            print("Wrote %d quote%s to %s (bid/ask midpoint; the detail block keeps both sides)."
                  % (len(quotes), "" if len(quotes) == 1 else "s", a.write))
        if out_json(a):
            print(json.dumps(quotes, indent=2))
    finally:
        term.close()
    return 0


def cmd_bars(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        real = term.spec_with_suffix(a.symbol)
        spec = term.symbol(real) or {}
        tf = L.tf_name(a.tf)
        start = datetime.date.fromisoformat(a.start) if a.start else None
        end = datetime.date.fromisoformat(a.end) if a.end else None
        bars = term.rates(real, tf, count=a.count, start=start, end=end)
        out = {"symbol": real, "timeframe": tf, "server_offset_hours": term.offset or 0.0,
               "as_of": now_of(a).strftime("%Y-%m-%dT%H:%M:%SZ"), "bars": bars}
        if a.write:
            L.write_json(a.write, out)
            print("Wrote %d %s bars to %s." % (len(bars), tf, a.write))
        if a.csv:
            L.write_csv(a.csv, bars, int(spec.get("digits") or 5))
            print("Wrote %s." % a.csv)
        if a.yahoo:
            doc = L.yahoo_doc(real, bars, {"shortName": spec.get("description") or real,
                                           "regularMarketPrice": bars[-1]["c"] if bars else None},
                              interval=tf.lower(), offset_hours=term.offset or 0.0)
            L.write_json(a.yahoo, doc)
            print("Wrote a Yahoo-chart-shaped copy to %s for trader-scanner/trader-entry/trader-exit/"
                  "trader-timemachine (--offline). MT5 bars are broker-session bars: check the session times."
                  % a.yahoo)
        if out_json(a):
            print(json.dumps(out, indent=2))
        elif not (a.write or a.csv or a.yahoo):
            if not bars:
                print("no bars")
            else:
                print("%s %s: %d bars, %s to %s (server time), last close %s" % (
                    real, tf, len(bars), L.iso(bars[0]["t"], term.offset or 0),
                    L.iso(bars[-1]["t"], term.offset or 0),
                    L.price(bars[-1]["c"], int(spec.get("digits") or 5))))
    finally:
        term.close()
    return 0


def cmd_levels(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        real = term.spec_with_suffix(a.symbol)
        spec = term.symbol(real) or {}
        tf = L.tf_name(a.tf)
        bars = term.rates(real, tf, count=a.count)
        lv = levels(real, spec, bars, tf, a.or_minutes, block, term.offset or 0.0)
        if a.write:
            L.write_json(a.write, lv)
            print("Wrote the levels to %s." % a.write)
        if out_json(a):
            print(json.dumps(lv, indent=2))
        else:
            print_levels(lv)
    finally:
        term.close()
    return 0


def cmd_setup(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        real = term.spec_with_suffix(a.symbol)
        spec = term.symbol(real) or {}
        if not spec:
            raise L.Mt5Error("the terminal does not know %r; find the broker's name with mt5.py symbols "
                             "--search" % a.symbol)
        tf = L.tf_name(a.tf)
        bars = term.rates(real, tf, count=a.count)
        lv = levels(real, spec, bars, tf, a.or_minutes, block, term.offset or 0.0)
        q = term.quote(real) or {}
        plan = setup(real, spec, bars, tf, block, q, lv, a.rr, a.or_minutes)
        if a.write_plan:
            L.write_json(a.write_plan, plan)
            print("Wrote the plan to %s." % a.write_plan)
        if out_json(a):
            print(json.dumps(plan, indent=2))
        else:
            print_setup(plan)
        return 0 if plan["verdict"] == "ready" else 1
    finally:
        term.close()


def scan_one(term, block, name, tf, count, or_minutes, rr):
    """One symbol through the same levels and setup one trade gets."""
    real = term.spec_with_suffix(name)
    spec = term.symbol(real) or {}
    row = {"symbol": real or name, "verdict": "unknown", "side": None, "trend": None,
           "entry": None, "stop": None, "target": None, "reward_risk": rr, "atr": None,
           "opening_range": None, "spread_pips": None, "why": []}
    if not spec:
        row["why"] = ["the terminal does not know this symbol: check the suffix with mt5.py symbols --search"]
        return row
    bars = term.rates(real, tf, count=count)
    if not bars or len(bars) < 30:
        row["why"] = ["not enough %s bars (%d): widen --count or use a longer --tf" % (tf, len(bars or []))]
        return row
    lv = levels(real, spec, bars, tf, or_minutes, block, term.offset or 0.0)
    plan = setup(real, spec, bars, tf, block, term.quote(real) or {}, lv, rr, or_minutes)
    d = int(spec.get("digits") or 5)
    row.update({"verdict": plan["verdict"], "side": plan.get("side"), "trend": plan.get("trend"),
                "entry": plan.get("entry"), "stop": plan.get("stop"), "target": plan.get("target"),
                "atr": lv.get("atr"), "opening_range": lv.get("opening_range"),
                "spread_pips": plan.get("spread_pips"), "why": plan.get("checks") or [],
                "digits": d, "last": bars[-1]["c"]})
    return row


def cmd_scan(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        names = [s.strip() for s in (a.symbols or "").split(",") if s.strip()]
        if not names:
            names = [str(s) for s in (block.get("symbols") or [])]
        if not names:
            names = [str(s.get("symbol")) for s in term.symbols() if s.get("visible", True)]
            if a.limit:
                names = names[:a.limit]
        names = [n for n in dict.fromkeys(names) if n]
        if not names:
            raise L.Mt5Error("nothing to scan: name symbols with --symbols EURUSD,GBPUSD or put them in "
                             "\"mt5.symbols\"")
        tf = L.tf_name(a.tf)
        rows = [scan_one(term, block, n, tf, a.count, a.or_minutes, a.rr) for n in names]
        order = {"ready": 0, "wait": 1, "unknown": 2}
        rows.sort(key=lambda r: (order.get(r["verdict"], 3), r["symbol"]))
        out = {"venue": "mt5", "timeframe": tf, "as_of": now_of(a).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "rule": "opening range (%d min) with an ATR stop, trend filter, %.1fR target" % (a.or_minutes, a.rr),
               "ready": sum(1 for r in rows if r["verdict"] == "ready"),
               "wait": sum(1 for r in rows if r["verdict"] == "wait"),
               "unknown": sum(1 for r in rows if r["verdict"] == "unknown"),
               "symbols": rows}
        if a.write:
            L.write_json(a.write, out)
            print("Wrote %d row(s) to %s." % (len(rows), a.write))
        if out_json(a):
            print(json.dumps(out, indent=2))
            return 0
        print("SCAN %s: %d ready, %d waiting, %d unknown (opening range %d min, %.1fR)" % (
            tf, out["ready"], out["wait"], out["unknown"], a.or_minutes, a.rr))
        for r in rows:
            d = int(r.get("digits") or 5)
            if r["verdict"] == "unknown":
                print("  %-10s unknown  %s" % (r["symbol"], "; ".join(r["why"])))
            elif r["verdict"] == "ready":
                print("  %-10s READY %-4s entry %s stop %s target %s  (last %s; %s)" % (
                    r["symbol"], (r["side"] or "").upper(), L.price(r["entry"], d), L.price(r["stop"], d),
                    L.price(r["target"], d), L.price(r.get("last"), d), "; ".join((r["why"] or [])[-2:])))
            else:
                print("  %-10s wait   %s" % (r["symbol"], "; ".join((r["why"] or [])[-2:])))
        print("A ready row is a plan, not an order: snapshot, lots.py, check.py and your yes still apply.")
        return 0
    finally:
        term.close()


def cmd_session(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        text = session_lines(term, block, a.symbol, now_of(a))
        if out_json(a):
            acct = term.account() or {}
            print(json.dumps({"server_offset_hours": term.offset,
                              "new_york": R.to_eastern(now_of(a)).strftime("%Y-%m-%d %H:%M"),
                              "server": (now_of(a) + datetime.timedelta(hours=term.offset or 0)).strftime(
                                  "%Y-%m-%d %H:%M"),
                              "account": acct,
                              "rollover_ny": [x.strftime("%H:%M") for x in R.rollover_window(
                                  dict(block, session=block.get("session") or {}),
                                  {"server_offset_hours": term.offset}, now_of(a))],
                              "session": block.get("session")}, indent=2))
        else:
            print(text)
    finally:
        term.close()
    return 0


def cmd_snapshot(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        extra = [s.strip() for s in (a.symbols or "").split(",") if s.strip()]
        doc = build_snapshot(term, cfg, block, {"plan": a.plan, "orders": a.orders},
                             extra_symbols=extra, days=a.days, now=now_of(a))
        if doc.get("missing"):
            warn("not in the terminal, so left out: %s" % ", ".join(doc["missing"]))
        if doc.get("from_watchlist"):
            print("No symbol was named, so the snapshot is your terminal's watchlist (%d symbols). "
                  "Name yours with --symbols EURUSD,XAUUSD or \"mt5.symbols\" in the config."
                  % len(doc["symbols"]))
        if a.write:
            L.write_json(a.write, doc)
            print("Wrote the snapshot to %s: %d symbols, %d positions, %d pending orders, %d deals." % (
                a.write, len(doc["symbols"]), len(doc["positions"]), len(doc["orders"]), len(doc["deals"])))
            print("trader-risk (check.py) and trader-budget (lots.py) read it. Next: lots.py --write, "
                  "check.py, ticket.py show, mt5.py execute.")
        if out_json(a):
            print(json.dumps(doc, indent=2))
        elif not a.write:
            print("Snapshot: %s, %d symbols, %d positions, %d orders, %d deals. Use --write to save it." % (
                doc["as_of"], len(doc["symbols"]), len(doc["positions"]), len(doc["orders"]), len(doc["deals"])))
        return 0
    finally:
        term.close()


def cmd_positions(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        got = term.positions(a.symbol)
        if out_json(a):
            print(json.dumps(got, indent=2))
        else:
            print_positions(term, got)
    finally:
        term.close()
    return 0


def cmd_orders(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        got = term.orders(a.symbol)
        if out_json(a):
            print(json.dumps(got, indent=2))
        else:
            print_orders(term, got)
    finally:
        term.close()
    return 0


def cmd_history(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        deals = term.deals(days=a.days, end=now_of(a))
        j = journal(deals, a.days)
        if a.write:
            L.write_json(a.write, j)
        if out_json(a):
            print(json.dumps(j, indent=2))
        else:
            print_journal(j)
            if a.write:
                print("Wrote the journal to %s." % a.write)
    finally:
        term.close()
    return 0


def cmd_margin(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        real = term.spec_with_suffix(a.symbol)
        spec = term.symbol(real) or {}
        q = term.quote(real) or {}
        px = a.price or (q.get("ask") if a.action == "buy" else q.get("bid")) or q.get("ask")
        if px is None:
            raise L.Mt5Error("no price: pass --price")
        margin = term.calc_margin(a.action, real, a.volume, px)
        profit = None
        if a.close_price:
            profit = term.calc_profit(a.action, real, a.volume, px, a.close_price)
        acct = term.account() or {}
        free = _f(acct.get("margin_free"))
        d = int(spec.get("digits") or 5)
        doc = {"symbol": real, "action": a.action, "volume": a.volume, "price": px, "margin": margin,
               "free_margin": free, "margin_pct": round(margin / free * 100.0, 1) if (margin and free) else None,
               "leverage": acct.get("leverage"), "profit_at_close": profit,
               "profit_close_price": a.close_price}
        if out_json(a):
            print(json.dumps(doc, indent=2))
        else:
            print("%s %s lots of %s at %s needs %s of margin" % (
                a.action.upper(), L.num(a.volume), real, L.price(px, d), L.money(margin)))
            if doc["margin_pct"] is not None:
                print("  that is %s%% of free margin %s (leverage 1:%s)" % (
                    L.num(doc["margin_pct"]), L.money(free), L.num(acct.get("leverage"))))
            if profit is not None:
                print("  profit at %s: %s" % (L.price(a.close_price, d), L.money(profit)))
    finally:
        term.close()
    return 0


def cmd_execute(a):
    cfg, block = cfg_and_block(a)
    idx, order = order_of(a)
    now = now_of(a)
    today = today_of(a, now)
    fp = R.fingerprint(order)
    term = open_terminal(a, cfg)
    try:
        spec = term.symbol(term.spec_with_suffix(order.get("symbol"))) or order.get("spec") or {}
        quote = term.quote(term.spec_with_suffix(order.get("symbol"))) or order.get("quote") or {}
        req = L.request(order, cfg, spec, quote)
        if a.dry_run:
            print("DRY RUN: nothing is sent. The request would be:")
            print(json.dumps(req, indent=2))
            return 0
        risk = risk_pass(a, order, today)
        appr = approval(a, order, today)
        acct = account_guard(term, block)
        info = term.terminal_info() or {}
        if info.get("connected") is False:
            raise L.Mt5Error("nothing was sent: the terminal is not connected to the broker")
        checked = term.check(req)
        rc = checked.get("retcode")
        if rc not in (None, 0) and rc not in L.OK_CODES:
            raise L.Mt5Error("nothing was sent: the terminal's own pre-check said %s (%s). Fix the order or the "
                             "symbol, check again, and get a new yes" % (
                                 L.RETCODES.get(rc, rc), checked.get("comment") or ""))
        result = term.send(req)
        rec = {
            "at": R.to_eastern(now).strftime("%Y-%m-%dT%H:%M:%S") +
                  ("-04:00" if R.eastern_offset(now) == -4 else "-05:00"),
            "date": today, "index": idx, "fingerprint": fp, "venue": "mt5",
            "symbol": str(order.get("symbol", "")).upper(), "side": order.get("side"),
            "volume": order.get("volume"), "qty": order.get("volume"), "kind": risk.get("kind", "entry"),
            "max_loss": risk.get("max_loss"), "stop": order.get("sl"), "target": order.get("tp"),
            "plain": "%s %s lots of %s" % (str(order.get("side", "")).upper(), L.num(order.get("volume")),
                                           order.get("symbol")),
            "status": "placed" if result.get("ok") else "failed",
            "broker_order_id": result.get("order"), "deal": result.get("deal"),
            "filled_price": result.get("price"), "retcode": result.get("retcode"),
            "retcode_text": result.get("retcode_text"), "reply": appr.get("reply"),
            "paper": bool(acct.get("trade_mode") != "real"), "account": acct.get("login"),
            "server": acct.get("server"), "request": result.get("sent") or req,
        }
        if a.note:
            rec["note"] = a.note
        record_state(a, rec)
        if out_json(a):
            print(json.dumps({"ok": result.get("ok"), "retcode": result.get("retcode"),
                              "retcode_text": result.get("retcode_text"), "order": result.get("order"),
                              "deal": result.get("deal"), "volume": result.get("volume"),
                              "price": result.get("price"), "request": result.get("sent") or req,
                              "recorded": rec}, indent=2))
        elif result.get("ok") and (result.get("sent") or req).get("action") == "pending":
            print("PLACED: %s %s lots of %s at %s, ticket %s (%s). The broker holds it until the price "
                  "gets there." % (
                      str(order.get("type") or "").replace("_", " ").upper(), L.num(order.get("volume")),
                      order.get("symbol"), L.num(req.get("price")), result.get("order"),
                      result.get("retcode_text")))
            print("Recorded in %s. The stop %s and the target %s travel with it; the time in force is %s." % (
                a.state, L.num(order.get("sl")), L.num(order.get("tp")) if order.get("tp") else "none",
                (result.get("sent") or req).get("time") or "gtc"))
            print("Next: mt5.py orders; cancel it with mt5.py manage cancel --ticket %s --yes \"yes\"" % (
                result.get("order")))
        elif result.get("ok"):
            print("SENT: %s %s lots of %s, ticket %s, deal %s, fill %s (%s)." % (
                str(order.get("side", "")).upper(), L.num(order.get("volume")), order.get("symbol"),
                result.get("order"), result.get("deal"), L.num(result.get("price") or order.get("price")),
                result.get("retcode_text")))
            print("Recorded in %s. The stop %s and the target %s live at the broker now." % (
                a.state, L.num(order.get("sl")), L.num(order.get("tp")) if order.get("tp") else "none"))
            print("Next: mt5.py positions; alerts via mt5.py quote --write + alerts.py; by flat-by: "
                  "mt5.py manage close")
        else:
            print("NOT SENT: the terminal answered %s (%s). Nothing to retry without a new check and a new yes." % (
                result.get("retcode"), result.get("retcode_text")))
        return 0 if result.get("ok") else 1
    finally:
        term.close()


def _manage(a, action):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        acct = term.account() or {}
        live_blocked = str(acct.get("trade_mode")) in ("real", "live") and not block.get("allow_live", False)
        pos = None
        if action in ("close", "partial", "trail", "breakeven"):
            pos = position_of(term, a)
        wanted = (pos or {}).get("symbol") or (a.symbol or "")
        spec = (term.symbol(term.spec_with_suffix(wanted)) if wanted else {}) or {}
        if action == "partial":
            vol = fill_volume(spec, pos.get("volume"), a.volume if a.volume else
                              (pos.get("volume", 0) * (a.pct or 50) / 100.0))
            req = {"action": "deal", "symbol": pos["symbol"], "volume": vol,
                   "type": "sell" if pos["type"] == "buy" else "buy",
                   "price": (term.quote(pos["symbol"]) or {}).get("bid" if pos["type"] == "buy" else "ask"),
                   "position": pos["ticket"], "deviation": int(block.get("deviation") or 20),
                   "magic": int(block.get("magic") or MAGIC),
                   "comment": "partial %s lots" % L.num(vol)}
            desc = "partial close of %s %s lots of %s" % (pos["type"], L.num(vol), pos["symbol"])
            guard_ok = True
        elif action == "close":
            vol = fill_volume(spec, pos.get("volume"), a.volume)
            req = {"action": "deal", "symbol": pos["symbol"], "volume": vol,
                   "type": "sell" if pos["type"] == "buy" else "buy",
                   "price": (term.quote(pos["symbol"]) or {}).get("bid" if pos["type"] == "buy" else "ask"),
                   "position": pos["ticket"], "deviation": int(block.get("deviation") or 20),
                   "magic": int(block.get("magic") or MAGIC), "comment": "close"}
            desc = "closing %s lots of %s (%s)" % (L.num(vol), pos["symbol"], pos["type"])
            guard_ok = True
        elif action == "cancel":
            orders = term.orders()
            ticket = a.ticket
            if not ticket:
                if not a.symbol:
                    raise L.Mt5Error("say which pending order: --ticket 123 or --symbol EURUSD")
                mine = [o for o in orders if str(o.get("symbol", "")).upper() == str(a.symbol).upper()]
                if len(mine) != 1:
                    raise L.Mt5Error("%d pending orders on %s: say --ticket" % (len(mine), a.symbol))
                ticket = mine[0]["ticket"]
            req = {"action": "remove", "order": int(ticket)}
            desc = "cancelling pending order %s" % ticket
            guard_ok = True
        elif action == "cancel-all":
            reqs = [{"action": "remove", "order": int(o["ticket"])} for o in term.orders(a.symbol)]
            req = None
            desc = "cancelling %d pending orders" % len(reqs)
            guard_ok = True
        elif action == "close-all":
            reqs = []
            for p in term.positions(a.symbol):
                q = term.quote(p["symbol"]) or {}
                reqs.append({"action": "deal", "symbol": p["symbol"], "volume": p["volume"],
                             "type": "sell" if p["type"] == "buy" else "buy",
                             "price": q.get("bid") if p["type"] == "buy" else q.get("ask"),
                             "position": p["ticket"], "deviation": int(block.get("deviation") or 20),
                             "magic": int(block.get("magic") or MAGIC), "comment": "close all"})
            req = None
            desc = "closing %d positions" % len(reqs)
            guard_ok = True
        elif action == "breakeven":
            q = term.quote(pos["symbol"]) or {}
            cur = q.get("bid" if pos["type"] == "buy" else "ask") or pos.get("price_current")
            risk = abs((pos.get("price_open") or 0) - (pos.get("sl") or 0))
            if not risk:
                raise L.Mt5Error("%s has no stop-loss: set one first, then the breakeven makes sense"
                                 % pos["symbol"])
            move = (cur - pos["price_open"]) if pos["type"] == "buy" else (pos["price_open"] - cur)
            r_now = move / risk
            if r_now < (a.at_r if a.at_r is not None else 1.0):
                raise L.Mt5Error("%s is only %.2fR in profit, breakeven waits for %.2fR" % (
                    pos["symbol"], r_now, a.at_r if a.at_r is not None else 1.0))
            d = int(spec.get("digits") or 5)
            sl = round(pos["price_open"], d)
            if pos["type"] == "buy" and pos.get("sl") and sl <= pos["sl"]:
                raise L.Mt5Error("%s's stop %s is already at or over breakeven" % (
                    pos["symbol"], L.price(pos["sl"], d)))
            if pos["type"] == "sell" and pos.get("sl") and sl >= pos["sl"]:
                raise L.Mt5Error("%s's stop %s is already at or under breakeven" % (
                    pos["symbol"], L.price(pos["sl"], d)))
            req = {"action": "sltp", "symbol": pos["symbol"], "position": pos["ticket"], "sl": sl,
                   "tp": pos.get("tp") or 0}
            desc = "moving %s's stop to breakeven %s" % (pos["symbol"], L.price(sl, d))
            guard_ok = True
        elif action == "trail":
            q = term.quote(pos["symbol"]) or {}
            cur = q.get("bid" if pos["type"] == "buy" else "ask") or pos.get("price_current")
            pt = _f(spec.get("point")) or 0.00001
            d = int(spec.get("digits") or 5)
            dist = (_f(a.points) if a.points else _f(block.get("guard", {}).get("trail_points")) or 150) * pt
            sl = round(cur - dist if pos["type"] == "buy" else cur + dist, d)
            if pos.get("sl") and ((pos["type"] == "buy" and sl <= pos["sl"]) or
                                  (pos["type"] == "sell" and sl >= pos["sl"])):
                print("%s: the trailing stop %s is not tighter than the current %s. Nothing to do." % (
                    pos["symbol"], L.price(sl, d), L.price(pos["sl"], d)))
                return 0
            if not pos.get("sl"):
                raise L.Mt5Error("%s has no stop-loss yet: set the original stop first so the risk is defined"
                                 % pos["symbol"])
            req = {"action": "sltp", "symbol": pos["symbol"], "position": pos["ticket"], "sl": sl,
                   "tp": pos.get("tp") or 0}
            desc = "trailing %s's stop to %s (%s points)" % (pos["symbol"], L.price(sl, d), L.num(dist / pt))
            guard_ok = True
        elif action == "modify":
            if not a.ticket:
                raise L.Mt5Error("modify wants --ticket (a pending order) and the new --price / --sl / --tp")
            orders = [o for o in term.orders() if int(o.get("ticket") or 0) == int(a.ticket)]
            if not orders:
                raise L.Mt5Error("no pending order with ticket %s" % a.ticket)
            o = orders[0]
            sl = a.sl if a.sl is not None else o.get("sl")
            tp = a.tp if a.tp is not None else o.get("tp")
            price = a.price if a.price is not None else o.get("price")
            if o.get("sl") and sl and abs(sl - o["sl"]) > 0:
                wider = abs((price or 0) - sl) > abs((price or 0) - o["sl"])
                if wider and not a.allow_wider_stop:
                    raise L.Mt5Error("that move widens the stop: it adds risk. If that is really the plan, "
                                     "pass --allow-wider-stop and say why in --note")
            req = {"action": "modify", "order": int(a.ticket), "price": price, "sl": sl or 0, "tp": tp or 0,
                   "time": o.get("type_time") or "gtc"}
            desc = "modifying pending order %s (price %s, sl %s, tp %s)" % (
                a.ticket, L.num(price), L.num(sl), L.num(tp))
            guard_ok = False
        else:
            raise L.Mt5Error("unknown management action %r" % action)
        if live_blocked:
            raise L.Mt5Error("nothing was sent: REAL-money account and \"mt5.allow_live\" is false")
        require_yes(a, desc, guard_ok=guard_ok and guard_enabled(a) and
                    guard_allows(a, action if action in GUARD_ACTIONS else action))
        if action in ("cancel-all", "close-all"):
            if not reqs:
                print("Nothing to do: no %s." % ("pending orders" if action == "cancel-all" else "positions"))
                return 0
            results = []
            for r in reqs:
                results.append(term.send(r))
            ok = sum(1 for r in results if r.get("ok"))
            print("%s: %d of %d done." % (desc[0].upper() + desc[1:], ok, len(reqs)))
            for r in results:
                if not r.get("ok"):
                    print("  not done: %s (%s)" % (r.get("retcode"), r.get("retcode_text")))
            return 0 if ok == len(reqs) else 1
        result = term.send(req)
        if out_json(a):
            print(json.dumps({"action": action, "request": result.get("sent") or req,
                              "result": result}, indent=2))
        elif result.get("ok"):
            what = desc[0].upper() + desc[1:]
            print("%s: done (%s, ticket %s%s)." % (
                what, result.get("retcode_text"), result.get("order"),
                (", fill " + L.num(result.get("price"))) if result.get("price") else ""))
            if action in ("trail", "breakeven", "partial"):
                guard_mark(a, (pos or {}).get("ticket"), action)
        else:
            print("%s: NOT done: %s (%s)." % (desc.capitalize(), result.get("retcode"),
                                               result.get("retcode_text")))
        return 0 if result.get("ok") else 1
    finally:
        term.close()


def cmd_guard(a):
    if a.guard_action == "show":
        doc = guard_doc(a)
        state = guard_state(a).get("positions") or {}
        print("Guard: %s" % ("ON" if doc.get("enabled") else "off"))
        print("  file: %s" % guard_path(a))
        if doc.get("enabled"):
            print("  covers: %s" % ", ".join(doc.get("actions") or GUARD_ACTIONS))
            print("  rules: breakeven at %sR, trail from %sR by %s points, partial %s%% at %sR" % (
                L.num(doc.get("breakeven_at_r")), L.num(doc.get("trail_at_r")), L.num(doc.get("trail_points")),
                L.num(doc.get("partial_pct")), L.num(doc.get("partial_at_r"))))
            print("  it only ever TIGHTENS a stop or closes part of a position: it cannot open or add one.")
        else:
            print("  The guard is off: every trail, breakeven or partial needs a fresh yes from you.")
        if state:
            print("  already done per position: %s" % json.dumps(state, sort_keys=True))
        return 0
    cfg, block = cfg_and_block(a)
    if a.guard_action == "off":
        doc = guard_doc(a)
        doc["enabled"] = False
        doc["off_at"] = R.to_eastern(now_of(a)).strftime("%Y-%m-%d %H:%M")
        L.write_json(guard_path(a), doc)
        print("Guard off. Protective actions need your yes again.")
        return 0
    if a.guard_action == "on":
        require_yes(a, "turning on the protective guard (breakeven, trailing stop and partial take-profit on "
                       "your open positions, and only those)")
        guard_cfg = block.get("guard") or {}
        doc = {"enabled": True, "actions": list(GUARD_ACTIONS),
               "breakeven_at_r": guard_cfg.get("breakeven_at_r", 1.0),
               "trail_at_r": guard_cfg.get("trail_at_r", 1.0),
               "trail_points": guard_cfg.get("trail_points", 150),
               "partial_at_r": guard_cfg.get("partial_at_r", 1.0),
               "partial_pct": guard_cfg.get("partial_pct", 50),
               "at": R.to_eastern(now_of(a)).strftime("%Y-%m-%d %H:%M"),
               "reply": getattr(a, "yes", "")}
        L.write_json(guard_path(a), doc)
        print("Guard ON: it may now move a stop toward profit, trail it, and take a partial at the R you set. "
              "It cannot open, add to or widen anything.")
        return 0
    # run
    if not guard_enabled(a):
        print("The guard is off: nothing to run. Turn it on with: mt5.py guard on --yes \"yes\"")
        return 0
    term = open_terminal(a, cfg)
    try:
        account_guard(term, block, "guard")
        doc = guard_doc(a)
        moved, skipped = 0, 0
        for p in term.positions(a.symbol):
            spec = term.symbol(p["symbol"]) or {}
            q = term.quote(p["symbol"]) or {}
            cur = q.get("bid" if p["type"] == "buy" else "ask") or p.get("price_current")
            risk = abs((p.get("price_open") or 0) - (p.get("sl") or 0))
            if not risk:
                print("#%s %s: no stop-loss, so the guard leaves it alone (set the stop first)" % (
                    p["ticket"], p["symbol"]))
                skipped += 1
                continue
            r_now = ((cur - p["price_open"]) if p["type"] == "buy" else (p["price_open"] - cur)) / risk
            d = int(spec.get("digits") or 5)
            pt = _f(spec.get("point")) or 0.00001
            new_sl = p.get("sl")
            if r_now >= (doc.get("partial_at_r") or 1.0) and not guard_done(a, p["ticket"], "partial"):
                vol = fill_volume(spec, p["volume"], p["volume"] * (doc.get("partial_pct") or 50) / 100.0)
                if vol < p["volume"] - 1e-9:
                    r = term.send({"action": "deal", "symbol": p["symbol"], "volume": vol,
                                   "type": "sell" if p["type"] == "buy" else "buy", "price": cur,
                                   "position": p["ticket"], "deviation": int(block.get("deviation") or 20),
                                   "magic": int(block.get("magic") or MAGIC), "comment": "guard partial"})
                    print("#%s %s: partial %s lots at %.2fR: %s" % (
                        p["ticket"], p["symbol"], L.num(vol), r_now, "done" if r.get("ok") else r.get("retcode")))
                    guard_mark(a, p["ticket"], "partial")
                    moved += 1
            if r_now >= (doc.get("breakeven_at_r") or 1.0) and not guard_done(a, p["ticket"], "breakeven"):
                be = p["price_open"]
                if (p["type"] == "buy" and (new_sl is None or be > new_sl)) or \
                        (p["type"] == "sell" and (new_sl is None or be < new_sl)):
                    new_sl = round(be, d)
                    guard_mark(a, p["ticket"], "breakeven")
            if r_now >= (doc.get("trail_at_r") or 1.0):
                trail = cur - (doc.get("trail_points") or 150) * pt if p["type"] == "buy" else \
                    cur + (doc.get("trail_points") or 150) * pt
                trail = round(trail, d)
                if (p["type"] == "buy" and (new_sl is None or trail > new_sl)) or \
                        (p["type"] == "sell" and (new_sl is None or trail < new_sl)):
                    new_sl = trail
            if new_sl is not None and abs((new_sl or 0) - (p.get("sl") or 0)) > pt / 2:
                r = term.send({"action": "sltp", "symbol": p["symbol"], "position": p["ticket"],
                               "sl": new_sl, "tp": p.get("tp") or 0})
                print("#%s %s: stop %s -> %s at %.2fR: %s" % (
                    p["ticket"], p["symbol"], L.price(p.get("sl"), d) if p.get("sl") else "none",
                    L.price(new_sl, d), r_now, "done" if r.get("ok") else r.get("retcode")))
                moved += 1 if r.get("ok") else 0
            else:
                skipped += 1
        print("Guard run: %d action(s), %d position(s) left alone. Tightening only; nothing was opened." % (
            moved, skipped))
        return 0
    finally:
        term.close()


def cmd_backtest(a):
    cfg, block = cfg_and_block(a)
    term = open_terminal(a, cfg)
    try:
        real = term.spec_with_suffix(a.symbol)
        spec = term.symbol(real) or {}
        tf = L.tf_name(a.tf)
        bars = term.rates(real, tf, count=a.count)
        q = term.quote(real) or {}
        spread_pts = _f(a.spread) if a.spread is not None else (_f(spec.get("spread")) or 0.0)
        bt = backtest(real, spec, bars, tf, term.offset or 0.0, rr=a.rr, or_minutes=a.or_minutes,
                      stop_mode=a.stop, atr_mult=a.atr_mult, spread_points=spread_pts,
                      commission_per_lot=_f(block.get("commission_per_lot")) or 0.0,
                      allow_short=not a.long_only,
                      flat_by=(block.get("session") or {}).get("flat_by") or "20:55",
                      session_open=(block.get("session") or {}).get("open") or "03:00")
        if a.write:
            L.write_json(a.write, bt)
        if out_json(a):
            print(json.dumps(bt, indent=2))
        else:
            print_backtest(bt)
            if a.write:
                print("Wrote the backtest to %s." % a.write)
        return 0
    finally:
        term.close()


# ---------------------------------------------------------------- argparse

def add_globals(p, suppress=False):
    d = argparse.SUPPRESS if suppress else None
    p.add_argument("--config", default=(argparse.SUPPRESS if suppress else "trader/config.json"),
                   help="trader/config.json")
    p.add_argument("--replay", default=(argparse.SUPPRESS if suppress else None), metavar="PATH",
                   help="read a saved snapshot instead of a terminal (macOS/Linux/tests)")
    p.add_argument("--now", default=(argparse.SUPPRESS if suppress else None),
                   help='pretend it is this New York time, e.g. "2026-10-20 10:00"')
    p.add_argument("--json", action="store_true", default=(argparse.SUPPRESS if suppress else False),
                   help="raw JSON out")


def build_parser():
    ap = argparse.ArgumentParser(description="MetaTrader 5: data, sizing inputs, orders and position management "
                                             "for the day-trader pack. Never sends without a pass, a yes and "
                                             "a terminal.", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    add_globals(ap)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("doctor", help="check the terminal, the package and the account")
    add_globals(p, True)

    p = sub.add_parser("init", help="write a config.json with the MT5 block")
    add_globals(p, True)
    p.add_argument("--write", nargs="?", const="trader/config.json", metavar="PATH")

    p = sub.add_parser("account", help="balance, equity, margin")
    add_globals(p, True)

    p = sub.add_parser("symbols", help="the broker's symbols (with their suffixes)")
    add_globals(p, True)
    p.add_argument("--search")
    p.add_argument("--group")
    p.add_argument("--limit", type=int, default=40)

    p = sub.add_parser("spec", help="everything about one symbol")
    add_globals(p, True)
    p.add_argument("symbol")

    p = sub.add_parser("quote", help="bid/ask/spread, and trader/prices.json")
    add_globals(p, True)
    p.add_argument("symbols", nargs="+")
    p.add_argument("--write", nargs="?", const="trader/prices.json", metavar="PATH")

    p = sub.add_parser("bars", help="OHLC bars (json, csv, or a Yahoo-shaped copy)")
    add_globals(p, True)
    p.add_argument("symbol")
    p.add_argument("--tf", default="M5")
    p.add_argument("--count", type=int, default=500)
    p.add_argument("--from", dest="start", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="end", metavar="YYYY-MM-DD")
    p.add_argument("--write", nargs="?", const="trader/mt5/bars.json", metavar="PATH")
    p.add_argument("--csv", nargs="?", const="trader/mt5/bars.csv", metavar="PATH")
    p.add_argument("--yahoo", nargs="?", const="trader/mt5/yahoo-chart.json", metavar="PATH",
                   help="a Yahoo chart JSON the equity tools can read with --offline")

    p = sub.add_parser("levels", help="opening range, ATR, pivots, yesterday")
    add_globals(p, True)
    p.add_argument("symbol")
    p.add_argument("--tf", default="M5")
    p.add_argument("--count", type=int, default=500)
    p.add_argument("--or-minutes", dest="or_minutes", type=int, default=60)
    p.add_argument("--write", nargs="?", const="trader/mt5/levels.json", metavar="PATH")

    p = sub.add_parser("setup", help="a plan from the chart (writes trader/plan.json with --write-plan)")
    add_globals(p, True)
    p.add_argument("symbol")
    p.add_argument("--tf", default="M15")
    p.add_argument("--count", type=int, default=400)
    p.add_argument("--or-minutes", dest="or_minutes", type=int, default=60)
    p.add_argument("--rr", type=float, default=1.5)
    p.add_argument("--write-plan", dest="write_plan", nargs="?", const="trader/plan.json", metavar="PATH")

    p = sub.add_parser("scan", help="the opening-range rule across a list of MT5 symbols")
    add_globals(p, True)
    p.add_argument("--symbols", help="comma separated; default \"mt5.symbols\", else the watchlist")
    p.add_argument("--tf", default="M15")
    p.add_argument("--count", type=int, default=400)
    p.add_argument("--or-minutes", dest="or_minutes", type=int, default=60)
    p.add_argument("--rr", type=float, default=1.5)
    p.add_argument("--limit", type=int, default=25, help="watchlist symbols to scan at most (default 25)")
    p.add_argument("--write", nargs="?", const="trader/mt5/scan.json", metavar="PATH")

    p = sub.add_parser("session", help="server time, New York time, rollover, flat-by")
    add_globals(p, True)
    p.add_argument("symbol", nargs="?")

    p = sub.add_parser("snapshot", help="the JSON trader-risk and trader-budget read")
    add_globals(p, True)
    p.add_argument("--write", nargs="?", const="trader/mt5/context.json", metavar="PATH")
    p.add_argument("--symbols", help="extra symbols, comma separated")
    p.add_argument("--plan", default="trader/plan.json")
    p.add_argument("--orders", default="trader/orders.json")
    p.add_argument("--days", type=int, default=2, help="days of deals to include (default 2)")

    p = sub.add_parser("positions", help="open positions, with the risk at each stop")
    add_globals(p, True)
    p.add_argument("--symbol")

    p = sub.add_parser("orders", help="pending orders")
    add_globals(p, True)
    p.add_argument("--symbol")

    p = sub.add_parser("history", help="closed trades and the honest numbers")
    add_globals(p, True)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--write", nargs="?", const="trader/mt5/journal.json", metavar="PATH")

    p = sub.add_parser("margin", help="the margin for a volume, and the profit at a price")
    add_globals(p, True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--volume", type=float, required=True)
    p.add_argument("--action", choices=["buy", "sell"], default="buy")
    p.add_argument("--price", type=float)
    p.add_argument("--close-price", dest="close_price", type=float)

    p = sub.add_parser("execute", help="send an order that trader-risk passed and you said yes to")
    add_globals(p, True)
    p.add_argument("--index", type=int)
    p.add_argument("--orders", default="trader/orders.json")
    p.add_argument("--risk", default="trader/state/risk.json")
    p.add_argument("--state", default="trader/state/broker.json")
    p.add_argument("--note")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="print the request, send nothing")

    p = sub.add_parser("manage", help="close, trail, breakeven, partial, modify, cancel")
    add_globals(p, True)
    msub = p.add_subparsers(dest="manage_action")
    for name, helptext in (("close", "close a position (or part of one)"),
                           ("partial", "close a percentage of a position"),
                           ("trail", "move the stop behind the price"),
                           ("breakeven", "move the stop to the entry once in profit"),
                           ("modify", "modify a pending order"),
                           ("cancel", "cancel one pending order"),
                           ("close-all", "close every position (optionally one symbol)"),
                           ("cancel-all", "cancel every pending order")):
        q = msub.add_parser(name, help=helptext)
        add_globals(q, True)
        q.add_argument("--symbol")
        q.add_argument("--ticket", type=int)
        q.add_argument("--volume", type=float, help="lots to close (default: all of it)")
        q.add_argument("--pct", type=float, help="percent to close, for partial")
        q.add_argument("--at-r", dest="at_r", type=float, help="R needed before breakeven")
        q.add_argument("--points", type=float, help="trail distance in points")
        q.add_argument("--price", type=float, help="new price, for modify")
        q.add_argument("--sl", type=float)
        q.add_argument("--tp", type=float)
        q.add_argument("--allow-wider-stop", dest="allow_wider_stop", action="store_true")
        q.add_argument("--yes", help="the user's reply, word for word")
        q.add_argument("--guard", help="guard file (default trader/mt5/guard.json)")
        q.add_argument("--guard-state", dest="guard_state", help="where the guard records what it did")

    p = sub.add_parser("guard", help="pre-authorized protective automation (tightening only)")
    add_globals(p, True)
    p.add_argument("guard_action", choices=["on", "off", "show", "run"])
    p.add_argument("--yes")
    p.add_argument("--symbol")
    p.add_argument("--guard", help="guard file (default trader/mt5/guard.json)")
    p.add_argument("--guard-state", dest="guard_state", help="where the guard records what it did")

    p = sub.add_parser("backtest", help="one rule, no lookahead, honest stats")
    add_globals(p, True)
    p.add_argument("symbol")
    p.add_argument("--tf", default="M5")
    p.add_argument("--count", type=int, default=5000)
    p.add_argument("--rr", type=float, default=2.0)
    p.add_argument("--or-minutes", dest="or_minutes", type=int, default=60)
    p.add_argument("--stop", choices=["or", "mid", "atr"], default="or")
    p.add_argument("--atr-mult", dest="atr_mult", type=float, default=1.0)
    p.add_argument("--spread", type=float, help="spread in points (default: the symbol's)")
    p.add_argument("--long-only", dest="long_only", action="store_true")
    p.add_argument("--write", nargs="?", const="trader/mt5/backtest.json", metavar="PATH")
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        ap.print_help()
        return 1
    # subparsers with add_globals(..., True) keep the global values, but a
    # missing attribute still has to read as its default
    for name, default in (("config", "trader/config.json"), ("replay", None), ("now", None), ("json", False)):
        if not hasattr(a, name):
            setattr(a, name, default)
    handlers = {
        "doctor": cmd_doctor, "init": cmd_init, "account": cmd_account, "symbols": cmd_symbols,
        "spec": cmd_spec, "quote": cmd_quote, "bars": cmd_bars, "levels": cmd_levels, "setup": cmd_setup,
        "session": cmd_session, "snapshot": cmd_snapshot, "positions": cmd_positions, "orders": cmd_orders,
        "history": cmd_history, "margin": cmd_margin, "execute": cmd_execute, "backtest": cmd_backtest,
        "scan": cmd_scan,
    }
    try:
        if a.cmd == "manage":
            action = getattr(a, "manage_action", None)
            if not action:
                print("manage wants an action: close, partial, trail, breakeven, modify, cancel, close-all, "
                      "cancel-all", file=sys.stderr)
                return 1
            return _manage(a, action)
        if a.cmd == "guard":
            return cmd_guard(a)
        return handlers[a.cmd](a)
    except L.Mt5Error as e:
        print("mt5.py: %s" % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
