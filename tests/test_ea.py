"""The Expert Advisor is one MQL5 file, and no MetaEditor runs on this machine,
so the checks here are the ones a compiler would do first: balanced brackets,
nothing called before it is defined, ASCII only, one Print() - plus the wiring
of the dashboard, where a row without a handler is a dead button."""

import os
import re
import unittest

from _load import ROOT

EA_DIR = os.path.join(ROOT, "trader-mt5", "ea")
EA = os.path.join(EA_DIR, "DayTraderMT5.mq5")

ENTRY_POINTS = ["OnInit", "OnDeinit", "OnTimer", "OnTick", "OnChartEvent"]
PAGES = ["DrawDash", "DrawRule", "DrawRisk", "DrawClock", "DrawManage", "DrawLog",
         "DrawTest", "DrawPack", "DrawHelp"]
SECTIONS = ["MARKET", "OPENING RANGE", "INDICATORS", "TODAY", "POSITION", "RISK AND SIZE", "STATUS"]

# one tag per kind of line the console can print
TAGS = ["INIT", "CONF", "GATE", "RULE", "SIGNAL", "BLOCK", "SIZE", "RISK",
        "ORDER", "MANAGE", "FLAT", "CTRL", "ERROR", "DAY", "STOP", "CHECK", "ALIVE"]

ROW_CALL = re.compile(r'Row(?:Read|Edit|Cycle|Toggle)\("([A-Za-z_0-9]+)"')
EDITABLE = re.compile(r'Row(?:Edit|Cycle|Toggle)\("([A-Za-z_0-9]+)"')


def source():
    with open(EA, encoding="utf-8") as fh:
        return fh.read()


def code_only(text):
    """Drop comments, strings and character literals, so brackets can be counted."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        out.append(c)
        i += 1
    return "".join(out)


def definitions(text):
    """(offset, name) for every function definition: a return type, a name, and
    a parameter list that closes the line."""
    pattern = r"(?m)^[A-Za-z_][A-Za-z0-9_]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*$"
    return [(m.start(), m.group(1)) for m in re.finditer(pattern, text)]


def body_of(text, name):
    """The body of one function, from its definition to the closing brace."""
    at = re.search(r"(?m)^[A-Za-z_][A-Za-z0-9_]*\s+" + name + r"\s*\(", text)
    if not at:
        raise AssertionError("no definition of " + name)
    start = at.start()
    depth = 0
    opened = False
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
            opened = True
        elif text[i] == "}":
            depth -= 1
            if opened and depth == 0:
                return text[start:i + 1]
    raise AssertionError("unbalanced body for " + name)


class TheFile(unittest.TestCase):
    def test_it_ships_next_to_its_docs(self):
        for name in ("DayTraderMT5.mq5", "README.md", "CONSOLE.md"):
            self.assertTrue(os.path.isfile(os.path.join(EA_DIR, name)), name)

    def test_it_is_ascii_and_ends_with_a_newline(self):
        text = source()
        self.assertEqual([c for c in text if ord(c) > 127], [])
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\r", text, "MQL5 source stays LF, git converts it for Windows")

    def test_the_version_is_not_stale(self):
        text = source()
        version = re.search(r'#property version\s+"([0-9.]+)"', text)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), "1.24")
        self.assertIn("v1.24", text, "the banner and the panel footer name the version")
        self.assertIn("#property copyright", text)
        self.assertIn("#property link", text)


class TheSyntax(unittest.TestCase):
    def test_brackets_balance(self):
        code = code_only(source())
        for left, right in (("{", "}"), ("(", ")"), ("[", "]")):
            self.assertEqual(code.count(left), code.count(right), left + right)

    def test_mql5_has_no_forward_references(self):
        """A helper has to appear above the line that calls it."""
        text = source()
        first = {}
        for offset, name in definitions(text):
            first.setdefault(name, offset)
        forward = []
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
            name, at = match.group(1), match.start()
            if name in first and at != first[name] and at < first[name]:
                forward.append("%s on line %d" % (name, text[:at].count("\n") + 1))
        self.assertEqual(forward, [])

    def test_nothing_is_defined_twice(self):
        names = [name for _, name in definitions(source())]
        self.assertEqual(sorted(n for n in set(names) if names.count(n) > 1), [])

    def test_the_five_entry_points_are_there(self):
        names = [name for _, name in definitions(source())]
        for point in ENTRY_POINTS:
            self.assertIn(point, names)
        for page in PAGES:
            self.assertIn(page, names)

    def test_it_includes_only_the_trade_library(self):
        includes = re.findall(r"(?m)^#include\s+(.+)$", source())
        self.assertEqual(includes, ["<Trade\\Trade.mqh>"])

    def test_no_mql4_only_property(self):
        self.assertNotIn("#property strict", source())


class TheInputs(unittest.TestCase):
    def test_every_input_is_documented_in_the_dialog(self):
        for line in source().splitlines():
            if line.startswith("input ") and not line.startswith("input group"):
                self.assertIn("//", line, line)

    def test_the_demo_defaults_are_the_safe_ones(self):
        text = source()
        self.assertRegex(text, r"InpAllowLive\s*=\s*false;")
        self.assertRegex(text, r"InpDryRun\s*=\s*false;")
        self.assertRegex(text, r"InpAllowShort\s*=\s*false;")
        self.assertRegex(text, r"InpMaxTradesPerDay\s*=\s*1;")

    def test_every_group_has_at_least_two_inputs(self):
        groups = source().split('input group "')[1:]
        self.assertGreaterEqual(len(groups), 7)
        for group in groups:
            body = group.split('\ninput group "')[0]
            self.assertGreaterEqual(body.count("\ninput "), 2, group.split('"')[0])


class TheConsole(unittest.TestCase):
    def test_print_happens_in_one_place_only(self):
        code = code_only(source())
        self.assertEqual(len(re.findall(r"\bPrint\s*\(", code)), 1)
        self.assertEqual(len(re.findall(r"\bPrintFormat\s*\(", code)), 0)

    def test_a_tag_exists_for_every_decision(self):
        text = source()
        for tag in TAGS:
            self.assertGreaterEqual(text.count('Log("%s"' % tag), 1, tag)

    def test_the_rule_does_not_repeat_itself(self):
        text = source()
        self.assertIn("void LogRule(", text)
        self.assertIn("g_ruleKey", text)
        self.assertIn("InpVerbose", text)

    def test_the_opening_range_is_logged_once_a_day(self):
        """Two lines on every bar is a log nobody reads: the range is fixed for
        the day, so it is said once, and the waiting line only on a change."""
        text = source()
        self.assertIn("g_rangeDay", text)
        entry = body_of(text, "TryEntry")
        self.assertIn("g_rangeDay", entry)
        self.assertIn("g_rangeDay != today", entry)

    def test_the_chart_keeps_its_own_copy(self):
        text = source()
        log = body_of(text, "Log")
        self.assertIn("LogRingPush(", log)
        self.assertIn("g_logRing[", body_of(text, "LogRingPush"))
        self.assertIn("g_logRing[", body_of(text, "DrawLog"))


class TheDashboard(unittest.TestCase):
    def test_every_object_carries_the_panel_prefix(self):
        text = source()
        self.assertIn('#define PANEL_TAG   "DTMT5_UI_"', text)
        self.assertEqual(text.count("ObjectCreate("), 3, "only the three Ui helpers create objects")

    def test_it_is_removed_when_the_ea_leaves(self):
        text = source()
        self.assertIn("ObjectsDeleteAll(0, PANEL_TAG)", text)
        on_deinit = body_of(text, "OnDeinit")
        self.assertIn("DeletePanel();", on_deinit)

    def test_every_page_is_drawn_and_switchable(self):
        text = source()
        panel = body_of(text, "UpdatePanel")
        for page in PAGES:
            self.assertIn(page + "()", panel, page)
        tabs = body_of(text, "UiTabs")
        for label in ("DASH", "RULE", "RISK", "CLOCK", "MANAGE", "LOG", "TEST", "PACK", "HELP"):
            self.assertIn('"%s"' % label, tabs, label)
        # a tab click lands on SetPage, which redraws the new page
        self.assertIn("SetPage(", body_of(text, "OnChartEvent"))
        self.assertIn("ObjectsDeleteAll", body_of(text, "SetPage"))

    def test_the_dash_page_shows_every_section(self):
        dash = body_of(source(), "DrawDash")
        for section in SECTIONS:
            self.assertIn('"%s"' % section, dash, section)

    def test_the_four_buttons_are_wired(self):
        text = source()
        events = body_of(text, "OnChartEvent")
        for button in ("btn_pause", "btn_dry", "btn_close", "btn_reset"):
            self.assertIn('"%s"' % button, events, button)
        # closing anything of ours needs a second click, and so does a reset
        self.assertIn("g_confirmClose", events)
        self.assertIn("g_confirmReset", events)
        self.assertIn("CloseAllOurs(", events)
        self.assertIn("ResetSettings(", events)

    def test_no_row_shows_the_same_key_twice_on_one_page(self):
        """Two rows with one key would draw on top of each other. The one
        exception is a row that is drawn in both arms of an if/else, where only
        one arm ever reaches the chart."""
        text = source()
        for page in PAGES:
            body = body_of(text, page)
            keys = ROW_CALL.findall(body)
            twice = [k for k in set(keys) if keys.count(k) == 2]
            self.assertEqual([k for k in set(keys) if keys.count(k) > 2], [], page)
            if twice:
                self.assertIn("else", body, page)
                self.assertIn("if(", body, page)


class TheSettings(unittest.TestCase):
    """A row with no handler is a button that does nothing, and a setting with
    no save is forgotten on the next chart change."""

    def test_every_clickable_row_has_a_handler(self):
        text = source()
        rows = set(EDITABLE.findall(text))
        handled = set(re.findall(r'id == "([A-Za-z_0-9]+)"', body_of(text, "AdjustSetting")))
        self.assertTrue(rows)
        self.assertEqual(sorted(rows - handled), [], "these rows have no handler")

    def test_every_handler_is_reachable_from_a_row(self):
        text = source()
        rows = set(EDITABLE.findall(text))
        handled = set(re.findall(r'id == "([A-Za-z_0-9]+)"', body_of(text, "AdjustSetting")))
        self.assertEqual(sorted(handled - rows), [], "these handlers have no row")

    def test_every_setting_is_saved_and_loaded(self):
        text = source()
        handled = set(re.findall(r'id == "([A-Za-z_0-9]+)"', body_of(text, "AdjustSetting")))
        saved = set(re.findall(r'CFG_PREFIX \+ "([A-Za-z_0-9]+)"', body_of(text, "SaveSettings")))
        loaded = set(re.findall(r'CfgHas\("([A-Za-z_0-9]+)"\)', body_of(text, "LoadSettings")))
        self.assertEqual(sorted(handled - saved), [], "not saved")
        self.assertEqual(sorted(handled - loaded), [], "not loaded back")
        self.assertEqual(sorted(saved - handled), [], "saved but never set")
        self.assertEqual(sorted(loaded - handled), [], "loaded but never set")

    def test_the_saved_table_is_clamped_on_the_way_back(self):
        text = source()
        loaded = body_of(text, "LoadSettings")
        self.assertGreaterEqual(loaded.count("ClampD(") + loaded.count("ClampI("), 20)

    def test_reset_returns_to_the_inputs(self):
        text = source()
        reset = body_of(text, "ResetSettings")
        self.assertIn("ForgetSettings();", reset)
        self.assertIn("ApplyInputDefaults();", reset)
        self.assertIn("CreateHandles();", reset)
        defaults = body_of(text, "ApplyInputDefaults")
        for input_name in ("InpRiskPercent", "InpMaxLots", "InpORMinutes", "InpBreakevenAtR", "InpAlertPopup"):
            self.assertIn(input_name, defaults, input_name)

    def test_a_retuned_rule_rebuilds_its_handles(self):
        text = source()
        adjust = body_of(text, "AdjustSetting")
        self.assertIn("CreateHandles()", adjust)
        for key in ('"tf"', '"ema_fast"', '"ema_slow"', '"atr_period"'):
            self.assertIn("id == " + key, adjust, key)


class TheGuards(unittest.TestCase):
    def test_a_real_account_needs_the_switch(self):
        text = source()
        self.assertIn("g_liveBlocked = (IsLiveAccount() && !g_allowLive);", text)
        ready = body_of(text, "TerminalReady")
        self.assertIn("g_liveBlocked", ready)

    def test_it_only_touches_its_own_magic(self):
        text = source()
        self.assertIn("PositionGetInteger(POSITION_MAGIC) != g_magic", text)
        self.assertIn("SetExpertMagicNumber", text)

    def test_the_panel_cannot_undo_a_guard(self):
        """Nothing on the chart may switch InpAllowLive or place an order itself."""
        adjust = body_of(source(), "AdjustSetting")
        self.assertNotIn("g_allowLive", adjust)
        self.assertNotIn(".Buy(", adjust)
        self.assertNotIn(".Sell(", adjust)

    def test_every_send_is_behind_the_gates(self):
        """The order is only reached from TryEntry, after the gate block."""
        text = source()
        entry = body_of(text, "TryEntry")
        self.assertIn('Log("BLOCK"', entry)
        self.assertLess(entry.index('Log("BLOCK"'), entry.index("g_trade.Buy("))
        self.assertLess(entry.index('if(gate != "")'), entry.index("g_trade.Buy("))
        # and nothing else in the file sends an order
        self.assertEqual(text.count("g_trade.Buy("), 1)
        self.assertEqual(text.count("g_trade.Sell("), 1)


class TheProof(unittest.TestCase):
    """Two questions the user is entitled to ask: does it talk to anyone but my
    broker, and would the terminal really take its order with a stop and a
    target? Both are answered in code, and both are checked here."""

    def test_it_is_offline(self):
        text = source()
        for call in ("WebRequest(", "SocketCreate(", "SocketConnect(", "SocketSend(",
                     "URLDownloadToFile(", "InternetOpen", "#import", "DllImport"):
            self.assertNotIn(call, text, call)

    def test_the_only_push_is_switched_off(self):
        text = source()
        self.assertIn("SendNotification(", text)          # the optional phone push
        self.assertRegex(text, r"InpAlertPush\s*=\s*false;")
        notify = body_of(text, "Notify")
        self.assertIn("g_alertPush", notify)

    def test_it_never_calls_ordersend_directly(self):
        """CTrade owns the send; the check path only validates."""
        text = source()
        self.assertNotIn("OrderSend(", text)
        # "RunOrderCheck" starts with "OrderCheck", so count the real calls
        calls = len(re.findall(r"(?<!Run)OrderCheck\(", code_only(text)))
        self.assertEqual(calls, 1, "one place validates, and it is not a sender")
        check = body_of(text, "RunOrderCheck")
        self.assertIn("OrderCheck(", check)
        self.assertNotIn("TRADE_ACTION_", check.replace("TRADE_ACTION_DEAL", ""))
        self.assertIn("never sent", check)

    def test_the_order_check_uses_the_real_stop_and_target(self):
        check = body_of(source(), "RunOrderCheck")
        for field in ("request.sl", "request.tp", "request.volume", "request.price",
                      "request.deviation", "request.magic"):
            self.assertIn(field, check, field)
        preview = body_of(source(), "PreviewOrder")
        self.assertIn("g_minRR", preview)
        self.assertIn("MinStopPoints()", preview)
        self.assertIn("SizeLots(", preview)

    def test_the_order_check_declares_a_check_result(self):
        """MetaEditor's signature is OrderCheck(const MqlTradeRequest&,
        MqlTradeCheckResult&). A MqlTradeResult there is a compile error - it is
        OrderSend's struct, and it carries no margin for the page to show."""
        text = source()
        self.assertNotIn("MqlTradeResult", text)
        check = body_of(text, "RunOrderCheck")
        self.assertRegex(check, r"MqlTradeCheckResult\s+result;")
        self.assertIn("result.margin", check)

    def test_the_test_page_names_every_gate(self):
        page = body_of(source(), "DrawTest")
        self.assertIn("CAN IT TRADE RIGHT NOW?", page)
        self.assertIn("GatePass(", page)
        self.assertIn("PreviewOrder(", page)
        self.assertIn('UiWide("btn_check"', page)
        self.assertIn('"btn_check"', body_of(source(), "OnChartEvent"))
        gates = body_of(source(), "GatePass")
        self.assertGreaterEqual(gates.count("if(which =="), 11)

    def test_there_is_a_heartbeat(self):
        text = source()
        self.assertIn("void Heartbeat(", text)
        self.assertIn("Heartbeat();", body_of(text, "OnTimer"))
        self.assertIn("InpHeartbeatMinutes", text)
        self.assertIn("GatesOpen(", body_of(text, "Heartbeat"))

    def test_the_panel_says_what_has_to_happen_next(self):
        """A trader should never have to scroll a log to learn why nothing
        happened: the price that would trigger an entry sits on the chart."""
        text = source()
        trigger = body_of(text, "NextTrigger")
        for phrase in ("weekend", "flat-by", "closed until", "paused", "in a trade",
                       "daily loss stop", "done for the day", "range still forming",
                       "close above"):
            self.assertIn(phrase, trigger, phrase)
        self.assertIn("NextTrigger()", body_of(text, "DrawDash"))
        self.assertIn("NextTrigger()", body_of(text, "DrawTest"))
        self.assertIn("NextTrigger()", body_of(text, "Heartbeat"))

    def test_no_page_draws_the_same_key_twice(self):
        """Two rows with one key are two labels drawn on top of each other."""
        text = source()
        call = re.compile(r'(?:RowRead|RowEdit|RowCycle|RowToggle|UiLine|UiSection|UiBar|UiWide)\("([A-Za-z_0-9]+)"')
        for page in ("DrawDash", "DrawRule", "DrawRisk", "DrawClock", "DrawManage",
                     "DrawLog", "DrawTest", "DrawPack", "DrawHelp"):
            body = body_of(text, page)
            keys = call.findall(body)
            for key in set(keys):
                drawn = keys.count(key)
                if drawn == 1:
                    continue
                # two arms of one if are fine: only one of them ever runs
                self.assertIn("else", body, "%s draws %s twice with no if/else" % (page, key))
                self.assertEqual(drawn, 2, "%s draws %s %d times" % (page, key, drawn))

    def test_the_pack_page_lists_every_skill(self):
        """The page is called PACK: all twelve, one line each, not four."""
        page = body_of(source(), "DrawPack")
        for name in ("mt5", "budget", "risk", "broker", "entry", "exit",
                     "scanner", "alerts", "news", "analyst", "pelosi", "timemachine"):
            self.assertIn('"%s"' % name, page, name)
        self.assertIn("dtcli", page)
        self.assertIn("offline", page)

    def test_the_panel_starts_below_the_buy_sell_corner(self):
        text = source()
        y = re.search(r"InpPanelY\s*=\s*(\d+);", text)
        self.assertIsNotNone(y)
        self.assertGreaterEqual(int(y.group(1)), 80, "the one click trading corner lives at the top left")
