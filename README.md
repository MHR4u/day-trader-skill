# The Day Trader skill

12 Claude skills for day trading: scan thousands of charts, track breaking news, time every entry and exit, and replay every outcome before you risk a dollar. Plus a MetaTrader 5 desk.

Free, MIT, no signup, no API key. The tools are plain Python that read free
public data: Yahoo Finance charts, Nasdaq Trader's symbol lists, SEC EDGAR
and the House Clerk.

One scans thousands of charts for setups. Another tracks breaking news on
every stock you watch. One watches a setup bar by bar and tells you the moment
to get in, and another sets your stop and your target before you do. And the
craziest one is the Time Machine: before you risk a dollar, it replays the
rest of the session 10,000 times from the stock's own recent bars, plus every
past day the same setup fired, and tells you the honest odds.

And if your broker is MetaTrader 5, the twelfth skill reads the terminal
itself: the real symbol names and their suffixes, the tick value that decides
what a pip is worth, the broker's volume ladder and stops level, the margin in
your account's currency, the server clock and its rollover, your open
positions and the terminal's own closed-trade history. It sizes in lots,
sends one order at a time, and manages what is open (breakeven, trailing
stop, partial, close).

And no trade goes through until you say yes. Nothing in this pack can place
an order on its own. Paper trading is the default.

> **Looking for the original Trader skill?** Copy an investor's 13F, the
> stock screener, tax lots and rebalancing live in
> [github.com/Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill).
> This repo is its day-trading sequel: the Trader skill v2.

## Install

Paste this into Claude:

```
https://github.com/Jakeschincariol/day-trader-skill

install skill
```

Or as a plugin, in Claude Code:

```
/plugin marketplace add Jakeschincariol/day-trader-skill
/plugin install day-trader-skill@day-trader-skill
```

Claude Code namespaces plugin skills, so installed as a plugin they show up as
`/day-trader-skill:trader-scanner` and so on. Copy the folders instead if you want
plain `/trader-scanner`:

```bash
git clone https://github.com/Jakeschincariol/day-trader-skill.git
cp -r day-trader-skill/trader-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's
`.claude/skills/`. No Claude Code at all? Paste any single `SKILL.md` at the
top of a chat and it runs as a mode. You lose the Python tools, but the method
works.

The tools need Python 3.8 or newer. Nothing to pip install for the free-data
tools; the MetaTrader 5 desk needs the broker's own `MetaTrader5` package on
Windows (`python -m pip install MetaTrader5`). The SEC tools
(news filings, the analyst) ask you to identify yourself: put your name and
email in `trader/config.json` (`"sec_user_agent": "Your Name you@example.com"`)
or in the `SEC_USER_AGENT` environment variable.

## The twelve

| command | job | what it does |
| --- | --- | --- |
| `/trader-scanner` | Chart Scanner | Scans thousands of charts for setups: opening-range breakouts, flags, oversold bounces. |
| `/trader-news` | News Monitor | Tracks breaking news on every stock you watch and flags what moves it. |
| `/trader-entry` | Entry Timer | Watches a setup bar by bar and tells you the moment to get in. |
| `/trader-exit` | Exit Planner | Sets your stop and your target before you enter, so you know when to get out. |
| `/trader-timemachine` | Time Machine | Replays every possible outcome of a trade before you risk a dollar: 10,000 simulated sessions plus every past time the setup fired. |
| `/trader-risk` | Risk Manager | Checks every trade against your limits and stops anything over them. |
| `/trader-budget` | Budget Manager | Sizes every position to your budget and your max loss per trade. |
| `/trader-broker` | Order Executor | Sends approved orders to your broker, paper trading by default, never without your yes. |
| `/trader-alerts` | Price Alerts | Rings when a price, a stop or the opening bell hits. |
| `/trader-analyst` | Earnings Analyst | Reads earnings reports and sums up what changed. |
| `/trader-pelosi` | Pelosi Tracker | Reads Congress's stock-trade disclosures the minute they are filed. |
| `/trader-mt5` | MT5 Desk | Reads your MetaTrader 5 terminal, sizes in lots, sends approved orders, manages the stops, journals the history. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by the close                                       (while it is open)
news / analyst / pelosi                                                        (on a schedule)
mt5: setup -> snapshot -> lots -> risk -> ticket -> execute -> manage -> history (one MT5 trade)
```

An example, the trade in the reel: Tesla, Monday October 19 2026, real data.

1. **`/trader-scanner`** at 10:15 AM ET: of the 231 charts in the reel's
   scan, 42 had closed above their 15-minute opening range. TSLA is one: range 354.47 to 362.18,
   the 10:10 candle closed at 364.18, 0.55 % over the top.
2. **`/trader-news`**: the morning's TSLA headlines, in New York time
   ("Tesla-SpaceX Merger Mania Strikes Wall Street Ahead of Earnings", 8:04,
   tagged earnings and deal). Tesla reports this week: a day trade is out
   before the close, so it is not exposed to the report.
3. **`/trader-entry`** watched TSLA bar by bar. At 10:12 it said waiting (the
   10:10 bar was still forming). At 10:15 it said triggered: the first
   5-minute close above the range, 364.18.
4. **`/trader-exit`** set the plan before the entry: stop at the range's
   midpoint, 358.32, so 5.86 a share at risk; target one times that risk,
   370.04; flat by 3:55 PM either way.
5. **`/trader-timemachine`** replayed the rest of the day 10,000 times, each
   5-minute candle drawn from TSLA's own candles at that time of day over the
   previous 59 sessions (seed 19, so anyone can repeat it): target first
   29.4 %, stop first 25.5 %, still open at the close 45.1 %. It also re-ran
   the same rule on those 59 real sessions: it fired 33 times, 13 hit the
   target, 15 the stop, 5 neither. Its verdict: close to a coin flip. That is
   the point of looking before you risk a dollar.
6. **`/trader-budget`** with a $5,000 account and a $50 max loss per trade:
   50 / 5.86 = 8 shares ($2,913.44). If the stop fills at 358.32, the loss is
   $46.88. It writes one bracket order: buy 8 TSLA, stop-loss 358.32,
   take-profit 370.04.
7. **`/trader-risk`** checks it against your limits: the max loss, the daily
   loss limit, trades per day, reward to risk, the entry window, position
   size and cash. PASS or BLOCK, with the reason.
8. **`/trader-broker`** shows you the ticket in plain words. You type yes for
   that exact order. Claude calls your brokerage connector (Alpaca's MCP
   server, paper account by default), and Claude's own "Allow once / Deny"
   card asks you one more time.
9. **`/trader-alerts`** rings on the stop, the target and at 3:55 PM to
   flatten whatever is still open.

### On MetaTrader 5

The MT5 desk replaces the share-based middle of that chain with the terminal's
own numbers, and it keeps the same rule: nothing opens without a PASS, your
yes, and the terminal.

```bash
python3 trader-mt5/mt5.py doctor                        # package, terminal, account, server clock
python3 trader-mt5/mt5.py init --write                  # a config with the "mt5" block
python3 trader-mt5/mt5.py symbols --search EUR          # the broker's real names (EURUSD.a ...)
python3 trader-mt5/mt5.py spec EURUSD.a                 # digits, tick value, lot ladder, stops level
python3 trader-mt5/mt5.py session EURUSD               # server time, rollover, flat-by countdown
python3 trader-mt5/mt5.py snapshot --write             # -> trader/mt5/context.json
python3 trader-mt5/mt5.py scan --symbols EURUSD,GBPUSD --tf M15   # which one is set up today?
python3 trader-mt5/mt5.py setup EURUSD --write-plan    # -> trader/plan.json from the chart
python3 trader-budget/lots.py --write                   # -> trader/orders.json, in lots
python3 trader-risk/check.py                            # PASS or BLOCK, MT5 rules
python3 trader-broker/ticket.py show                    # the ticket and the exact order_send JSON
python3 trader-broker/ticket.py approve --index 1 --reply "yes"
python3 trader-mt5/mt5.py execute --index 1             # the third gate
python3 trader-mt5/mt5.py positions                     # what is open, risk at each stop
python3 trader-mt5/mt5.py manage breakeven --symbol EURUSD --at-r 1 --yes "yes"
python3 trader-mt5/mt5.py manage trail --symbol EURUSD --points 150 --yes "yes"
python3 trader-mt5/mt5.py guard on --yes "yes" && python3 trader-mt5/mt5.py guard run
python3 trader-mt5/mt5.py history --days 30 --write     # the terminal's own results, honestly counted
```

`mt5.py quote --write` puts MT5 bid/ask into `trader/prices.json`, so
trader-alerts and trader-risk read MT5 quotes with no changes. `mt5.py bars
--yahoo` exports the bars as a Yahoo-shaped chart on a UTC clock, so the
scanner, the entry timer, the exit planner and the time machine can read them
with `--offline`. Those tools still think in the 09:30 to 16:00 New York
session, so outside those hours work from `mt5.py levels`, `mt5.py setup` and
`mt5.py backtest`. The MT5 session is 24 hours, so use `mt5.py session` and
the `mt5.session` block for the entry window and flat-by time instead of the
NYSE clock.

The full MT5 walkthrough, every flag, the symbol-suffix and filling-mode
traps, and the troubleshooting table are in `trader-mt5/SKILL.md`.

### One program for all of it: dtcli

The twelve tools also come as one command, and one Windows executable with no
Python to install: `dtcli` finds the tool you name and hands it your arguments,
so the output and the exit codes are the tool's own.

```bash
python3 trader-mt5/dtcli.py list              # the thirteen tools
python3 trader-mt5/dtcli.py mt5 doctor
python3 trader-mt5/dtcli.py lots --write && python3 trader-mt5/dtcli.py risk
```

```bat
dtcli.exe mt5 --replay snapshot.json --now "2026-10-20 09:35" account
```

The exe is built by the `build-exe` workflow and published here:
[dtcli.exe](https://github.com/MHR4u/day-trader-skill/releases/download/dtcli-latest/dtcli.exe),
or build it yourself on Windows with `trader-mt5\build-exe.bat`. The three
ways, and what is inside the binary, are in `trader-mt5/BUILD-EXE.md`.

## The tools

All standard-library Python except the MT5 bridge, which uses the broker's own
Windows package. The data tools read public endpoints and are
polite about it.

```bash
python3 trader-scanner/scan.py universe                                # ~5,900 US stocks, Nasdaq Trader
python3 trader-scanner/scan.py daily                                   # pre-market setups, whole universe
python3 trader-scanner/scan.py orb --at 10:15                          # opening-range breakouts so far
python3 trader-news/news.py --tickers TSLA --hours 12                  # headlines, 8-Ks, today's move
python3 trader-entry/entry.py check TSLA --setup orb                   # waiting / triggered / expired
python3 trader-entry/entry.py watch TSLA --every 30                    # bar by bar until it triggers
python3 trader-exit/exit.py plan --stop or-mid --target 1R --write     # -> trader/plan.json
python3 trader-timemachine/timemachine.py run --write                  # 10,000 replays + the history
python3 trader-budget/size.py --write                                  # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # the tickets, READY or not
python3 trader-alerts/alerts.py add --from-plan                        # stop, target, flat by close
python3 trader-alerts/alerts.py check                                  # rings what hit, once
python3 trader-analyst/facts.py TSLA                                   # quarters, growth, EPS
python3 trader-pelosi/ptr.py index --member pelosi                     # her PTRs this year

# MetaTrader 5 (Windows for the real terminal; --replay reads a saved snapshot anywhere)
python3 trader-mt5/mt5.py doctor                                      # is the terminal usable?
python3 trader-mt5/mt5.py snapshot --write                            # -> trader/mt5/context.json
python3 trader-mt5/mt5.py spec EURUSD.a                               # the broker's own numbers
python3 trader-mt5/mt5.py quote EURUSD XAUUSD --write                 # -> trader/prices.json
python3 trader-mt5/mt5.py scan --symbols EURUSD,GBPUSD --tf M15       # the same rule across a list
python3 trader-mt5/mt5.py levels EURUSD --or-minutes 60                # range, ATR, pivots, yesterday
python3 trader-mt5/mt5.py setup EURUSD --write-plan                    # -> trader/plan.json
python3 trader-budget/lots.py --write                                  # -> trader/orders.json (lots)
python3 trader-risk/check.py --mt5-context trader/mt5/context.json     # PASS / BLOCK
python3 trader-mt5/mt5.py execute --index 1                            # after your recorded yes
python3 trader-mt5/mt5.py manage close --symbol EURUSD --yes "yes"     # getting out
python3 trader-mt5/mt5.py backtest EURUSD --tf M5 --count 5000         # one rule, costs counted
python3 trader-mt5/mt5.py history --days 30 --write                    # your realised history
```

```bash
python3 -m unittest discover -s tests -v
```

The MT5 tests run offline too: a synthetic demo server at GMT+3, three symbol
specs (EURUSD, XAUUSD, US500) with their real lot ladders and tick values, two
days of 5-minute bars, quotes and today's closed deals. They check the server
clock, the lot maths, every risk rule, the ticket, and the whole
PASS -> yes -> execute path, with the terminal replayed from a file.

The equity tests run offline, on fixtures cut from real data: TSLA's 5-minute bars
for the 60 days to October 19 2026, the 10:15 AM opening-range scan, Yahoo's
TSLA headlines that morning, the House Clerk's 2026 index, real PTR text and
real XBRL facts. They reproduce every number in the example above.

## Fine print

**MetaTrader 5 is Windows software.** The official `MetaTrader5` Python
package only loads on Windows, next to a running, logged-in terminal
(`python -m pip install MetaTrader5`). On macOS or Linux, every read can be
replayed from a snapshot with `--replay`, and the sizing and the risk checks
are pure Python. The tools never ask for your broker password: they read the
terminal you are already logged in to.

**Not financial advice.** This is software that reads public data and does
arithmetic. It does not know your situation and it cannot see the future.
Most people who day trade lose money. You can lose money. Decide for
yourself, and talk to a licensed professional if you need advice.

**No trade goes through until you say yes.** Only `/trader-broker` can lead to
an order, and only after `/trader-risk` passes that exact order and you type
yes for it in the chat. Set your brokerage tool to "Needs approval" in Claude
(Customize, Connectors, tool permissions), never "Always allow", so Claude's
own "Allow once / Deny" card is a second check. No options, margin, short
selling or leverage unless you turn them on.

**Paper first.** `"paper": true` is the default in `config.example.json`, and
Alpaca's MCP server defaults to its paper account. Keys live in environment
variables, never in the chat. On MT5, `"mt5.allow_live": false` is the
default, so a REAL account cannot place an entry until you change it on
purpose; demo and contest accounts are paper and work as they are.

**The Time Machine is a simulation, not a prediction.** It is built from the
stock's own last 60 days of 5-minute bars. The future can do things those 60
days never did: an earnings report, a halt, a headline. Treat its odds as a
reality check, never as a promise.

**The MT5 guard is still your decision.** You switch it on with an explicit
yes, it can only move a stop toward profit or take part of a position, and
`mt5.py guard off` ends it. It cannot open, add to or widen anything.

**A stop is a plan, not a guarantee.** In a fast market or across a gap, a
stop order can fill well past its price. The max loss shown is the loss at
the stop price.

**The MT5 data is the broker's own.** Spreads, swaps, sessions, stops levels
and filling modes are whatever your broker sets, and a demo server can differ
from the live one. `mt5.py spec` and `mt5.py session` show the numbers that
are in force right now. A backtest over the bars you fetched is a reality
check, not a promise.

**The data is free and unofficial.** Yahoo Finance's chart endpoint is not an
official API: it can lag, change or rate-limit you. The scanner and the entry
timer read 1-minute or 5-minute bars, not every tick. Check anything that
matters against your broker before you act on it.

**Day-trading rules.** FINRA removed the $25,000 pattern-day-trader minimum
on June 4, 2026 (Regulatory Notice 26-10), and brokers may phase the change
in until October 20, 2027, so yours may still apply the old rule. If it does,
set `"pdt_guard": true` and `/trader-risk` counts your day trades.

**Congress's trades are public, not inside information.** Members must disclose
trades over $1,000 within 45 days (the STOCK Act). The Pelosi skill reads those
public filings the minute they post.

**Taxes.** Day-trading gains are short-term gains, and frequent trading makes
wash sales likely. Nothing here is tax advice.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-risk/        SKILL.md, check.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-broker/      SKILL.md, ticket.py, claude_desktop_config.example.json
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-analyst/     SKILL.md, facts.py, metrics.example.json
trader-pelosi/      SKILL.md, ptr.py
trader-mt5/         SKILL.md, mt5.py, mt5lib.py, mt5rules.py
                    (budget/lots.py sits next to size.py in trader-budget/)
tests/              unittest suite + offline fixtures
```

MIT. Made by [Jake Schincariol](https://opusjake.ai).
