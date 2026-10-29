import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime

from _load import load, ROOT, FIX

mt5 = load("trader-mt5", "mt5")
mt5lib = load("trader-mt5", "mt5lib")
rules = load("trader-mt5", "mt5rules")
lots = load("trader-budget", "lots")
ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CTX = os.path.join(FIX, "trader-mt5", "context.json")
POSITIONS = os.path.join(FIX, "trader-mt5", "positions.json")
CFG = os.path.join(ROOT, "trader-budget", "config.example.json")
NOW = "2026-10-20 09:35"
TODAY = "2026-10-20"


def read(path):
    with open(path) as fh:
        return json.load(fh)


def write(path, doc):
    with open(path, "w") as fh:
        json.dump(doc, fh)


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mod.main(argv)
    return code, out.getvalue(), err.getvalue()


def ctx_doc():
    return read(CTX)


def mt5_order(**over):
    """A valid EURUSD order with the fixture's spec and quote, the shape
    lots.py writes."""
    ctx = ctx_doc()
    spec = ctx["symbols"]["EURUSD"]
    quote = dict(ctx["quotes"]["EURUSD"])
    order = {"venue": "mt5", "symbol": "EURUSD", "side": "buy", "type": "market", "volume": "0.27",
             "deviation": 20, "magic": 20261019, "comment": "orb", "filling": "auto", "time": "gtc",
             "sl": 1.08432, "tp": 1.08862, "spec": spec, "quote": quote,
             "risk": {"risk": 48.33, "risk_pct": 0.96, "commission": 1.89, "rr": 1.5, "margin": 293.23,
                      "margin_pct": 5.9, "margin_level_after": 1709.0, "pips_risk": 17.2,
                      "spread_pips": 1.2, "breakeven": 1.08616, "per_lot_risk": 172.0},
             "why": "opening-range breakout"}
    order.update(over)
    return order


def config(**over):
    cfg = read(CFG)
    for k, v in over.items():
        if k == "mt5":
            cfg.setdefault("mt5", {}).update(v)
        else:
            cfg[k] = v
    return cfg


class TimeAndMath(unittest.TestCase):
    def test_new_york_offset(self):
        self.assertEqual(rules.eastern_offset(datetime(2026, 7, 1, 12)), -4)
        self.assertEqual(rules.eastern_offset(datetime(2026, 12, 1, 12)), -5)
        self.assertEqual(rules.eastern_offset(datetime(2026, 10, 20, 13, 35)), -4)

    def test_server_clock(self):
        """A GMT+3 server at 16:35 is 13:35 UTC and 09:35 in New York."""
        srv = datetime(2026, 10, 20, 16, 35)
        self.assertEqual(rules.server_to_ny(srv, 3), datetime(2026, 10, 20, 9, 35))
        utc = datetime(2026, 10, 20, 13, 35)
        tick = (utc - datetime(1970, 1, 1)).total_seconds() + 3 * 3600 + 20   # 20s of staleness
        self.assertEqual(mt5lib.detect_offset(tick, utc), 3.0)

    def test_pip_and_tick_value(self):
        ctx = ctx_doc()["symbols"]
        self.assertAlmostEqual(rules.pip(ctx["EURUSD"]), 0.0001)
        self.assertAlmostEqual(rules.pip(ctx["XAUUSD"]), 0.1)      # 2 digits: a pip is 10 points
        self.assertAlmostEqual(rules.pip(ctx["US500"]), 1.0)       # 1 digit: a pip is one index point
        self.assertAlmostEqual(rules.money_per_pip(ctx["EURUSD"]), 10.0)
        self.assertAlmostEqual(rules.money_per_pip(ctx["XAUUSD"]), 10.0)
        self.assertAlmostEqual(rules.money_per_pip(ctx["US500"]), 1.0)
        self.assertAlmostEqual(rules.distance_money(ctx["EURUSD"], 0.00172, 0.29), 49.88, places=2)

    def test_volume_ladder(self):
        spec = ctx_doc()["symbols"]["EURUSD"]
        self.assertEqual(rules.floor_volume(0.137, spec), 0.13)
        self.assertEqual(rules.floor_volume(0.005, spec), 0.0)
        self.assertTrue(rules.volume_fits(0.29, spec)[0])
        ok, why = rules.volume_fits(0.137, spec)
        self.assertFalse(ok)
        self.assertIn("step", why)
        self.assertFalse(rules.volume_fits(0.001, spec)[0])
        self.assertFalse(rules.volume_fits(500, spec)[0])

    def test_rollover_is_converted_from_server_time(self):
        cfg = rules.mt5_config({})
        start, end = rules.rollover_window(cfg, {"server_offset_hours": 3},
                                           datetime(2026, 10, 20, 13, 35))
        self.assertEqual((start.strftime("%H:%M"), end.strftime("%H:%M")), ("16:55", "17:10"))

    def test_fingerprint_matches_the_ticket(self):
        order = mt5_order()
        self.assertEqual(rules.fingerprint(order), ticket.fingerprint(order))
        changed = mt5_order(volume="0.30")
        self.assertNotEqual(rules.fingerprint(order), rules.fingerprint(changed))


class ConfigContract(unittest.TestCase):
    def test_the_example_block_is_the_defaults(self):
        """config.example.json and MT5_DEFAULTS cannot drift apart: what the
        docs promise, init writes and the rules read are one set of numbers."""
        block = read(CFG)["mt5"]
        for key, value in rules.MT5_DEFAULTS.items():
            if key == "venue":
                continue                      # the order carries it, the block need not
            self.assertIn(key, block, key)
            if key in ("session", "guard"):
                for k2, v2 in value.items():
                    self.assertEqual(block[key][k2], v2, "%s.%s" % (key, k2))
            else:
                self.assertEqual(block[key], value, key)


class Lots(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.plan = os.path.join(self.d, "plan.json")
        self.orders = os.path.join(self.d, "orders.json")
        self.cfgfile = os.path.join(self.d, "config.json")
        write(self.cfgfile, config())

    def tearDown(self):
        shutil.rmtree(self.d)

    def plan_from_mt5(self, symbol="EURUSD", tf="M5"):
        code, _, _ = run(mt5, ["--replay", CTX, "--now", NOW, "setup", symbol, "--tf", tf, "--count",
                              "300", "--write-plan", self.plan])
        self.assertEqual(code, 0)
        return read(self.plan)

    def size(self, *extra, plan=None):
        return run(lots, ["--plan", plan or self.plan, "--context", CTX, "--config", self.cfgfile,
                          "--write", self.orders, "--now", NOW] + list(extra))

    def test_sizes_to_the_risk_budget_in_lots(self):
        plan = self.plan_from_mt5()
        self.assertEqual(plan["verdict"], "ready")
        self.assertEqual(plan["side"], "buy")
        self.assertLess(plan["stop"], plan["target"])
        code, out, err = self.size()
        self.assertEqual(code, 0, err)
        order = read(self.orders)["orders"][0]
        self.assertEqual(order["venue"], "mt5")
        self.assertEqual(order["type"], "market")
        # risk at the stop plus the 7 per lot commission stays inside the 50 budget
        self.assertLessEqual(order["risk"]["risk"], 50.01)
        self.assertGreater(order["risk"]["risk"], 30)
        self.assertAlmostEqual(round(float(order["volume"]) / 0.01), float(order["volume"]) / 0.01, places=6)
        self.assertLess(order["sl"], order["plan"]["entry"])
        self.assertGreater(order["tp"], order["sl"])
        self.assertEqual(order["filling"], "auto")
        self.assertGreaterEqual(order["volume"], "0.01")
        self.assertEqual(order["spec"]["symbol"], "EURUSD")
        self.assertIn("per lot", order["why"])

    def test_a_smaller_budget_means_fewer_lots(self):
        self.plan_from_mt5()
        self.size()
        big = float(read(self.orders)["orders"][0]["volume"])
        self.size("--risk", "15")
        small = float(read(self.orders)["orders"][0]["volume"])
        self.assertLess(small, big)
        self.assertGreater(small, 0)

    def test_it_uses_the_ask_for_a_buy(self):
        self.plan_from_mt5()
        self.size()
        order = read(self.orders)["orders"][0]
        # the plan is sized at the ask (1.08604), not the bid (1.08592)
        self.assertAlmostEqual(order["plan"]["entry"], 1.08604, places=5)
        self.assertEqual(float(order["spec"]["tick"]["ask"]), 1.08604)

    def test_it_refuses_a_stop_inside_the_stops_level(self):
        write(self.plan, {"venue": "mt5", "symbol": "XAUUSD", "side": "buy", "entry": 2412.62,
                          "stop": 2412.50, "target": 2420.00, "setup": "orb", "date": TODAY})
        code, _, err = self.size("--symbol", "XAUUSD")
        self.assertEqual(code, 1)
        self.assertIn("stops level", err)

    def test_it_refuses_a_bad_reward_risk(self):
        write(self.plan, {"venue": "mt5", "symbol": "EURUSD", "side": "buy", "entry": 1.08604,
                          "stop": 1.08432, "target": 1.08621, "setup": "orb", "date": TODAY})
        code, _, err = self.size()
        self.assertEqual(code, 1)
        self.assertIn("reward:risk", err)

    def test_it_refuses_a_wide_spread(self):
        self.plan_from_mt5()
        code, _, err = self.size("--spread", "60")
        self.assertEqual(code, 1)
        self.assertIn("spread", err)

    def test_it_refuses_a_budget_under_the_minimum_lot(self):
        self.plan_from_mt5()
        code, _, err = self.size("--risk", "0.5")
        self.assertEqual(code, 1)
        self.assertIn("minimum lot", err)

    def test_the_margin_cap_shrinks_the_size(self):
        self.plan_from_mt5()
        self.size()
        full = float(read(self.orders)["orders"][0]["volume"])
        cfg = config()
        cfg["mt5"]["max_margin_use_pct"] = 1
        write(self.cfgfile, cfg)
        code, _, err = self.size()
        self.assertEqual(code, 0, err)
        capped = float(read(self.orders)["orders"][0]["volume"])
        self.assertLess(capped, full)

    def test_a_pending_order_carries_its_price(self):
        write(self.plan, {"venue": "mt5", "symbol": "EURUSD", "side": "buy", "entry": 1.09100,
                          "stop": 1.08800, "target": 1.09700, "setup": "breakout", "date": TODAY})
        code, out, err = self.size("--type", "buy_stop", "--price", "1.09050")
        self.assertEqual(code, 0, err)
        order = read(self.orders)["orders"][0]
        self.assertEqual(order["type"], "buy_stop")
        self.assertAlmostEqual(order["price"], 1.09050, places=5)
        self.assertIn("buy stop order", out)

    def test_partial_volume(self):
        code, out, _ = run(lots, ["--partial", "--symbol", "EURUSD", "--lots", "0.29", "--at-r", "1",
                                  "--pct", "50", "--context", CTX, "--config", self.cfgfile, "--json"])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc["volume"], 0.14)
        self.assertEqual(doc["left"], 0.15)

    def test_an_unknown_symbol_says_what_to_do(self):
        write(self.plan, {"venue": "mt5", "symbol": "EURUSDX", "side": "buy", "entry": 1.08,
                          "stop": 1.07, "target": 1.09, "setup": "orb", "date": TODAY})
        code, _, err = self.size("--symbol", "EURUSDX")
        self.assertEqual(code, 1)
        self.assertIn("mt5.py symbols", err)


class Rules(unittest.TestCase):
    def cfg(self, **over):
        return config(**over)

    def check(self, orders, ctx=None, state=None, now=NOW, cfg=None):
        return rules.check_orders(list(enumerate(orders, 1)), cfg or self.cfg(),
                                  ctx if ctx is not None else ctx_doc(), state, TODAY,
                                  rules.parse_now(now))

    def test_a_good_order_passes(self):
        res = self.check([mt5_order()])
        self.assertEqual(res["results"][0]["verdict"], "PASS", res["results"][0]["reasons"])
        r = res["results"][0]
        self.assertEqual(r["venue"], "mt5")
        self.assertAlmostEqual(r["max_loss"], 48.33, places=2)
        self.assertAlmostEqual(r["volume"], 0.27)
        self.assertAlmostEqual(r["spread_pips"], 1.2)
        self.assertEqual(res["account"]["trade_mode"], "demo")

    def test_no_stop_blocks(self):
        res = self.check([mt5_order(sl=None)])
        self.assertEqual(res["results"][0]["verdict"], "BLOCK")
        self.assertTrue(any("no stop-loss" in x for x in res["results"][0]["reasons"]))

    def test_a_stop_on_the_wrong_side_blocks(self):
        res = self.check([mt5_order(sl=1.09000, tp=1.10000)])
        reasons = " ".join(res["results"][0]["reasons"])
        self.assertIn("under the entry", reasons)

    def test_a_stop_inside_the_stops_level_blocks(self):
        ctx = ctx_doc()
        order = mt5_order(symbol="XAUUSD", volume="0.10", sl=2412.55, tp=2420.00,
                          risk={"risk": 40.0})
        res = self.check([order], ctx=ctx)
        reasons = " ".join(res["results"][0]["reasons"])
        self.assertIn("stops level", reasons)

    def test_a_volume_off_the_step_blocks(self):
        res = self.check([mt5_order(volume="0.137")])
        self.assertIn("step", " ".join(res["results"][0]["reasons"]))

    def test_too_many_lots_blocks(self):
        res = self.check([mt5_order(volume="5.00", sl=1.08432, tp=1.09)])
        self.assertIn("max_lots_per_order", " ".join(res["results"][0]["reasons"]))

    def test_a_wide_spread_blocks(self):
        res = self.check([mt5_order()], cfg=self.cfg(mt5={"max_spread_pips": 0.5}))
        self.assertIn("spread", " ".join(res["results"][0]["reasons"]))

    def test_a_stale_quote_blocks(self):
        res = self.check([mt5_order()], now="2026-10-20 10:30")
        reasons = " ".join(res["results"][0]["reasons"])
        self.assertIn("seconds old", reasons)

    def test_a_symbol_not_allowlisted_blocks(self):
        res = self.check([mt5_order()], cfg=self.cfg(mt5={"symbols": ["XAUUSD"]}))
        self.assertIn("not on your mt5.symbols list", " ".join(res["results"][0]["reasons"]))

    def test_a_missing_snapshot_blocks_with_a_reason(self):
        res = self.check([mt5_order()], ctx={})
        r = res["results"][0]
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("no MT5 snapshot" in x for x in r["reasons"]))
        self.assertTrue(any("snapshot" in w for w in r["warnings"]))

    def test_a_real_account_needs_allow_live(self):
        ctx = ctx_doc()
        ctx["account"] = dict(ctx["account"], trade_mode="real")
        res = self.check([mt5_order()], ctx=ctx)
        self.assertIn("REAL-money account", " ".join(res["results"][0]["reasons"]))
        res = self.check([mt5_order()], ctx=ctx, cfg=self.cfg(mt5={"allow_live": True}))
        self.assertEqual(res["results"][0]["verdict"], "PASS")

    def test_the_daily_loss_counts_today(self):
        # today's closed trades lost 41.40, and 110 of the 150 is gone
        state = {"orders": [{"date": TODAY, "status": "placed", "kind": "entry", "symbol": "XAUUSD",
                             "side": "buy", "max_loss": 110.0}]}
        res = self.check([mt5_order()], state=state)
        reasons = " ".join(res["results"][0]["reasons"])
        self.assertIn("max_daily_loss_usd", reasons)
        self.assertAlmostEqual(res["loss_today"], 127.1, places=1)

    def test_an_entry_already_placed_today_blocks(self):
        state = {"orders": [{"date": TODAY, "status": "placed", "kind": "entry", "symbol": "EURUSD",
                             "side": "buy", "max_loss": 20.0}]}
        res = self.check([mt5_order()], state=state)
        self.assertIn("already placed today", " ".join(res["results"][0]["reasons"]))

    def test_the_entry_window(self):
        res = self.check([mt5_order()], now="2026-10-20 19:30")
        self.assertIn("no new entries after", " ".join(res["results"][0]["reasons"]))
        res = self.check([mt5_order()], now="2026-10-20 02:00")
        self.assertIn("no new entries before", " ".join(res["results"][0]["reasons"]))

    def test_the_rollover_window_blocks_new_entries(self):
        res = self.check([mt5_order()], now="2026-10-20 17:00")
        self.assertIn("rollover", " ".join(res["results"][0]["reasons"]))

    def test_the_weekend_is_closed(self):
        res = self.check([mt5_order()], now="2026-10-24 10:00")
        self.assertIn("closed on Saturday", " ".join(res["results"][0]["reasons"]))

    def test_the_margin_cap_blocks(self):
        res = self.check([mt5_order()], cfg=self.cfg(mt5={"max_margin_use_pct": 1}))
        self.assertIn("margin", " ".join(res["results"][0]["reasons"]))

    def test_max_open_positions_blocks(self):
        ctx = read(POSITIONS)
        order = mt5_order()
        res = self.check([order], ctx=ctx, cfg=self.cfg(mt5={"max_open_positions": 2}))
        self.assertIn("open positions", " ".join(res["results"][0]["reasons"]))

    def test_a_short_is_blocked_unless_allowed(self):
        short = mt5_order(side="sell", sl=1.08700, tp=1.08300, volume="0.27")
        res = self.check([short])
        self.assertIn("allow_short", " ".join(res["results"][0]["reasons"]))
        res = self.check([short], cfg=self.cfg(allow_short=True))
        self.assertEqual(res["results"][0]["verdict"], "PASS", res["results"][0]["reasons"])

    def test_an_exit_is_never_blocked_by_the_entry_rules(self):
        ctx = read(POSITIONS)          # holds 0.20 lots of EURUSD long
        exit_order = {"venue": "mt5", "symbol": "EURUSD", "side": "sell", "type": "market",
                      "volume": "0.20", "deviation": 20, "magic": 20261019, "comment": "close"}
        res = self.check([exit_order], ctx=ctx, now="2026-10-20 20:40")
        r = res["results"][0]
        self.assertEqual(r["kind"], "exit")
        self.assertEqual(r["verdict"], "PASS", r["reasons"])
        self.assertIsNone(r["max_loss"])

    def test_an_exit_cannot_close_more_than_is_open(self):
        ctx = read(POSITIONS)
        exit_order = {"venue": "mt5", "symbol": "EURUSD", "side": "sell", "type": "market",
                      "volume": "0.50", "deviation": 20, "magic": 20261019}
        res = self.check([exit_order], ctx=ctx)
        self.assertIn("holds 0.2 lots", " ".join(res["results"][0]["reasons"]))

    def test_a_sell_on_a_long_is_an_exit_not_a_hedge(self):
        ctx = read(POSITIONS)                     # 0.20 lots of EURUSD long
        part = mt5_order(side="sell", volume="0.10", sl=None, tp=None)
        res = self.check([part], ctx=ctx)
        self.assertEqual(res["results"][0]["kind"], "exit")
        self.assertEqual(res["results"][0]["verdict"], "PASS", res["results"][0]["reasons"])
        # an order that says it is an entry while a long is open is a hedge
        hedge = mt5_order(side="sell", volume="0.10", intent="entry", sl=1.08800, tp=1.08000)
        res = self.check([hedge], ctx=ctx, cfg=self.cfg(allow_short=True))
        self.assertIn("hedge", " ".join(res["results"][0]["reasons"]))

    def test_pending_orders_need_a_price(self):
        res = self.check([mt5_order(type="buy_limit")])
        self.assertIn("needs a price", " ".join(res["results"][0]["reasons"]))

    def test_the_filling_mode_is_resolved_for_the_ticket(self):
        res = self.check([mt5_order()])
        self.assertIn("filling fok", " ".join(res["results"][0]["info"]))


class TerminalAndCli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.plan = os.path.join(self.d, "plan.json")
        self.orders = os.path.join(self.d, "orders.json")
        self.risk = os.path.join(self.d, "risk.json")
        self.state = os.path.join(self.d, "state.json")
        self.cfg = os.path.join(self.d, "config.json")
        write(self.cfg, config())

    def tearDown(self):
        shutil.rmtree(self.d)

    def mt5run(self, *args, replay=CTX, now=NOW):
        return run(mt5, ["--replay", replay, "--now", now, "--config", self.cfg] + list(args))

    def test_doctor(self):
        code, out, _ = self.mt5run("doctor")
        self.assertEqual(code, 0)
        self.assertIn("account: 5001234 DEMO on Broker-Demo", out)
        self.assertIn("UTC+3", out)
        self.assertIn("symbols visible: 3", out)

    def test_account_spec_quote(self):
        code, out, _ = self.mt5run("account")
        self.assertEqual(code, 0)
        self.assertIn("balance $5,000.00", out)
        self.assertIn("1:100", out)
        code, out, _ = self.mt5run("spec", "XAUUSD")
        self.assertIn("pip 0.1", out)
        self.assertIn("one pip is about $10.00", out)
        self.assertIn("stops level 50 points", out)
        prices = os.path.join(self.d, "prices.json")
        code, out, _ = self.mt5run("quote", "EURUSD", "XAUUSD", "--write", prices)
        self.assertEqual(code, 0)
        doc = read(prices)
        self.assertAlmostEqual(doc["prices"]["EURUSD"], 1.08598, places=5)
        self.assertEqual(doc["detail"]["EURUSD"]["source"], "mt5")
        self.assertEqual(doc["detail"]["EURUSD"]["bid"], 1.08592)

    def test_bars_levels_and_the_yahoo_export(self):
        bars = os.path.join(self.d, "bars.json")
        csv = os.path.join(self.d, "bars.csv")
        yahoo = os.path.join(self.d, "yahoo.json")
        code, _, err = self.mt5run("bars", "EURUSD", "--tf", "M5", "--count", "200", "--write", bars,
                                   "--csv", csv, "--yahoo", yahoo)
        self.assertEqual(code, 0, err)
        doc = read(bars)
        self.assertEqual(len(doc["bars"]), 200)
        self.assertEqual(doc["timeframe"], "M5")
        self.assertTrue(os.path.exists(csv))
        y = read(yahoo)["chart"]["result"][0]
        self.assertEqual(len(y["timestamp"]), 200)
        self.assertEqual(len(y["indicators"]["quote"][0]["close"]), 200)
        # the chart's clock is UTC, not the broker's GMT+3, so the equity tools
        # read the same New York hours as they would from Yahoo
        self.assertEqual(y["timestamp"][0], doc["bars"][0]["t"] - 3 * 3600)

        code, out, _ = self.mt5run("levels", "EURUSD", "--or-minutes", "60")
        self.assertEqual(code, 0)
        self.assertIn("opening range (60 min)", out)
        lv = json.loads(self.mt5run("levels", "EURUSD", "--or-minutes", "60", "--json")[1])
        self.assertLess(lv["opening_range"]["low"], lv["opening_range"]["high"])
        self.assertLess(lv["opening_range"]["high"], lv["last"])
        self.assertEqual(lv["session_open"], "03:00")
        self.assertIn("pivots", lv)
        self.assertIsNotNone(lv["prev_day"])

    def test_scan_ranks_a_list_of_symbols(self):
        out = os.path.join(self.d, "scan.json")
        code, text, err = self.mt5run("scan", "--tf", "M5", "--count", "300", "--write", out)
        self.assertEqual(code, 0, err)
        self.assertIn("SCAN M5", text)
        self.assertIn("READY BUY", text)
        doc = read(out)
        self.assertEqual(doc["timeframe"], "M5")
        self.assertEqual(doc["ready"], 1)
        self.assertEqual(len(doc["symbols"]), 3)
        self.assertEqual(doc["symbols"][0]["symbol"], "EURUSD")
        self.assertEqual(doc["symbols"][0]["verdict"], "ready")
        self.assertTrue(any("bars" in " ".join(r["why"]) for r in doc["symbols"]
                            if r["verdict"] == "unknown"))
        code, _, err = self.mt5run("scan", "--symbols", "NOPE")
        self.assertEqual(code, 0, err)                 # an unknown symbol is a row, not a crash

    def test_session_shows_both_clocks_and_rollover(self):
        code, out, _ = self.mt5run("session", "EURUSD")
        self.assertEqual(code, 0)
        self.assertIn("Server time Tue 2026-10-20 16:35 (UTC+3)", out)
        self.assertIn("New York Tue 09:35", out)
        self.assertIn("Broker rollover 16:55 to 17:10 New York", out)
        self.assertIn("flat by 20:55", out)

    def test_setup_writes_a_plan(self):
        code, out, err = self.mt5run("setup", "EURUSD", "--tf", "M5", "--count", "300",
                                     "--write-plan", self.plan)
        self.assertEqual(code, 0, err)
        plan = read(self.plan)
        self.assertEqual(plan["venue"], "mt5")
        self.assertEqual(plan["side"], "buy")
        self.assertEqual(plan["verdict"], "ready")
        self.assertLess(plan["stop"], plan["entry"])
        self.assertGreater(plan["target"], plan["entry"])
        self.assertAlmostEqual(plan["reward_risk"], 1.5)
        self.assertEqual(plan["flat_by"], "20:55")

    def test_positions_and_orders(self):
        code, out, _ = self.mt5run("positions", replay=POSITIONS)
        self.assertEqual(code, 0)
        self.assertIn("BUY EURUSD 0.2 lots", out)
        self.assertIn("SELL XAUUSD 0.1 lots", out)
        self.assertIn("risk at the stop", out)
        code, out, _ = self.mt5run("orders", replay=POSITIONS)
        self.assertIn("BUY LIMIT EURUSD 0.1 lots at 1.08400", out)

    def test_history_journal(self):
        j = json.loads(self.mt5run("history", "--days", "2", "--json", replay=POSITIONS)[1])
        self.assertEqual(j["closed_trades"], 2)
        self.assertEqual(j["wins"], 1)
        self.assertEqual(j["losses"], 1)
        self.assertAlmostEqual(j["net_profit"], -17.10, places=2)
        self.assertAlmostEqual(j["profit_factor"], 0.59, places=2)
        self.assertAlmostEqual(j["max_drawdown"], 41.40, places=2)
        out = os.path.join(self.d, "journal.json")
        code, _, _ = self.mt5run("history", "--days", "2", "--write", out, replay=POSITIONS)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out))

    def test_margin(self):
        code, out, _ = self.mt5run("margin", "--symbol", "EURUSD", "--volume", "0.50", "--action", "buy")
        self.assertEqual(code, 0)
        self.assertIn("needs $543.02", out)         # 0.50 x 100,000 x 1.08604 / 100
        doc = json.loads(self.mt5run("margin", "--symbol", "EURUSD", "--volume", "0.50", "--json")[1])
        self.assertAlmostEqual(doc["margin"], 543.02, places=2)

    def test_snapshot_collects_the_orders_symbols_and_deals(self):
        write(self.plan, {"venue": "mt5", "symbol": "EURUSD", "side": "buy", "entry": 1.08604,
                          "stop": 1.08432, "target": 1.08862})
        write(self.orders, {"orders": [mt5_order()]})
        out = os.path.join(self.d, "context.json")
        code, text, err = self.mt5run("snapshot", "--write", out, "--plan", self.plan,
                                      "--orders", self.orders, replay=POSITIONS)
        self.assertEqual(code, 0, err)
        doc = read(out)
        self.assertIn("EURUSD", doc["symbols"])
        self.assertIn("XAUUSD", doc["symbols"])
        self.assertEqual(doc["server_offset_hours"], 3)
        self.assertEqual(len(doc["positions"]), 2)
        self.assertEqual(len(doc["deals"]), 4)
        self.assertEqual(len(doc["orders"]), 1)
        self.assertEqual(doc["symbols"]["EURUSD"]["tick"]["ask"], 1.08604)

    def test_backtest(self):
        bt = json.loads(self.mt5run("backtest", "EURUSD", "--tf", "M5", "--count", "400",
                                    "--rr", "1.5", "--json")[1])
        self.assertGreater(bt["trades"], 0)
        self.assertGreaterEqual(bt["trades"], 1)
        self.assertEqual(bt["sessions"], 2)
        self.assertIn("expectancy_r", bt)
        self.assertGreaterEqual(bt["small_sample"], False)
        for t in bt["detail"]:
            self.assertIn(t["why"].split()[0], ("target", "stop", "flat", "session"))
            self.assertIn(t["side"], ("buy", "sell"))

    def test_unknown_symbol_and_no_replay_are_explained(self):
        code, _, err = self.mt5run("spec", "NOPE")
        self.assertEqual(code, 1)
        self.assertIn("symbols --search", err)
        code, _, err = run(mt5, ["--config", self.cfg, "--now", NOW, "account"])
        self.assertEqual(code, 1)
        self.assertIn("MetaTrader5", err)


class TheThreeGates(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.plan = os.path.join(self.d, "plan.json")
        self.orders = os.path.join(self.d, "orders.json")
        self.risk = os.path.join(self.d, "risk.json")
        self.state = os.path.join(self.d, "state.json")
        self.cfg = os.path.join(self.d, "config.json")
        write(self.cfg, config())
        run(mt5, ["--replay", CTX, "--now", NOW, "setup", "EURUSD", "--tf", "M5", "--count", "300",
                  "--write-plan", self.plan])
        code, _, err = run(lots, ["--plan", self.plan, "--context", CTX, "--config", self.cfg,
                                  "--write", self.orders, "--now", NOW])
        self.assertEqual(code, 0, err)
        self.order = read(self.orders)["orders"][0]

    def tearDown(self):
        shutil.rmtree(self.d)

    def mt5run(self, *args):
        return run(mt5, ["--replay", CTX, "--now", NOW, "--config", self.cfg] + list(args))

    def run_risk(self):
        return run(check, ["--orders", self.orders, "--config", self.cfg, "--portfolio",
                           os.path.join(self.d, "none.json"), "--prices", os.path.join(self.d, "none.json"),
                           "--state", self.state, "--mt5-context", CTX, "--now", NOW, "--out", self.risk])

    def ticket(self, *args):
        args = list(args)
        cmd = args[0]
        return run(ticket, [cmd, "--orders", self.orders, "--config", self.cfg, "--risk", self.risk,
                            "--state", self.state, "--now", NOW] + args[1:])

    def test_the_whole_flow_and_no_second_send(self):
        code, out, err = self.ticket("show")
        self.assertEqual(code, 1)                     # no risk check yet
        self.assertIn("NOT READY", out)
        self.assertIn("MetaTrader 5", out)
        self.assertEqual(self.ticket("approve", "--index", "1", "--reply", "yes")[0], 1)

        code, out, err = self.run_risk()
        self.assertEqual(code, 0, out + err)
        risk = read(self.risk)
        self.assertEqual(risk["results"][0]["venue"], "mt5")
        self.assertEqual(risk["results"][0]["verdict"], "PASS")
        self.assertIn("MT5 DEMO account", out)

        code, out, _ = self.ticket("show", "--index", "1")
        self.assertEqual(code, 0)
        self.assertIn("MetaTrader 5", out)
        self.assertIn('"action": "deal"', out)
        self.assertIn("mt5.py execute --index 1", out)

        code, out, _ = self.ticket("approve", "--index", "1", "--reply", "sure")
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", out)
        self.assertFalse(os.path.exists(self.state))

        code, out, _ = self.ticket("approve", "--index", "1", "--reply", "yes")
        self.assertEqual(code, 0)
        self.assertIn("mt5.py execute --index 1", out)
        rec = read(self.state)["orders"][0]
        self.assertEqual((rec["status"], rec["venue"], rec["reply"]), ("approved", "mt5", "yes"))
        self.assertEqual(rec["fingerprint"], rules.fingerprint(self.order))

        code, out, err = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                     "--risk", self.risk, "--state", self.state)
        self.assertEqual(code, 0, err)
        self.assertIn("SENT", out)
        state = read(self.state)
        self.assertEqual([r["status"] for r in state["orders"]], ["approved", "placed"])
        self.assertEqual(state["orders"][1]["kind"], "entry")
        self.assertAlmostEqual(state["orders"][1]["max_loss"], risk["results"][0]["max_loss"], places=2)
        self.assertEqual(state["orders"][1]["reply"], "yes")

        code, _, err = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                   "--risk", self.risk, "--state", self.state)
        self.assertEqual(code, 1)
        self.assertIn("already recorded as placed", err)

        code, out, _ = self.ticket("show", "--index", "1")
        self.assertIn("DONE: placed", out)

    def test_a_pending_order_is_placed_not_filled(self):
        code, _, err = run(lots, ["--plan", self.plan, "--context", CTX, "--config", self.cfg,
                                  "--write", self.orders, "--now", NOW, "--type", "buy_limit",
                                  "--price", "1.08550", "--time", "day"])
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.orders)["orders"][0]["type"], "buy_limit")
        code, out, err = self.run_risk()
        self.assertEqual(code, 0, out + err)
        self.ticket("approve", "--index", "1", "--reply", "yes")
        code, out, err = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                     "--risk", self.risk, "--state", self.state)
        self.assertEqual(code, 0, err)
        self.assertIn("PLACED: BUY LIMIT", out)
        self.assertIn("1.0855", out)
        self.assertNotIn("SENT", out)
        self.assertEqual(read(self.state)["orders"][-1]["status"], "placed")

    def test_execute_needs_the_risk_pass(self):
        code, _, err = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                   "--risk", self.risk, "--state", self.state)
        self.assertEqual(code, 1)
        self.assertIn("run check.py first", err)

    def test_execute_needs_your_yes(self):
        self.run_risk()
        code, _, err = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                   "--risk", self.risk, "--state", self.state)
        self.assertEqual(code, 1)
        self.assertIn("no yes recorded", err)

    def test_an_edited_order_is_not_ready(self):
        self.run_risk()
        doc = read(self.orders)
        doc["orders"][0]["volume"] = "0.28"
        write(self.orders, doc)
        code, out, _ = self.ticket("show", "--index", "1")
        self.assertIn("was not in the last risk check", out)

    def test_dry_run_sends_nothing(self):
        code, out, _ = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                   "--risk", self.risk, "--state", self.state, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertIn('"volume"', out)
        self.assertFalse(os.path.exists(self.state))

    def test_a_blocked_order_is_never_sent(self):
        cfg = config()
        cfg["mt5"]["max_spread_pips"] = 0.1
        write(self.cfg, cfg)
        code, out, err = self.run_risk()
        self.assertEqual(code, 1)
        self.assertIn("BLOCK", out)
        code, _, err = self.mt5run("execute", "--index", "1", "--orders", self.orders,
                                   "--risk", self.risk, "--state", self.state)
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", err)

    def test_a_real_account_is_blocked_at_both_gates(self):
        ctx = read(CTX)
        ctx["account"] = dict(ctx["account"], trade_mode="real")
        replay = os.path.join(self.d, "real.json")
        write(replay, ctx)
        run(check, ["--orders", self.orders, "--config", self.cfg, "--state", self.state,
                    "--mt5-context", replay, "--now", NOW, "--out", self.risk])
        self.assertEqual(read(self.risk)["results"][0]["verdict"], "BLOCK")
        code, _, err = run(mt5, ["--replay", replay, "--now", NOW, "--config", self.cfg, "execute",
                                 "--index", "1", "--orders", self.orders, "--risk", self.risk,
                                 "--state", self.state])
        self.assertEqual(code, 1)
        self.assertIn("REAL-money", err)

    def test_ticket_json_exposes_the_mt5_tool(self):
        self.run_risk()
        code, out, _ = self.ticket("show", "--index", "1", "--json")
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc["venue"], "mt5")
        self.assertEqual(doc["broker"], "mt5")
        self.assertIn("order_send", doc["tool"])
        self.assertEqual(doc["tool_input"]["action"], "deal")
        self.assertEqual(doc["tool_input"]["filling"], "fok")
        self.assertEqual(doc["tool_input"]["sl"], self.order["sl"])
        self.assertAlmostEqual(doc["max_loss"], self.order["risk"]["risk"], places=2)

    def test_result_does_not_touch_the_share_portfolio(self):
        self.run_risk()
        self.ticket("approve", "--index", "1", "--reply", "yes")
        portfolio = os.path.join(self.d, "portfolio.json")
        code, out, _ = self.ticket("result", "--index", "1", "--status", "placed", "--broker-id", "3001",
                                   "--filled-qty", "0.27", "--filled-price", "1.08604",
                                   "--portfolio", portfolio)
        self.assertEqual(code, 0)
        self.assertIn("leaves", out.replace("left", "leaves"))
        self.assertFalse(os.path.exists(portfolio))
        self.assertEqual(read(self.state)["orders"][-1]["broker_order_id"], "3001")

    def test_flatten_explains_that_mt5_closes_itself(self):
        write(self.plan, {"venue": "mt5", "symbol": "EURUSD", "flat_by": "20:55"})
        code, out, _ = run(ticket, ["flatten", "--symbol", "EURUSD", "--qty", "0.20", "--orders",
                                    self.orders, "--config", self.cfg, "--plan", self.plan,
                                    "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("mt5.py manage close --symbol EURUSD", out)


class Managing(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = os.path.join(self.d, "config.json")
        self.guard = os.path.join(self.d, "guard.json")
        self.guard_state = os.path.join(self.d, "guard-state.json")
        write(self.cfg, config())
        self.ctx = read(POSITIONS)

    def tearDown(self):
        shutil.rmtree(self.d)

    def replay(self, doc=None, name="replay.json"):
        path = os.path.join(self.d, name)
        write(path, doc or self.ctx)
        return path

    def mt5run(self, *args, replay=None):
        return run(mt5, ["--replay", replay or self.replay(), "--now", NOW, "--config", self.cfg] + list(args))

    def test_a_trailing_stop_needs_a_yes_and_then_moves(self):
        code, _, err = self.mt5run("manage", "trail", "--symbol", "EURUSD", "--yes", "sure")
        self.assertEqual(code, 1)
        self.assertIn("starts with yes", err)
        code, out, err = self.mt5run("manage", "trail", "--symbol", "EURUSD", "--points", "150",
                                     "--yes", "yes")
        self.assertEqual(code, 0, err)
        self.assertIn("1.08442", out)

    def test_breakeven_waits_for_one_r(self):
        code, _, err = self.mt5run("manage", "breakeven", "--symbol", "EURUSD", "--at-r", "1", "--yes", "yes")
        self.assertEqual(code, 1)
        self.assertIn("0.46R", err)

    def test_close_one_and_close_all(self):
        code, out, err = self.mt5run("manage", "close", "--symbol", "XAUUSD", "--yes", "yes")
        self.assertEqual(code, 0, err)
        self.assertIn("Closing", out)
        code, out, err = self.mt5run("manage", "close-all", "--yes", "yes")
        self.assertEqual(code, 0, err)
        self.assertIn("2 of 2 done", out)

    def test_partial_close_rounds_to_the_step(self):
        code, out, err = self.mt5run("manage", "partial", "--symbol", "EURUSD", "--pct", "50", "--yes", "yes")
        self.assertEqual(code, 0, err)
        self.assertIn("0.1 lots", out)

    def test_modify_refuses_to_widen_a_stop(self):
        code, _, err = self.mt5run("manage", "modify", "--ticket", "2001", "--price", "1.08350",
                                   "--sl", "1.08100", "--yes", "yes")
        self.assertEqual(code, 1)
        self.assertIn("widens the stop", err)
        code, _, err = self.mt5run("manage", "modify", "--ticket", "2001", "--price", "1.08350",
                                   "--sl", "1.08100", "--allow-wider-stop", "--yes", "yes")
        self.assertEqual(code, 0, err)

    def test_cancel_a_pending_order(self):
        code, out, err = self.mt5run("manage", "cancel", "--ticket", "2001", "--yes", "yes")
        self.assertEqual(code, 0, err)
        self.assertIn("Cancelling pending order 2001", out)

    def test_the_guard_needs_an_explicit_yes(self):
        code, _, err = self.mt5run("guard", "on", "--yes", "ok", "--guard", self.guard)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.guard))
        code, out, _ = self.mt5run("guard", "on", "--yes", "yes", "--guard", self.guard)
        self.assertEqual(code, 0)
        self.assertTrue(read(self.guard)["enabled"])
        code, out, _ = self.mt5run("guard", "show", "--guard", self.guard)
        self.assertIn("Guard: ON", out)
        code, out, _ = self.mt5run("guard", "off", "--guard", self.guard)
        self.assertFalse(read(self.guard)["enabled"])

    def test_the_guard_run_only_tightens(self):
        doc = read(POSITIONS)
        doc["positions"][0]["price_current"] = 1.08750      # 1.25R in profit
        doc["quotes"]["EURUSD"] = dict(doc["quotes"]["EURUSD"], bid=1.08750, ask=1.08762)
        replay = self.replay(doc, "r1.json")
        self.mt5run("guard", "on", "--yes", "yes", "--guard", self.guard)
        code, out, err = self.mt5run("guard", "run", "--guard", self.guard, replay=replay)
        self.assertEqual(code, 0, err)
        self.assertIn("#1001", out)
        self.assertIn("partial", out)
        self.assertIn("stop", out)
        code, out, _ = self.mt5run("guard", "show", "--guard", self.guard)
        self.assertIn("already done", out)


class CheckIntegration(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.orders = os.path.join(self.d, "orders.json")
        self.cfg = os.path.join(self.d, "config.json")
        self.risk = os.path.join(self.d, "risk.json")
        self.state = os.path.join(self.d, "state.json")
        write(self.cfg, config())
        write(self.orders, {"orders": [mt5_order()]})

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_check_py_delegates_mt5_orders(self):
        code, out, err = run(check, ["--orders", self.orders, "--config", self.cfg, "--state", self.state,
                                    "--mt5-context", CTX, "--now", NOW, "--out", self.risk])
        self.assertEqual(code, 0, out + err)
        self.assertIn("PASS  #1 buy EURUSD", out)
        self.assertIn("lots", out)
        self.assertIn("Free margin after the passed orders", out)
        doc = read(self.risk)
        self.assertEqual(doc["mt5"]["account"]["trade_mode"], "demo")
        self.assertEqual(doc["results"][0]["fingerprint"], rules.fingerprint(mt5_order()))

    def test_a_missing_snapshot_blocks_instead_of_skipping(self):
        code, out, _ = run(check, ["--orders", self.orders, "--config", self.cfg, "--state", self.state,
                                   "--mt5-context", os.path.join(self.d, "nope.json"), "--now", NOW,
                                   "--out", self.risk])
        self.assertEqual(code, 1)
        self.assertIn("BLOCK", out)
        self.assertIn("no MT5 snapshot", out)

    def test_the_share_and_mt5_halves_keep_their_own_rules(self):
        share = {"symbol": "AAPL", "side": "buy", "qty": "5", "type": "market", "time_in_force": "day",
                 "order_class": "bracket", "take_profit_limit_price": "200", "stop_loss_stop_price": "190"}
        write(self.orders, {"orders": [share, mt5_order()]})
        prices = os.path.join(self.d, "prices.json")
        write(prices, {"as_of": "2026-10-19T14:15:00Z", "prices": {"AAPL": 195}})
        code, out, err = run(check, ["--orders", self.orders, "--config", self.cfg, "--state", self.state,
                                    "--prices", prices, "--mt5-context", CTX, "--now", NOW,
                                    "--out", self.risk])
        doc = read(self.risk)
        self.assertEqual([r.get("venue") for r in doc["results"]], [None, "mt5"])
        self.assertEqual(doc["results"][1]["verdict"], "PASS")
        self.assertTrue(any("mixes share orders and MT5 orders" in w for w in doc["warnings"]))


if __name__ == "__main__":
    unittest.main()
