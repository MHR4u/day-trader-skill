import copy
import os
import sys
import unittest

from _load import ROOT, gold_config

sys.path.insert(0, os.path.join(ROOT, "trader-gold"))

from gold.backtest import _volume_round, calculate_metrics, run_backtest
from gold.models import Bar


def research_config():
    cfg = copy.deepcopy(gold_config())
    cfg["data"]["base_timeframe"] = "H1"
    cfg["strategy"].update({
        "signal_timeframe": "H1", "trend_timeframe": "CURRENT",
        "fast_ema": 1, "slow_ema": 2, "breakout_bars": 2, "atr_period": 2,
        "stop_atr": 1.0, "target_r": 2.0, "min_atr_pct": 0.0, "max_atr_pct": 100.0,
        "allow_long": True, "allow_short": False,
    })
    cfg["account"].update({
        "initial_balance": 10000.0, "price_value_per_lot": 100.0,
        "volume_min": 0.01, "volume_max": 50.0, "volume_step": 0.01,
    })
    cfg["execution"].update({
        "max_spread_price": 1.0, "slippage_price": 0.0,
        "commission_per_lot_side": 0.0, "min_stop_distance_price": 0.0,
    })
    cfg["risk"].update({
        "risk_per_trade_pct": 1.0, "max_daily_loss_pct": 0.0,
        "max_weekly_loss_pct": 0.0, "max_total_drawdown_pct": 0.0,
        "max_trades_per_day": 10, "cooldown_bars": 0, "max_holding_bars": 100,
        "session_start_hour": 0, "session_end_hour": 24, "friday_close": False,
    })
    cfg["exits"].update({
        "partial_enabled": False, "breakeven_enabled": False, "trailing_enabled": False,
    })
    return cfg


def bar(index, o, h, low, c, spread=0.2):
    return Bar(index * 3600, (index + 1) * 3600, o, h, low, c, 100.0, spread)


def long_breakout_bars():
    return [
        bar(0, 100.0, 101.0, 99.0, 100.5),
        bar(1, 100.5, 101.5, 100.0, 101.0),
        bar(2, 101.0, 121.0, 100.5, 120.0),
        bar(3, 120.0, 150.0, 105.0, 130.0),
    ]


def short_breakout_bars():
    return [
        bar(0, 110.0, 111.0, 109.0, 109.5),
        bar(1, 109.5, 110.0, 108.5, 109.0),
        bar(2, 109.0, 109.5, 90.0, 91.0),
        bar(3, 91.0, 92.0, 69.0, 70.0),
    ]


class GoldBacktestTests(unittest.TestCase):
    def test_volume_is_rounded_down_to_broker_step(self):
        self.assertEqual(_volume_round(0.37, 0.1), 0.3)
        self.assertEqual(_volume_round(0.99, 0.01), 0.99)
        self.assertEqual(_volume_round(0.009, 0.01), 0.0)

    def test_metrics_without_trades_do_not_invent_a_profit_factor(self):
        metrics = calculate_metrics([], [], 10000.0, 0, 1, 0.0, 0, 86400)
        self.assertEqual(metrics["trades"], 0)
        self.assertIsNone(metrics["profit_factor"])
        self.assertEqual(metrics["ambiguous_bar_policy"], "stop_first")

    def test_long_entry_is_ask_and_ambiguous_bar_fills_stop_first(self):
        result = run_backtest(long_breakout_bars(), research_config())
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.direction, "buy")
        self.assertAlmostEqual(trade.entry, 120.2)
        self.assertGreater(trade.initial_target, trade.entry)
        self.assertLess(trade.initial_stop, trade.entry)
        self.assertEqual(trade.exit_reason, "stop_loss")
        self.assertAlmostEqual(trade.exit, 109.075)
        self.assertLess(trade.net_pnl, 0.0)

    def test_short_entry_is_bid_and_target_exit_uses_ask(self):
        cfg = research_config()
        cfg["strategy"]["allow_long"] = False
        cfg["strategy"]["allow_short"] = True
        result = run_backtest(short_breakout_bars(), cfg)
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.direction, "sell")
        self.assertAlmostEqual(trade.entry, 91.0)
        self.assertAlmostEqual(trade.initial_target, 69.75)
        self.assertEqual(trade.exit_reason, "take_profit")
        self.assertAlmostEqual(trade.exit, 69.75)
        expected = (trade.entry - trade.exit) * trade.initial_volume * 100.0
        self.assertAlmostEqual(trade.net_pnl, expected, places=4)
        self.assertGreater(trade.net_pnl, 0.0)

    def test_partial_close_accounts_for_gross_and_three_commissions(self):
        cfg = research_config()
        cfg["execution"]["commission_per_lot_side"] = 1.0
        cfg["execution"]["min_stop_distance_price"] = 1.0
        cfg["strategy"]["stop_atr"] = 0.01
        cfg["risk"]["max_holding_bars"] = 2
        cfg["exits"].update({
            "partial_enabled": True, "partial_pct": 50.0, "partial_at_r": 1.0,
        })
        bars = [
            bar(0, 100.0, 101.0, 99.0, 100.5),
            bar(1, 100.5, 101.5, 100.0, 101.0),
            bar(2, 101.0, 121.0, 100.5, 120.0),
            bar(3, 120.0, 121.5, 119.5, 121.0),
            bar(4, 121.0, 121.6, 119.5, 121.4),
        ]
        result = run_backtest(bars, cfg)
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.exit_reason, "time_exit")
        self.assertAlmostEqual(trade.initial_volume, 0.98)
        self.assertAlmostEqual(trade.exit_volume, 0.49)
        self.assertAlmostEqual(trade.partial_pnl, 48.51, places=6)
        self.assertAlmostEqual(trade.commission, 1.96, places=6)
        self.assertAlmostEqual(trade.gross_pnl, 107.8, places=6)
        self.assertAlmostEqual(trade.net_pnl, 105.84, places=6)
        self.assertAlmostEqual(trade.net_pnl,
                               trade.gross_pnl - trade.commission, places=6)

    def test_bars_after_the_exit_cannot_change_completed_trades(self):
        cfg = research_config()
        original = long_breakout_bars() + [
            bar(4, 130.0, 131.0, 129.0, 130.5),
            bar(5, 130.5, 131.5, 129.5, 131.0),
        ]
        changed = list(original)
        changed[4] = bar(4, 300.0, 400.0, 10.0, 350.0)
        changed[5] = bar(5, 350.0, 500.0, 5.0, 400.0)
        end = 4 * 3600
        first = run_backtest(original, cfg, 0, end)
        second = run_backtest(changed, cfg, 0, end)
        self.assertEqual(first.trades, second.trades)
        self.assertEqual(first.metrics["net_profit"], second.metrics["net_profit"])


if __name__ == "__main__":
    unittest.main()
