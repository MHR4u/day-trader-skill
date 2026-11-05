"""Closed-bar Donchian breakouts with a completed higher-timeframe EMA filter."""

from collections import deque
from typing import Dict, List, Optional, Sequence, Tuple

from .data import iso_time, timeframe_minutes
from .models import Bar, GoldError, Signal


AUTO_TREND = {
    "M1": "M15", "M2": "M15", "M3": "M15", "M4": "M20", "M5": "M30",
    "M6": "M30", "M10": "H1", "M12": "H1", "M15": "H1", "M20": "H2",
    "M30": "H4", "H1": "H4", "H2": "H8", "H3": "H12", "H4": "D1",
    "H6": "D1", "H8": "D1", "H12": "D1", "D1": "W1", "W1": "MN1", "MN1": "MN1",
}


def resolve_trend_timeframe(signal_timeframe: str, configured: str) -> str:
    signal_timeframe = signal_timeframe.upper()
    configured = configured.upper()
    if configured == "AUTO":
        return AUTO_TREND[signal_timeframe]
    if configured in ("CURRENT", ""):
        return signal_timeframe
    return configured


def ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Standard EMA seeded with the SMA of the first `period` values."""
    if period < 1:
        raise GoldError("EMA periods must be positive")
    out = [None] * len(values)  # type: List[Optional[float]]
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for index in range(period, len(values)):
        current = alpha * values[index] + (1.0 - alpha) * current
        out[index] = current
    return out


def atr(bars: Sequence[Bar], period: int) -> List[Optional[float]]:
    """Wilder ATR seeded with the mean of the first `period` true ranges."""
    if period < 1:
        raise GoldError("ATR period must be positive")
    out = [None] * len(bars)  # type: List[Optional[float]]
    if len(bars) < period:
        return out
    true_ranges = []
    previous_close = None
    for bar in bars:
        true_range = bar.high - bar.low
        if previous_close is not None:
            true_range = max(true_range, abs(bar.high - previous_close), abs(bar.low - previous_close))
        true_ranges.append(true_range)
        previous_close = bar.close
    current = sum(true_ranges[:period]) / period
    out[period - 1] = current
    for index in range(period, len(bars)):
        current = ((current * (period - 1)) + true_ranges[index]) / period
        out[index] = current
    return out


def previous_extremes(bars: Sequence[Bar], lookback: int) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Previous N highs/lows, excluding the signal bar itself."""
    highs = []  # type: List[Optional[float]]
    lows = []  # type: List[Optional[float]]
    high_queue = deque()
    low_queue = deque()
    for i, bar in enumerate(bars):
        candidate = i - 1
        if candidate >= 0:
            value = bars[candidate].high
            while high_queue and high_queue[-1][1] <= value:
                high_queue.pop()
            high_queue.append((candidate, value))
            value = bars[candidate].low
            while low_queue and low_queue[-1][1] >= value:
                low_queue.pop()
            low_queue.append((candidate, value))
        oldest = i - lookback
        while high_queue and high_queue[0][0] < oldest:
            high_queue.popleft()
        while low_queue and low_queue[0][0] < oldest:
            low_queue.popleft()
        if i >= lookback and high_queue and low_queue:
            highs.append(high_queue[0][1])
            lows.append(low_queue[0][1])
        else:
            highs.append(None)
            lows.append(None)
    return highs, lows


def validate_strategy(config: Dict[str, object]) -> None:
    fast = int(config["fast_ema"])
    slow = int(config["slow_ema"])
    if fast >= slow:
        raise GoldError("fast_ema must be smaller than slow_ema")
    if int(config["breakout_bars"]) < 2 or int(config["atr_period"]) < 2:
        raise GoldError("breakout_bars and atr_period must be at least 2")
    if float(config["stop_atr"]) <= 0 or float(config["target_r"]) <= 0:
        raise GoldError("stop_atr and target_r must be positive")
    if float(config["max_atr_pct"]) <= 0 or float(config["min_atr_pct"]) < 0:
        raise GoldError("ATR percentage bounds are invalid")
    if float(config["min_atr_pct"]) >= float(config["max_atr_pct"]):
        raise GoldError("min_atr_pct must be below max_atr_pct")


def generate_signals(bars: Sequence[Bar], trend_bars: Sequence[Bar], config: Dict[str, object],
                     start: int = 0, end: Optional[int] = None) -> Dict[int, Signal]:
    """Generate a signal only at a closed signal bar and completed HTF bar.

    `start` limits entries, while all preceding bars remain available as warm-up.
    """
    validate_strategy(config)
    closes = [b.close for b in trend_bars]
    fast_values = ema(closes, int(config["fast_ema"]))
    slow_values = ema(closes, int(config["slow_ema"]))
    atr_values = atr(bars, int(config["atr_period"]))
    highs, lows = previous_extremes(bars, int(config["breakout_bars"]))
    signals = {}  # type: Dict[int, Signal]
    trend_index = -1
    allow_long = bool(config.get("allow_long", True))
    allow_short = bool(config.get("allow_short", True))
    min_atr_pct = float(config["min_atr_pct"])
    max_atr_pct = float(config["max_atr_pct"])
    for i, bar in enumerate(bars):
        while trend_index + 1 < len(trend_bars) and trend_bars[trend_index + 1].end <= bar.end:
            trend_index += 1
        if bar.end < start or (end is not None and bar.end >= end):
            continue
        if trend_index < 0 or atr_values[i] is None or highs[i] is None:
            continue
        fast = fast_values[trend_index]
        slow = slow_values[trend_index]
        current_atr = atr_values[i]
        if fast is None or slow is None or current_atr is None or current_atr <= 0:
            continue
        atr_pct = 100.0 * current_atr / bar.close
        if not min_atr_pct <= atr_pct <= max_atr_pct:
            continue
        trend_close = trend_bars[trend_index].close
        long_trend = fast > slow and trend_close > slow
        short_trend = fast < slow and trend_close < slow
        if allow_long and long_trend and bar.close > highs[i]:
            signals[i] = Signal(1, i, current_atr, "close_above_previous_donchian_high")
        elif allow_short and short_trend and bar.close < lows[i]:
            signals[i] = Signal(-1, i, current_atr, "close_below_previous_donchian_low")
    return signals


def signal_audit(signal: Signal, bars: Sequence[Bar]) -> Dict[str, object]:
    bar = bars[signal.bar_index]
    return {
        "signal_bar_end": iso_time(bar.end),
        "direction": "buy" if signal.direction == 1 else "sell",
        "close": bar.close,
        "atr": signal.atr,
        "rule": signal.reason,
    }
