"""Shared data structures for the Gold research factory. Python 3.8+."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Bar:
    """A bid OHLC bar. start and end are Unix seconds, end is exclusive."""

    start: int
    end: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 0.0


@dataclass
class Signal:
    direction: int
    bar_index: int
    atr: float
    reason: str


@dataclass
class Position:
    direction: int
    volume: float
    initial_volume: float
    entry: float
    stop: float
    target: float
    initial_risk: float
    entry_time: int
    entry_bar: int
    entry_atr: float
    entry_commission: float
    realized: float = 0.0
    partial_commission: float = 0.0
    partial_done: bool = False
    breakeven_done: bool = False
    trailing_stop: Optional[float] = None


@dataclass
class Trade:
    direction: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    initial_volume: float
    exit_volume: float
    initial_stop: float
    initial_target: float
    exit_reason: str
    gross_pnl: float
    commission: float
    net_pnl: float
    r_multiple: float
    bars_held: int
    partial_pnl: float = 0.0

    def as_dict(self) -> Dict[str, object]:
        return dict(self.__dict__)


@dataclass
class BacktestResult:
    metrics: Dict[str, object]
    trades: List[Trade] = field(default_factory=list)
    equity: List[Dict[str, object]] = field(default_factory=list)
    blocks: Dict[str, int] = field(default_factory=dict)
    parameters: Dict[str, object] = field(default_factory=dict)


class GoldError(Exception):
    """A user-facing data, configuration or research error."""
