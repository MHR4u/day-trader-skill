import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from _load import ROOT

sys.path.insert(0, os.path.join(ROOT, "trader-gold"))

import factory


CONFIG = os.path.join(ROOT, "trader-gold", "config.example.json")


def run_factory(argv):
    with contextlib.redirect_stdout(io.StringIO()):
        return factory.main(argv)


def csv_with_late_start(path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("datetime,open,high,low,close,volume\n")
        handle.write("2004-01-01T00:00:00Z,100,101,99,100,10\n")
        handle.write("2004-01-02T00:00:00Z,100,102,99,101,10\n")


class GoldFactoryTests(unittest.TestCase):
    def overrides(self):
        return ["--config", CONFIG,
                "--override", "data.base_timeframe=D1",
                "--override", "strategy.signal_timeframe=D1",
                "--override", "strategy.trend_timeframe=CURRENT"]

    def test_csv_backtest_fails_2000_gate_and_never_claims_live_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            data = os.path.join(folder, "late.csv")
            output = os.path.join(folder, "artifacts")
            csv_with_late_start(data)
            argv = self.overrides() + [
                "backtest", "--data", data, "--output", output,
                "--source-url", "https://example.invalid/not-real-data",
                "--source-description", "Two synthetic test rows, not market data",
            ]
            self.assertEqual(run_factory(argv), 0)
            with open(os.path.join(output, "report.json"), encoding="utf-8") as handle:
                report = json.load(handle)
            with open(os.path.join(output, "GoldProfessionalEA.research.set"), encoding="utf-8") as handle:
                set_text = handle.read()
            with open(os.path.join(output, "summary.md"), encoding="utf-8") as handle:
                summary = handle.read()
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["deployment_status"], "MT5_VALIDATION_REQUIRED")
        self.assertFalse(report["data"]["coverage_pass"])
        self.assertFalse(report["data"]["synthetic"])
        self.assertFalse(report["ea_review"]["compiled"])
        self.assertFalse(report["ea_review"]["mt5_tick_test_passed"])
        self.assertFalse(report["validation"]["checks"]["mt5_compile_and_real_tick_test"])
        self.assertFalse(report["validation"]["checks"]["demo_forward_test"])
        self.assertIn("InpEnableNewEntries=false", set_text)
        self.assertIn("mt5_compile_and_real_tick_test: NOT RUN", summary)
        self.assertIn("demo_forward_test: NOT RUN", summary)

    def test_demo_is_always_synthetic_only(self):
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "demo")
            argv = self.overrides() + [
                "demo", "--years", "1", "--seed", "19", "--no-optimize",
                "--output", output,
            ]
            self.assertEqual(run_factory(argv), 0)
            with open(os.path.join(output, "report.json"), encoding="utf-8") as handle:
                report = json.load(handle)
        self.assertEqual(report["status"], "SYNTHETIC_ONLY")
        self.assertTrue(report["data"]["synthetic"])
        self.assertEqual(report["mode"], "demo")
        self.assertFalse(report["data"]["coverage_pass"])
        self.assertEqual(report["deployment_status"], "MT5_VALIDATION_REQUIRED")

    def test_review_ea_writes_a_static_report(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(run_factory(["review-ea", "--output", folder]), 0)
            with open(os.path.join(folder, "ea_review.json"), encoding="utf-8") as handle:
                review = json.load(handle)
        self.assertTrue(review["static_pass"])
        self.assertFalse(review["compiled"])
        self.assertFalse(review["mt5_tick_test_passed"])


if __name__ == "__main__":
    unittest.main()
