# Architecture

`trader-gold` is a standard-library Python 3.8+ research factory plus one MQL5
Expert Advisor. It has no broker connector and no order placement path. The CLI
`factory.py` coordinates six specialist agents and writes an auditable artifact
directory.

## Data flow

```text
CSV or synthetic bars
  -> Data Agent: validate, normalize, provenance, coverage gate
  -> Risk Agent: validate limits and execution assumptions
  -> Strategy Agent: freeze causal rules and allowed optimization grid
  -> Backtest Agent: cost-aware Bid-bar simulation
  -> Validation Agent: rolling walk-forward, unseen tests, cost stress, gates
  -> EA Review Agent: static source checks and new-entries-OFF set file
  -> report.json, summary.md, trades.csv, equity.csv, provenance, set file
```

## Agents

`RiskAgent` runs before data ingestion. It rejects invalid account sizing,
negative costs, impossible loss percentages, bad session hours and unsafe exit
settings. It also returns warnings for zero spread, zero commission, risk above
one percent and break-even without a cost offset.

`DataAgent` delegates parsing to `gold/data.py`. It reads MT4/MT5 tab or comma
files, handles `date` plus `time`, Unix timestamps, timezone offsets, gzip,
unordered rows, duplicate timestamps and spread units. It records SHA-256,
row count, coverage, largest gap and warnings. The 2000 gate allows the first
trading week of January 2000 because New Year holidays can delay the first bar.

`StrategyAgent` restricts optimization to six explicit fields: `fast_ema`,
`slow_ema`, `breakout_bars`, `stop_atr`, `target_r` and `atr_period`. Unknown
fields raise an error. This prevents a search from silently adding martingale,
grid or unbounded-risk behavior.

`BacktestAgent` calls `gold/backtest.py`. It resamples source bars into the
signal and higher timeframes without inventing empty candles. Signals are
generated only from closed bars. Entries happen on the next bar. A completed
higher-timeframe bar is usable only at or after its end.

`ValidationAgent` uses rolling fixed-length windows. For each fold it selects
candidates using training data only, runs one unseen test, then repeats the
same test with stressed spread, slippage and commission. Stressed bars and the
stressed config are built once per call, not once per candidate. It reports
enough folds, enough trades, OOS profit factor, positive fold ratio, worst fold
drawdown, positive stress net profit, worst stress profit factor and profit
concentration.

`EAAgent` checks that the MQL5 source contains the required safety tokens,
records a source hash, and writes a `.set` file with new entries disabled. It
does not compile MQL5 or run MT5. A static pass is only a source review.

## Causal indicators

`gold/strategy.py` uses an SMA-seeded EMA, Wilder ATR seeded with the mean of
the first period true ranges, and rolling previous-bar Donchian extremes that
exclude the signal candle itself. Higher-timeframe EMA values are read only for
bars whose end time has passed. Tests change future bars and assert that past
signals remain unchanged.

## Execution model

The engine treats CSV prices as Bid OHLC and models spread separately. Long
entries pay Ask, short entries receive Bid, long exits use Bid, short exits pay
Ask. Stops fill with adverse slippage or gap prices, targets receive no
favorable slippage, and a candle touching both stop and target is resolved
stop-first. Commissions are charged per lot per side and included in R.

Risk sizing rounds volume down to the broker step. Daily, weekly and total
drawdown locks, trade count, cooldown, session, Friday, weekend, spread,
maximum holding time and minimum stop distance are enforced. Partial profit,
break-even and trailing are explicit state transitions. Break-even is applied
after a partial only when break-even is enabled.

## Timeframes

All 21 MT5 standard timeframes are supported as signal timeframes: M1 through
MN1. `AUTO` maps each to a higher timeframe. `CURRENT` uses the signal
timeframe itself. Resampling uses actual week and month boundaries for W1 and
MN1. A higher timeframe bar is never used before it closes.

## Statuses and deployment

- `SYNTHETIC_ONLY`: deterministic software test, never market evidence.
- `RESEARCH_ONLY`: real or proxy data failed at least one gate.
- `PAPER_CANDIDATE`: Python gates passed, still not MT5 validated.

Every report keeps `deployment_status: "MT5_VALIDATION_REQUIRED"`. Compilation,
real-tick testing and demo forward validation are separate human steps.
