# DayTraderMT5.mq5 - the pack as one Expert Advisor

One file. Drop it in MetaTrader 5, compile it, attach it to a chart, and the
terminal trades the rule by itself. No Python, no bridge, no terminal window
left open, nothing to type.

It is the same rule the Python desk in `trader-mt5/` checks for you: a
trend-filtered opening-range breakout with an ATR stop, a target at an R
multiple, risk-percent sizing from the symbol's own tick value, and the
broker's stops level and the spread checked before anything is sent.

```
trader-mt5/ea/DayTraderMT5.mq5     the EA (this folder)
trader-mt5/ea/CONSOLE.md           every console line and every panel field, explained
trader-mt5/ea/README.md            you are here
```

## What it does, in order

1. Waits for the first `InpORMinutes` minutes of the New York session and
   measures the high and the low of that window: the opening range.
2. On every closed bar after that, if the close is above the range high and
   the fast EMA is above the slow EMA, it buys. With `InpAllowShort` on, a
   close under the range low with the fast EMA below the slow one sells.
3. Stop: half an ATR behind the entry, but never tighter than the range mid,
   and never inside the broker's stops level plus the spread plus
   `InpStopBufferPoints`.
4. Target: `InpMinRR` times the risk.
5. Size: the risk budget (`InpRiskPercent` of equity, or `InpRiskMoney`,
   whichever is smaller) divided by what one lot loses at that stop, floored
   to the volume step, capped by `InpMaxLots` and by `InpMaxMarginPct` of free
   margin.
6. Then it manages the trade: breakeven at `InpBreakevenAtR`, a trailing stop
   after `InpTrailAtR`, an optional partial close at `InpPartialAtR`, and
   everything is closed at `InpFlatBy`.
7. Gates that stop it: one entry a day (default), a daily realised-loss stop,
   a session window, weekdays only, a spread ceiling, and never a second
   position while it already has one open.

All times are read as **New York** time (`InpNewYorkTimes = true`), with the
US daylight-saving switch handled for you. The default session is 03:05 to
19:00 with flat-by 20:55, which is the pre-market open to the closing bell and
a little past it.

## Install, in five steps

**1. Copy the file.** In MetaTrader 5: `File > Open Data Folder`, then
`MQL5 > Experts`, and copy `DayTraderMT5.mq5` in there. Or, without the
terminal: paste it into
`C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<long id>\MQL5\Experts\`.

**2. Compile it.** Open MetaEditor (F4 in the terminal), find the file in the
Navigator under `Experts`, and press **F7** (or `Compile`). The Toolbox at the
bottom should say `0 errors, 0 warnings`. If it says anything else, the error
names the line: fix that line before going on.

**3. Turn trading on.** In the terminal toolbar the **AutoTrading** button must
be green, and `Tools > Options > Expert Advisors` needs
`Allow algorithmic trading` ticked. The EA checks both and tells you in the
panel which one is missing.

**4. Attach it.** Open an **M5 chart** of the symbol you want (EURUSD, XAUUSD,
US30, whatever your broker lists), drag `DayTraderMT5` from the Navigator onto
the chart, and tick `Allow algorithmic trading` in the dialog. Inputs are in
the `Inputs` tab if you want to change anything.

**5. Watch it on a demo first.** The account type and the reason it is not
trading yet are printed on the chart and in the `Experts` tab of the Toolbox.

Start with a **demo** account. On a REAL-money account the EA refuses to trade
until you set `InpAllowLive = true`, on purpose, and it says so in the log.

## The inputs that matter

| Input | Default | What it is |
| --- | --- | --- |
| `InpAllowLive` | `false` | A REAL account needs this true. Demo is unaffected. |
| `InpDryRun` | `false` | Log the signal it would send, send nothing. Start here if you only want to watch. |
| `InpMagic` | `20261019` | Its own label on its trades. It never touches anything else. |
| `InpRiskPercent` | `1.0` | Percent of equity risked per trade. |
| `InpRiskMoney` | `50.0` | Or a fixed amount. The **smaller** of the two wins, so a small account still risks a small sum. |
| `InpMaxLots` | `2.0` | Hard cap on volume. |
| `InpMaxSpreadPoints` | `25` | Skip the entry when the spread is wider. `0` turns it off. |
| `InpMinRR` | `1.5` | Reward:risk the target is built from. |
| `InpTimeframe` | `M5` | Bar size the rule reads. It can differ from the chart you attach it to. |
| `InpUseTrend` | `true` | The EMA filter. Off means the break alone decides. |
| `InpAtrPeriod` | `14` | ATR period behind the stop. |
| `InpORMinutes` | `60` | Length of the opening range. |
| `InpAtrMult` | `0.5` | ATR multiple behind the entry for the stop. |
| `InpAllowShort` | `false` | Downside breaks too. Off by default. |
| `InpSessionStart` / `InpSessionEnd` | `03:05` / `19:00` | New York time, no entries outside. |
| `InpFlatBy` | `20:55` | Close everything of ours at this New York time. |
| `InpMaxTradesPerDay` | `1` | Entries a day. |
| `InpMaxDailyLoss` | `150` | Stop for the day after this much realised loss. `0` turns it off. |
| `InpBreakevenAtR` | `1.0` | Move the stop to the entry here. `0` is off. |
| `InpTrailAtR` | `1.0` | Start trailing here. `0` is off. |
| `InpTrailPoints` | `150` | Trail distance, in points. |
| `InpPartialAtR` / `InpPartialPercent` | `0` / `50` | Take part of the position at an R. Off by default. |
| `InpMinRangePoints` | `0` | Skip the day when the opening range is narrower than this. `0` is off. |
| `InpAlertPopup` / `InpAlertSound` / `InpAlertPush` | `true` / `false` / `false` | Alert on a fill and on a close: popup, sound, phone. |

Every input has a one-line comment next to it in MetaTrader's input dialog, so
you do not have to come back to this table.

## The dashboard: nine pages, every number one click

Attach the EA and the chart gets a dashboard. It is drawn with chart objects, so
there is nothing to install, no DLL, no file. Nine tabs, two rows (five and four).
It starts 96 pixels down, below the terminal's own buy/sell corner, so the One
Click Trading buttons stay visible; move it with `InpPanelX` / `InpPanelY`:

| page | what is on it |
| --- | --- |
| `DASH` | the day at a glance: market and the New York clock, the opening range, the EMAs, the ATR and spread, today, the open position with its R progress, the risk budget, and `Trading: yes` or `no: <the switch>` |
| `RULE` | bar size, both EMA periods, the trend filter, the ATR period, the opening-range length, the stop multiple, the range floor, the reward:risk, the short side - all clickable |
| `RISK` | risk percent or fixed amount, lot cap, margin cap, spread ceiling, daily loss stop, entries a day - plus budget, free margin, equity and spread right now |
| `CLOCK` | the New York switch, session start and end, flat-by, weekdays only - plus what time it is there and how long until flat-by |
| `MANAGE` | breakeven, trailing, partial, slippage, stop buffer, the three alert switches, and the verbose log |
| `LOG` | the last eight console lines, on the chart, and today's journal: closed trades, wins/losses, net, the last one |
| `TEST` | can it trade right now (eleven gates, PASS or NO, and the two that need a price: stops distance and margin) and the exact order it would send; one button, `RUN ORDER CHECK`, hands that order to the terminal's own `OrderCheck` so you get the broker's verdict without a single order being sent |
| `PACK` | every skill in the pack, and honestly: what lives inside this EA and what stays in the Python desk |
| `HELP` | how the panel works, what the four buttons do, and the safety lines |

**Every row with buttons is live.** `[-]` and `[+]` move a number by the step in
`trader-mt5/ea/CONSOLE.md`, `<` and `>` walk a short list (the bar size), and
`ON/OFF` flips a switch. A click is written to the terminal's global variables
(`DTMT5_C_<name>`), so changing the chart, the timeframe or restarting the
terminal keeps your tuning; `RESET` puts the inputs back.

The four buttons at the bottom:

- **PAUSE / RESUME**: no new entries. Management, breakeven, trailing and the
  flat-by close keep running.
- **DRY OFF / DRY ON**: signal-only mode, live, without touching the inputs.
- **CLOSE OUR**: two clicks within six seconds, and only on its own magic number.
- **RESET**: two clicks, and every setting goes back to the inputs.

### Proving it trades, without trading

Two questions worth asking any EA: does it phone home, and would the terminal
really take its order with a stop and a target?

- **It is offline.** No `WebRequest`, no sockets, no `URLDownloadToFile`, no
  `#import`, and one include: `<Trade\Trade.mqh>`, which ships with MetaTrader. It
  talks to your terminal, and your terminal talks to your broker. The only thing
  that can leave the machine is the optional phone push (`InpAlertPush`), which
  is off by default and goes to your own MetaQuotes ID. `tests/test_ea.py` checks
  the file for every one of those calls.
- **The TEST page proves the order.** Eleven gates listed one by one with PASS or
  NO and the reason, then the exact order it would send right now: side, lots,
  entry, stop, target, distances in points and R, and the margin. `RUN ORDER
  CHECK` sends that request through `OrderCheck()`, which validates symbol,
  volume, stops level, margin and filling mode and prices it - and sends nothing.
  You get `CHECK | ... the terminal accepted the whole order ... Nothing was sent`
  or the broker's retcode, in one line.
- **A heartbeat.** Every `InpHeartbeatMinutes` (15 by default) the log gets one
  `ALIVE` line: the symbol, the bar size, where the rule is, how many of the
  eleven gates are open, and the first closed one. On a quiet day that is your
  proof the EA is awake and watching.

### The console

Every decision is one tagged line in the Toolbox, `Experts` tab, in the shape
`time | TAG | what happened`:

```
2026.10.29 13:58:02 | CONF  | rule      : M5 bars, EMA 50/200, opening range 60 min, long only
2026.10.29 13:58:02 | CONF  | clock     : New York time, session 03:05-19:00, flat by 20:55, weekdays only
2026.10.29 13:58:02 | GATE  | trading is allowed: the terminal, the account and the broker all agree
2026.10.29 14:05:33 | SIGNAL | BUY signal: M5 closed 2394.12, above the range (2388.10 - 2393.40), trend up
2026.10.29 14:05:33 | SIZE  | 0.42 lots, stop 2387.40 (670 points, ATR 2.00 x 0.50), target 2404.20 (1.50R)
2026.10.29 14:05:33 | ORDER | accepted: order #132889001, deal #241112233 at 2394.35, 0.42 lots
2026.10.29 15:12:10 | MANAGE | #132889001: stop to the entry 2394.10 at 1.02R
2026.10.29 15:12:11 | CTRL  | setting trail_r is now 1.50
```

Fifteen tags in all (`INIT, CONF, GATE, RULE, SIGNAL, BLOCK, SIZE, RISK, ORDER,
MANAGE, FLAT, CTRL, ERROR, DAY, STOP`). A `BLOCK` line always names the single
gate that stopped the order, so "why did it not trade" is one line, not a hunt.
Every message, every panel field, every row's step and every input is in
[CONSOLE.md](CONSOLE.md).

## When nothing happens

- **`trading: no, the AutoTrading button in the toolbar is off`**: click it. It
  is the big button at the top; it has to be green.
- **`... Options > Expert Advisors > Allow algorithmic trading is off`**:
  `Tools > Options > Expert Advisors`, tick it, restart the EA.
- **`... a REAL-money account and InpAllowLive is false`**: that is the guard
  working. Use a demo account, or set the input true if you really mean it.
- **`opening range: not formed yet`**: it is before, or inside, the first
  `InpORMinutes` of the session. It also needs at least two bars in that
  window, so a chart that was just opened waits.
- **`no order: under the broker's smallest lot`**: the risk budget is too small
  for one minimum lot at this stop distance. Raise `InpRiskPercent` /
  `InpRiskMoney`, or pick a smaller-value symbol.
- **`no order: it needs X of margin, over 40% of free margin`**: lower
  `InpMaxLots`, or `InpMaxMarginPct` deliberately.
- **`invalid stops` from the broker (retcode 10016)**: some brokers quote a
  bigger stops level than the terminal reports. Raise `InpStopBufferPoints` to
  20 or 30.
- **`not sent: 10027`**: algorithmic trading is still off. Back to step 3.
- **`not sent: 10018`**: the market is closed for this symbol. Nothing to fix;
  the EA tries again on the next bar.

## What this EA is not

It does not read the news filter, the scanner, or the analyst sheet from the
rest of the pack. Those live in Python (`trader-mt5/`, `dtcli`) and stay there.
It also will not trade through a weekend, a holiday, or a closed market.

It is education and tooling, not financial advice. Most people who day trade
lose money. A stop is a plan, not a guarantee, and slippage is real.

## Pairs with

- `trader-mt5/START-HERE.md` - the Python desk, in order.
- `trader-mt5/GUIDE-urdu.md` - the same walkthrough in Urdu.
- `trader-mt5/ea/DayTraderMT5.mq5` - this EA.
- `dtcli` - the whole pack as one program:
  <https://github.com/MHR4u/day-trader-skill/releases/download/dtcli-latest/dtcli.exe>
