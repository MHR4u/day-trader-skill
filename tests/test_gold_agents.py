import copy
import os
import sys
import tempfile
import unittest

from _load import ROOT, gold_config

sys.path.insert(0, os.path.join(ROOT, "trader-gold"))

from gold.agents import DataAgent, EAAgent, RiskAgent, StrategyAgent, ValidationAgent
from gold.data import parse_iso_date, synthetic_bars, timestamp
from gold.models import GoldError


def write_small_csv(path, first_date):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("datetime,open,high,low,close,volume\n")
        handle.write("%sT00:00:00Z,100,101,99,100,10\n" % first_date)
        handle.write("%sT00:00:00Z,100,102,99,101,10\n" % ("2000-01-05" if first_date == "2000-01-04" else "2004-01-02"))


class GoldAgentTests(unittest.TestCase):
    def test_data_agent_accepts_first_trading_week_of_2000_and_rejects_2004(self):
        cfg = copy.deepcopy(gold_config())
        cfg["data"]["base_timeframe"] = "D1"
        cfg["validation"]["require_data_since"] = "2000-01-01"
        with tempfile.TemporaryDirectory() as folder:
            good = os.path.join(folder, "good.csv")
            late = os.path.join(folder, "late.csv")
            write_small_csv(good, "2000-01-04")
            write_small_csv(late, "2004-01-01")
            passed, good_meta = DataAgent().load(good, cfg)
            failed, late_meta = DataAgent().load(late, cfg)
        self.assertEqual(len(passed), 2)
        self.assertTrue(good_meta["coverage_pass"])
        self.assertFalse(late_meta["coverage_pass"])
        self.assertIn("first week of 2000-01-01", " ".join(late_meta["warnings"]))
        self.assertIn("coverage_deadline", late_meta)

    def test_strategy_agent_rejects_unknown_optimization_fields(self):
        cfg = copy.deepcopy(gold_config())
        cfg["validation"]["optimization_grid"] = {"martingale_multiplier": [2, 3]}
        with self.assertRaises(GoldError):
            StrategyAgent().candidates(cfg, True)
        cfg["validation"]["optimization_grid"] = {}
        self.assertEqual(StrategyAgent().candidates(cfg, False), [{}])

    def test_risk_agent_enforces_conservative_limits(self):
        cfg = copy.deepcopy(gold_config())
        cfg["risk"]["risk_per_trade_pct"] = 6.0
        with self.assertRaises(GoldError):
            RiskAgent().validate(cfg)
        cfg = copy.deepcopy(gold_config())
        cfg["execution"]["commission_per_lot_side"] = -1.0
        with self.assertRaises(GoldError):
            RiskAgent().validate(cfg)
        cfg = copy.deepcopy(gold_config())
        cfg["execution"]["default_spread_price"] = 0.0
        warnings = RiskAgent().validate(cfg)
        self.assertIn("Zero spread is not a conservative Gold assumption", warnings)

    def test_ea_review_is_static_and_generated_set_disables_entries(self):
        ea_path = os.path.join(ROOT, "trader-gold", "mt5", "GoldProfessionalEA.mq5")
        agent = EAAgent()
        review = agent.review(ea_path)
        self.assertTrue(review["static_pass"])
        self.assertFalse(review["compiled"])
        self.assertFalse(review["mt5_tick_test_passed"])
        self.assertTrue(review["static_checks"]["indicator readiness"])
        self.assertTrue(review["static_checks"]["higher timeframe validation"])
        with tempfile.TemporaryDirectory() as folder:
            set_path = os.path.join(folder, "research.set")
            agent.write_set(set_path, gold_config(), {})
            with open(set_path, encoding="utf-8") as handle:
                text = handle.read()
        self.assertIn("InpEnableNewEntries=false", text)
        self.assertIn("InpMagic=260119", text)
        self.assertIn("InpUseNewsFilter=false", text)
        self.assertIn("InpSignalTimeframe=0", text)

    def test_walk_forward_keeps_training_and_unseen_windows_separate(self):
        cfg = copy.deepcopy(gold_config())
        cfg["data"]["base_timeframe"] = "D1"
        cfg["strategy"].update({
            "signal_timeframe": "D1", "trend_timeframe": "CURRENT",
            "fast_ema": 5, "slow_ema": 10, "breakout_bars": 5,
            "atr_period": 5, "min_atr_pct": 0.0, "max_atr_pct": 100.0,
        })
        cfg["validation"].update({
            "start_date": "2016-01-01", "train_years": 2, "test_years": 1,
            "min_train_trades": 0, "min_oos_folds": 1, "min_oos_trades": 0,
            "min_oos_profit_factor": 0.0, "min_positive_fold_ratio": 0.0,
            "max_worst_fold_drawdown_pct": 100.0, "min_stress_profit_factor": 0.0,
            "max_profit_concentration_pct": 100.0, "optimization_grid": {},
        })
        result = ValidationAgent(cfg).walk_forward(synthetic_bars(8, "D1", 19), optimize=False)
        folds = result["fold_details"]
        self.assertGreaterEqual(len(folds), 3)
        self.assertTrue(result["method"].startswith("Rolling fixed-length"))
        self.assertIn(result["status"], ("RESEARCH_ONLY", "PAPER_CANDIDATE"))
        self.assertIn("equity", result)
        self.assertIn("blocks", result)
        self.assertGreater(len(result["equity"]), 0)
        for fold in folds:
            self.assertEqual(fold["selected_parameters"], {})
            self.assertLess(fold["train_start"], fold["train_end"])
            self.assertLess(fold["train_end"], fold["test_end"])
            self.assertEqual(fold["train_end"], fold["test_start"])
            self.assertEqual(fold["training_metrics"]["test_end"], fold["train_end"])
            self.assertEqual(fold["test_metrics"]["test_start"], fold["test_start"])
        first_test = min(timestamp(parse_iso_date(f["test_start"])) for f in folds)
        last_test = max(timestamp(parse_iso_date(f["test_end"])) for f in folds)
        for trade in result["oos_trades"]:
            self.assertGreaterEqual(timestamp(parse_iso_date(trade.entry_time)), first_test)
            self.assertLessEqual(timestamp(parse_iso_date(trade.exit_time)), last_test)


if __name__ == "__main__":
    unittest.main()
