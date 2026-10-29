"""The Expert Advisor is one MQL5 file, and no MetaEditor runs on this machine,
so the checks here are the ones a compiler would do first: balanced brackets,
nothing called before it is defined, ASCII only, every input documented in the
dialog, and a console with a tag for every kind of decision."""

import os
import re
import unittest

from _load import ROOT

EA_DIR = os.path.join(ROOT, "trader-mt5", "ea")
EA = os.path.join(EA_DIR, "DayTraderMT5.mq5")

ENTRY_POINTS = ["OnInit", "OnDeinit", "OnTimer", "OnTick", "OnChartEvent"]

# one tag per kind of line the console can print
TAGS = ["INIT", "CONF", "GATE", "RULE", "SIGNAL", "BLOCK", "SIZE", "RISK",
        "ORDER", "MANAGE", "FLAT", "CTRL", "ERROR", "DAY", "STOP"]


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


class TheFile(unittest.TestCase):
    def test_it_ships_next_to_its_docs(self):
        for name in ("DayTraderMT5.mq5", "README.md", "CONSOLE.md"):
            self.assertTrue(os.path.isfile(os.path.join(EA_DIR, name)), name)

    def test_it_is_ascii_and_ends_with_a_newline(self):
        text = source()
        self.assertEqual([c for c in text if ord(c) > 127], [])
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\r", text, "MQL5 source stays LF, git converts it for Windows")

    def test_the_buffer_version_is_not_stale(self):
        text = source()
        version = re.search(r'#property version\s+"([0-9.]+)"', text)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), "1.10")
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
                self.assertTrue(line.rstrip().endswith("//" + line.split("//", 1)[1]),
                                "the comment has to sit at the end of the line: " + line)

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
        """Every line goes through Log(), so the timestamp and the tag line up."""
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

    def test_every_line_starts_with_the_time(self):
        text = source()
        self.assertIn("TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS)", text)


class TheDashboard(unittest.TestCase):
    def test_every_object_carries_the_panel_prefix(self):
        text = source()
        self.assertIn('#define PANEL_TAG   "DTMT5_UI_"', text)
        # nothing is created outside the Ui* helpers, and they all use the tag
        self.assertEqual(text.count("ObjectCreate("), 3)

    def test_it_is_removed_when_the_ea_leaves(self):
        text = source()
        self.assertIn("ObjectsDeleteAll(0, PANEL_TAG)", text)
        on_deinit = text[text.index("void OnDeinit("):]
        self.assertIn("DeletePanel();", on_deinit.split("void OnTimer(")[0])

    def test_the_three_buttons_are_wired(self):
        text = source()
        events = text[text.index("void OnChartEvent("):text.index("int OnInit(")]
        for button in ("btn_pause", "btn_dry", "btn_close"):
            self.assertIn('PANEL_TAG + "%s"' % button, events)
        # closing anything of ours needs a second click
        self.assertIn("g_confirmClose", events)
        self.assertIn("CloseAllOurs(", events)

    def test_the_panel_shows_every_section(self):
        text = source()
        panel = text[text.index("void UpdatePanel("):text.index("void OnChartEvent(")]
        for section in ("MARKET", "OPENING RANGE", "INDICATORS", "TODAY",
                        "POSITION", "RISK AND SIZE", "STATUS"):
            self.assertIn('"%s"' % section, panel)


class TheGuards(unittest.TestCase):
    def test_a_real_account_needs_the_switch(self):
        text = source()
        self.assertIn("g_liveBlocked = (IsLiveAccount() && !g_allowLive);", text)
        ready = text[text.index("bool TerminalReady("):text.index("//| Indicators")]
        self.assertIn("g_liveBlocked", ready)

    def test_it_only_touches_its_own_magic(self):
        text = source()
        self.assertIn("PositionGetInteger(POSITION_MAGIC) != g_magic", text)
        self.assertIn("SetExpertMagicNumber", text)

    def test_every_send_is_behind_the_gates(self):
        """The order is only reached from TryEntry, after the gate block."""
        text = source()
        entry = text[text.index("void TryEntry("):text.index("//| Managing what is open")]
        self.assertIn('Log("BLOCK"', entry)
        self.assertLess(entry.index('Log("BLOCK"'), entry.index("g_trade.Buy("))
        self.assertLess(entry.index('if(gate != "")'), entry.index("g_trade.Buy("))
        # and nothing else in the file sends an order
        self.assertEqual(text.count("g_trade.Buy("), 1)
        self.assertEqual(text.count("g_trade.Sell("), 1)
