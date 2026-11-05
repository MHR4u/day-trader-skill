import datetime as dt
import os
import sys
import tempfile
import unittest

from _load import ROOT

sys.path.insert(0, os.path.join(ROOT, "trader-gold"))

from gold.data import (iso_time, load_csv, period_bounds, resample, synthetic_bars,
                       timestamp, write_bars_csv)
from gold.models import Bar, GoldError


class GoldDataTests(unittest.TestCase):
    def test_week_and_month_boundaries(self):
        start, end = period_bounds(timestamp(dt.datetime(2024, 1, 4, 12)), "W1")
        self.assertEqual(iso_time(start), "2024-01-01T00:00:00Z")
        self.assertEqual(iso_time(end), "2024-01-08T00:00:00Z")
        start, end = period_bounds(timestamp(dt.datetime(2024, 2, 20)), "MN1")
        self.assertEqual(iso_time(start), "2024-02-01T00:00:00Z")
        self.assertEqual(iso_time(end), "2024-03-01T00:00:00Z")

    def test_resample_ohlc_and_completed_boundaries(self):
        bars = [
            Bar(0, 3600, 100, 103, 99, 102, 10, 0.2),
            Bar(3600, 7200, 102, 105, 101, 104, 20, 0.3),
            Bar(7200, 10800, 104, 106, 103, 105, 30, 0.4),
            Bar(10800, 14400, 105, 107, 102, 103, 40, 0.5),
        ]
        result = resample(bars, "H4", "H1")
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].open, result[0].high, result[0].low, result[0].close),
                         (100, 107, 99, 103))
        self.assertEqual(result[0].volume, 100)
        self.assertEqual(result[0].spread, 0.5)
        self.assertEqual(result[0].end, 14400)

    def test_mt5_headers_spread_points_and_timezone(self):
        text = ("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<SPREAD>\n"
                "2024.01.02\t01:00\t100\t102\t99\t101\t50\t20\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(text)
            path = handle.name
        try:
            bars, meta = load_csv(path, "H1", timezone_offset_hours=2)
            self.assertEqual(iso_time(bars[0].start), "2024-01-01T23:00:00Z")
            self.assertEqual(bars[0].spread, 0.2)
            self.assertEqual(meta["rows"], 1)
            self.assertEqual(meta["spread_source"], "csv")
        finally:
            os.unlink(path)

    def test_duplicate_timestamps_are_rejected(self):
        text = ("datetime,open,high,low,close\n"
                "2024-01-01T00:00:00Z,100,101,99,100\n"
                "2024-01-01T00:00:00Z,100,101,99,100\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(text)
            path = handle.name
        try:
            with self.assertRaises(GoldError):
                load_csv(path, "H1")
        finally:
            os.unlink(path)

    def test_csv_round_trip_preserves_price_spread(self):
        bars = synthetic_bars(1, "D1", 7)[:3]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as handle:
            path = handle.name
        try:
            write_bars_csv(path, bars)
            loaded, _ = load_csv(path, "D1", spread_column_unit="price")
            self.assertEqual(len(loaded), 3)
            self.assertAlmostEqual(loaded[0].spread, bars[0].spread)
            self.assertEqual(loaded[0].start, bars[0].start)
        finally:
            os.unlink(path)

    def test_synthetic_is_deterministic_and_not_weekend_heavy(self):
        first = synthetic_bars(1, "H1", 19)
        second = synthetic_bars(1, "H1", 19)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 5000)
        self.assertTrue(all(b.high >= max(b.open, b.close) for b in first))
        self.assertTrue(all(b.low <= min(b.open, b.close) for b in first))
        self.assertTrue(all(dt.datetime.utcfromtimestamp(b.start).weekday() < 5 for b in first))


if __name__ == "__main__":
    unittest.main()
