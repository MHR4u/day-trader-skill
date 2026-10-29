import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

dtcli = load("trader-mt5", "dtcli")

CTX = os.path.join(FIX, "trader-mt5", "context.json")
NOW = "2026-10-20 09:35"


def read(path):
    with open(path) as fh:
        return json.load(fh)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = dtcli.main(argv)
    return code, out.getvalue(), err.getvalue()


class TheLauncher(unittest.TestCase):
    def test_it_knows_every_skill(self):
        """One command per skill folder, so nothing in the pack is left out."""
        folders = sorted(d for d in os.listdir(ROOT) if d.startswith("trader-"))
        covered = sorted({folder for folder, _, _ in dtcli.TOOLS.values()})
        self.assertEqual(covered, folders)

    def test_every_tool_file_exists(self):
        for key, (folder, filename, what) in dtcli.TOOLS.items():
            path = os.path.join(ROOT, folder, filename)
            self.assertTrue(os.path.isfile(path), key)
            self.assertGreater(len(what), 20, key)

    def test_list_and_version(self):
        code, out, _ = run([])
        self.assertEqual(code, 0)
        self.assertIn("dtcli %s" % dtcli.VERSION, out)
        self.assertIn("the day-trader pack in one command", out)
        for key in dtcli.TOOLS:
            self.assertIn(key, out)
        self.assertIn("dtcli mt5 doctor", out)
        code, out, _ = run(["--version"])
        self.assertEqual((code, out.strip()), (0, "dtcli %s" % dtcli.VERSION))
        code, out, _ = run(["list"])
        self.assertIn("ticket", out)

    def test_env_says_where_everything_is(self):
        code, out, _ = run(["env"])
        self.assertEqual(code, 0)
        self.assertIn("root %s" % os.path.abspath(ROOT), out)
        self.assertEqual(out.count(" ok"), 13)
        self.assertIn("MetaTrader5 package:", out)
        self.assertIn("frozen False", out)

    def test_an_unknown_tool_is_explained(self):
        code, _, err = run(["m55"])
        self.assertEqual(code, 2)
        self.assertIn("no tool called 'm55'", err)
        self.assertIn("Did you mean mt5", err)
        code, _, err = run(["nothing-like-this"])
        self.assertEqual(code, 2)
        self.assertNotIn("Did you mean", err)

    def test_it_runs_a_tool_with_its_own_arguments(self):
        code, out, err = run(["mt5", "--replay", CTX, "--now", NOW, "account"])
        self.assertEqual(code, 0, err)
        self.assertIn("MT5 DEMO account 5001234 on Broker-Demo", out)
        self.assertIn("balance $5,000.00", out)

    def test_the_tools_own_help_comes_through(self):
        code, out, err = run(["ticket", "--help"])
        self.assertEqual(code, 0, err)
        self.assertIn("show", out)
        self.assertIn("approve", out)

    def test_a_tools_exit_code_is_kept(self):
        # an unknown symbol exits 1 inside mt5.py, and dtcli must not hide it
        code, _, err = run(["mt5", "--replay", CTX, "--now", NOW, "spec", "NOPE"])
        self.assertEqual(code, 1)
        self.assertIn("symbols --search", err)
        # argparse's own error path exits 2, and that survives too
        code, _, _ = run(["mt5", "no-such-command"])
        self.assertEqual(code, 2)

    def test_the_risk_check_runs_through_the_launcher(self):
        d = tempfile.mkdtemp()
        try:
            orders = os.path.join(d, "orders.json")
            cfg = os.path.join(d, "config.json")
            state = os.path.join(d, "state.json")
            risk = os.path.join(d, "risk.json")
            with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
                cfgdoc = json.load(fh)
            cfgdoc["mt5"]["symbols"] = []
            with open(cfg, "w") as fh:
                json.dump(cfgdoc, fh)
            order = {"venue": "mt5", "symbol": "EURUSD", "side": "buy", "type": "market",
                     "volume": "0.27", "deviation": 20, "magic": 20261019, "sl": 1.08432,
                     "tp": 1.08862, "filling": "auto", "time": "gtc",
                     "spec": read(CTX)["symbols"]["EURUSD"],
                     "quote": read(CTX)["quotes"]["EURUSD"],
                     "risk": {"risk": 40.0}}
            with open(orders, "w") as fh:
                json.dump({"orders": [order]}, fh)
            code, out, err = run(["risk", "--orders", orders, "--config", cfg, "--state", state,
                                  "--mt5-context", CTX, "--now", NOW, "--out", risk])
            self.assertIn(code, (0, 1), out + err)
            self.assertIn("EURUSD", out)
            self.assertTrue(os.path.exists(risk))
        finally:
            shutil.rmtree(d)

    def test_home_can_be_pointed_somewhere_else(self):
        d = tempfile.mkdtemp()
        old = os.environ.get("DAYTRADER_HOME")
        try:
            os.environ["DAYTRADER_HOME"] = d
            code, _, err = run(["mt5", "account"])
            self.assertEqual(code, 1)          # no tools there to load
            self.assertIn("cannot find", err)
            self.assertIn(d, err)
        finally:
            if old is None:
                os.environ.pop("DAYTRADER_HOME", None)
            else:
                os.environ["DAYTRADER_HOME"] = old
            shutil.rmtree(d)


class TheBuild(unittest.TestCase):
    def test_the_spec_bundles_every_skill_folder(self):
        path = os.path.join(ROOT, "trader-mt5", "daytrader.spec")
        with open(path, encoding="utf-8") as fh:
            spec = fh.read()
        self.assertIn('"trader-*"', spec)
        self.assertIn('name="dtcli"', spec)
        self.assertIn("console=True", spec)          # a CLI has to print
        self.assertIn("urllib.request", spec)        # tools are data, so their imports are named
        self.assertIn("MetaTrader5", spec)

    def test_the_windows_build_exists_and_runs_the_tests(self):
        path = os.path.join(ROOT, ".github", "workflows", "build-exe.yml")
        with open(path, encoding="utf-8") as fh:
            flow = fh.read()
        self.assertIn("windows-latest", flow)
        self.assertIn("python -m unittest discover -s tests", flow)
        self.assertIn("pyinstaller --clean --noconfirm trader-mt5/daytrader.spec", flow)
        self.assertIn("dist\\dtcli.exe", flow)
        self.assertIn("actions/upload-artifact", flow)

    def test_the_one_click_windows_script_is_there(self):
        path = os.path.join(ROOT, "trader-mt5", "build-exe.bat")
        with open(path, encoding="utf-8") as fh:
            bat = fh.read()
        self.assertIn("PyInstaller", bat)
        self.assertIn("daytrader.spec", bat)
        self.assertIn("dtcli.exe", bat)

    def test_the_docs_explain_the_three_ways_to_get_it(self):
        path = os.path.join(ROOT, "trader-mt5", "BUILD-EXE.md")
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
        for line in ("dtcli.exe list", "build-exe.bat", "--replay", "MetaTrader5"):
            self.assertIn(line, doc)


if __name__ == "__main__":
    unittest.main()
