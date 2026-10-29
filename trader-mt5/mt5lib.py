#!/usr/bin/env python3
"""The MetaTrader 5 side of the pack: one place that talks to the terminal and
one place that turns its namedtuples into plain JSON. Standard library only.

`mt5.py` is the command line; this module is the plumbing it uses:

  Terminal        connect to the terminal (or replay a saved snapshot), read
                  account, symbols, quotes, bars, positions, orders, deals,
                  calculate margin and profit, check and send requests
  snapshot()      the small JSON file trader-risk and trader-budget read:
                  account, specs, quotes, positions, orders, today's deals
  request()       a proposed order -> the exact MT5 request, in JSON, with the
                  terminal's integer constants filled in at send time
  prices_doc()    quotes -> trader/prices.json, the shape trader-alerts and
                  trader-risk already read
  yahoo_doc()     MT5 bars -> a Yahoo chart JSON, so the free tools that read
                  Yahoo's chart format (trader-scanner, trader-entry,
                  trader-exit, trader-timemachine) can be pointed at MT5 bars

Replay mode is how the tests and the replay files work without a terminal:
a JSON document with terminal, account, symbols, quotes, positions, orders,
deals, rates and optional "send" answers. The real terminal is only imported
when no replay document is given, on Windows, with MetaTrader5 installed.

MT5 facts this file handles on purpose, because they bite people:

  * a broker's symbol is not "EURUSD": it can be EURUSD.a, EURUSDm, XAUUSD.cash.
    Everything reads the terminal's own symbol list and keeps its suffix.
  * server time is a broker clock, usually UTC+2 or UTC+3, not your time and
    not UTC. The snapshot records the detected offset so traders see the
    session in New York time.
  * volume_min, volume_max and volume_step are the broker's ladder: 0.13 lots
    is rejected if the step is 0.01 and the minimum 0.10 only on some symbols.
  * trade_stops_level, trade_freeze_level, the spread and the filling mode are
    per symbol and per broker, and MT5 rejects orders that ignore them.
  * a REAL account and a DEMO account are the same API: only account_info
    tells them apart, so this file does, loudly.
"""

import datetime
import json
import math
import os
import sys

# ---------------------------------------------------------------- constants

TIMEFRAMES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 16385, "H4": 16388,
              "D1": 16408, "W1": 32769, "MN1": 49153}
TF_ALIASES = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4",
              "1d": "D1", "1w": "W1", "1mn": "MN1"}
ORDER_TYPES = {"buy": 0, "sell": 1, "buy_limit": 2, "sell_limit": 3, "buy_stop": 4,
               "sell_stop": 5, "buy_stop_limit": 6, "sell_stop_limit": 7}
ORDER_TYPE_NAMES = {v: k for k, v in ORDER_TYPES.items()}
ORDER_TIME = {"gtc": 0, "day": 1, "specified": 2, "specified_day": 3}
ORDER_TIME_NAMES = {v: k for k, v in ORDER_TIME.items()}
FILLING = {"fok": 0, "ioc": 1, "return": 2, "boc": 3}
FILLING_NAMES = {v: k for k, v in FILLING.items()}
ACTIONS = {"deal": 1, "pending": 5, "sltp": 6, "modify": 7, "remove": 8, "close_by": 10}
ACTION_NAMES = {v: k for k, v in ACTIONS.items()}
TRADE_MODES = {0: "demo", 1: "contest", 2: "real"}
SYMBOL_TRADE_MODES = {0: "disabled", 1: "long_only", 2: "short_only", 3: "close_only", 4: "full"}
MARGIN_MODES = {0: "netting", 1: "exchange", 2: "hedging"}
DEAL_ENTRIES = {0: "in", 1: "out", 2: "inout", 3: "out_by"}
SWAP_MODES = {0: "disabled", 1: "points", 2: "symbol_currency", 3: "margin_currency",
              4: "deposit_currency", 5: "interest", 6: "interest_open", 7: "interest_close"}
RETCODES = {
    10004: "requote", 10006: "rejected", 10007: "canceled by the trader", 10008: "placed",
    10009: "done", 10010: "done partially", 10011: "error", 10012: "timeout",
    10013: "invalid request", 10014: "invalid volume", 10015: "invalid price",
    10016: "invalid stops", 10017: "trading disabled", 10018: "market closed",
    10019: "not enough money", 10020: "prices changed", 10021: "no quotes",
    10022: "invalid expiration", 10023: "order changed", 10024: "too many requests",
    10025: "no changes", 10026: "server disabled the autotrading", 10027: "autotrading disabled by client",
    10028: "request locked", 10029: "frozen", 10030: "invalid filling", 10031: "no connection",
    10032: "only real accounts", 10033: "order limit reached", 10034: "volume limit reached",
    10035: "invalid or prohibited order type", 10036: "position already closed",
    10038: "close volume over the position", 10039: "a close order already exists",
    10040: "the number of open positions is limited", 10041: "a pending order to close exists",
    10042: "the position is being closed by another request", 10043: "only long positions allowed",
    10044: "only short positions allowed", 10045: "only close by allowed", 10046: "fifo rule",
    10047: "opposite volume is hedged", 10048: "the order's expiration is close",
}
OK_CODES = (10008, 10009, 10010)


class Mt5Error(Exception):
    pass


def _f(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def num(x, places=8):
    v = _f(x)
    if v is None:
        return "?"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return (("%." + str(places) + "f") % v).rstrip("0").rstrip(".")


def money(x):
    v = _f(x) or 0.0
    return ("-" if v < 0 else "") + "$" + "{:,.2f}".format(abs(v))


def price(x, digits=5):
    v = _f(x)
    return "?" if v is None else ("%." + str(int(digits)) + "f") % v


def tf_name(text):
    if text is None:
        return "M5"
    t = str(text).strip()
    if t.upper() in TIMEFRAMES:
        return t.upper()
    if t.lower() in TF_ALIASES:
        return TF_ALIASES[t.lower()]
    raise Mt5Error("unknown timeframe %r: use M1, M5, M15, M30, H1, H4, D1, W1, MN1" % text)


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


def iso(epoch, offset_hours=0.0):
    """MT5 epoch seconds (a server clock) -> ISO UTC text, offset removed."""
    v = _f(epoch)
    if v is None:
        return None
    utc = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=v - float(offset_hours) * 3600.0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_of(utc_text):
    dt = parse_utc(utc_text)
    if dt is None:
        return None
    return int((dt - datetime.datetime(1970, 1, 1)).total_seconds())


def detect_offset(tick_epoch, now_utc=None):
    """The broker's server offset from UTC, to the nearest 15 minutes, from a
    live tick's timestamp: a tick stamped 12:00:03 on a UTC+3 server arrives
    when it is 09:00:03 UTC."""
    v = _f(tick_epoch)
    if not v:
        return 0.0
    now = now_utc or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    now_epoch = (now - datetime.datetime(1970, 1, 1)).total_seconds()
    secs = v - now_epoch
    if abs(secs) > 20 * 3600:
        return 0.0
    return round(secs / 900.0) / 4.0


# ---------------------------------------------------------------- normalizing

def _dict(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    for attr in ("_asdict", "_asdict_"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return dict(fn())
            except Exception:
                pass
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_") and
            not callable(getattr(obj, k))}


def norm_account(a):
    if not a:
        return {}
    return {
        "login": a.get("login"), "trade_mode": TRADE_MODES.get(a.get("trade_mode"), a.get("trade_mode")),
        "leverage": a.get("leverage"), "currency": a.get("currency"), "server": a.get("server"),
        "company": a.get("company"), "name": a.get("name"), "balance": round(_f(a.get("balance")) or 0.0, 2),
        "equity": round(_f(a.get("equity")) or 0.0, 2), "margin": round(_f(a.get("margin")) or 0.0, 2),
        "margin_free": round(_f(a.get("margin_free")) or 0.0, 2),
        "margin_level": round(_f(a.get("margin_level")) or 0.0, 2),
        "profit": round(_f(a.get("profit")) or 0.0, 2), "credit": round(_f(a.get("credit")) or 0.0, 2),
        "trade_allowed": bool(a.get("trade_allowed", True)),
        "trade_expert": bool(a.get("trade_expert", True)),
        "margin_so_call": a.get("margin_so_call"), "margin_so_so": a.get("margin_so_so"),
        "margin_mode": MARGIN_MODES.get(a.get("margin_mode"), a.get("margin_mode")),
        "hedge": MARGIN_MODES.get(a.get("margin_mode")) == "hedging",
    }


def filling_modes(bits):
    out = []
    try:
        bits = int(bits)
    except (TypeError, ValueError):
        return ["fok", "ioc", "return"]
    if bits & 1:
        out.append("fok")
    if bits & 2:
        out.append("ioc")
    if not out:
        out = ["return"]
    return out


def norm_symbol(s):
    if not s:
        return {}
    return {
        "symbol": s.get("name") or s.get("symbol"),
        "description": s.get("description") or "",
        "path": s.get("path") or "",
        "digits": s.get("digits"), "point": _f(s.get("point")),
        "spread": s.get("spread"), "spread_float": bool(s.get("spread_float", True)),
        "trade_mode": SYMBOL_TRADE_MODES.get(s.get("trade_mode"), s.get("trade_mode")),
        "trade_execution": s.get("trade_execution"),
        "volume_min": _f(s.get("volume_min")), "volume_max": _f(s.get("volume_max")),
        "volume_step": _f(s.get("volume_step")),
        "trade_tick_size": _f(s.get("trade_tick_size")), "trade_tick_value": _f(s.get("trade_tick_value")),
        "trade_tick_value_profit": _f(s.get("trade_tick_value_profit")),
        "trade_tick_value_loss": _f(s.get("trade_tick_value_loss")),
        "trade_contract_size": _f(s.get("trade_contract_size")),
        "trade_stops_level": s.get("trade_stops_level"), "trade_freeze_level": s.get("trade_freeze_level"),
        "swap_long": _f(s.get("swap_long")), "swap_short": _f(s.get("swap_short")),
        "swap_mode": SWAP_MODES.get(s.get("swap_mode"), s.get("swap_mode")),
        "margin_initial": _f(s.get("margin_initial")), "margin_maintenance": _f(s.get("margin_maintenance")),
        "currency_base": s.get("currency_base"), "currency_profit": s.get("currency_profit"),
        "currency_margin": s.get("currency_margin"),
        "filling_modes": filling_modes(s.get("filling_mode")),
        "expiration_modes": s.get("expiration_mode"),
        "visible": bool(s.get("visible", True)),
        "select": bool(s.get("select", True)),
        "sessions": [],
    }


def norm_tick(t):
    if not t:
        return {}
    return {"bid": _f(t.get("bid")), "ask": _f(t.get("ask")), "last": _f(t.get("last")),
            "volume": _f(t.get("volume")), "time": t.get("time"), "time_msc": t.get("time_msc"),
            "spread_points": None}


def _side(typ):
    """MT5 numbers a position 0 for buy and 1 for sell; a replay file may
    already say "buy"/"sell"."""
    if isinstance(typ, str):
        t = typ.strip().lower()
        return t if t in ("buy", "sell") else ("buy" if t in ("0", "long") else "sell")
    return "buy" if typ == 0 else "sell"


def norm_position(p, offset=0.0):
    if not p:
        return {}
    typ = p.get("type")
    return {
        "ticket": p.get("ticket"), "symbol": p.get("symbol"), "type": _side(typ),
        "volume": _f(p.get("volume")), "price_open": _f(p.get("price_open")),
        "price_current": _f(p.get("price_current")), "sl": _f(p.get("sl")), "tp": _f(p.get("tp")),
        "profit": round(_f(p.get("profit")) or 0.0, 2), "swap": round(_f(p.get("swap")) or 0.0, 2),
        "commission": round(_f(p.get("commission")) or 0.0, 2),
        "magic": p.get("magic"), "comment": p.get("comment") or "",
        "time": p.get("time"), "time_utc": iso(p.get("time"), offset),
        "identifier": p.get("identifier"),
    }


def norm_order(o, offset=0.0):
    if not o:
        return {}
    typ = o.get("type")
    return {
        "ticket": o.get("ticket"), "symbol": o.get("symbol"),
        "type": ORDER_TYPE_NAMES.get(typ, typ),
        "volume": _f(o.get("volume_current") or o.get("volume_initial") or o.get("volume")),
        "price": _f(o.get("price_open") or o.get("price")), "sl": _f(o.get("sl")), "tp": _f(o.get("tp")),
        "price_current": _f(o.get("price_current")), "price_stoplimit": _f(o.get("price_stoplimit")),
        "type_time": ORDER_TIME_NAMES.get(o.get("type_time"), o.get("type_time")),
        "type_filling": FILLING_NAMES.get(o.get("type_filling"), o.get("type_filling")),
        "state": o.get("state"), "magic": o.get("magic"), "comment": o.get("comment") or "",
        "time_setup": o.get("time_setup"), "time_utc": iso(o.get("time_setup"), offset),
        "expiration": iso(o.get("time_expiration"), offset) if o.get("time_expiration") else None,
    }


def norm_deal(d, offset=0.0):
    if not d:
        return {}
    typ = d.get("type")
    side = "buy" if typ == 0 else ("sell" if typ == 1 else str(typ))
    return {
        "ticket": d.get("ticket"), "order": d.get("order"), "position_id": d.get("position_id"),
        "symbol": d.get("symbol") or "", "type": side,
        "entry": DEAL_ENTRIES.get(d.get("entry"), d.get("entry")),
        "volume": _f(d.get("volume")), "price": _f(d.get("price")),
        "profit": round(_f(d.get("profit")) or 0.0, 2), "swap": round(_f(d.get("swap")) or 0.0, 2),
        "commission": round(_f(d.get("commission")) or 0.0, 2), "fee": round(_f(d.get("fee")) or 0.0, 2),
        "magic": d.get("magic"), "comment": d.get("comment") or "",
        "time": d.get("time"), "time_utc": iso(d.get("time"), offset),
    }


def bars_from_rates(rates):
    """MT5's structured array -> [{"t","o","h","l","c","v","spread","real_volume"}]."""
    out = []
    for r in rates or []:
        try:
            out.append({"t": int(r["time"]), "o": float(r["open"]), "h": float(r["high"]),
                        "l": float(r["low"]), "c": float(r["close"]),
                        "v": int(r["tick_volume"]), "spread": int(r["spread"]),
                        "real_volume": int(r["real_volume"]) if "real_volume" in r.dtype.names else 0})
        except (TypeError, ValueError, KeyError, AttributeError):
            try:                                    # a plain dict from a replay file
                out.append({"t": int(r["t"]), "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                            "c": float(r["c"]), "v": int(r.get("v") or r.get("volume") or 0),
                            "spread": int(r.get("spread") or 0),
                            "real_volume": int(r.get("real_volume") or 0)})
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
    return out


# ---------------------------------------------------------------- the terminal

class Terminal:
    """One connection. `replay` is a path (or document) that replaces the
    terminal: every read comes from it and every send is recorded."""

    def __init__(self, cfg=None, replay=None):
        self.cfg = cfg or {}
        self.block = self.cfg.get("mt5") if isinstance(self.cfg.get("mt5"), dict) else {}
        self.replay = None
        self.replay_path = None
        self.mt5 = None
        self.sent = []
        self.replies = []
        self.offset = _f(self.block.get("server_offset_hours"))
        if replay:
            self.replay = replay if isinstance(replay, dict) else self._read_replay(replay)
            self.replay_path = replay if isinstance(replay, str) else None
            self.replies = list(self.replay.get("send") or [])
            if self.offset is None:
                self.offset = _f(self.replay.get("server_offset_hours")) or 0.0
        else:
            self.mt5 = _import_mt5()
            path = self.block.get("terminal_path") or os.environ.get("MT5_PATH")
            ok = self.mt5.initialize(path) if path else self.mt5.initialize()
            if not ok:
                code, msg = _last_error(self.mt5)
                raise Mt5Error("the terminal did not initialize (%s %s). Open MetaTrader 5, log in to the "
                               "account, turn on Tools > Options > Expert Advisors > Allow algorithmic trading, "
                               "and check the path in \"mt5.terminal_path\" or MT5_PATH"
                               % (code, msg))
            login = os.environ.get("MT5_LOGIN")
            if login:
                pw = os.environ.get("MT5_PASSWORD") or ""
                server = os.environ.get("MT5_SERVER") or ""
                if not self.mt5.login(int(login), password=pw, server=server):
                    code, msg = _last_error(self.mt5)
                    raise Mt5Error("the terminal could not log in to %s on %s (%s %s); the terminal is already "
                                   "logged in to another account, so check the login in the terminal itself"
                                   % (login, server, code, msg))
        if self.offset is None:
            self.offset = self._detect_offset()

    # -- plumbing
    def _read_replay(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            raise Mt5Error("cannot read the replay file %s: %s" % (path, e))
        if not isinstance(doc, dict):
            raise Mt5Error("%s is not a replay document" % path)
        return doc

    def _detect_offset(self):
        """Ask a liquid symbol's tick what time the server thinks it is."""
        if self.replay is not None:
            return _f(self.replay.get("server_offset_hours")) or 0.0
        for sym in ("EURUSD", "XAUUSD", "US500", "EURUSD.a", "GBPUSD"):
            try:
                t = self.mt5.symbol_info_tick(sym)
            except Exception:
                t = None
            if t and t.time:
                return detect_offset(t.time)
        return 0.0

    def close(self):
        if self.mt5 is not None:
            try:
                self.mt5.shutdown()
            except Exception:
                pass

    def _symbols_doc(self):
        return {str(k).upper(): v for k, v in (self.replay.get("symbols") or {}).items()}

    # -- reads
    def terminal_info(self):
        if self.replay is not None:
            d = dict(self.replay.get("terminal") or {})
            d.setdefault("connected", True)
            d.setdefault("trade_allowed", True)
            d.setdefault("name", "MetaTrader 5 (replay)")
            return d
        d = _dict(self.mt5.terminal_info()) or {}
        return {"connected": bool(d.get("connected", False)), "trade_allowed": bool(d.get("trade_allowed", False)),
                "dlls_allowed": bool(d.get("dlls_allowed", False)), "tradeapi_disabled": bool(d.get("tradeapi_disabled", False)),
                "build": d.get("build"), "name": d.get("name"), "company": d.get("company"),
                "path": d.get("path"), "data_path": d.get("data_path"), "language": d.get("language"),
                "maxbars": d.get("maxbars"), "ping_last": d.get("ping_last"), "community_connection": bool(d.get("community_connection", False))}

    def account(self):
        if self.replay is not None:
            return norm_account(self.replay.get("account") or {}) or {}
        return norm_account(_dict(self.mt5.account_info()))

    def symbol_names(self, group=None):
        if self.replay is not None:
            return sorted(self._symbols_doc().keys())
        try:
            got = self.mt5.symbols_get(group) if group else self.mt5.symbols_get()
        except Exception as e:
            raise Mt5Error("the terminal refused symbols_get: %s" % e)
        return sorted([s.name for s in got or []])

    def symbols(self):
        """Every symbol the terminal lists, in the same shape as symbol()."""
        if self.replay is not None:
            return [dict(doc, symbol=name) for name, doc in sorted(self._symbols_doc().items())]
        try:
            got = self.mt5.symbols_get()
        except Exception as e:
            raise Mt5Error("the terminal refused symbols_get: %s" % e)
        out = []
        for s in got or []:
            try:
                out.append(norm_symbol(_dict(s)))
            except Exception:
                continue
        return out

    def symbol(self, name, select=True):
        sym = str(name or "").strip().upper()
        if self.replay is not None:
            doc = self._symbols_doc().get(sym)
            if not doc:
                return None
            out = dict(doc)
            out.setdefault("symbol", sym)
            out.setdefault("sessions", [])
            return out
        if select:
            try:
                if not self.mt5.symbol_select(sym, True):
                    return None
            except Exception:
                return None
        info = self.mt5.symbol_info(sym)
        if info is None:
            return None
        out = norm_symbol(_dict(info))
        try:
            sessions = []
            for day in range(7):
                idx = 0
                while idx < 4:
                    got = self.mt5.symbol_info_session_trade(sym, day, idx)
                    if not got:
                        break
                    start = int(got[0]) if not isinstance(got, dict) else got.get("from")
                    end = int(got[1]) if not isinstance(got, dict) else got.get("to")

                    def hm(sec):
                        sec = int(sec) % 86400
                        return "%02d:%02d" % (sec // 3600, (sec % 3600) // 60)
                    sessions.append({"day": day, "from": hm(start), "to": hm(end)})
                    idx += 1
            out["sessions"] = sessions
        except Exception:
            out["sessions"] = []
        return out

    def spec_with_suffix(self, name):
        """The broker's real symbol name, accepting a bare ticker."""
        sym = str(name or "").strip().upper()
        if self.replay is not None:
            names = self._symbols_doc()
            if sym in names:
                return sym
            for k in names:
                if k.upper().startswith(sym):
                    return k
            return sym
        if self.mt5.symbol_info(sym) is not None:
            return sym
        want = sym + str(self.block.get("symbol_suffix") or "")
        try:
            for s in self.mt5.symbols_get(want + "*") or []:
                if s.name.upper() == want.upper():
                    return s.name
        except Exception:
            pass
        return sym

    def quote(self, name):
        sym = str(name or "").strip().upper()
        if self.replay is not None:
            q = dict((self.replay.get("quotes") or {}).get(sym) or {})
            spec = self._symbols_doc().get(sym) or {}
            if not q:
                q = dict(spec.get("tick") or {})
            return q
        try:
            t = self.mt5.symbol_info_tick(sym)
        except Exception:
            t = None
        d = norm_tick(_dict(t))
        if d and d.get("time") and self.offset:
            d["time_utc"] = iso(d["time"], self.offset)
        return d

    def rates(self, name, timeframe="M5", count=500, start=None, end=None):
        sym = str(name or "").strip().upper()
        tf = tf_name(timeframe)
        if self.replay is not None:
            doc = self.replay.get("rates") or {}
            got = doc.get("%s:%s" % (sym, tf)) or doc.get("%s:%s" % (sym, tf.lower())) or []
            if start is None and end is None:
                got = got[-int(count):] if count else got
            return bars_from_rates(got)
        if start is not None or end is not None:
            from_dt = datetime.datetime.combine(start or datetime.date.today(), datetime.time(0, 0))
            to_dt = datetime.datetime.combine(end or datetime.date.today(), datetime.time(23, 59))
            raw = self.mt5.copy_rates_range(sym, TIMEFRAMES[tf], from_dt, to_dt)
        else:
            raw = self.mt5.copy_rates_from_pos(sym, TIMEFRAMES[tf], 0, int(count))
        if raw is None or len(raw) == 0:
            code, msg = _last_error(self.mt5)
            raise Mt5Error("no %s bars for %s (%s %s). Is the symbol in Market Watch, and is the market open?"
                           % (tf, sym, code, msg))
        return bars_from_rates(raw)

    def ticks(self, name, start, end, count=None):
        sym = str(name or "").strip().upper()
        if self.replay is not None:
            return list((self.replay.get("ticks") or {}).get(sym) or [])
        raw = self.mt5.copy_ticks_range(sym, start, end, self.mt5.COPY_TICKS_ALL)
        return [_dict(t) for t in raw or []]

    def positions(self, symbol=None):
        if self.replay is not None:
            out = [norm_position(p, self.offset) for p in self.replay.get("positions") or []]
        else:
            raw = self.mt5.positions_get(symbol=symbol) if symbol else self.mt5.positions_get()
            out = [norm_position(_dict(p), self.offset) for p in raw or []]
        if symbol:
            out = [p for p in out if str(p.get("symbol", "")).upper() == str(symbol).upper()]
        return out

    def orders(self, symbol=None):
        if self.replay is not None:
            out = [norm_order(o, self.offset) for o in self.replay.get("orders") or []]
        else:
            raw = self.mt5.orders_get(symbol=symbol) if symbol else self.mt5.orders_get()
            out = [norm_order(_dict(o), self.offset) for o in raw or []]
        if symbol:
            out = [p for p in out if str(p.get("symbol", "")).upper() == str(symbol).upper()]
        return out

    def deals(self, days=2, start=None, end=None):
        """Closed and opening deals, newest last. `days` counts back from now."""
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        end_utc = end or now
        start_utc = start or (end_utc - datetime.timedelta(days=int(days)))
        if self.replay is not None:
            out = [norm_deal(d, self.offset) for d in self.replay.get("deals") or []]
            return [d for d in out if _in_range(d.get("time_utc"), start_utc, end_utc)]
        frm = start_utc + datetime.timedelta(hours=self.offset or 0)
        to = end_utc + datetime.timedelta(hours=self.offset or 0)
        raw = self.mt5.history_deals_get(frm, to)
        return [norm_deal(_dict(d), self.offset) for d in raw or []]

    def calc_margin(self, action, symbol, volume, price):
        if self.replay is not None:
            spec = self._symbols_doc().get(str(symbol).upper()) or {}
            acct = self.account()
            rate = _f(spec.get("margin_initial"))
            px = _f(price) or 0.0
            contract = _f(spec.get("trade_contract_size")) or 100000.0
            if rate is not None and rate > 0:
                return volume * contract * px * rate / 100.0
            return volume * contract * px / (_f(acct.get("leverage")) or 100.0)
        v = self.mt5.order_calc_margin(ORDER_TYPES.get(str(action).lower(), 0), symbol, float(volume), float(price))
        return _f(v)

    def calc_profit(self, action, symbol, volume, price_open, price_close):
        if self.replay is not None:
            spec = self._symbols_doc().get(str(symbol).upper()) or {}
            tick_size = _f(spec.get("trade_tick_size")) or _f(spec.get("point")) or 0.00001
            tick_value = _f(spec.get("trade_tick_value")) or 1.0
            sign = 1.0 if str(action).lower() in ("buy", "0", "long") else -1.0
            return sign * (float(price_close) - float(price_open)) / tick_size * tick_value * float(volume)
        v = self.mt5.order_calc_profit(ORDER_TYPES.get(str(action).lower(), 0), symbol, float(volume),
                                       float(price_open), float(price_close))
        return _f(v)

    # -- writes
    def send(self, request):
        """Send one JSON-friendly request. Returns the normalized result."""
        req = dict(request)
        self.sent.append(req)
        if self.replay is not None:
            resp = self.replies.pop(0) if self.replies else {"retcode": 10009, "order": 0, "deal": 0,
                                                             "volume": req.get("volume"),
                                                             "price": req.get("price"), "comment": "replay"}
            resp = dict(resp)
            resp.setdefault("request", req)
            out = _norm_result(resp, req)
            out["sent"] = req
            return out
        raw = self._to_mt5_request(req)
        result = self.mt5.order_send(raw)
        if result is None:
            code, msg = _last_error(self.mt5)
            return {"ok": False, "retcode": code, "comment": "order_send returned nothing: %s" % msg,
                    "sent": raw}
        out = _norm_result(_dict(result), req)
        out["sent"] = raw
        return out

    def check(self, request):
        if self.replay is not None:
            return {"retcode": 0, "comment": "replay: the order would be accepted",
                    "margin": self.calc_margin(request.get("type", "buy"), request.get("symbol"),
                                               _f(request.get("volume")) or 0.0,
                                               _f(request.get("price")) or 0.0)}
        raw = self._to_mt5_request(request)
        got = self.mt5.order_check(raw)
        if got is None:
            code, msg = _last_error(self.mt5)
            return {"retcode": code, "comment": msg}
        d = _dict(got)
        return {"retcode": d.get("retcode"), "comment": d.get("comment"),
                "margin": _f(d.get("margin")), "margin_free": _f(d.get("margin_free")),
                "balance": _f(d.get("balance")), "equity": _f(d.get("equity")),
                "profit": _f(d.get("profit"))}

    def _to_mt5_request(self, req):
        mt5 = self.mt5
        action = str(req.get("action") or "deal").lower()
        out = {"action": getattr(mt5, "TRADE_ACTION_" + action.upper(), ACTIONS.get(action, 1)),
               "magic": int(_f(req.get("magic")) or 0),
               "comment": str(req.get("comment") or "")[:26]}
        if req.get("symbol"):
            sym = self.spec_with_suffix(req["symbol"])
            out["symbol"] = sym
            if req.get("volume") is not None:
                out["volume"] = float(req["volume"])
        if action == "deal":
            typ = str(req.get("type") or "buy").lower()
            out["type"] = ORDER_TYPES.get(typ, 0)
            if req.get("price") is not None:
                out["price"] = float(req["price"])
            if req.get("position") is not None:
                out["position"] = int(req["position"])
            if req.get("deviation") is not None:
                out["deviation"] = int(req["deviation"])
            out["type_time"] = ORDER_TIME.get(str(req.get("time") or "gtc").lower(), 0)
            fill = str(req.get("filling") or "auto").lower()
            if fill in FILLING:
                out["type_filling"] = FILLING[fill]
        elif action == "pending":
            typ = str(req.get("type") or "buy_limit").lower()
            out["type"] = ORDER_TYPES.get(typ, 2)
            out["price"] = float(req.get("price") or 0)
            out["type_time"] = ORDER_TIME.get(str(req.get("time") or "gtc").lower(), 0)
            if req.get("expiration"):
                out["expiration"] = epoch_of(req["expiration"])
            fill = str(req.get("filling") or "auto").lower()
            if fill in FILLING:
                out["type_filling"] = FILLING[fill]
            if req.get("stoplimit") is not None:
                out["stoplimit"] = float(req["stoplimit"])
        elif action == "sltp":
            out["position"] = int(req.get("position") or req.get("ticket") or 0)
            out["sl"] = float(req.get("sl") or 0)
            out["tp"] = float(req.get("tp") or 0)
        elif action == "modify":
            out["order"] = int(req.get("order") or req.get("ticket") or 0)
            out["price"] = float(req.get("price") or 0)
            out["sl"] = float(req.get("sl") or 0)
            out["tp"] = float(req.get("tp") or 0)
            out["type_time"] = ORDER_TIME.get(str(req.get("time") or "gtc").lower(), 0)
        elif action == "remove":
            out["order"] = int(req.get("order") or req.get("ticket") or 0)
        for k in ("sl", "tp"):
            if req.get(k) is not None and k not in out:
                out[k] = float(req[k])
        return out


def _in_range(iso_text, start, end):
    dt = parse_utc(iso_text)
    if dt is None:
        return True
    return start - datetime.timedelta(days=1) <= dt <= end + datetime.timedelta(days=1)


def _norm_result(d, req):
    rc = d.get("retcode")
    try:
        rc = int(rc)
    except (TypeError, ValueError):
        rc = None
    return {"ok": rc in OK_CODES, "retcode": rc,
            "retcode_text": RETCODES.get(rc, str(d.get("comment") or "")),
            "order": d.get("order"), "deal": d.get("deal"), "volume": _f(d.get("volume")),
            "price": _f(d.get("price")), "bid": _f(d.get("bid")), "ask": _f(d.get("ask")),
            "comment": d.get("comment") or "", "request_id": d.get("request_id"),
            "request": d.get("request") or req}


def _last_error(mt5):
    try:
        got = mt5.last_error()
        if isinstance(got, (tuple, list)) and len(got) >= 2:
            return got[0], got[1]
        return got, ""
    except Exception:
        return "?", ""


def _import_mt5():
    try:
        import MetaTrader5 as mt5          # noqa: F401
        return mt5
    except Exception as e:
        raise Mt5Error("the MetaTrader5 package is not available here (%s). It is Windows-only: on the "
                       "machine that runs MetaTrader 5, run\n"
                       "    python -m pip install MetaTrader5\n"
                       "and keep the terminal installed and logged in. On macOS or Linux, run the tools "
                       "against a saved snapshot instead (--replay) or use a Windows VPS. The other "
                       "commands explain themselves with: python3 mt5.py doctor" % e)


# ---------------------------------------------------------------- files and docs

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise Mt5Error("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise Mt5Error("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def write_csv(path, bars, digits=5):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("time,open,high,low,close,tick_volume,spread\n")
        for b in bars:
            fh.write("%s,%s,%s,%s,%s,%d,%d\n" % (iso(b["t"]), price(b["o"], digits), price(b["h"], digits),
                                                 price(b["l"], digits), price(b["c"], digits), b["v"],
                                                 b["spread"]))
    return path


def prices_doc(quotes, now_utc, offset=0.0):
    """Quotes -> the trader/prices.json shape the rest of the pack reads."""
    prices, detail = {}, {}
    for sym, q in quotes.items():
        bid, ask = _f(q.get("bid")), _f(q.get("ask"))
        if bid is None or ask is None:
            continue
        prices[sym] = round((bid + ask) / 2.0, 8)
        detail[sym] = {"bid": bid, "ask": ask, "spread": round(ask - bid, 8),
                       "time": q.get("time_utc") or iso(q.get("time"), offset),
                       "fetched": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "mt5"}
    return {"as_of": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "mt5: bid/ask midpoint",
            "prices": prices, "detail": detail}


def yahoo_doc(symbol, bars, meta=None, interval="5m", digits=5, offset_hours=0.0):
    """MT5 bars -> Yahoo's chart JSON, so the free chart tools can read them.
    The timestamps are moved from the broker's server clock onto real UTC, so
    the New York session logic in the other tools reads the right hours; the
    bars themselves are still the broker's own sessions."""
    meta = dict(meta or {})
    meta.setdefault("symbol", symbol)
    meta.setdefault("currency", "USD")
    meta.setdefault("exchangeName", "MT5")
    meta.setdefault("instrumentType", "FOREX")
    meta.setdefault("timezone", "UTC")
    meta.setdefault("exchangeTimezoneName", "UTC")
    meta.setdefault("dataGranularity", interval)
    if bars:
        meta.setdefault("regularMarketPrice", bars[-1]["c"])
        meta.setdefault("regularMarketTime", int(bars[-1]["t"] - (offset_hours or 0.0) * 3600.0))
        meta.setdefault("chartPreviousClose", bars[0]["o"])
    return {"chart": {"result": [{
        "meta": meta,
        "timestamp": [int(b["t"] - (offset_hours or 0.0) * 3600.0) for b in bars],
        "indicators": {"quote": [{
            "open": [b["o"] for b in bars], "high": [b["h"] for b in bars],
            "low": [b["l"] for b in bars], "close": [b["c"] for b in bars],
            "volume": [b["v"] for b in bars]}]},
    }], "error": None}}


def request(order, cfg, spec, quote):
    """A proposed order -> the exact MT5 request, JSON-friendly. The numeric
    constants are filled in at send time by Terminal._to_mt5_request, so the
    ticket can be read (and matched) without a terminal."""
    side = str(order.get("side") or "buy").lower()
    typ = str(order.get("type") or "market").lower()
    bid, ask = _f((quote or {}).get("bid")), _f((quote or {}).get("ask"))
    action = "deal" if typ == "market" else "pending"
    price = _f(order.get("price"))
    if action == "deal":
        px = ask if side == "buy" else bid
        if px is None:
            px = _f((order.get("plan") or {}).get("entry"))
    else:
        px = price
    req = {"action": action, "symbol": str(order.get("symbol") or "").upper(),
           "volume": _f(order.get("volume")), "type": typ, "price": round(px, 8) if px is not None else None,
           "deviation": int(_f(order.get("deviation")) or 20),
           "magic": int(_f(order.get("magic")) or _f((cfg.get("mt5") or {}).get("magic")) or 20261019),
           "comment": str(order.get("comment") or "")[:26],
           "time": str(order.get("time") or "gtc").lower()}
    for k in ("sl", "tp"):
        if _f(order.get(k)) is not None:
            req[k] = round(_f(order[k]), 8)
    fill = str(order.get("filling") or "auto").lower()
    if fill == "auto" and spec:
        modes = spec.get("filling_modes") or ["fok", "ioc", "return"]
        fill = "fok" if "fok" in modes else ("ioc" if "ioc" in modes else "return")
    req["filling"] = fill
    if req["time"] in ("specified", "specified_day"):
        req["expiration"] = order.get("expiration")
    return req
