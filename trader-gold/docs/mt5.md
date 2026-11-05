# MT5 Expert Advisor

`mt5/GoldProfessionalEA.mq5` is a research EA, not a compiled or certified
product. It must be opened in MetaEditor, compiled, tested on broker real ticks
and forwarded on demo before anyone considers live entries.

## Compile

1. Copy `GoldProfessionalEA.mq5` into `MQL5/Experts/` in the MetaTrader 5 data
   folder.
2. Open MetaEditor and compile. Resolve every error and warning that affects
   execution.
3. Load `GoldProfessionalEA.research.set` from a factory run. It contains
   `InpEnableNewEntries=false`.
4. Attach the EA to an XAUUSD chart. Keep `InpRequireGoldSymbol=true` unless
   your broker uses a non-XAU Gold symbol name.
5. Confirm Algo Trading, terminal trading, account trading and expert trading
   permissions are enabled in the tester or demo terminal.

A static source review in `ea_review.json` is not compilation. The factory
reports `compiled: false` and `mt5_tick_test_passed: false` on every run.

## Timeframes

The generated set file uses `PERIOD_CURRENT` for both signal and trend inputs.
The signal timeframe is the chart timeframe. `AutoTrend()` maps every MT5
standard timeframe from M1 to MN1 to a completed higher timeframe. OnInit
rejects a manually selected trend timeframe that is lower than the signal
timeframe.

To trade several timeframes at the same time, attach separate EA instances on
separate charts with different magic numbers and separate set files. One chart
instance evaluates one signal timeframe.

## Entry logic

`EvaluateEntry()` runs once per newly closed signal bar. It requires indicator
buffers calculated with `BarsCalculated`, a completed trend bar, ATR within the
configured percentage bounds, a closed-bar Donchian breakout, EMA regime
agreement, a tradable symbol mode, a clear spread, a clear news window, a clear
cooldown and an acceptable account protection state.

`CopyRates` starts at shift 1, so the forming bar is never used. Indicator
`CopyBuffer` also starts at shift 1. `lastSignalBar` prevents repeated entries
on the same bar and prevents a stale entry immediately after attachment.
Reference: https://www.mql5.com/en/docs/series/copybuffer

## Sizing and bracket

`OrderCalcProfit` estimates one-lot risk in account currency. `OrderCalcMargin`
checks free margin. Volume is rounded down to broker min, max and step. Entry,
stop and target prices account for spread and broker stops level. Every order
is checked with `ResultRetcode()` after the CTrade call, because a successful
CTrade structure check is not a server execution guarantee.
Reference: https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade/ctradepositionmodify

Hard SL and TP are sent with the entry. Stops and targets are later modified
only with `PositionModify` by ticket, with retcode, stops level and freeze
level checks. Reference: https://www.mql5.com/en/docs/trading/ordercalcprofit

## Profit management

- Partial close uses `PositionClosePartial` on hedging accounts. Netting and
  exchange accounts use a strictly smaller opposite market deal instead.
- Break-even moves the stop only after the configured R trigger, with a small
  offset to cover costs.
- ATR trailing uses the completed ATR buffer and only tightens the stop.
- Per-position initial risk, volume and partial state are stored in terminal
  global variables. After a restart without saved state, the EA uses deal
  history and disables R-based management rather than inventing a target.

## Protection

`UpdateProtection()` tracks day, week and peak equity. It uses deal history for
profit, swap, commission and fee. Daily and weekly locks reset on a new period.
The total drawdown lock is persistent and can be cleared only by setting
`InpResetProtectionLocks=true` for one initialization, then setting it back to
false.

Other guards are maximum trades per day, cooldown bars, maximum holding bars,
Friday close, optional session window, optional day-end close, maximum spread,
foreign-position isolation, magic-number isolation and trading permissions.

## News filter

`NewsClear()` uses `CalendarValueHistory` and `CalendarEventById` to find
high-impact USD events around the current time. If the calendar call fails and
`InpNewsFailClosed=true`, entries are blocked. In the tester, an enabled news
filter causes OnInit to fail unless `InpAllowTesterWithoutNews=true`. This
prevents a silent news-free backtest from being reported as if the filter had
been applied. The generated set file leaves the filter off for research.

## Tester and custom criterion

Use "Every tick based on real ticks" with variable spread and broker-specific
symbol settings. "Open prices only" and "1 minute OHLC" cannot validate
intrabar stop and target behavior. Reference:
https://www.mql5.com/en/docs/runtime/testing

`OnTester()` returns a custom score from trades, profit, profit factor and
relative equity drawdown using `TesterStatistics`. It is an optimization
criterion, not a live-readiness verdict. References:
https://www.mql5.com/en/docs/common/testerstatistics and
https://www.mql5.com/en/docs/event_handlers/ontester

## Required validation checklist

1. Compile with zero errors.
2. Confirm symbol contract size, tick size, tick value, digits, stops level,
   freeze level, volume limits, margin mode and commission.
3. Run real-tick tests with variable spread on an in-sample period.
4. Repeat on a separate out-of-sample period and with stressed costs.
5. Compare Python and MT5 trade lists; investigate every material difference.
6. Forward test on demo for multiple weeks across different volatility and
   news regimes.
7. Inspect logs for retcodes, skipped entries, partial-close behavior and
   recovery after terminal restart.
8. Only then decide whether to set `InpEnableNewEntries=true`.

No step in this document guarantees profit. A stop can gap, news can move
price faster than an EA can react, and broker execution can differ from both
Python bars and tester ticks.
