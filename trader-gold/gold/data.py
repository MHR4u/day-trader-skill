"""Input validation, timezone handling, resampling and synthetic test data."""

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import random
from bisect import bisect_right
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Bar, GoldError


EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
MINUTES = {
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M6": 6,
    "M10": 10, "M12": 12, "M15": 15, "M20": 20, "M30": 30,
    "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360,
    "H8": 480, "H12": 720, "D1": 1440,
}
TIMEFRAMES = tuple(MINUTES) + ("W1", "MN1")


def iso_time(timestamp: int) -> str:
    return EPOCH.fromtimestamp(timestamp, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_date(text: str) -> dt.datetime:
    try:
        value = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        raise GoldError("Dates must be ISO format, for example 2000-01-01 or 2000-01-01T00:00:00Z")
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def timestamp(value: dt.datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return int(value.timestamp())


def timeframe_minutes(name: str) -> float:
    name = str(name).upper()
    if name in MINUTES:
        return float(MINUTES[name])
    if name == "W1":
        return 7.0 * 1440.0
    if name == "MN1":
        return 31.0 * 1440.0
    raise GoldError("Unsupported timeframe %r. Choose %s" % (name, ", ".join(TIMEFRAMES)))


def period_bounds(start: int, timeframe: str) -> Tuple[int, int]:
    """Return UTC period start and exclusive end. W1 starts Monday, MN1 on the first."""
    timeframe = timeframe.upper()
    moment = EPOCH.fromtimestamp(start, dt.timezone.utc).replace(tzinfo=None)
    if timeframe in MINUTES:
        seconds = MINUTES[timeframe] * 60
        opening = start - start % seconds
        return opening, opening + seconds
    if timeframe == "W1":
        day = moment.date() - dt.timedelta(days=moment.weekday())
        opening_dt = dt.datetime.combine(day, dt.time())
        closing_dt = opening_dt + dt.timedelta(days=7)
    elif timeframe == "MN1":
        opening_dt = dt.datetime(moment.year, moment.month, 1)
        closing_dt = dt.datetime(moment.year + (moment.month == 12), moment.month % 12 + 1, 1)
    else:
        timeframe_minutes(timeframe)
        raise AssertionError("unreachable")
    return timestamp(opening_dt), timestamp(closing_dt)


def resample(bars: Sequence[Bar], timeframe: str, base_timeframe: str) -> List[Bar]:
    """Resample without inventing empty bars. A bar is usable only at its end."""
    timeframe = timeframe.upper()
    base_timeframe = base_timeframe.upper()
    if timeframe_minutes(timeframe) < timeframe_minutes(base_timeframe):
        raise GoldError("%s bars cannot be rebuilt from lower-resolution %s data" % (timeframe, base_timeframe))
    if timeframe == base_timeframe:
        return list(bars)
    groups = {}  # type: Dict[int, List[Bar]]
    ends = {}  # type: Dict[int, int]
    for bar in bars:
        opening, closing = period_bounds(bar.start, timeframe)
        groups.setdefault(opening, []).append(bar)
        ends[opening] = closing
    out = []
    for opening in sorted(groups):
        members = groups[opening]
        out.append(Bar(
            start=opening,
            end=ends[opening],
            open=members[0].open,
            high=max(b.high for b in members),
            low=min(b.low for b in members),
            close=members[-1].close,
            volume=sum(b.volume for b in members),
            spread=members[-1].spread,
        ))
    return out


def completed_at(bars: Sequence[Bar], when: int) -> int:
    """Index of the newest bar fully closed at `when`, or -1."""
    return bisect_right([b.end for b in bars], when) - 1


def _normal_header(value: str) -> str:
    return value.strip().strip("\ufeff").strip("<>").lower().replace(" ", "_")


def _number(row: Dict[str, str], names: Sequence[str], line: int, default: Optional[float] = None) -> float:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            try:
                answer = float(value)
            except (TypeError, ValueError):
                break
            if math.isfinite(answer):
                return answer
            break
    if default is not None:
        return default
    raise GoldError("CSV line %d has no valid %s value" % (line, "/".join(names)))


def _parse_datetime(row: Dict[str, str], offset_hours: float, line: int) -> int:
    stamp = ""
    if row.get("date") and row.get("time"):
        stamp = row["date"].strip() + " " + row["time"].strip()
    else:
        for key in ("datetime_utc", "datetime", "timestamp", "time", "date"):
            if row.get(key):
                stamp = row[key].strip()
                break
    if not stamp:
        raise GoldError("CSV line %d has no datetime or date/time value" % line)
    if stamp.replace(".", "", 1).isdigit() and len(stamp) >= 9 and "-" not in stamp:
        raw = float(stamp)
        if raw > 100000000000:
            raw /= 1000.0
        return int(raw)
    text = stamp.replace("T", " ").replace("Z", "+00:00")
    parsed = None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                pass
    if parsed is None:
        raise GoldError("CSV line %d has an unsupported timestamp %r" % (line, stamp))
    if parsed.tzinfo is not None:
        return int(parsed.timestamp())
    utc = parsed - dt.timedelta(hours=offset_hours)
    return timestamp(utc)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: str, base_timeframe: str, timezone_offset_hours: float = 0.0,
             default_spread_price: float = 0.20, point_size: float = 0.01,
             spread_column_unit: str = "points") -> Tuple[List[Bar], Dict[str, object]]:
    """Read MT4/MT5 or ordinary OHLC CSV. Input prices are assumed to be Bid."""
    if not os.path.isfile(path):
        raise GoldError("Data file not found: %s" % path)
    if point_size <= 0 or default_spread_price < 0:
        raise GoldError("point_size must be positive and default_spread_price cannot be negative")
    if spread_column_unit not in ("points", "price"):
        raise GoldError("spread_column_unit must be 'points' or 'price'")
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", errors="strict", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(handle, dialect)
        try:
            raw_header = next(reader)
        except StopIteration:
            raise GoldError("The data CSV is empty")
        header = [_normal_header(x) for x in raw_header]
        if not ({"open", "high", "low", "close"} <= set(header)):
            raise GoldError("CSV needs open, high, low and close headers; got %s" % ", ".join(header))
        bars = []
        unordered = 0
        previous = None
        for line, values in enumerate(reader, 2):
            if not values or not any(str(x).strip() for x in values):
                continue
            if len(values) != len(header):
                raise GoldError("CSV line %d has %d fields, expected %d" % (line, len(values), len(header)))
            row = dict(zip(header, values))
            start = _parse_datetime(row, timezone_offset_hours, line)
            _, end = period_bounds(start, base_timeframe)
            o = _number(row, ("open", "<open>"), line)
            h = _number(row, ("high", "<high>"), line)
            low = _number(row, ("low", "<low>"), line)
            c = _number(row, ("close", "<close>"), line)
            volume = _number(row, ("tick_volume", "tickvol", "volume", "vol"), line, 0.0)
            spread = default_spread_price
            for spread_name in ("spread", "spread_points", "spread_price"):
                if row.get(spread_name) not in (None, ""):
                    spread = _number(row, (spread_name,), line)
                    if spread_name != "spread_price" and (spread_column_unit == "points" or spread_name == "spread_points"):
                        spread *= point_size
                    break
            if min(o, h, low, c) <= 0 or h < max(o, c) or low > min(o, c) or h < low:
                raise GoldError("CSV line %d has invalid OHLC prices" % line)
            if spread < 0 or volume < 0:
                raise GoldError("CSV line %d has negative spread or volume" % line)
            if previous is not None and start < previous:
                unordered += 1
            previous = start
            bars.append(Bar(start, end, o, h, low, c, volume, spread))
    if not bars:
        raise GoldError("The CSV contains no usable bars")
    bars.sort(key=lambda b: b.start)
    duplicates = sum(1 for a, b in zip(bars, bars[1:]) if a.start == b.start)
    if duplicates:
        raise GoldError("The CSV has %d duplicate bar timestamps; deduplicate it before testing" % duplicates)
    deltas = [b.start - a.start for a, b in zip(bars, bars[1:]) if b.start > a.start]
    largest_gap = max(deltas) if deltas else 0
    metadata = {
        "path": os.path.abspath(path),
        "sha256": file_sha256(path),
        "rows": len(bars),
        "start": iso_time(bars[0].start),
        "end": iso_time(bars[-1].end),
        "base_timeframe": base_timeframe.upper(),
        "timezone_offset_hours": timezone_offset_hours,
        "unordered_rows_sorted": unordered,
        "duplicate_timestamps": duplicates,
        "largest_gap_days": round(largest_gap / 86400.0, 3),
        "price_basis": "bid_ohlc_assumed",
        "spread_source": "csv" if any(name in header for name in ("spread", "spread_points", "spread_price")) else "configured_default",
        "warnings": [],
    }
    if unordered:
        metadata["warnings"].append("Input was not chronological and was sorted before use")
    if largest_gap > 14 * 86400:
        metadata["warnings"].append("The largest data gap exceeds 14 days; inspect missing history")
    return bars, metadata


def synthetic_bars(years: int = 6, timeframe: str = "H1", seed: int = 19) -> List[Bar]:
    """Deterministic regime-switching prices for software tests, never market evidence."""
    if years < 1 or years > 30:
        raise GoldError("Synthetic years must be between 1 and 30")
    if timeframe not in MINUTES:
        raise GoldError("Synthetic data supports intraday and D1 timeframes only")
    rng = random.Random(seed)
    step = MINUTES[timeframe] * 60
    current = timestamp(dt.datetime(2016, 1, 4, tzinfo=dt.timezone.utc))
    finish = timestamp(dt.datetime(2016 + years, 1, 4, tzinfo=dt.timezone.utc))
    price = 1200.0
    bars = []
    index = 0
    while current < finish:
        local = EPOCH.fromtimestamp(current, dt.timezone.utc)
        if local.weekday() < 5:
            regime = math.sin(index / 650.0) * 0.00045 + math.sin(index / 97.0) * 0.00018
            shock = rng.gauss(0.0, 0.0011)
            opening = price
            closing = max(10.0, opening * (1.0 + regime + shock))
            wick_up = abs(rng.gauss(0.0, opening * 0.00065))
            wick_down = abs(rng.gauss(0.0, opening * 0.00065))
            high = max(opening, closing) + wick_up
            low = max(1.0, min(opening, closing) - wick_down)
            bars.append(Bar(current, current + step, opening, high, low, closing,
                            float(rng.randint(20, 500)), 0.20))
            price = closing
            index += 1
        current += step
    return bars


def write_bars_csv(path: str, bars: Iterable[Bar]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("datetime", "open", "high", "low", "close", "volume", "spread_price"))
        for b in bars:
            writer.writerow((iso_time(b.start), "%.8f" % b.open, "%.8f" % b.high,
                             "%.8f" % b.low, "%.8f" % b.close, "%.4f" % b.volume, "%.8f" % b.spread))
