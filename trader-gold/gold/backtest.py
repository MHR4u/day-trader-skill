"""A conservative Bid-bar research backtester with explicit trading costs.

It is deliberately not presented as a replacement for MT5 tick testing. If a
bar touches both stop and target, the stop wins. Stops fill with adverse
slippage and gaps; targets receive no favourable slippage.
"""

import datetime as dt
import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

from .data import EPOCH, iso_time, resample
from .models import BacktestResult, Bar, GoldError, Position, Signal, Trade
from .strategy import generate_signals, resolve_trend_timeframe


ENGINE_VERSION = "gold-research-1.0.0"


def _day(value: int) -> dt.date:
    return EPOCH.fromtimestamp(value, dt.timezone.utc).date()


def _moment(value: int) -> dt.datetime:
    return EPOCH.fromtimestamp(value, dt.timezone.utc).replace(tzinfo=None)


def _volume_round(volume: float, step: float) -> float:
    units = math.floor(volume / step + 1e-9)
    decimals = max(0, int(round(-math.log10(step))) if step < 1 else 0)
    return round(units * step, min(8, decimals + 2))


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    return numerator / denominator if denominator > 0 else None


def calculate_metrics(trades: Sequence[Trade], equity: Sequence[Dict[str, object]],
                      initial_balance: float, exposed_bars: int, total_bars: int,
                      commissions: float, test_start: int, test_end: int) -> Dict[str, object]:
    final_equity = float(equity[-1]["equity"]) if equity else initial_balance
    net_profit = final_equity - initial_balance
    profits = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    losses = -sum(t.net_pnl for t in trades if t.net_pnl < 0)
    peak = initial_balance
    max_dd = 0.0
    max_dd_money = 0.0
    dd_start = None
    longest_dd_days = 0
    current_dd_start = None
    for point in equity:
        stamp = int(point["time"])
        value = float(point["equity"])
        if value >= peak:
            if current_dd_start is not None:
                longest_dd_days = max(longest_dd_days, (stamp - current_dd_start) // 86400)
            peak = value
            current_dd_start = None
        elif value > 0:
            if current_dd_start is None:
                current_dd_start = stamp
            dd = 100.0 * (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
                max_dd_money = peak - value
                dd_start = current_dd_start
    if current_dd_start is not None and equity:
        longest_dd_days = max(longest_dd_days, (int(equity[-1]["time"]) - current_dd_start) // 86400)
    daily = {}
    for point in equity:
        daily[_day(int(point["time"]))] = float(point["equity"])
    daily_values = list(daily.values())
    returns = [(b / a - 1.0) for a, b in zip(daily_values, daily_values[1:]) if a > 0]
    sharpe = None
    sortino = None
    if len(returns) >= 2:
        mean = statistics.mean(returns)
        deviation = statistics.stdev(returns)
        if deviation > 0:
            sharpe = mean / deviation * math.sqrt(252.0)
        downside = math.sqrt(sum(min(0.0, r) ** 2 for r in returns) / len(returns))
        if downside > 0:
            sortino = mean / downside * math.sqrt(252.0)
    days = max(0, (test_end - test_start) / 86400.0)
    cagr = None
    if days >= 30 and final_equity > 0 and initial_balance > 0:
        cagr = 100.0 * ((final_equity / initial_balance) ** (365.25 / days) - 1.0)
    r_values = [t.r_multiple for t in trades]
    winners = sum(1 for t in trades if t.net_pnl > 0)
    return {
        "engine": ENGINE_VERSION,
        "initial_balance": round(initial_balance, 2),
        "final_equity": round(final_equity, 2),
        "net_profit": round(net_profit, 2),
        "return_pct": round(100.0 * net_profit / initial_balance, 6),
        "cagr_pct": None if cagr is None else round(cagr, 6),
        "max_drawdown_pct": round(max_dd, 6),
        "max_drawdown_money": round(max_dd_money, 2),
        "max_drawdown_start": iso_time(dd_start) if dd_start is not None else None,
        "longest_drawdown_days": int(longest_dd_days),
        "trades": len(trades),
        "wins": winners,
        "losses": len(trades) - winners,
        "win_rate_pct": round(100.0 * winners / len(trades), 6) if trades else 0.0,
        "profit_factor": None if losses == 0 else round(profits / losses, 6),
        "gross_profit_after_costs": round(profits, 2),
        "gross_loss_after_costs": round(losses, 2),
        "expectancy_r": round(statistics.mean(r_values), 6) if r_values else 0.0,
        "average_trade": round(statistics.mean([t.net_pnl for t in trades]), 4) if trades else 0.0,
        "median_trade_r": round(statistics.median(r_values), 6) if r_values else 0.0,
        "daily_sharpe": None if sharpe is None else round(sharpe, 6),
        "daily_sortino": None if sortino is None else round(sortino, 6),
        "exposure_pct": round(100.0 * exposed_bars / total_bars, 6) if total_bars else 0.0,
        "commissions": round(commissions, 2),
        "test_start": iso_time(test_start),
        "test_end": iso_time(test_end),
        "ambiguous_bar_policy": "stop_first",
        "price_basis": "bid_ohlc_with_spread_and_adverse_slippage",
    }


class Backtester:
    def __init__(self, source_bars: Sequence[Bar], config: Dict[str, object]):
        self.source_bars = source_bars
        self.config = config
        self.account = config["account"]
        self.execution = config["execution"]
        self.strategy = config["strategy"]
        self.risk = config["risk"]
        self.exits = config["exits"]
        data_cfg = config["data"]
        signal_tf = str(self.strategy["signal_timeframe"]).upper()
        trend_tf = resolve_trend_timeframe(signal_tf, str(self.strategy.get("trend_timeframe", "AUTO")))
        self.signal_tf = signal_tf
        self.trend_tf = trend_tf
        self.bars = resample(source_bars, signal_tf, str(data_cfg["base_timeframe"]))
        self.trend_bars = resample(source_bars, trend_tf, str(data_cfg["base_timeframe"]))

    def run(self, start: Optional[int] = None, end: Optional[int] = None,
            parameter_override: Optional[Dict[str, object]] = None) -> BacktestResult:
        if not self.bars:
            raise GoldError("No bars available for the requested timeframe")
        strategy = dict(self.strategy)
        if parameter_override:
            strategy.update(parameter_override)
        start = self.bars[0].start if start is None else start
        end = self.bars[-1].end if end is None else end
        if end <= start:
            raise GoldError("Backtest end must be after its start")
        signals = generate_signals(self.bars, self.trend_bars, strategy, start, end)
        balance = float(self.account["initial_balance"])
        initial_balance = balance
        position = None  # type: Optional[Position]
        pending = None  # type: Optional[Signal]
        trades = []  # type: List[Trade]
        equity_curve = []  # type: List[Dict[str, object]]
        blocks = {}  # type: Dict[str, int]
        last_exit_bar = -10**12
        current_day = None
        current_week = None
        day_start_equity = balance
        week_start_equity = balance
        day_locked = False
        week_locked = False
        total_locked = False
        trades_today = 0
        peak_equity = balance
        commissions = 0.0
        exposed_bars = 0
        processed_bars = 0
        last_bar = None
        last_index = -1

        def block(reason: str) -> None:
            blocks[reason] = blocks.get(reason, 0) + 1

        def mark(bar: Bar, at_open: bool = False) -> float:
            value = balance
            if position is not None:
                raw = bar.open if at_open else bar.close
                closing_bid = raw
                closing_ask = raw + bar.spread
                exit_price = closing_bid if position.direction == 1 else closing_ask
                value += position.direction * (exit_price - position.entry) * position.volume * float(self.account["price_value_per_lot"])
                value -= position.volume * float(self.execution["commission_per_lot_side"])
            return value

        def close_position(bar: Bar, bar_index: int, price: float, reason: str) -> None:
            nonlocal balance, position, last_exit_bar, commissions
            if position is None:
                return
            final_volume = position.volume
            gross = position.direction * (price - position.entry) * final_volume * float(self.account["price_value_per_lot"])
            exit_commission = final_volume * float(self.execution["commission_per_lot_side"])
            balance += gross - exit_commission
            commissions += exit_commission
            gross_total = position.realized + gross
            commission_total = position.entry_commission + position.partial_commission + exit_commission
            net_total = gross_total - commission_total
            monetary_risk = (position.initial_risk * position.initial_volume * float(self.account["price_value_per_lot"])
                             + 2.0 * position.initial_volume * float(self.execution["commission_per_lot_side"]))
            trades.append(Trade(
                direction="buy" if position.direction == 1 else "sell",
                entry_time=iso_time(position.entry_time), exit_time=iso_time(bar.end),
                entry=round(position.entry, 8), exit=round(price, 8),
                initial_volume=position.initial_volume, exit_volume=final_volume,
                initial_stop=round(position.entry - position.direction * position.initial_risk, 8),
                initial_target=round(position.entry + position.direction * position.initial_risk * float(strategy["target_r"]), 8),
                exit_reason=reason, gross_pnl=round(gross_total, 6),
                commission=round(commission_total, 6), net_pnl=round(net_total, 6),
                r_multiple=round(net_total / monetary_risk, 8) if monetary_risk > 0 else 0.0,
                bars_held=bar_index - position.entry_bar + 1,
                partial_pnl=round(position.realized - position.partial_commission, 6),
            ))
            position = None
            last_exit_bar = bar_index

        def partial_close(bar: Bar, fraction: float) -> None:
            nonlocal balance, position, commissions
            if position is None:
                return
            account = self.account
            close_volume = _volume_round(position.initial_volume * fraction, float(account["volume_step"]))
            close_volume = min(close_volume, position.volume)
            if close_volume < float(account["volume_min"]) or position.volume - close_volume < float(account["volume_min"]):
                block("partial_volume_below_broker_minimum")
                position.partial_done = True
                return
            price = position.entry + position.direction * position.initial_risk * float(self.exits["partial_at_r"])
            gross = position.direction * (price - position.entry) * close_volume * float(account["price_value_per_lot"])
            fee = close_volume * float(self.execution["commission_per_lot_side"])
            balance += gross - fee
            commissions += fee
            position.realized += gross
            position.partial_commission += fee
            position.volume = _volume_round(position.volume - close_volume, float(account["volume_step"]))
            position.partial_done = True

        for i, bar in enumerate(self.bars):
            if bar.start >= end:
                break
            if bar.end < start:
                continue
            last_bar = bar
            last_index = i
            processed_bars += 1
            day = _day(bar.start)
            moment = _moment(bar.start)
            week = day.isocalendar()[:2]
            if day != current_day:
                current_day = day
                day_start_equity = mark(bar, True)
                day_locked = False
                trades_today = 0
            if week != current_week:
                current_week = week
                week_start_equity = mark(bar, True)
                week_locked = False

            opening_equity = mark(bar, True)
            if opening_equity > peak_equity:
                peak_equity = opening_equity
            if float(self.risk["max_daily_loss_pct"]) > 0 and opening_equity <= day_start_equity * (1.0 - float(self.risk["max_daily_loss_pct"]) / 100.0):
                day_locked = True
            if float(self.risk["max_weekly_loss_pct"]) > 0 and opening_equity <= week_start_equity * (1.0 - float(self.risk["max_weekly_loss_pct"]) / 100.0):
                week_locked = True
            if float(self.risk["max_total_drawdown_pct"]) > 0 and opening_equity <= peak_equity * (1.0 - float(self.risk["max_total_drawdown_pct"]) / 100.0):
                total_locked = True
            if position is not None and (day_locked or week_locked or total_locked):
                close_price = bar.open if position.direction == 1 else bar.open + bar.spread
                close_price -= position.direction * float(self.execution["slippage_price"])
                reason = "total_drawdown_lock" if total_locked else ("weekly_loss_lock" if week_locked else "daily_loss_lock")
                close_position(bar, i, close_price, reason)

            if pending is not None and position is None and bar.start >= start:
                signal = pending
                pending = None
                allowed = True
                if total_locked:
                    block("total_drawdown_lock")
                    allowed = False
                elif day_locked:
                    block("daily_loss_lock")
                    allowed = False
                elif week_locked:
                    block("weekly_loss_lock")
                    allowed = False
                elif trades_today >= int(self.risk["max_trades_per_day"]):
                    block("max_trades_per_day")
                    allowed = False
                elif i - last_exit_bar < int(self.risk["cooldown_bars"]):
                    block("cooldown")
                    allowed = False
                elif bar.spread > float(self.execution["max_spread_price"]):
                    block("spread")
                    allowed = False
                start_hour = int(self.risk["session_start_hour"])
                end_hour = int(self.risk["session_end_hour"])
                hour = moment.hour + moment.minute / 60.0
                in_session = start_hour <= hour < end_hour if start_hour <= end_hour else (hour >= start_hour or hour < end_hour)
                if allowed and not in_session:
                    block("session")
                    allowed = False
                if allowed and moment.weekday() >= 5:
                    block("weekend")
                    allowed = False
                if allowed and moment.weekday() == 4 and bool(self.risk["friday_close"]) and hour >= int(self.risk["friday_close_hour"]):
                    block("friday_cutoff")
                    allowed = False
                if allowed:
                    slippage = float(self.execution["slippage_price"])
                    entry = bar.open + bar.spread + slippage if signal.direction == 1 else bar.open - slippage
                    stop_distance = max(signal.atr * float(strategy["stop_atr"]), float(self.execution["min_stop_distance_price"]))
                    if stop_distance <= 0 or entry - signal.direction * stop_distance <= 0:
                        block("invalid_stop")
                        allowed = False
                if allowed:
                    equity_now = mark(bar, True)
                    risk_cash = equity_now * float(self.risk["risk_per_trade_pct"]) / 100.0
                    per_lot_risk = (stop_distance + slippage) * float(self.account["price_value_per_lot"]) + 2.0 * float(self.execution["commission_per_lot_side"])
                    raw_volume = risk_cash / per_lot_risk if per_lot_risk > 0 else 0.0
                    volume = _volume_round(min(raw_volume, float(self.account["volume_max"])), float(self.account["volume_step"]))
                    if volume < float(self.account["volume_min"]):
                        block("below_minimum_volume")
                        allowed = False
                if allowed:
                    entry_commission = volume * float(self.execution["commission_per_lot_side"])
                    balance -= entry_commission
                    commissions += entry_commission
                    position = Position(
                        direction=signal.direction, volume=volume, initial_volume=volume, entry=entry,
                        stop=entry - signal.direction * stop_distance,
                        target=entry + signal.direction * stop_distance * float(strategy["target_r"]),
                        initial_risk=stop_distance, entry_time=bar.start, entry_bar=i,
                        entry_atr=signal.atr, entry_commission=entry_commission,
                    )
                    trades_today += 1
            elif pending is not None:
                pending = None

            if position is not None:
                exposed_bars += 1
                spread = bar.spread
                slippage = float(self.execution["slippage_price"])
                if position.direction == 1:
                    stop_hit = bar.low <= position.stop
                    target_hit = bar.high >= position.target
                else:
                    stop_hit = bar.high + spread >= position.stop
                    target_hit = bar.low + spread <= position.target
                if stop_hit:
                    if position.direction == 1:
                        stop_fill = min(position.stop, bar.open) - slippage
                    else:
                        stop_fill = max(position.stop, bar.open + spread) + slippage
                    close_position(bar, i, stop_fill, "stop_loss")
                elif target_hit:
                    close_position(bar, i, position.target, "take_profit")
                else:
                    if bool(self.exits["partial_enabled"]) and not position.partial_done:
                        partial_price = position.entry + position.direction * position.initial_risk * float(self.exits["partial_at_r"])
                        partial_hit = bar.high >= partial_price if position.direction == 1 else bar.low + spread <= partial_price
                        if partial_hit:
                            partial_close(bar, float(self.exits["partial_pct"]) / 100.0)
                            if position is not None and bool(self.exits["breakeven_enabled"]):
                                be_price = position.entry + position.direction * float(self.exits["breakeven_offset_price"])
                                if position.direction * (be_price - position.stop) > 0:
                                    position.stop = be_price
                                    position.breakeven_done = True
                    if position is not None and bool(self.exits["breakeven_enabled"]) and not position.breakeven_done:
                        be_trigger = position.entry + position.direction * position.initial_risk * float(self.exits["breakeven_trigger_r"])
                        be_hit = bar.high >= be_trigger if position.direction == 1 else bar.low + spread <= be_trigger
                        if be_hit:
                            be_price = position.entry + position.direction * float(self.exits["breakeven_offset_price"])
                            if position.direction * (be_price - position.stop) > 0:
                                position.stop = be_price
                                position.breakeven_done = True
                    if position is not None and bool(self.exits["trailing_enabled"]):
                        trail_trigger = position.entry + position.direction * position.initial_risk * float(self.exits["trailing_start_r"])
                        trail_active = bar.close >= trail_trigger if position.direction == 1 else bar.close + spread <= trail_trigger
                        if trail_active:
                            closing_ask = bar.close + spread
                            quote = closing_ask if position.direction == -1 else bar.close
                            candidate = quote - position.direction * position.entry_atr * float(self.exits["trailing_atr"])
                            if position.direction * (candidate - position.stop) > 0:
                                position.stop = candidate
                                position.trailing_stop = candidate

            if position is not None:
                bars_held = i - position.entry_bar + 1
                time_exit = bars_held >= int(self.risk["max_holding_bars"])
                friday_exit = (moment.weekday() == 4 and bool(self.risk["friday_close"])
                               and moment.hour >= int(self.risk["friday_close_hour"]))
                if time_exit or friday_exit:
                    close_price = bar.close if position.direction == 1 else bar.close + bar.spread
                    close_price -= position.direction * float(self.execution["slippage_price"])
                    close_position(bar, i, close_price, "time_exit" if time_exit else "friday_exit")

            closing_equity = mark(bar)
            if closing_equity > peak_equity:
                peak_equity = closing_equity
            if float(self.risk["max_daily_loss_pct"]) > 0 and closing_equity <= day_start_equity * (1.0 - float(self.risk["max_daily_loss_pct"]) / 100.0):
                day_locked = True
            if float(self.risk["max_weekly_loss_pct"]) > 0 and closing_equity <= week_start_equity * (1.0 - float(self.risk["max_weekly_loss_pct"]) / 100.0):
                week_locked = True
            if float(self.risk["max_total_drawdown_pct"]) > 0 and closing_equity <= peak_equity * (1.0 - float(self.risk["max_total_drawdown_pct"]) / 100.0):
                total_locked = True
            if position is not None and (day_locked or week_locked or total_locked):
                close_price = bar.close if position.direction == 1 else bar.close + bar.spread
                close_price -= position.direction * float(self.execution["slippage_price"])
                reason = "total_drawdown_lock" if total_locked else ("weekly_loss_lock" if week_locked else "daily_loss_lock")
                close_position(bar, i, close_price, reason)
                closing_equity = mark(bar)
            equity_curve.append({"time": bar.end, "equity": round(closing_equity, 8), "balance": round(balance, 8)})
            if i in signals and bar.end < end:
                pending = signals[i]

        if position is not None and last_bar is not None:
            close_price = last_bar.close if position.direction == 1 else last_bar.close + last_bar.spread
            close_price -= position.direction * float(self.execution["slippage_price"])
            close_position(last_bar, last_index, close_price, "end_of_test")
            if equity_curve:
                equity_curve[-1] = {"time": last_bar.end, "equity": round(balance, 8), "balance": round(balance, 8)}
        metrics = calculate_metrics(trades, equity_curve, initial_balance, exposed_bars,
                                    processed_bars, commissions, start, end)
        parameters = dict(strategy)
        parameters["resolved_trend_timeframe"] = self.trend_tf
        return BacktestResult(metrics=metrics, trades=trades, equity=equity_curve,
                              blocks=blocks, parameters=parameters)


def run_backtest(source_bars: Sequence[Bar], config: Dict[str, object], start: Optional[int] = None,
                 end: Optional[int] = None, parameter_override: Optional[Dict[str, object]] = None) -> BacktestResult:
    return Backtester(source_bars, config).run(start, end, parameter_override)
