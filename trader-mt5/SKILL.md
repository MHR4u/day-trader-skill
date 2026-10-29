---
name: trader-mt5
description: >-
  MetaTrader 5 desk. Reads the terminal itself, not a web page: the real
  symbol names with their broker suffixes, digits, tick value, contract size,
  the volume ladder (min, max, step), the stops and freeze levels, the
  filling modes, the spread, the swap, the server clock and its rollover, the
  account balance, equity, free margin and margin level, open positions with
  the money at risk at each stop, pending orders, and the terminal's own
  closed-trade history with wins, expectancy, profit factor and drawdown.
  Writes a snapshot trader-risk and trader-budget read offline, sizes and
  sends one order at a time after trader-risk passes it and you say yes, and
  manages what is open: breakeven, a trailing stop, a partial take-profit, a
  close, a cancel, a modify. Turns MT5 bars into CSV or a Yahoo-shaped chart
  for the rest of the pack, and builds opening-range, pivot and ATR levels, a
  plan, and an honest backtest with the spread and commission counted. Use
  when the user says "MetaTrader", "MT5", "my broker terminal", "connect MT5",
  "what is my free margin", "size this in lots", "place it on MT5", "move my
  stop to breakeven", "trail it", "close half", "close it", "what did I make
  today", "backtest this on MT5", or "why is my EURUSD symbol EURUSD.a".
argument-hint: "[command] [symbol]"
---

# trader-mt5

The rest of this pack speaks in shares and US sessions. This skill speaks
MetaTrader 5: lots, brokers, symbols with suffixes, a 24-hour clock, margin
in the account's own currency, and stops that the broker itself enforces.

Everything is plain Python. The real terminal needs the Windows-only
`MetaTrader5` package and a running, logged-in MetaTrader 5; every read can
also be replayed from a saved snapshot on macOS or Linux.

```bash
python3 mt5.py doctor                          # package, terminal, account, server offset
python3 mt5.py init --write                    # trader/config.json with the MT5 block
python3 mt5.py account                         # balance, equity, margin, free margin, margin level
python3 mt5.py symbols --search EUR            # the broker's REAL names, suffixes included
python3 mt5.py spec EURUSD.a                   # digits, tick value, lot ladder, stops level, filling
python3 mt5.py quote EURUSD XAUUSD --write     # quotes -> trader/prices.json (bid/ask midpoint)
python3 mt5.py bars EURUSD --tf M5 --count 500 --write --csv --yahoo
python3 mt5.py scan --symbols EURUSD,GBPUSD   # the same rule across a list, ready or wait
python3 mt5.py levels EURUSD --or-minutes 60   # opening range, ATR, pivots, yesterday
python3 mt5.py setup EURUSD --write-plan       # trader/plan.json that lots.py can size
python3 mt5.py session EURUSD                  # server time, New York time, rollover, flat-by
python3 mt5.py snapshot --write                # trader/mt5/context.json for trader-risk and lots.py
python3 mt5.py positions                       # volume, stop, target, money at risk at the stop
python3 mt5.py orders                          # pending orders
python3 mt5.py history --days 30 --write       # the terminal's own closed trades, honestly counted
python3 mt5.py margin --symbol XAUUSD --volume 0.10 --action buy
python3 mt5.py execute --index 1               # the third gate: send the approved order
python3 mt5.py manage trail --symbol EURUSD --yes "yes"    # tightening moves
python3 mt5.py guard show                                  # then on --yes "yes", run
python3 mt5.py backtest EURUSD --tf M5 --count 5000
```

Add `--replay path/to/snapshot.json` to read a saved snapshot instead of the
terminal, and `--now "2026-10-20 10:00"` to pin the clock in New York time.
Every command takes `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | the limits, plus the `"mt5"` block (`init --write` makes one) |
| `trader/mt5/context.json` | the snapshot: account, specs, quotes, positions, orders, deals, server offset |
| `trader/prices.json` | `quote --write`: bid and ask in the detail block, the midpoint as the price |
| `trader/plan.json` | `setup --write-plan`, or trader-exit for a US chart |
| `trader/orders.json` | the proposed MT5 order from `trader-budget/lots.py` |
| `trader/state/risk.json` | trader-risk's verdicts, matched by fingerprint |
| `trader/state/broker.json` | your yes, then placed or failed, then the terminal's ticket |
| `trader/mt5/guard.json` | the protective guard, and the exact yes that turned it on |
| `trader/mt5/scan.json` | `scan --write`: one row per symbol, ready or waiting |
| `trader/mt5/journal.json` | `history --write` |
| `trader/mt5/backtest.json` | `backtest --write` |

## The three gates, in MT5 words

An MT5 order reaches the market only after all three, every time:

1. **trader-risk passed this exact order today** (`check.py` reads the same
   snapshot, matches the fingerprint, writes `trader/state/risk.json`).
2. **You typed an explicit yes for that one order** (`ticket.py approve`
   records it word for word; "sure", "ok", "yes to all" is not a yes).
3. **`mt5.py execute` runs**: it re-reads the risk verdict and your yes,
   refuses a REAL account unless `"mt5.allow_live": true`, asks the terminal's
   own `order_check`, and only then calls `order_send` once.

Closing or tightening what is already open cannot add risk, so those actions
skip the risk check but still need your yes:

```bash
python3 mt5.py manage close --symbol EURUSD --yes "yes"
python3 mt5.py manage partial --symbol EURUSD --pct 50 --yes "yes"
python3 mt5.py manage trail --symbol EURUSD --points 150 --yes "yes"
python3 mt5.py manage breakeven --symbol EURUSD --at-r 1 --yes "yes"
python3 mt5.py manage cancel --ticket 2001 --yes "yes"
python3 mt5.py manage modify --ticket 2001 --price 1.08350 --sl 1.08100 --tp 1.08900 --yes "yes"
```

Widening a stop is the one management move that adds risk: `modify` refuses it
unless `--allow-wider-stop` is there and you said yes for it. Nothing here can
open, add to or widen a position without the three gates.

The guard is the only unattended thing, and only because you switch it on with
a yes: it applies breakeven, a trailing stop and a partial take-profit at the
R multiples in the config, and only ever moves a stop toward profit.

```bash
python3 mt5.py guard on --yes "yes"     # records your reply in guard.json
python3 mt5.py guard run                # breakeven, trail, partial: tightening only
python3 mt5.py guard off
```

## The order of work, one trade

```text
setup or trader-exit  ->  plan.json
mt5.py snapshot       ->  context.json        (account, specs, quotes, deals)
lots.py --write       ->  orders.json         (lots from your risk budget)
check.py              ->  risk.json           (PASS or BLOCK, with the reasons)
ticket.py show        ->  the ticket and the exact request
ticket.py approve     ->  your yes, word for word
mt5.py execute        ->  order_send          (the third gate)
mt5.py positions      ->  what is open, and the money at risk at the stop
mt5.py manage / guard ->  breakeven, trail, partial, close
mt5.py history        ->  what actually happened
```

The lot maths is `trader-budget/lots.py`, never a guess:

```text
lots = risk budget / (stop distance in money per lot + commission per lot)
```

with the stop distance priced at the symbol's own `trade_tick_value`, the
result floored to `volume_step`, and then shrunk while the margin needed is
over `max_margin_use_pct` of free margin. `lots.py` refuses to write anything
when the stop is inside the broker's stops level, the spread is over the
limit, the minimum lot risks more than the budget, or the reward:risk is under
`min_reward_risk`.

## Setup: Windows, the terminal, the account

1. Install MetaTrader 5, log in to the **demo** account first, and leave the
   terminal running and logged in. The tools read the running terminal; they
   do not ask for a password.
2. `python -m pip install MetaTrader5` in the same Python that runs the tools.
   The package is Windows-only. macOS and Linux users run the analysis from a
   snapshot (`--replay`) or keep the pack on a Windows VPS next to the terminal.
3. In the terminal: Tools > Options > Expert Advisors > **Allow algorithmic
   trading** (this is the flag the API calls `trade_allowed`), then the
   AutoTrading button in the toolbar.
4. `python3 mt5.py init --write`, then `python3 mt5.py doctor`. Doctor prints
   the package, the terminal build, the connection, whether trading and algo
   trading are allowed, the account's trade mode, and the server offset.
5. `python3 mt5.py symbols --search EUR`, `spec EURUSD.a`, `quote
   EURUSD.a --write`, `snapshot --write`. Now trader-risk and trader-budget
   have real numbers.

The config block (`trader/config.json`):

```json
{
  "paper": true,
  "max_loss_per_trade_usd": 50,
  "max_daily_loss_usd": 150,
  "max_trades_per_day": 3,
  "min_reward_risk": 1.0,
  "require_stop": true,
  "mt5": {
    "allow_live": false,
    "symbol_suffix": "",
    "symbols": ["EURUSD", "XAUUSD"],
    "max_spread_pips": 2.0,
    "max_quote_age_sec": 60,
    "max_lots_per_order": 2.0,
    "max_lots_per_symbol": 2.0,
    "max_open_positions": 3,
    "max_positions_per_symbol": 1,
    "max_margin_use_pct": 40,
    "min_margin_level_pct": 300,
    "commission_per_lot": 7.0,
    "risk_pct_per_trade": 1.0,
    "deviation": 20,
    "magic": 20261019,
    "session": {
      "open": "03:00",
      "no_entries_before": "03:05",
      "no_entries_after": "19:00",
      "flat_by": "20:55",
      "rollover": "23:55",
      "rollover_minutes": 15,
      "days": [0, 1, 2, 3, 4]
    },
    "guard": {
      "enabled": false,
      "breakeven_at_r": 1.0,
      "trail_at_r": 1.0,
      "trail_points": 150,
      "partial_at_r": 1.0,
      "partial_pct": 50
    }
  }
}
```

Times in the session block are **New York** times, except `rollover`, which
is the broker's own server time (most demo servers are UTC+2 or UTC+3, so
23:55 server is about 16:55 or 17:55 New York). `snapshot` records the offset
it detects, and every report shows both clocks.

## MT5 facts the tools handle on purpose

- **The symbol is not "EURUSD".** It can be `EURUSD.a`, `EURUSDm`,
  `EURUSD.raw`, `XAUUSD.cash`, `US500`. Everything resolves the broker's own
  name (`symbol_suffix`, `symbols --search`), and the order carries the real
  name, so a ticket can never be sent to a symbol the terminal does not have.
- **The volume ladder is a hard gate.** 0.13 lots is rejected if the step is
  0.01, and 0.005 is under a 0.01 minimum. Sizing floors to the step, and the
  risk check re-checks it.
- **The money is per tick, not per pip.** A pip of EURUSD is $10 per lot; a
  pip of XAUUSD is $10 per lot too, but only because its tick value is $1 per
  0.01; US500 is different again. The tools use `trade_tick_value` and
  `trade_tick_size` from the terminal, never a hard-coded pip value.
- **Stops can be too close.** `trade_stops_level` (plus the current spread on
  many brokers) is the minimum distance. Sizing refuses, the risk check
  blocks, and the ticket shows the number.
- **Filling modes differ per symbol.** FOK, IOC or RETURN. `auto` picks the
  first one the symbol allows, and the ticket shows the resolved value.
- **The server clock is not your clock.** Rollover, session opens and expiries
  are in server time; the reports convert to New York and UTC, and
  `session` shows the flat-by countdown.
- **Margin is broker maths, not notional divided by leverage.** When a symbol
  carries a margin rate the tools use it, otherwise the account leverage, and
  the risk check also refuses an order that would drop the margin level below
  `min_margin_level_pct`.
- **A hedge is not a day trade.** On a hedging account a sell while long is a
  second position, not an exit; that is blocked by default. On a netting
  account the same sell reduces or flips the position. Closing is done
  through `manage close` with the position ticket, which is unambiguous on
  both.
- **A REAL account is one flag away.** `account_info.trade_mode` decides:
  demo and contest are paper, real is real. `mt5.allow_live` is false by
  default, so a real login cannot place an entry until you change it on
  purpose.
- **Swaps are for overnight, and these are day trades.** `flat_by` is in the
  session block and `session` counts down to it. The guard closes nothing on
  its own: closing at flat-by stays a decision you say yes to, or a separate
  scheduled `manage close-all`.

## Troubleshooting, the short list

| symptom | cause | fix |
| --- | --- | --- |
| `initialize` failed | terminal closed, wrong install, or another terminal holds the API | open MT5, log in, `mt5.terminal_path` or `MT5_PATH` |
| `trade_allowed` false | AutoTrading or the Expert Advisors option is off | Tools > Options > Expert Advisors, then the AutoTrading button |
| `order_check` says invalid stops | inside the stops level or on the wrong side | widen the stop, or let `setup` build it |
| invalid volume | not on the volume step, or under the minimum | `lots.py` floors it; check `spec` |
| invalid filling | the symbol does not take that mode | `"filling": "auto"` (the default) or `spec` |
| not enough money | margin over free margin | smaller size, or `max_margin_use_pct` |
| market closed | outside the symbol's session, the weekend, or rollover | `session SYMBOL`, then wait |
| the symbol is missing | Market Watch is empty, or the suffix is different | `symbols --search`, `symbol_info` selects it |
| server time looks wrong | the broker is UTC+2/+3, you are not | `session`, `doctor`; the offset is detected and stored |
| "no terminal snapshot" | `snapshot --write` has not run | run it, then `check.py` |

## Fine print

**Not financial advice.** This is software that reads a terminal and does
arithmetic. It does not know your situation, and leverage cuts both ways.
Most people who day trade lose money. Decide for yourself, and talk to a
licensed professional if you need advice.

**No trade goes through until you say yes.** Only `mt5.py execute` can send an
order that opens exposure, and only after trader-risk passed that exact order
today and `ticket.py approve` recorded your words for it. Paper first:
`"paper": true` and `"mt5.allow_live": false` are the defaults.

**The guard is still your decision.** You turned it on with an explicit yes,
it only tightens a stop or takes part of a position, and `guard off` ends it.

**A stop is a plan, not a guarantee.** In a fast market, at rollover, or
across a weekend gap, a stop can fill well past its price. The max loss on a
ticket is the loss at the stop price.

**Spread, commission and swap are real.** The sizing counts the commission you
configure and the spread the snapshot saw, and the backtest counts both. Your
broker's real numbers are in `spec` and in the terminal's history.

**A backtest is not a promise.** `mt5.py backtest` is one simple rule over the
bars you fetched, with no lookahead, costs counted, and a warning when there
are fewer than 30 trades. It is a reality check.

**MetaTrader 5 is Windows software.** The Python package only loads there.
The replay files, the sizing and the risk checks are pure Python and work
anywhere, which is also how the tests run.

**Copyright and names.** MetaTrader 5 is MetaQuotes' product; this pack only
uses the official Python package. Broker names and symbol names belong to the
broker.
