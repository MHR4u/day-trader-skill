"""Specialist agents. Each writes evidence; none can declare a live-ready bot."""

import copy
import datetime as dt
import hashlib
import itertools
import json
import math
import os
import shutil
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .backtest import Backtester, run_backtest
from .data import EPOCH, iso_time, load_csv, parse_iso_date, timestamp
from .models import BacktestResult, Bar, GoldError, Trade
from .strategy import validate_strategy


class DataAgent:
    name = "Data Agent"

    def load(self, path: str, config: Dict[str, object]) -> Tuple[List[Bar], Dict[str, object]]:
        data = config["data"]
        execution = config["execution"]
        bars, metadata = load_csv(
            path, str(data["base_timeframe"]), float(data["timezone_offset_hours"]),
            float(execution["default_spread_price"]), float(execution["point_size"]),
            str(data.get("spread_column_unit", "points")),
        )
        required = config["validation"].get("require_data_since")
        metadata["required_start"] = required
        metadata["coverage_pass"] = True
        if required:
            required_ts = timestamp(parse_iso_date(str(required)))
            # A New Year holiday can put the first trading day a few days into January.
            coverage_deadline = required_ts + 7 * 86400
            metadata["coverage_pass"] = bars[0].start <= coverage_deadline
            metadata["coverage_deadline"] = iso_time(coverage_deadline)
            if not metadata["coverage_pass"]:
                metadata["warnings"].append("Coverage does not begin in the first week of " + str(required))
        return bars, metadata


class StrategyAgent:
    name = "Strategy Agent"

    ALLOWED_GRID = {"fast_ema", "slow_ema", "breakout_bars", "stop_atr", "target_r", "atr_period"}

    def candidates(self, config: Dict[str, object], optimize: bool = True) -> List[Dict[str, object]]:
        strategy = config["strategy"]
        validate_strategy(strategy)
        if not optimize:
            return [{}]
        grid = config["validation"].get("optimization_grid") or {}
        if not grid:
            return [{}]
        unknown = set(grid) - self.ALLOWED_GRID
        if unknown:
            raise GoldError("Unsupported optimization fields: %s" % ", ".join(sorted(unknown)))
        keys = sorted(grid)
        values = []
        for key in keys:
            options = grid[key]
            if not isinstance(options, list) or not options:
                raise GoldError("Optimization grid %s must be a non-empty list" % key)
            values.append(options)
        limit = int(config["validation"].get("max_candidates", 32))
        candidates = []
        for combination in itertools.product(*values):
            candidate = dict(zip(keys, combination))
            merged = dict(strategy)
            merged.update(candidate)
            try:
                validate_strategy(merged)
            except GoldError:
                continue
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        if not candidates:
            raise GoldError("The optimization grid has no valid candidates")
        return candidates


class RiskAgent:
    name = "Risk Agent"

    def validate(self, config: Dict[str, object]) -> List[str]:
        account = config["account"]
        execution = config["execution"]
        risk = config["risk"]
        exits = config["exits"]
        if float(account["initial_balance"]) <= 0 or float(account["price_value_per_lot"]) <= 0:
            raise GoldError("initial_balance and price_value_per_lot must be positive")
        if not 0 < float(account["volume_min"]) <= float(account["volume_max"]):
            raise GoldError("Broker volume_min/volume_max are invalid")
        if float(account["volume_step"]) <= 0:
            raise GoldError("Broker volume_step must be positive")
        for key in ("default_spread_price", "slippage_price", "commission_per_lot_side", "max_spread_price"):
            if float(execution[key]) < 0:
                raise GoldError("Execution %s cannot be negative" % key)
        if float(execution["point_size"]) <= 0:
            raise GoldError("point_size must be positive")
        if not 0 < float(risk["risk_per_trade_pct"]) <= 5:
            raise GoldError("risk_per_trade_pct must be above 0 and no more than 5")
        for key in ("max_daily_loss_pct", "max_weekly_loss_pct", "max_total_drawdown_pct"):
            if not 0 <= float(risk[key]) < 100:
                raise GoldError("%s must be in [0, 100)" % key)
        if int(risk["max_trades_per_day"]) < 1 or int(risk["max_holding_bars"]) < 1:
            raise GoldError("Trade and holding limits must be positive")
        if int(risk["cooldown_bars"]) < 0:
            raise GoldError("cooldown_bars cannot be negative")
        start_hour = int(risk["session_start_hour"])
        end_hour = int(risk["session_end_hour"])
        if not 0 <= start_hour <= 23 or not 1 <= end_hour <= 24:
            raise GoldError("Session hours must use 0-23 start and 1-24 end")
        if not 0 < float(exits["partial_pct"]) < 100:
            raise GoldError("partial_pct must be between 0 and 100")
        for key in ("partial_at_r", "breakeven_trigger_r", "trailing_start_r", "trailing_atr"):
            if float(exits[key]) <= 0:
                raise GoldError("Exit %s must be positive" % key)
        warnings = []
        if float(risk["risk_per_trade_pct"]) > 1:
            warnings.append("Risk above 1 percent per trade is aggressive for an unvalidated EA")
        if float(execution["default_spread_price"]) == 0:
            warnings.append("Zero spread is not a conservative Gold assumption")
        if float(execution["commission_per_lot_side"]) == 0:
            warnings.append("Zero commission may understate real trading costs")
        if float(exits["breakeven_offset_price"]) == 0:
            warnings.append("Break-even without an offset can still lose money after costs")
        return warnings


class BacktestAgent:
    name = "Backtest Agent"

    def run(self, bars: Sequence[Bar], config: Dict[str, object], start: Optional[int] = None,
            end: Optional[int] = None, parameters: Optional[Dict[str, object]] = None) -> BacktestResult:
        return run_backtest(bars, config, start, end, parameters)


class ValidationAgent:
    name = "Validation Agent"

    def __init__(self, config: Dict[str, object]):
        self.config = config
        self.strategy_agent = StrategyAgent()

    @staticmethod
    def _add_years(value: dt.datetime, years: int) -> dt.datetime:
        try:
            return value.replace(year=value.year + years)
        except ValueError:
            return value.replace(year=value.year + years, day=28)

    @staticmethod
    def _profit_factor(trades: Sequence[Trade]) -> Optional[float]:
        gains = sum(t.net_pnl for t in trades if t.net_pnl > 0)
        losses = -sum(t.net_pnl for t in trades if t.net_pnl < 0)
        if losses == 0:
            return None
        return gains / losses

    @staticmethod
    def _pf_for_gate(value: Optional[float], net_profit: float) -> float:
        if value is None:
            return 999.0 if net_profit > 0 else 0.0
        return value

    def _score(self, result: BacktestResult) -> float:
        m = result.metrics
        trades = int(m["trades"])
        minimum = int(self.config["validation"]["min_train_trades"])
        if trades < minimum:
            return -1000000.0 + trades
        net = float(m["net_profit"])
        pf = self._pf_for_gate(m["profit_factor"], net)
        if net <= 0 or pf <= 1.0:
            return -100000.0 + net / max(1.0, float(m["initial_balance"])) * 100.0
        years = max(1.0 / 365.25, (self._last_train_end - self._last_train_start) / (365.25 * 86400.0))
        annual_return = math.log(max(1e-9, float(m["final_equity"]) / float(m["initial_balance"]))) / years
        return annual_return - float(m["max_drawdown_pct"]) / 100.0 + 0.05 * min(2.0, pf - 1.0) + 0.01 * math.sqrt(trades)

    def _select(self, backtester: Backtester, candidates: Sequence[Dict[str, object]],
                start: int, end: int) -> Tuple[Dict[str, object], BacktestResult, List[Dict[str, object]]]:
        self._last_train_start = start
        self._last_train_end = end
        best_parameters = None
        best_result = None
        best_score = -float("inf")
        leaderboard = []
        for parameters in candidates:
            result = backtester.run(start, end, parameters)
            score = self._score(result)
            leaderboard.append({
                "parameters": parameters, "training_score": round(score, 8),
                "training_metrics": result.metrics,
            })
            if score > best_score:
                best_score = score
                best_parameters = parameters
                best_result = result
        leaderboard.sort(key=lambda row: row["training_score"], reverse=True)
        return best_parameters or {}, best_result, leaderboard

    def walk_forward(self, bars: Sequence[Bar], optimize: bool = True,
                     keep_leaderboard: bool = False) -> Dict[str, object]:
        validation = self.config["validation"]
        candidates = self.strategy_agent.candidates(self.config, optimize)
        train_years = int(validation["train_years"])
        test_years = int(validation["test_years"])
        if train_years < 1 or test_years < 1:
            raise GoldError("train_years and test_years must be positive")
        first_moment = EPOCH.fromtimestamp(bars[0].start, dt.timezone.utc).replace(tzinfo=None)
        data_year_start = dt.datetime(first_moment.year, 1, 1)
        if validation.get("start_date"):
            requested_start = parse_iso_date(str(validation["start_date"])).replace(tzinfo=None)
            train_start = max(requested_start, data_year_start)
        else:
            train_start = data_year_start
        last_data = EPOCH.fromtimestamp(bars[-1].end, dt.timezone.utc).replace(tzinfo=None)
        backtester = Backtester(bars, self.config)
        stress_config = copy.deepcopy(self.config)
        stress = validation["stress"]
        spread_factor = float(stress["spread_factor"])
        stressed_bars = [replace(b, spread=b.spread * spread_factor) for b in bars]
        stress_config["execution"]["slippage_price"] = float(self.config["execution"]["slippage_price"]) * float(stress["slippage_factor"])
        stress_config["execution"]["commission_per_lot_side"] = float(self.config["execution"]["commission_per_lot_side"]) * float(stress["commission_factor"])
        stress_config["execution"]["max_spread_price"] = float(self.config["execution"]["max_spread_price"]) * spread_factor
        folds = []
        all_oos_trades = []  # type: List[Trade]
        all_oos_equity = []  # type: List[Dict[str, object]]
        all_blocks = {}  # type: Dict[str, int]
        latest_parameters = {}
        while True:
            train_end = self._add_years(train_start, train_years)
            test_end = self._add_years(train_end, test_years)
            if timestamp(train_end) >= bars[-1].end:
                break
            actual_test_end = min(test_end, last_data)
            if timestamp(train_start) >= bars[-1].end:
                break
            selected, training, leaderboard = self._select(
                backtester, candidates, timestamp(train_start), timestamp(train_end))
            testing = backtester.run(timestamp(train_end), timestamp(actual_test_end), selected)
            stressed = run_backtest(stressed_bars, stress_config, timestamp(train_end), timestamp(actual_test_end), selected)
            fold = {
                "train_start": iso_time(timestamp(train_start)),
                "train_end": iso_time(timestamp(train_end)),
                "test_start": iso_time(timestamp(train_end)),
                "test_end": iso_time(timestamp(actual_test_end)),
                "selected_parameters": selected,
                "training_metrics": training.metrics,
                "test_metrics": testing.metrics,
                "stress_metrics": stressed.metrics,
                "test_blocks": testing.blocks,
            }
            if keep_leaderboard:
                fold["training_leaderboard"] = leaderboard
            folds.append(fold)
            all_oos_trades.extend(testing.trades)
            all_oos_equity.extend(testing.equity)
            for reason, count in testing.blocks.items():
                all_blocks[reason] = all_blocks.get(reason, 0) + count
            latest_parameters = selected
            train_start = self._add_years(train_start, test_years)
            if test_end >= last_data:
                break
        oos_net = sum(t.net_pnl for t in all_oos_trades)
        oos_pf_raw = self._profit_factor(all_oos_trades)
        oos_pf = self._pf_for_gate(oos_pf_raw, oos_net)
        positive_folds = sum(1 for f in folds if float(f["test_metrics"]["net_profit"]) > 0)
        positive_ratio = positive_folds / len(folds) if folds else 0.0
        worst_dd = max([float(f["test_metrics"]["max_drawdown_pct"]) for f in folds] or [100.0])
        stress_net = sum(float(f["stress_metrics"]["net_profit"]) for f in folds)
        stress_trades = []  # type: List[Trade]
        # Stress trade details are intentionally not retained; fold metrics are sufficient for the gate.
        stress_pf_values = [self._pf_for_gate(f["stress_metrics"]["profit_factor"], float(f["stress_metrics"]["net_profit"])) for f in folds]
        stress_pf_min = min(stress_pf_values) if stress_pf_values else 0.0
        yearly = {}
        for trade in all_oos_trades:
            year = trade.exit_time[:4]
            yearly[year] = yearly.get(year, 0.0) + trade.net_pnl
        positive_year_sum = sum(v for v in yearly.values() if v > 0)
        concentration = 100.0 * max([v for v in yearly.values() if v > 0] or [0.0]) / positive_year_sum if positive_year_sum > 0 else 100.0
        summary = {
            "folds": len(folds),
            "oos_trades": len(all_oos_trades),
            "oos_net_profit": round(oos_net, 2),
            "oos_profit_factor": None if oos_pf_raw is None else round(oos_pf_raw, 6),
            "oos_expectancy_r": round(sum(t.r_multiple for t in all_oos_trades) / len(all_oos_trades), 6) if all_oos_trades else 0.0,
            "positive_folds": positive_folds,
            "positive_fold_ratio": round(positive_ratio, 6),
            "worst_fold_max_drawdown_pct": round(worst_dd, 6),
            "stress_net_profit": round(stress_net, 2),
            "worst_fold_stress_profit_factor": round(stress_pf_min, 6),
            "yearly_oos_net_profit": {k: round(v, 2) for k, v in sorted(yearly.items())},
            "positive_year_profit_concentration_pct": round(concentration, 6),
        }
        checks = {
            "enough_folds": len(folds) >= int(validation["min_oos_folds"]),
            "enough_oos_trades": len(all_oos_trades) >= int(validation["min_oos_trades"]),
            "oos_profit_factor": oos_pf >= float(validation["min_oos_profit_factor"]),
            "positive_fold_ratio": positive_ratio >= float(validation["min_positive_fold_ratio"]),
            "drawdown": worst_dd <= float(validation["max_worst_fold_drawdown_pct"]),
            "positive_stress_net": stress_net > 0,
            "stress_profit_factor": stress_pf_min >= float(validation["min_stress_profit_factor"]),
            "profit_concentration": concentration <= float(validation["max_profit_concentration_pct"]),
        }
        status = "PAPER_CANDIDATE" if all(checks.values()) else "RESEARCH_ONLY"
        return {
            "status": status,
            "checks": checks,
            "summary": summary,
            "fold_details": folds,
            "latest_training_parameters": latest_parameters,
            "oos_trades": all_oos_trades,
            "equity": all_oos_equity,
            "blocks": all_blocks,
            "method": "Rolling fixed-length walk-forward; parameters selected on training only, then tested once on the next unseen window",
        }

    def single(self, bars: Sequence[Bar]) -> Dict[str, object]:
        result = run_backtest(bars, self.config)
        return {
            "status": "RESEARCH_ONLY",
            "checks": {"out_of_sample_validation": False},
            "summary": result.metrics,
            "fold_details": [],
            "latest_training_parameters": {},
            "oos_trades": result.trades,
            "equity": result.equity,
            "blocks": result.blocks,
            "parameters": result.parameters,
            "method": "Single in-sample research run; no professional or live-readiness claim",
        }


class EAAgent:
    name = "EA Review Agent"

    REQUIRED = {
        "hard SL and TP": "trade.Buy(",
        "sell execution": "trade.Sell(",
        "server retcode checks": "ResultRetcode()",
        "partial profit": "PositionClosePartial(",
        "break-even": "ManageBreakEven",
        "ATR trailing": "ManageTrailing",
        "daily protection": "dailyLocked",
        "weekly protection": "weeklyLocked",
        "total drawdown protection": "totalLocked",
        "spread filter": "InpMaxSpreadPoints",
        "magic isolation": "POSITION_MAGIC",
        "closed bar signals": "lastSignalBar",
        "news filter": "CalendarValueHistory(",
        "broker stop distance": "SYMBOL_TRADE_STOPS_LEVEL",
        "indicator readiness": "BarsCalculated(",
        "higher timeframe validation": "PeriodSeconds(trendTF)",
        "custom tester criterion": "OnTester()",
    }

    def review(self, ea_path: str) -> Dict[str, object]:
        if not os.path.isfile(ea_path):
            raise GoldError("MT5 EA source is missing: %s" % ea_path)
        with open(ea_path, encoding="utf-8") as handle:
            source = handle.read()
        checks = {name: token in source for name, token in self.REQUIRED.items()}
        compiler = shutil.which("metaeditor64") or shutil.which("metaeditor")
        return {
            "path": os.path.abspath(ea_path),
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "static_checks": checks,
            "static_pass": all(checks.values()),
            "compiler_found": bool(compiler),
            "compiler_path": compiler,
            "compiled": False,
            "mt5_tick_test_passed": False,
            "note": "Static source review is not compilation, a tick backtest, or live approval",
        }

    def write_set(self, path: str, config: Dict[str, object], parameters: Dict[str, object]) -> None:
        strategy = dict(config["strategy"])
        strategy.update(parameters or {})
        risk = config["risk"]
        exits = config["exits"]
        execution = config["execution"]
        full_session = (int(risk["session_start_hour"]) == 0 and
                        int(risk["session_end_hour"]) == 24)
        values = {
            "InpEnableNewEntries": "false",
            "InpMagic": execution.get("magic", 260119),
            "InpRequireGoldSymbol": "true",
            "InpMaxSpreadPoints": round(float(execution["max_spread_price"]) / float(execution["point_size"])),
            "InpDeviationPoints": round(float(execution["slippage_price"]) / float(execution["point_size"])),
            "InpCommissionPerLotSide": execution["commission_per_lot_side"],
            "InpAllowLong": str(bool(strategy.get("allow_long", True))).lower(),
            "InpAllowShort": str(bool(strategy.get("allow_short", True))).lower(),
            "InpOnePositionPerSymbol": "true",
            "InpSignalTimeframe": "0",
            "InpTrendTimeframe": "0",
            "InpFastEMA": strategy["fast_ema"],
            "InpSlowEMA": strategy["slow_ema"],
            "InpBreakoutBars": strategy["breakout_bars"],
            "InpATRPeriod": strategy["atr_period"],
            "InpStopATR": strategy["stop_atr"],
            "InpTargetR": strategy["target_r"],
            "InpMinATRPercent": strategy["min_atr_pct"],
            "InpMaxATRPercent": strategy["max_atr_pct"],
            "InpMinStopDistancePoints": round(float(execution["min_stop_distance_price"]) / float(execution["point_size"])),
            "InpRiskPerTradePct": risk["risk_per_trade_pct"],
            "InpMaxDailyLossPct": risk["max_daily_loss_pct"],
            "InpMaxWeeklyLossPct": risk["max_weekly_loss_pct"],
            "InpMaxTotalDrawdownPct": risk["max_total_drawdown_pct"],
            "InpMaxTradesPerDay": risk["max_trades_per_day"],
            "InpCooldownBars": risk["cooldown_bars"],
            "InpMaxHoldingBars": risk["max_holding_bars"],
            "InpResetProtectionLocks": "false",
            "InpUsePartial": str(bool(exits["partial_enabled"])).lower(),
            "InpPartialPercent": exits["partial_pct"],
            "InpPartialAtR": exits["partial_at_r"],
            "InpUseBreakEven": str(bool(exits["breakeven_enabled"])).lower(),
            "InpBreakEvenAtR": exits["breakeven_trigger_r"],
            "InpBreakEvenOffsetPoints": round(float(exits["breakeven_offset_price"]) / float(execution["point_size"])),
            "InpUseTrailing": str(bool(exits["trailing_enabled"])).lower(),
            "InpTrailStartR": exits["trailing_start_r"],
            "InpTrailATR": exits["trailing_atr"],
            "InpUseSessionFilter": str(not full_session).lower(),
            "InpSessionStartHour": risk["session_start_hour"],
            "InpSessionEndHour": risk["session_end_hour"],
            "InpCloseAtDayEnd": "false",
            "InpDayEndHour": "23",
            "InpFridayClose": str(bool(risk["friday_close"])).lower(),
            "InpFridayCloseHour": risk["friday_close_hour"],
            "InpUseNewsFilter": "false",
            "InpNewsCurrency": "USD",
            "InpNewsMinutesBefore": "30",
            "InpNewsMinutesAfter": "30",
            "InpNewsImportance": "3",
            "InpNewsFailClosed": "true",
            "InpAllowTesterWithoutNews": "false",
            "InpChartStatus": "true",
            "InpVerboseLog": "false",
        }
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("; Research parameters only. New entries are OFF. Validate in MT5 before demo use.\n")
            for key, value in values.items():
                handle.write("%s=%s\n" % (key, value))
