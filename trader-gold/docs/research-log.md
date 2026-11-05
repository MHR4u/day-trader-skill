# Research log

This log records the work done for the request to build a multi-agent Gold
research system, backtest from 2000, and iterate until a professional MT5 EA
exists. The honest result is: a repeatable multi-agent research system and a
feature-complete research EA now exist, but no run produced a professional or
live-ready bot. Every saved run was rejected by at least one explicit gate.

## What was built

- Six Python agents: Data, Strategy, Risk, Backtest, Validation, EA Review.
- Causal closed-bar Donchian strategy with completed higher-timeframe EMA,
  SMA-seeded EMA, Wilder ATR, automatic timeframe mapping for all 21 MT5
  standard timeframes, and rolling previous-bar extremes.
- Cost-aware Bid-bar engine with spread, commission, slippage, gap-aware stops,
  stop-first ambiguity, broker volume rounding, partials, break-even, trailing,
  time, session, Friday, daily, weekly and total drawdown controls.
- Rolling fixed-length walk-forward with training-only candidate selection,
  one-shot unseen tests, cost stress, profit concentration and rejection gates.
- MQL5 EA with automatic entries in tester, live entries OFF by default, hard
  SL/TP, broker-aware sizing, retcode checks, partial profit, break-even,
  trailing, news blackout, account guards, persistent state and OnTester.
- Generated report, provenance, trades, equity, resolved config, summary and
  new-entries-OFF set file for every run.
- 25 focused Gold tests plus the repository contract tests. The full suite has
  340 passing tests. Static EA review passes 17 source checks, but no MQL5
  compiler or MetaEditor was available in this sandbox.

## Data found

A verified broker spot XAUUSD OHLC series starting in 2000 was not found in the
public sources checked. Two real public datasets were used, with different
limitations:

1. Unverified daily Gold OHLC proxy from 2000-01-04 to 2022-09-02, mirrored at
   https://github.com/hariomvyas/Commodity-Forecasting/blob/main/Data/gold.csv
   and described as a Kaggle daily Gold price dataset. It passes the 2000 date
   gate, but the exact instrument and venue are not documented, so it is not
   broker spot XAUUSD.
2. MT4-exported XAU/USD H1 from 2004-06-11 to 2025-06-06 at
   https://github.com/FeziweMelvin/XAUUSD-Gold-Price/blob/main/XAU_1h_data.csv
   It is closer to the requested instrument but fails the 2000 coverage gate.

A daily LBMA PM fix close-only series from 1968 was also examined at
https://github.com/bpineau/pofo/blob/master/pkg/datasets/refdata/XAUUSD-LBMA.csv
but it has no OHLC or spread and was not used as a bar backtest. Supplying
broker-exported M1 or tick data from 2000 is still required to fully satisfy
that requirement.

## Saved iterations

The exact commands, source URLs, SHA-256 values and per-run artifacts are in
`../research/README.md`. A compact generated table is in
`../research/iterations.md` and machine-readable details are in
`../research/iterations.json`.

| Run | Data and method | Status | OOS folds | OOS trades | OOS net | OOS PF | Positive folds | Stress net | Coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic-smoke | 8 years deterministic H1, no optimization | SYNTHETIC_ONLY | 6 | 1114 | 29871.44 | 7.60 | 6/6 | 28246.00 | FAIL |
| daily-2000-proxy | 2000 to 2022 daily Gold proxy, optimized walk-forward | RESEARCH_ONLY | 20 | 30 | 175.50 | 1.60 | 7/20 | 171.17 | PASS |
| hourly-2004-xauusd | 2004 to 2025 H1 XAUUSD, baseline walk-forward | RESEARCH_ONLY | 19 | 2226 | -239.74 | 0.99 | 10/19 | -1955.69 | FAIL |
| hourly-optimized-a | H1 XAUUSD, smaller training-only grid | RESEARCH_ONLY | 19 | 2645 | -812.92 | 0.97 | 7/19 | -3261.17 | FAIL |
| hourly-long-only-b | H1 XAUUSD, long-only training-only grid | RESEARCH_ONLY | 19 | 1124 | 578.77 | 1.05 | 12/19 | -486.01 | FAIL |

Synthetic numbers are deliberately not treated as evidence. The generated bars
have a persistent drift, so a breakout rule can look excellent while proving
nothing about Gold. Status is forced to `SYNTHETIC_ONLY`.

The daily proxy passed the 2000 date gate and had a positive OOS profit factor,
but only 7 of 20 folds were positive and the worst stressed fold profit factor
was 0.0. It was rejected. The proxy is also not verified XAUUSD.

The baseline H1 XAUUSD run had 19 unseen folds and 2226 OOS trades, but OOS
profit factor 0.99, negative stress net profit and a 2000 coverage failure. It
was rejected. The two additional training-only optimization variants also
failed. The long-only variant improved OOS net profit to 578.77 and 12 of 19
positive folds, but its OOS profit factor 1.05 stayed below the 1.10 gate and
its stressed net profit was -486.01. No variant was selected on the basis of
these OOS results; each run is an independent research attempt.

All five runs keep `deployment_status: MT5_VALIDATION_REQUIRED`. The MT5
compile and real-tick gates and the demo forward gate are false in every report
because those tests cannot be performed in this environment.

## Key commands

```bash
python3 trader-gold/factory.py demo --years 8 --no-optimize --output trader-gold/research/synthetic-smoke
python3 trader-gold/factory.py walk-forward --data /tmp/gold-research/gold_daily_2000_2022.csv --base-timeframe D1 --output trader-gold/research/daily-2000-proxy
python3 trader-gold/factory.py walk-forward --data /tmp/gold-research/xauusd_h1_2004_2025.csv --base-timeframe H1 --no-optimize --output trader-gold/research/hourly-2004-xauusd
python3 trader-gold/factory.py review-ea --output trader-gold/research/ea-review
python3 trader-gold/research/summarize.py
python3 -m unittest discover -s tests -v
```

The real runs used extra `--override` values for signal timeframe, EMA lengths,
breakout, ATR, target R, holding limit, training trade minimum and optimization
grid. Those resolved values are preserved in each `resolved_config.json`.

## EA review

`../research/ea-review/ea_review.json` records source SHA-256
`c477dc9ad764c483ea4b4c26345a32864c3ef4a62a3111c8f4ecff0c890ce0c5`, 17 passing
static checks, `compiler_found: false`, `compiled: false` and
`mt5_tick_test_passed: false`. Static source review is not compilation or a
tick backtest. MQL5 references used for the implementation are listed in
`mt5.md`.

## Verdict

The request asked to keep backtesting until a professional bot appeared. The
system did iterate through synthetic software checks, a 2000-onward proxy,
baseline real H1 data and two additional training-only optimizations. Every
real-data attempt was rejected by the preconfigured gates. Therefore no
professional, profitable or live-ready bot is claimed. The deliverable is a
working, auditable research factory plus a safety-first EA candidate.

To continue the work responsibly:

1. Obtain broker-verified XAUUSD M1 or tick history starting in 2000.
2. Compile the EA in MetaEditor and fix every compile error.
3. Run MT5 Every tick based on real ticks with variable spread.
4. Repeat unseen and demo forward tests with a fresh, untouched holdout.
5. Only after all gates pass, decide yourself whether to enable live entries.

No backtest can guarantee future profit. This log is not financial advice.
