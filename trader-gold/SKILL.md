---
name: trader-gold
description: Research XAUUSD Gold from 2000 onward with a six-agent Python pipeline and generate a MetaTrader 5 Expert Advisor for every chart timeframe. Includes closed-bar Donchian entries, completed higher-timeframe EMA regime filtering, ATR stops, R targets, broker-aware sizing, hard SL/TP, partial profit booking, break-even, ATR trailing, account/session/news guards, rolling walk-forward, cost stress tests, data provenance and explicit MT5 validation gates. The tool never places a live order, never guarantees profit, is not financial advice, and requires your yes before any later deployment.
---

# Gold EA Research Factory

This skill builds a repeatable research system for XAUUSD. It does not sell a
signal and it does not promise a winning bot. It turns a price history CSV into
an auditable report and a safety-first MQL5 Expert Advisor.

Not financial advice. A backtest, even a walk-forward backtest, cannot certify
that a strategy will make money in the future. The generated EA keeps live new
entries OFF by default. You must say yes only after your own MT5 compilation,
real-tick testing and demo forward test.

Roman Urdu note: Ye tool research aur testing ke liye hai. Live trade tabhi
sochna jab aap khud MetaEditor mein compile karein, real ticks par MT5 test
karein, demo forward test dekhein aur phir apni marzi se entries enable karein.
Profit ki koi guarantee nahi hai.

## Multi-agent pipeline

1. **Risk Agent** validates account, execution and limit assumptions before any
   bar is processed. It rejects zero or negative sizing inputs, impossible
   loss limits, invalid session hours and unsupported optimization fields.
2. **Data Agent** reads MT4/MT5 or ordinary OHLC CSV, normalizes headers,
   handles timezone offsets, detects duplicate timestamps and large gaps,
   records SHA-256 provenance, and applies the 2000 coverage gate.
3. **Strategy Agent** freezes the allowed optimization grid. Only Donchian
   lookback, EMA lengths, ATR period, ATR stop multiple and R target may be
   searched. Martingale, grid and unbounded multipliers are not available.
4. **Backtest Agent** runs a conservative Bid-bar engine. Long entries pay the
   Ask, short entries receive the Bid, long exits use the Bid, short exits pay
   the Ask, stops fill with adverse slippage or gaps, and a bar touching both
   stop and target is resolved stop-first.
5. **Validation Agent** runs rolling fixed-length walk-forward windows. Each
   fold selects parameters on training data only, tests once on the following
   unseen window, then repeats with stressed spread, slippage and commission.
6. **EA Review Agent** performs static source checks, records the source hash,
   and writes a `.set` file. Static review is not compilation, not a tick test
   and not live approval.

## Quick start

```bash
python3 trader-gold/factory.py demo --years 8 --no-optimize --output /tmp/gold-demo
python3 trader-gold/factory.py review-ea --output /tmp/gold-review
```

The demo uses deterministic synthetic bars. Its status is always
`SYNTHETIC_ONLY`, no matter how attractive the numbers look.

For a real CSV:

```bash
python3 trader-gold/factory.py walk-forward \
  --data XAUUSD_H1.csv \
  --base-timeframe H1 \
  --source-url https://example.com/provider \
  --source-description "Broker XAUUSD H1 Bid OHLC, UTC, variable spread" \
  --output /tmp/gold-wf
```

Use `backtest` instead of `walk-forward` for a single descriptive run. A single
run has no unseen-data gate and can never be called out-of-sample validation.

## Input data

Accepted headers include `datetime`, `date` plus `time`, `timestamp`, `<DATE>`
plus `<TIME>`, and the OHLC columns `open`, `high`, `low`, `close`. Optional
columns are `volume`, `tick_volume`, `spread`, `spread_points` and
`spread_price`. Comma, semicolon, tab and gzip CSV files are supported.

Prices are assumed to be Bid OHLC. Spread is added separately, never silently
treated as zero. Set `data.timezone_offset_hours` to convert broker-local
timestamps to UTC. Set `data.spread_column_unit` to `points` or `price`.

The coverage gate requires data starting in the first week of the configured
`validation.require_data_since`, which defaults to `2000-01-01`. A 2004 start
fails that gate and forces `RESEARCH_ONLY`. A daily Gold proxy from 2000 is not
the same as verified broker spot XAUUSD; label the instrument honestly.

## Every timeframe

`strategy.signal_timeframe` can be any of M1, M2, M3, M4, M5, M6, M10, M12,
M15, M20, M30, H1, H2, H3, H4, H6, H8, H12, D1, W1 or MN1. With
`trend_timeframe: "AUTO"`, the completed higher timeframe is selected
automatically. With `trend_timeframe: "CURRENT"`, the signal timeframe itself
is used. A higher timeframe bar is usable only after it closes.

The EA uses `PERIOD_CURRENT` in the generated `.set` file, so one instance runs
on whatever chart timeframe you attach it to. To cover several timeframes at
once, attach separate instances with different magic numbers and separate set
files. Do not assume one chart can simultaneously read all timeframes as signal
bars.

## EA features

- Closed-bar Donchian breakout with completed higher-timeframe EMA regime.
- Wilder ATR volatility filter and ATR-based initial stop.
- Automatic hard SL and TP on every new position.
- `OrderCalcProfit` and `OrderCalcMargin` for broker-aware risk sizing.
- Server retcode checks after entries, modifications and exits.
- Broker volume min, max, step, stops level, freeze level and margin checks.
- Partial profit booking, break-even and ATR trailing.
- Hedging partial close and a netting-mode opposite-deal fallback.
- Daily, weekly and persistent total drawdown locks.
- Trade count, cooldown, maximum holding time, Friday cut and spread filter.
- Optional USD high-impact calendar blackout with fail-closed error handling.
- Magic-number isolation and recoverable per-position R state.
- `OnTester` custom optimization score, not a live-readiness verdict.

## Output artifacts

Each run writes `report.json`, `summary.md`, `trades.csv`, `equity.csv`,
`data_provenance.json`, `resolved_config.json` and
`GoldProfessionalEA.research.set`. The set file always contains
`InpEnableNewEntries=false`.

Status meanings:

- `SYNTHETIC_ONLY`: software test on generated bars, never market evidence.
- `RESEARCH_ONLY`: real or proxy data failed at least one gate.
- `PAPER_CANDIDATE`: all Python gates passed, still not MT5 validated.

Every report keeps `deployment_status: "MT5_VALIDATION_REQUIRED"`.

## Required before live use

1. Compile `mt5/GoldProfessionalEA.mq5` in MetaEditor and fix all errors.
2. Export broker-specific XAUUSD real ticks with variable spread.
3. Run MT5 Every tick based on real ticks, not Open prices only.
4. Repeat out-of-sample and demo forward tests on a separate period.
5. Inspect swaps, contract size, commission, stop levels and slippage.
6. Only then decide, yourself, whether to enable new entries.

## Files

```text
trader-gold/factory.py                 CLI and artifact writer
trader-gold/config.example.json        conservative research defaults
trader-gold/gold/models.py             shared data structures
trader-gold/gold/data.py               CSV, resampling, synthetic bars
trader-gold/gold/strategy.py           causal indicators and signals
trader-gold/gold/backtest.py           cost-aware Bid-bar engine
trader-gold/gold/agents.py             six specialist agents
trader-gold/mt5/GoldProfessionalEA.mq5 MQL5 Expert Advisor
trader-gold/docs/                      architecture, data, MT5 and research notes
```

## Fine print

No Python bar backtest reproduces MT5 tick execution, swaps, broker contract
changes, news blackout behavior or actual slippage. Calendar history is not
reproduced by the CSV engine and a tester run with the news filter enabled is
refused unless you explicitly allow a news-free test. A stop is a plan, not a
guarantee. Most retail traders lose money. Decide for yourself and consult a
licensed professional if you need advice.
