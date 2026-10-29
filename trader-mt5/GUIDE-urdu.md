# MetaTrader 5 par day-trader-skill: mukammal guide (Urdu / Hinglish)

Ye guide batata hai ke pack ab MT5 par kaise chalta hai: data, scanner, entry/exit, sizing,
risk, order, position management, alerts, history aur backtest. Har command asli output ke
sath diya gaya hai (numbers demo fixture se hain, taake aap compare kar sakein).

---

## 1. Ek nazar mein: kya kya bana

| hissa | file | kaam |
| --- | --- | --- |
| naya 12th skill | `trader-mt5/SKILL.md`, `mt5.py`, `mt5lib.py`, `mt5rules.py` | terminal padhna, snapshot, scan, setup, execute, manage, guard, backtest |
| lot sizing | `trader-budget/lots.py` | risk budget se lots, margin/step/stops level ka khayal |
| risk rules | `trader-risk/check.py` (MT5 half) | MT5 order par PASS/BLOCK, alag rules |
| ticket | `trader-broker/ticket.py` | MT5 ticket, exact `order_send` JSON, aap ka "yes" |
| alerts | `trader-alerts/alerts.py` | `mt5.py quote --write` se MT5 bid/ask |
| docs | `README.md`, 8 skills ke SKILL.md | MT5 notes, commands, fine print |
| tests | `tests/test_mt5.py` + fixtures | 391 tests, sab offline |

Kuch bhi order **khud se** nahi jata: risk PASS + aap ka saaf "yes" + terminal, teenon lazmi.

---

## 2. Pehli baar setup (Windows)

1. MetaTrader 5 install karein, **demo** account se login karein, terminal khula chhorein.
2. Terminal mein: `Tools > Options > Expert Advisors > Allow algorithmic trading` ON,
   aur toolbar ka **AutoTrading** button ON.
3. Wahi Python jo tools chalata hai us mein:
   ```bash
   python -m pip install MetaTrader5
   ```
   Ye package sirf Windows par chalta hai (macOS/Linux ke liye neeche "Bina Windows" dekhein).
4. Project folder mein:
   ```bash
   python3 trader-mt5/mt5.py doctor
   python3 trader-mt5/mt5.py init --write          # trader/config.json + "mt5" block
   python3 trader-mt5/mt5.py symbols --search EUR  # broker ke asli naam: EURUSD.a, EURUSDm ...
   python3 trader-mt5/mt5.py spec EURUSD.a         # digits, tick value, lot ladder, stops level
   ```
5. `trader/config.json` mein apne broker ke hisaab se:
   - `"mt5": {"commission_per_lot": 7.0, ...}` apni commission (round turn) daalein,
   - `"mt5": {"symbols": ["EURUSD.a", "XAUUSD"]}` watchlist,
   - `"mt5": {"allow_live": false}` chhor dein jab tak demo par tassalli na ho,
   - `max_loss_per_trade_usd` (default 50), `max_daily_loss_usd` (150), `min_reward_risk` (1.0).

`doctor` ka sample output:
```
account: 5001234 DEMO on Broker-Demo, balance 5000 USD
server offset: UTC+3 (detected from a tick)
account trading allowed: True, algo trading: True
```

---

## 3. Aik trade ka poora safar

```bash
# 1) kis symbol mein aaj setup hai
python3 trader-mt5/mt5.py scan --symbols EURUSD,XAUUSD,GBPUSD --tf M15
#   SCAN M15: 1 ready, 0 waiting, 2 unknown
#     EURUSD     READY BUY  entry 1.08604 stop 1.08556 target 1.08676
#   (jo symbol terminal mein nahi ya bars kam hain, woh "unknown" row banta hai)

# 2) plan + snapshot (dono file ban jati hain)
python3 trader-mt5/mt5.py setup EURUSD --tf M15 --write-plan   # -> trader/plan.json
python3 trader-mt5/mt5.py snapshot --write                     # -> trader/mt5/context.json

# 3) lots (shares nahi, lots)
python3 trader-budget/lots.py --write
#   SIZE BUY 0.9 lots of EURUSD (market order)
#   entry 1.08604 (the ask), stop 1.08556, target 1.08676
#   4.8 pips of risk, $55.00 per lot: $49.50 at risk (0.99% of $5,012.40)
#   margin $977.44 (leverage 1:100), 19.5% of free margin

# 4) risk check (MT5 rules)
python3 trader-risk/check.py --mt5-context trader/mt5/context.json
#   PASS  #1 buy EURUSD 0.9 lots, entry ... MT5 DEMO account 5001234 ...

# 5) ticket: exact JSON jo bhejne wala hai
python3 trader-broker/ticket.py show
python3 trader-broker/ticket.py approve --index 1 --reply "yes"

# 6) teesra darwaza: asli send
python3 trader-mt5/mt5.py execute --index 1
#   SENT: BUY 0.9 lots of EURUSD, ticket 3001, deal 5001, fill 1.08604 (done).

# 7) manage (sab "tightening" - risk kam, barhta nahi)
python3 trader-mt5/mt5.py positions
python3 trader-mt5/mt5.py manage breakeven --symbol EURUSD --at-r 1 --yes "yes"
python3 trader-mt5/mt5.py manage trail --symbol EURUSD --points 150 --yes "yes"
python3 trader-mt5/mt5.py manage partial --symbol EURUSD --pct 50 --yes "yes"
python3 trader-mt5/mt5.py manage close --symbol EURUSD --yes "yes"

# 8) guard: ek dafa "yes" se ON, phir khud tightening
python3 trader-mt5/mt5.py guard on --yes "yes"
python3 trader-mt5/mt5.py guard run
#   #1001 EURUSD: stop 1.08300 -> 1.08600 at 1.25R: done
#   Guard run: 1 action(s), 1 position(s) left alone. Tightening only; nothing was opened.

# 9) hisaab
python3 trader-mt5/mt5.py history --days 30 --write
#   Closed trades 2: 1 wins, 1 losses (50% win rate)
#   Net -$17.10, profit factor 0.59, max drawdown $41.40
```

Pending order bhi isi chain se jata hai:
```bash
# buy limit: price entry se neeche, stop us se bhi neeche (plan ke mutabiq)
python3 trader-budget/lots.py --type buy_limit --price 1.08200 --time day --write
python3 trader-risk/check.py && python3 trader-broker/ticket.py show
python3 trader-broker/ticket.py approve --index 1 --reply "yes"
python3 trader-mt5/mt5.py execute --index 1
#   PLACED: BUY LIMIT ... lots of EURUSD at 1.082, ticket 2002 (done)
#   (pending order fill nahi hota: broker us price ka intezaar karta hai, SL/TP sath jate hain)
```

---

## 4. Har command, ek line mein

| command | kaam |
| --- | --- |
| `doctor` | package, terminal, account, server offset |
| `init --write` | `trader/config.json` + `mt5` block |
| `account` | balance, equity, margin, free margin, margin level |
| `symbols --search EUR` | broker ke asli naam aur suffix |
| `spec EURUSD.a` | digits, point, pip, tick value, contract, lot ladder, stops level, filling, swap, margin |
| `quote EURUSD XAUUSD --write` | bid/ask, aur `trader/prices.json` (alerts/risk ke liye) |
| `bars EURUSD --tf M5 --count 500 --write --csv --yahoo` | bars JSON/CSV/Yahoo-shape |
| `scan --symbols ... --tf M15` | ek hi rule poore list par: ready ya wait |
| `levels EURUSD --or-minutes 60` | opening range, ATR, pivots, kal ka high/low |
| `setup EURUSD --write-plan` | plan: trend + range + ATR stop + R target |
| `session EURUSD` | server time, New York time, rollover, flat-by countdown |
| `snapshot --write` | account/specs/quotes/positions/orders/deals ek file mein |
| `positions` / `orders` | khuli position aur pending order, stop par risk ke sath |
| `history --days 30 --write` | terminal ki apni closed history + journal |
| `margin --symbol XAUUSD --volume 0.10` | margin aur profit calculation |
| `execute --index N` | sirf PASS + yes + terminal ke baad send |
| `manage close/partial/trail/breakeven/modify/cancel[/-all]` | position/order management |
| `guard on/off/show/run` | pre-authorized protective automation |
| `backtest EURUSD --tf M5 --count 5000` | ek rule, costs ke sath, no lookahead |

---

## 5. Paisa aur risk ka hisaab (formula)

```
har lot ka stop-risk = stop distance / tick_size x tick_value
commission          = lots x commission_per_lot
risk budget         = min(max_loss_per_trade_usd, risk_pct x equity)
lots                = floor((budget / (per-lot risk + commission)) / volume_step) x volume_step
```

Phir: `max_lots_per_order`, `max_margin_use_pct` (free margin ka 40%), `min_margin_level_pct`
(300%), aur broker ka `volume_min/max/step` lagoo hota hai. Agar stop broker ke
`stops_level` ke andar ho, spread `max_spread_pips` se zyada ho, ya reward:risk
`min_reward_risk` se kam ho to `lots.py` file likhne se **inkaar** kar deta hai.

Example (demo fixture, M15 plan): EURUSD, ask 1.08604, stop 1.08556, 4.8 pips, $55/lot,
budget $50 → **0.9 lots**, risk $49.50, margin $977.44 (= free margin ka 19.5%), margin level 513%.

---

## 6. Teen darwaze (gates) aur guard

1. **Risk PASS** - `check.py` usi snapshot se wahi order check karta hai (fingerprint match).
2. **Aap ka yes** - `ticket.py approve --reply "yes"`. "sure", "ok", "haan sab" nahi chalte.
3. **`mt5.py execute`** - dobara risk + yes padhta hai, REAL account par `"mt5.allow_live": true`
   ke bagair rukta hai, terminal se `order_check` karata hai, phir ek dafa `order_send`.

**Guard** sirf risk kam kar sakta hai: breakeven, trailing stop, partial take-profit.
Kabhi open/add/widen nahi karta. `guard off` se band.

---

## 7. MT5 ke 10 traps jo pack pehle se handle karta hai

1. **Symbol ka naam wahi nahi hota** - `EURUSD.a`, `EURUSDm`, `XAUUSD.cash`. `symbol_suffix`,
   `symbols --search`, aur order mein terminal ka asli naam jata hai.
2. **Lot ladder** - 0.137 lots reject ho jate hain; sizing step par floor hoti hai.
3. **Pip ki qeemat broker ki tick value se** - EURUSD $10/pip/lot, XAUUSD bhi $10, US500
   different. Hard-code kuch nahi.
4. **Stops level** - stop bohot qareeb ho to broker reject karta hai; sizing/check pehle rok dete hain.
5. **Filling mode** - FOK / IOC / RETURN. `"auto"` symbol ke mutabiq choose karta hai; ticket
   resolved value dikhata hai.
6. **Server clock** - broker GMT+2/+3 ho sakta hai; rollover aur session times server ke hain,
   reports dono clocks dikhati hain, `snapshot` offset detect karke save karta hai.
7. **Rollover window** - spread wide hota hai; us waqt naye entry block.
8. **Margin broker ki maths** - margin rate ya leverage, aur `min_margin_level_pct`.
9. **Demo vs REAL** - `trade_mode` demo/contest = paper; REAL ke liye `"mt5.allow_live": true`.
10. **Weekend / market closed** - `session` batata hai, risk block karta hai.

---

## 8. Backtest, history, scan

```bash
python3 trader-mt5/mt5.py backtest EURUSD --tf M5 --count 5000 --rr 1.5
#   BACKTEST EURUSD M5: opening range (60 min), or stop, 1.5R target, flat by 20:55
#   2 trades over 2 sessions: 1 wins, 1 losses (50%), expectancy 0.25R per trade
#   WARNING: under 30 trades. That is not a sample you can trust.
```

- Backtest mein spread aur commission count hote hain, koi lookahead nahi, 30 se kam trades par warning.
- `history` terminal ki **asli** closed deals se win rate, expectancy, profit factor, max drawdown
  nikalta hai - ye simulation nahi, aap ka apna record hai.
- `scan` ek hi rule (opening range + trend + ATR stop) ko kai symbols par chalata hai.

---

## 9. Bina Windows (macOS/Linux, ya sirf test)

Terminal ke bagair bhi sab kuch chalta hai - bas snapshot file se:

```bash
python3 trader-mt5/mt5.py --replay tests/fixtures/trader-mt5/context.json --now "2026-10-20 09:35" account
python3 trader-mt5/mt5.py --replay tests/fixtures/trader-mt5/context.json --now "2026-10-20 09:35" scan --tf M5
```

`--replay` har read us file se leta hai (account, specs, quotes, positions, deals, rates) aur
`sent` list mein replies; execute bhi replay par test hota hai. Isi tarah poora test suite
offline chalta hai:

```bash
python3 -m unittest discover -s tests -v     # 391 tests, all pass
```

---

## 10. Kya ye nahi karta (honest limits)

- **Windows-only package**: asli terminal reads/sends ke liye Windows + chalta hua MT5 lazmi.
- **Yahoo-wale tools ka session**: `bars --yahoo` se scanner/entry/exit/timemachine MT5 bars
  padh lete hain, lekin unka dimaag 09:30-16:00 New York ka hai. 24 ghante ke symbol par
  `mt5.py scan/levels/setup/backtest` behtar hain.
- **Stop guarantee nahi**: fast market, rollover ya weekend gap mein stop us se aage bhar sakta hai.
- **Demo server live se different** ho sakta hai: spread, swap, filling, stops level.
- **Financial advice nahi**: ye software terminal padhta hai aur hisaab karta hai; zyada tar
  day traders paisa kho dete hain. Apna faisla khud karein.

---

## 11. Agla qadam (aap ke liye)

1. Demo account par `doctor` + `spec` + `session` chalayein, numbers apne broker ke sath match karein.
2. `config.json` mein commission, symbols, aur limits apne hisaab se set karein.
3. Ek hafta sirf `scan → setup → lots → check → ticket` chalayein (execute nahi) - numbers ka
   behaviour samajh aaye.
4. Demo par ek trade poora karein, `history --write` se apna record dekhein.
5. Jab consistent lage, tabhi `"mt5.allow_live": true` - aur pehle chhoti size.
