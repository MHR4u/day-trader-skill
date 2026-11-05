import os
import sys
import unittest
from dataclasses import replace

from _load import ROOT, gold_config

sys.path.insert(0, os.path.join(ROOT, "trader-gold"))

from gold.data import TIMEFRAMES
from gold.models import Bar
from gold.strategy import (AUTO_TREND, atr, ema, generate_signals, previous_extremes,
                           resolve_trend_timeframe)


def rising_bars(count, step=3600):
    bars = []
    for i in range(count):
        price = 100.0 + i
        bars.append(Bar(i * step, (i + 1) * step, price, price + 1.2,
                        price - 0.2, price + 1.0, 10, 0.2))
    return bars


class GoldStrategyTests(unittest.TestCase):
    def config(self):
        cfg = dict(gold_config()["strategy"])
        cfg.update({"fast_ema": 1, "slow_ema": 2, "breakout_bars": 2,
                    "atr_period": 2, "max_atr_pct": 100.0})
        return cfg

    def test_all_mt5_timeframes_have_an_auto_trend_mapping(self):
        self.assertEqual(len(TIMEFRAMES), 21)
        self.assertEqual(set(AUTO_TREND), set(TIMEFRAMES))
        for name in TIMEFRAMES:
            self.assertIn(resolve_trend_timeframe(name, "AUTO"), TIMEFRAMES)
            self.assertEqual(resolve_trend_timeframe(name, "CURRENT"), name)
        self.assertEqual(resolve_trend_timeframe("M15", "AUTO"), "H1")
        self.assertEqual(resolve_trend_timeframe("H1", "AUTO"), "H4")
        self.assertEqual(resolve_trend_timeframe("D1", "AUTO"), "W1")
        self.assertEqual(resolve_trend_timeframe("W1", "AUTO"), "MN1")
        self.assertEqual(resolve_trend_timeframe("MN1", "AUTO"), "MN1")
        self.assertEqual(resolve_trend_timeframe("M15", "CURRENT"), "M15")
        self.assertEqual(resolve_trend_timeframe("H1", "H8"), "H8")

    def test_indicators_are_sma_seeded_and_causal(self):
        values = ema([1.0, 2.0, 3.0, 4.0], 2)
        self.assertIsNone(values[0])
        self.assertAlmostEqual(values[1], 1.5)
        self.assertAlmostEqual(values[2], 2.5)
        self.assertAlmostEqual(values[3], 3.5)
        bars = rising_bars(4)
        ranges = atr(bars, 2)
        self.assertIsNone(ranges[0])
        self.assertAlmostEqual(ranges[1], 1.4)
        self.assertAlmostEqual(ranges[2], 1.4)
        changed = list(bars[:2]) + [replace(b, high=b.high * 10) for b in bars[2:]]
        self.assertAlmostEqual(atr(changed, 2)[1], ranges[1])
        self.assertAlmostEqual(ema([1.0, 2.0, 3.0, 999.0], 2)[1], 1.5)

    def test_donchian_excludes_signal_candle(self):
        bars = rising_bars(5)
        highs, _ = previous_extremes(bars, 2)
        self.assertIsNone(highs[1])
        self.assertEqual(highs[2], bars[1].high)
        modified = list(bars)
        modified[2] = replace(modified[2], high=10000.0)
        highs, _ = previous_extremes(modified, 2)
        self.assertEqual(highs[2], bars[1].high)
        self.assertEqual(highs[3], 10000.0)

    def test_unfinished_higher_timeframe_bar_is_not_used(self):
        signal = rising_bars(12, 3600)
        trend = []
        for i in range(3):
            part = signal[i * 4:(i + 1) * 4]
            trend.append(Bar(part[0].start, part[-1].end, part[0].open,
                             max(b.high for b in part), min(b.low for b in part), part[-1].close))
        signals = generate_signals(signal, trend, self.config())
        self.assertTrue(all(index >= 7 for index in signals))
        self.assertIn(7, signals)

    def test_changing_future_bars_cannot_change_past_signals(self):
        bars = rising_bars(30)
        config = self.config()
        before = generate_signals(bars, bars, config)
        changed = list(bars[:20])
        for b in bars[20:]:
            changed.append(replace(b, high=b.high * 3, low=b.low / 2, close=b.close * 2))
        after = generate_signals(changed, changed, config)
        self.assertEqual({i: s.direction for i, s in before.items() if i < 19},
                         {i: s.direction for i, s in after.items() if i < 19})


if __name__ == "__main__":
    unittest.main()
