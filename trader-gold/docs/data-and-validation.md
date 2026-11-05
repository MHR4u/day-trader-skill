# Data and validation

## Accepted CSV

The loader accepts comma, semicolon, tab and gzip files. Header names are
normalized, so `<DATE>`, `<TIME>`, `<OPEN>`, `Date`, `datetime`, `timestamp`
and Unix seconds are all understood. Required price columns are `open`, `high`,
`low` and `close`. Optional columns are `volume`, `tick_volume`, `spread`,
`spread_points` and `spread_price`.

Prices are assumed to be Bid OHLC. Spread is added separately as a price
amount. `data.spread_column_unit` can be `points` or `price`; point conversion
uses `execution.point_size`. `data.timezone_offset_hours` converts broker-local
timestamps to UTC. If no spread column exists, `execution.default_spread_price`
is used and provenance records `spread_source: "configured_default"`.

Duplicate timestamps are rejected. Unordered rows are sorted and reported.
Gaps larger than 14 days are reported as warnings. Resampling never fills an
empty bar with invented prices.

## Provenance and the 2000 gate

`data_provenance.json` records absolute path, SHA-256, rows, start, end, base
timeframe, timezone offset, unordered row count, duplicate count, largest gap,
price basis, spread source, warnings, requested coverage start and coverage
pass. The CLI also stores `--source-url` and `--source-description`.

`validation.require_data_since` defaults to `2000-01-01`. Because New Year
holidays can delay the first trading bar, the gate accepts a start within the
first seven days of that date. A dataset starting in 2004 fails and forces
`RESEARCH_ONLY`. A daily Gold proxy starting in 2000 may pass the date gate,
but that does not make it verified broker spot XAUUSD.

Public sources examined during development:

- `https://github.com/hariomvyas/Commodity-Forecasting/blob/main/Data/gold.csv`
  and its Kaggle mirror, daily OHLC from 2000-01-04 to 2022-09-02. The exact
  instrument and venue are not documented by the mirror, so treat it as an
  unverified daily Gold proxy, not broker XAUUSD.
- `https://github.com/FeziweMelvin/XAUUSD-Gold-Price`, daily and hourly XAU/USD
  exported from MetaTrader 4. The hourly file begins 2004-06-11, so it cannot
  satisfy the 2000 gate.
- `https://github.com/bpineau/pofo/blob/master/pkg/datasets/refdata/XAUUSD-LBMA.csv`,
  daily LBMA PM fix close-only history from 1968. It is useful as a reference
  price series but has no OHLC or spread and is not a broker bar file.

No verified real spot XAUUSD OHLC series from 2000 was available in the public
sources checked. Supplying broker-exported M1 or tick data is the correct way
to complete that requirement.

## Walk-forward method

`ValidationAgent.walk_forward` uses rolling fixed-length windows:

```text
fold 1: train [start, start + train_years)  test [train_end, train_end + test_years)
fold 2: train [start + test_years, ...)     test [train_end + test_years, ...)
```

`train_start` advances by `test_years`, so unseen windows are contiguous and no
test year is skipped. Every fold selects parameters using training bars only,
then evaluates the chosen candidate once on the next unseen window. The final
fold is truncated at the last available bar.

The training score requires `min_train_trades` and rewards positive annual
return net of drawdown, with small bonuses for profit factor above one and
trade count. It is a selection heuristic, not a profitability proof.

## Stress and rejection gates

Each fold is repeated with spread multiplied by `stress.spread_factor`,
slippage by `stress.slippage_factor`, commission by `stress.commission_factor`
and the maximum spread filter raised by the same spread factor. The checks are:

- enough folds and enough OOS trades,
- OOS profit factor at or above `min_oos_profit_factor`,
- positive fold ratio at or above `min_positive_fold_ratio`,
- worst fold drawdown at or below `max_worst_fold_drawdown_pct`,
- positive aggregate stress net profit,
- worst fold stress profit factor at or above `min_stress_profit_factor`,
- positive-year profit concentration at or below `max_profit_concentration_pct`.

A missing profit factor is treated as zero for a gate unless there are winning
trades and no losing trades, in which case it is treated as a large value. A
`PAPER_CANDIDATE` still has `deployment_status: "MT5_VALIDATION_REQUIRED"`.

## Limitations

Python Bid-bar results are not MT5 real-tick results. They do not model swaps,
broker contract changes, news blackout behavior, requotes, partial fills or
actual intrabar tick sequences. The news filter is not reproduced by the CSV
engine. The EA refuses a tester run with the news filter enabled unless a
news-free test is explicitly allowed. Synthetic runs can exercise software but
can never establish a real edge.
