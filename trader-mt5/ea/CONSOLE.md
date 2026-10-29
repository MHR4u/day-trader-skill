# CONSOLE.md - DayTraderMT5 ka console aur dashboard, ek ek chez

Ye file sirf `DayTraderMT5.mq5` ke bare mein hai. Do hisse hain:

1. **Console** - jo lines `Experts` tab mein aati hain (aur log file mein rehti hain).
2. **Dashboard** - jo chart par panel banta hai, teen buttons ke sath.

Dono ka ek hi maqsad: aapko har waqt pata ho ke EA ne kya dekha, kya socha,
kya kiya, aur agar kuch nahi kiya to kyun nahi kiya.

**v1.23:** dashboard 9 pages ka hai (DASH, RULE, RISK, CLOCK, MANAGE, LOG,
TEST, PACK, HELP), aur har number chart par hi **click se badalta** hai: `[-]`
`[+]` se number, `ON/OFF` se switch, `<` `>` se list. Jo aap click karte hain wo
terminal ke global variables mein save ho jata hai, is liye chart band kar ke
wapas kholen to bhi aap ki tuning barqarar rehti hai.

Do sawal har EA se poochne chahiye: kya ye internet par baat karta hai (jawab:
nahi, section 16), aur kya terminal is ka order sach mein le lega (jawab: TEST
page, section 11.7 - gates aur `RUN ORDER CHECK`).

Install steps `README.md` mein hain. Ye file sirf "kaunsi line ka kya matlab hai"
aur "panel ke kis khaane ka kya matlab hai" ke liye hai.

---

## 1. Console kahan hai

| jagah | kaise | kya milta hai |
| --- | --- | --- |
| Toolbox, `Experts` tab | MT5 mein `Ctrl+T`, phir `Experts` | live lines, sabse aasan |
| Toolbox, `Journal` tab | `Ctrl+T`, `Journal` | terminal ki apni baatein (login, connection) |
| Log file | `File > Open Data Folder > MQL5 > Logs` | `YYYYMMDD.log`, har din ki file |
| Terminal log | `Open Data Folder > logs` | terminal ka poora log, EA ki lines bhi isi mein |
| Experts log | `Open Data Folder > MQL5 > Logs` | sirf EAs, script aur indicator ki lines |

Tips:

- `Experts` tab par right-click: `Clear` (saaf), `Auto Scroll` (band kar dein to
  line ruk jati hai jab aap parh rahe hon), `Copy` (line copy), `Open` (log file).
- Har line ke shuru mein **terminal ka waqt** hota hai, aapke local waqt mein nahi.
  Broker ka server GMT+2 ya GMT+3 par hota hai, is liye waqt alag lagega. EA khud
  New York ka waqt nikalta hai aur panel par dikhata hai; console line terminal ke
  waqt par hoti hai.
- Ek din ki poori file ka size chhota rehta hai, kyunki rule ki lines sirf tab
  aati hain jab haalat badalti hain (`InpVerbose = true` kar dein to har bar par).

---

## 2. Ek line ka format

```
2026.10.29 14:05:33 | SIGNAL | BUY signal: M5 closed 2394.12, above the range (2388.10 - 2393.40), trend up
```

| hissa | matlab |
| --- | --- |
| `2026.10.29 14:05:33` | terminal ka waqt (date + second) |
| `SIGNAL` | tag, 5 characters ka, column seedha rakhne ke liye |
| baqi | insaani zaban mein wahi cheez jo EA ne ki |

Har line `Log()` se guzarti hai. File mein `Print()` sirf ek jagah hai, isi
function ke andar, is liye har line ka format ek jaisa hai.

---

## 3. Tags, ek nazar mein

| tag | kab aata hai | aap ko kya batata hai |
| --- | --- | --- |
| `INIT` | EA chart par lagte waqt | version, symbol, account, magic, banner, aur ye ke EA offline hai |
| `CONF` | wahin, startup par | poora config: rule, stop, clock, risk, limits, broker levels, manage |
| `GATE` | startup par, aur jab trade rukta ho | terminal/account/broker ki ijazat, 11 gates ka hisaab, ya `InpAllowLive` ki deewar |
| `RULE` | haalat badalne par (ya har bar, verbose mein) | range ban raha hai, ban gaya, wait, kya close hua |
| `SIGNAL` | jab break milta hai | taraf, close, range, trend |
| `BLOCK` | signal mila par order nahi gaya | **wajah**, ek line mein |
| `SIZE` | order se pehle | lots, stop, points, ATR, target, R |
| `RISK` | order se pehle | budget, lot ka hisaab, margin ki had |
| `ORDER` | bhejte waqt | dry run, ya bheja, ya broker ne accept kiya (ticket) |
| `MANAGE` | khuli position par | breakeven, trailing, partial (aur dry run ke "would have") |
| `FLAT` | flat-by par, ya button se | kaunsi ticket band hui, kis wajah se |
| `CTRL` | panel ke button | pause, resume, dry on/off, close-ours armed/confirmed |
| `ERROR` | jo kaam nahi hua | broker ka retcode, ya terminal ka error |
| `DAY` | New York mein naya din | aaj ki session, flat-by |
| `STOP` | EA hatne par | reason code (0, 1, 2, 3, 4) |
| `CHECK` | TEST page ka button | terminal ne order qabool kiya ya mana, margin ke sath |
| `ALIVE` | har heartbeat (default 15 min) | EA zinda hai, rule kahan hai, kitne gates khule |

---

## 4. Startup par jo aata hai

```
2026.10.29 13:58:02 | INIT  | -------------------------------------------------------------
2026.10.29 13:58:02 | INIT  | DayTraderMT5 v1.23 on XAUUSD M5, account DEMO #5001234, magic 20261019
2026.10.29 13:58:02 | INIT  | -------------------------------------------------------------
2026.10.29 13:58:02 | CONF  | rule      : M5 bars, EMA 50/200, opening range 60 min, long only
2026.10.29 13:58:02 | CONF  | stops     : 0.50 ATR behind the entry or the range mid, target 1.50R
2026.10.29 13:58:02 | CONF  | clock     : New York time, session 03:05-19:00, flat by 20:55, weekdays only
2026.10.29 13:58:02 | CONF  | risk      : 1.00% of equity and 50.00 USD per trade, cap 2.00 lots, 40% of free margin
2026.10.29 13:58:02 | CONF  | limits    : 1 entry a day, daily loss stop 150.00 USD, spread ceiling 25 points
2026.10.29 13:58:02 | CONF  | broker    : stops level 0 points, freeze level 0 points, so no stop closer than 35 points
2026.10.29 13:58:02 | CONF  | levels    : contract 100, tick value 1.00, volume 0.01 to 50.00 step 0.01
2026.10.29 13:58:02 | CONF  | manage    : breakeven 1.00R, trail 1.00R / 150 points, partial off
2026.10.29 13:58:02 | GATE  | trading is allowed: the terminal, the account and the broker all agree
2026.10.29 13:58:02 | GATE  | all 11 gates are open: an entry would be sent on the next break
2026.10.29 13:58:02 | INIT  | this EA is offline: no WebRequest, no sockets, no DLL, no include beyond Trade.mqh
2026.10.29 13:58:02 | INIT  | dashboard: 9 pages, click a tab; every row with [-] [+] is live
2026.10.29 13:58:02 | INIT  | -------------------------------------------------------------
```

Ye poora block **har attach par** aata hai. Isay parh kar aap 10 second mein
jaan jate hain ke EA kis cheez par chal raha hai. Agar yahan kuch ajeeb ho (galat
symbol, galat session, `long only` jab aap short bhi chahte hain), to `Inputs` se
theek karein - baad mein dhoondna nahi parega.

`GATE` ki do aur shakalein:

```
2026.10.29 13:58:02 | GATE  | trading is not allowed yet: the AutoTrading button in the toolbar is off
2026.10.29 13:58:02 | GATE  | REAL account and InpAllowLive is false: this EA will read and log, and will not trade.
```

Pehli: toolbar ka bara button dabayein. Doosri: ye guard hai, demo par jayein ya
`InpAllowLive = true` saaf niyat se karein.

---

## 5. RULE lines: rule kya dekh raha hai

Sirf tab ati hain jab haalat badalti hai (ya `InpVerbose = true` par har bar).
Har line ek hi cheez batati hai: is waqt rule kis stage par hai.

| line | matlab | aap kya karein |
| --- | --- | --- |
| `no opening range yet: the session has not printed two bars inside 03:05-09:05 New York` | session shuru hua par 2 bar bhi nahi bane | intezar; chart naya khula ho to thora waqt |
| `opening range still forming: 7 bar(s), 2388.10 - 2393.40, done at 09:05` | range ban raha hai, live high/low | kuch nahi, ye normal hai |
| `opening range 2388.10 - 2393.40, mid 2390.75, 12 bars, 530 points wide` | range ban gaya | ab break ka intezar |
| `waiting: XAUUSD M5 closed 2391.20, inside the range (range 2388.10 - 2393.40, trend up)` | break nahi hua, trend up | intezar |
| `waiting: ... closed 2394.00, above the range, but the trend filter disagrees` | break hua par EMA ulta | intezar; trend filter jaan boojh kar laga hai |
| `waiting: ... closed 2385.00, below the range, but short entries are off (InpAllowShort)` | neeche break, par short band | chahein to `InpAllowShort = true` |
| `opening range is 180 points, under the floor you set (250): no entries today` | range bohot tang hai, aap ne floor lagaya hua hai | RULE tab par `Range floor` kam karein yaa `off` |
| `no bars from the terminal for XAUUSD M5` | terminal ne bars nahi diye | symbol Market Watch mein ho, chart par data aaye |
| `the ATR is not ready yet` | chart mein itni history nahi | chart ko left tak scroll karein (F5 se refresh) |

---

## 6. SIGNAL, BLOCK, SIZE, RISK, ORDER: ek order ka safar

### 6.1 SIGNAL

```
| SIGNAL | BUY signal: M5 closed 2394.12, above the range (2388.10 - 2393.40), trend up
```

Rule trigger hua. Ye abhi **order nahi** hai - pehle 6 darwaze hain.

### 6.2 BLOCK: order kyun nahi gaya

Ye tag sabse zyada kaam ka hai. Har line mein pehle taraf, phir `skipped:`, phir
wajah. Poori list:

| wajah | matlab | kya karein |
| --- | --- | --- |
| `it is the weekend in New York` | Sat/Sun | kuch nahi, `InpWeekdaysOnly` ki marzi |
| `outside the session 03:05-19:00 New York (now 21:40)` | waqt se bahar | session inputs theek karein, ya intezar |
| `entries are paused from the dashboard` | panel par PAUSE dabaya hua hai | RESUME dabayein |
| `a position of ours is already open` | ek trade khula hai | intezar; ye by design hai |
| `the daily entry limit is used (1 of 1)` | aaj ka quota khatam | kal, ya `InpMaxTradesPerDay` barhayein |
| `the daily loss stop: realised -152.00 USD against a limit of 150.00 USD` | din ka loss limit | aaj ke liye ruk gaya, ye sahi hai |
| `the spread is 34 points, over your ceiling of 25` | spread zyada | news ke waqt normal; `InpMaxSpreadPoints` dekh lein |
| `the AutoTrading button in the toolbar is off` | terminal band | button dabayein |
| `Tools > Options > Expert Advisors > Allow algorithmic trading is off` | setting band | option tick karein, EA restart |
| `this account is not allowed to trade (investor password, or the broker closed it)` | account | broker se baat |
| `the broker disabled expert advisors on this account` | broker | broker se baat |
| `this is a REAL-money account and InpAllowLive is false` | guard | demo, ya jaan boojh kar allow |
| `the stop is 12 points away and the broker needs 35` | stop bohot tight | `InpStopBufferPoints` ya `InpAtrMult` barhayein |
| `the rounded target is 1.48R, under your 1.50R` | rounding ke baad R kam | `InpMinRR` thora kam, ya digits wale symbol par |
| `no order: the smallest lot risks more than the budget` | budget bohot chhota | risk barhayein, ya sasta symbol |
| `no order: over InpMaxLots (2.00)` | lot cap | cap barhayein ya risk kam |
| `no order: it needs 2100.00 of margin, over 40% of free margin` | margin | `InpMaxLots` kam, ya `InpMaxMarginPct` barhayein |

Ek order par sirf **pehli** rukawat likhi jati hai, warna log bhar jata. Sab
darwaze pass ho jayen to agla tag `SIZE` aata hai.

### 6.3 SIZE aur RISK

```
| SIZE  | 0.42 lots, stop 2387.40 (670 points, ATR 2.00 x 0.50), target 2404.20 (1.50R)
| RISK  | risk budget 50.00, 12.00 per lot, budget 50.00 USD, margin under 40% of free
```

`SIZE` batata hai lots kahan se aaye: stop ki doori (points), ATR, target, aur
asli R. `RISK` batata hai paisa: per lot kitna, budget kitna, margin kitni had tak.

### 6.4 ORDER

| line | matlab |
| --- | --- |
| `DRY RUN: would have sent BUY XAUUSD 0.42 lots at 2394.10, stop 2387.40, target 2404.20 (1.50R)` | `InpDryRun` on hai, kuch nahi bheja |
| `sending BUY XAUUSD 0.42 lots at ...` | ja raha hai |
| `accepted: order #132889001, deal #241112233 at 2394.35, 0.42 lots` | broker ne le liya, ye aap ki ticket hai |
| `ERROR | refused: 10016 invalid stops` | broker ne stop pasand nahi kiya |

### 6.5 Broker ke retcodes jo aap dekh sakte hain

| code | matlab | hal |
| --- | --- | --- |
| `10009` | done | kuch nahi, ye kamyabi hai |
| `10004` | requote | agle bar par khud try karega |
| `10006` | rejected | broker ne mana, wajah Journal mein |
| `10016` | invalid stops | `InpStopBufferPoints` barhayein (20-30) |
| `10018` | market closed | waqt par band, kuch nahi |
| `10019` | no money | margin kam, lot ya risk kam |
| `10027` | algo trading disabled | AutoTrading / options |
| `10030` | unsupported filling | EA khud symbol ki filling chunta hai; broker se poochein |
| `10031` | no connection | internet / terminal |

---

## 7. MANAGE: khuli trade ka intezam

```
| MANAGE | #132889001: stop to the entry 2394.10 at 1.02R
| MANAGE | #132889001: stop trailed to 2397.60 at 1.80R
| MANAGE | took 0.21 lots of #132889001 at 2.05R, 0.21 lots left
```

| line | kab |
| --- | --- |
| `stop to the entry ... at 1.02R` | `InpBreakevenAtR` (1.0) cross hua |
| `stop trailed to ... at 1.80R` | `InpTrailAtR` ke baad, har behtar stop par |
| `took X lots of #... at 2.05R, Y lots left` | `InpPartialAtR` par |
| `DRY RUN: would have ...` | dry run mein sirf likha jata hai |

Trailing har tick par nahi hota: stop sirf tab hilta hai jab naya stop purane se
kam az kam trail ka paanchwan hissa (ya broker ki minimum doori) aage ho. Isi
liye log par ek trade ki 3-4 lines aati hain, 300 nahi.

---

## 8. FLAT: band karne ki lines

```
| FLAT  | closed #132889001 (0.21 lots) at 20:55, flat by 20:55 New York
| FLAT  | 1 position(s) closed, flat by 20:55 New York
| FLAT  | closed #132889001 (0.42 lots) at 14:12, closed from the dashboard
```

Flat-by par har 30 second mein ek koshish hoti hai (agar band na ho paye), is liye
log bhar nahi jata. `could not close #...: 10018 market closed` aaye to market
band hai - aap kuch nahi kar sakte.

---

## 9. CTRL: panel ke button

| line | matlab |
| --- | --- |
| `entries paused from the dashboard. Management and the flat-by close keep running` | naye trade band, purane ka intezam jari |
| `entries resumed from the dashboard` | wapas chalu |
| `dry run on: signals and orders are logged, nothing is sent` | sirf log |
| `dry run off: orders will be sent` | asli order |
| `CLOSE OURS armed for 6 seconds: 1 of our position(s) on XAUUSD will be closed on a second click` | pehla click, kuch nahi hua |
| `CLOSE OURS confirmed by the second click` | doosra click, band kar diya |
| `CLOSE OURS expired after 6 seconds: nothing was closed` (quiet) | waqt guzar gaya |
| `setting risk_pct is now 0.50` | aap ne panel se koi number badla | jo chahiye tha, ho gaya |
| `settings reset to the inputs (from the dashboard)` | RESET confirm kiya | sab inputs par wapas |
| `3 setting(s) restored from what you set on the chart last time` | chart dobara khola, purani tuning wapas | kuch nahi, ye feature hai |
| `the session ends cannot be the same minute: moved to ...` | start aur end ek hi waqt par aa gaye | khud theek kar diya |

---

## 10. DAY aur STOP

```
| DAY   | a new day in New York: 2026.10.30, session 03:05-19:00, flat by 20:55
| STOP  | removed from the chart, reason 3 (0 chart closed, 1 terminal closed, 2 recompile, 3 new inputs, 4 timeframe)
```

`DAY` roz ek dafa aata hai, aur us waqt purani tickets ke marks (breakeven,
trailing, partial ki yaaddasht) saaf ho jate hain.

`STOP` ke reasons: `0` chart band hua, `1` terminal band hua, `2` recompile, `3`
inputs badle, `4` timeframe badla. `2` se `4` par EA dobara `INIT` banner deta hai.

---

## 11. Dashboard: chart par panel, 9 pages

Panel chart objects se banta hai: koi DLL nahi, koi file nahi, koi resource nahi.
Ek dafa banta hai, phir sirf text badalta hai, is liye chart slow nahi hota. Page
badalne par purane page ke objects hata diye jate hain, naye ban jate hain.

```
+----------------------------------------------------+
| DayTraderMT5  the day at a glance          DEMO    |   header: naam, page, account type
+----------------------------------------------------+
| [DASH][RULE][RISK][CLOCK][MANAGE]                  |   9 tabs, 2 rows, active tab neela
| [ LOG ][ TEST ][ PACK ][ HELP ]                    |
+----------------------------------------------------+
| = MARKET                                           |
|   Symbol / rule   XAUUSD  M5                       |
|   New York        2026.10.29 14:05  EDT            |
|   Session         03:05-19:00  OPEN                |
|   [======================--------------]           |
| = OPENING RANGE ...  (yahi 7 sections DASH par)    |
| ...                                                |
|  [ PAUSE ] [ DRY OFF ] [ CLOSE OUR ] [ RESET ]     |
| v1.23  magic 20261019  quiet log                   |
+----------------------------------------------------+
```

Rang: **hara** = theek/nafa/on, **lal** = khatra/nuqsan/blocked, **peela** = dhyan
dein (pause, dry run, range ban raha hai, quota poora), **bhoora** = sirf maloomat.

### 11.1 Page DASH - aaj ka aina

| section | rows |
| --- | --- |
| MARKET | symbol aur rule ka bar size, New York ka waqt (EDT/EST), session khula/band + progress bar, aur **`next:`** line - wahi ek jumla jo batata hai ab trade kyun nahi hui (neeche section 17) |
| OPENING RANGE | high / low, mid, width points aur bars (na bane to `still forming`) |
| INDICATORS | EMA fast/slow ki value, trend (`up` / `down` / `filter off`), ATR aur spread (max ke sath) |
| TODAY | entries / quota, realised P/L, loss room (`STOPPED for the day` jab khatam) |
| POSITION | ticket aur side, lots aur entry, stop aur target, R mein progress + P/L + bar |
| RISK AND SIZE | budget per trade, caps (lots, margin, R) |
| STATUS | `Trading: yes` ya `no: <wajah>`, mode (DEMO/REAL/DRY/PAUSED + kitni open), last console line |

### 11.2 Page RULE - rule ki har cheez click se badlein

| row | click | step | hadd |
| --- | --- | --- | --- |
| Bar size | `<` `>` | M1, M5, M15, M30, H1 | - |
| Fast EMA | `[-]` `[+]` | 5 | 2 se 400 |
| Slow EMA | `[-]` `[+]` | 10 | 5 se 800 |
| Trend filter | `ON/OFF` | - | - |
| ATR period | `[-]` `[+]` | 1 | 2 se 50 |
| Opening range | `[-]` `[+]` | 5 min | 5 se 240 |
| Stop distance | `[-]` `[+]` | 0.1 ATR | 0.1 se 3.0 |
| Range floor | `[-]` `[+]` | 10 points | 0 (off) se 5000 |
| Reward:risk | `[-]` `[+]` | 0.1 | 1.0 se 5.0 |
| Short side | `ON/OFF` | - | - |

Neeche do read-only lines: **State** (rule is waqt kahan hai) aur **Next size**
(abhi ke ATR par agla order kitne lots ka hoga).

### 11.3 Page RISK - paisa

| row | click | step | hadd |
| --- | --- | --- | --- |
| Risk per trade | `[-]` `[+]` | 0.25% | 0 se 10 |
| or a fixed | `[-]` `[+]` | 10 | 0 se 1,000,000 |
| Lot cap | `[-]` `[+]` | 0.1 | 0.01 se 500 |
| Margin cap | `[-]` `[+]` | 5% | 5 se 100 |
| Spread ceiling | `[-]` `[+]` | 5 points | 0 (off) se 1000 |
| Daily loss stop | `[-]` `[+]` | 25 | 0 (off) se 1,000,000 |
| Entries a day | `[-]` `[+]` | 1 | 1 se 20 |

Read-only: budget per trade, free margin, equity, realised today, spread now.
Percent aur fixed dono ho to **chhota** jeetta hai - yahi panel par `Budget per
trade` mein dikhta hai.

### 11.4 Page CLOCK - waqt

| row | click | step |
| --- | --- | --- |
| Time base | `ON/OFF` | New York (DST ke sath) yaa server |
| No entries before | `[-]` `[+]` | 5 min, 00:00-23:55 ghoomta hai |
| No entries after | `[-]` `[+]` | 5 min |
| Close everything | `[-]` `[+]` | 5 min |
| Weekdays only | `ON/OFF` | - |

Read-only: New York ka waqt, session OPEN/closed, flat-by kitne minute baad,
aaj ke entries, server ka waqt. Start aur end ek hi minute par aa jayen to EA
khud 60 minute ka farq kar deta hai aur console par likh deta hai.

### 11.5 Page MANAGE - trade ka intezam, broker, alerts, log

| row | click | step | hadd |
| --- | --- | --- | --- |
| Stop to entry at | `[-]` `[+]` | 0.1R | 0 (off) se 5 |
| Trail from | `[-]` `[+]` | 0.1R | 0 (off) se 5 |
| Trail distance | `[-]` `[+]` | 10 points | 10 se 5000 |
| Take part at | `[-]` `[+]` | 0.1R | 0 (off) se 5 |
| Part size | `[-]` `[+]` | 5% | 10 se 90 |
| Slippage allowed | `[-]` `[+]` | 5 points | 1 se 500 |
| Stop buffer | `[-]` `[+]` | 5 points | 0 se 500 |
| Popup alert / Sound / Push | `ON/OFF` | - | - |
| Every bar (verbose) | `ON/OFF` | - | - |
| Alive line | `[-]` `[+]` | 5 min | 0 (off) se 240 |

Read-only: broker ka stops level (buffer ke sath), aur broker ka **last answer**
(`done`, `10016`, `10009`...). Yeh wahi `g_lastRetcode` hai jo `ERROR` line mein aata hai.

### 11.6 Page LOG - console chart par

- **CONSOLE, NEWEST FIRST**: aakhri 8 lines, bilkul wahi jo `Experts` tab mein
  hain, `time | TAG | baat` format mein. Naya line sabse upar aur safaid rang mein.
- **JOURNAL TODAY**: aaj ke band trades, wins/losses, net (commission aur swap ke
  sath), aakhri closed trade ka waqt aur nafa, aur kitni position khuli hai.

Log file kholne ki zaroorat nahi: chart par hi pata chal jata hai ke kya hua.

### 11.7 Page TEST - "kya ye sach mein trade lega?"

Yeh page do sawalon ka jawab deta hai, dono **koi order bheje baghair**.

Pehle do line **rule ki haalat** par: `waiting for a break` jaisa state, aur `next:` -
yani kis price par entry trigger hogi. Phir **CAN IT TRADE RIGHT NOW?** - 11 gates, ek ek,
`PASS` (hara) yaa `NO: <wajah>` (lal):

| # | gate | PASS kab |
| --- | --- | --- |
| 1 | Toolbar | terminal ka AutoTrading button on |
| 2 | Algo setting | `Tools > Options > Expert Advisors > Allow algorithmic trading` on |
| 3 | Account | account trade kar sakta hai (investor password nahi) |
| 4 | Broker EA | broker ne is account par EA band nahi kiya |
| 5 | Live guard | REAL nahi, yaa `InpAllowLive = true` |
| 6 | Weekday | Sat/Sun nahi (ya weekdays-only off) |
| 7 | Session | New York ke session ke andar |
| 8 | Entries left | aaj ka quota baqi hai |
| 9 | Loss room | daily loss stop hit nahi hua |
| 10 | Spread | spread ceiling ke andar |
| 11 | Market data | bars aur ATR maujood |

Uske baad do hisaab wale gates: **Stops distance** (stop broker ki kam se kam
doori se bahar hai ya nahi) aur **Margin** (order ki margin free margin ke aap
ke cap ke andar hai ya nahi).

**WHAT IT WOULD SEND** - bilkul wahi order jo rule abhi bhejta:

| row | matlab |
| --- | --- |
| Side / lots | BUY yaa SELL, aur kitne lots (risk budget se) |
| Entry | abhi ka ask (buy) yaa bid (sell) |
| Stop | SL ki price aur points mein doori |
| Target | TP ki price, points, aur R |
| Terminal check | `-` (abhi test nahi hua), `ok: margin ...`, yaa `no: <retcode> <comment>` |

Neeche bada button: **RUN ORDER CHECK (sends nothing)**. Ye EA ka poora order
(prices, lots, SL, TP, deviation, filling mode, magic) terminal ke apne
`OrderCheck()` mein daalta hai. Terminal wahi validation karta hai jo asli order
par karta: symbol trade ho sakta hai? volume ladder theek? stops level ke andar?
margin hai? filling mode supported? - aur **kuch bhejta nahi**. Jawab console par:

```
| CHECK | BUY XAUUSD 0.42 lots at 2394.10, stop 2387.40, target 2404.20: the terminal accepted the whole order and priced the margin at 152.30 USD. Nothing was sent.
| CHECK | BUY XAUUSD 0.42 lots: the terminal refused it, 10016 invalid stops. Nothing was sent.
```

`10016` aaye to MANAGE page par **Stop buffer** barha dein. Ye page har 5 second
refresh hota hai, is liye session khulne par gates khud badalte dikhte hain.

### 11.8 Page PACK - poora day-trader pack, kaun hissa kahan

| row | kya dikhata hai |
| --- | --- |
| scanner | is chart par opening range scan |
| entry | range ke close ka break |
| exit | stop aur target (aap ke numbers) |
| risk | rule is waqt kahan hai (`waiting for a break`, `in a trade`, `done for the day`...) |
| budget | agla order kitne lots / kitne points |
| broker | broker ka last jawab |
| alerts | alerts on/off |
| mt5 desk | magic number aur account type |
| news, analyst, pelosi, time machine | `dtcli ...`: ye Python side par hain, EA offline rehta hai |

Aakhri line saaf likhti hai: **those read the web; the EA stays offline**. Yani
jo cheez EA ke andar nahi hai, wo jhooti tarah andar dikhayi nahi jati.

### 11.9 Page HELP - kaise chalayein

Chhota card: tabs, `[-]` `[+]`, `ON/OFF`, `<` `>`, save, RESET, chaar button ka
matlab, aur safety (`REAL` ke liye `InpAllowLive`, apna magic, demo pehle).

### 11.10 Chaar buttons (har page par neeche)

| button | pehla click | doosra click | rang |
| --- | --- | --- | --- |
| `PAUSE` / `RESUME` | naye entries band / chalu | - | pause par peela |
| `DRY OFF` / `DRY ON` | dry run on/off (live) | - | on par peela |
| `CLOSE OUR` | arm (6 second) | band karta hai | armed par lal `SURE?` |
| `RESET` | arm (6 second) | sab settings inputs par | armed par lal `SURE?` |

`PAUSE` sirf naye entries rokta hai: breakeven, trailing, partial, flat-by sab
chalte rehte hain. `RESET` poore panel ki tuning ko inputs par le jata hai (page
ka nahi, sab ka) - is liye do click.

### 11.11 Click badlav kahan save hota hai

Har click par EA poora table `GlobalVariable` mein likhta hai:

```
DTMT5_C_risk_pct = 1.0      DTMT5_C_tf = 5        DTMT5_C_flat_by = 1255
DTMT5_C_or_min   = 60        DTMT5_C_shorts = 0   ... 34 keys
```

Isi liye chart band karke wapas kholen, timeframe badlein, yaa terminal restart
karein - aap ki tuning wapas milti hai (`CONF ... N setting(s) restored ...`).
`RESET` in keys ko delete karta hai aur `Inputs` wale numbers wapas le aata hai.
`InpShowPanel = false` panel ko poori tarah band karta hai; `InpPanelX/Y` us ki
jagah badalte hain (pixels, left/top se). Default `InpPanelY = 96` hai, kyunki
MT5 ka apna **buy/sell corner** (One Click Trading) chart ke top-left par hota
hai - panel us ke neeche shuru hota hai taake Buy aur Sell buttons chhupe nahi.
Agar aap ke terminal mein One Click Trading off hai aur upar jagah khali hai, to
`InpPanelY` ko 30 kar dein; aur agar chart window chhoti hai aur panel neeche se
screen se bahar ja raha hai to 60 karein, yaa `InpShowPanel = false` karke sirf
console par kaam karein.

## 12. Har input, ek ek (40 inputs, 8 groups)

Inputs factory settings hain. Panel se jo badla jata hai wo un ke upar chalta hai
(aur save rehta hai); `RESET` sab inputs par wapas le aata hai.

### The gates

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpAllowLive` | `false` | REAL account par trade ki ijazat (panel se badal nahi sakte) | sirf demo par tassalli ke baad |
| `InpDryRun` | `false` | sirf log, order nahi (panel ka `DRY` isi ko badalta hai) | pehle din |
| `InpMagic` | `20261019` | EA ki apni label | do EA ek chart par hon |

### Risk and size (panel: RISK)

| input | default | matlab |
| --- | --- | --- |
| `InpRiskPercent` | `1.0` | equity ka %, per trade |
| `InpRiskMoney` | `50.0` | yaa fixed amount (dono mein se chhota jeetta hai) |
| `InpMaxLots` | `2.0` | ek order ka hard cap |
| `InpMaxMarginPct` | `40.0` | free margin ka max % |
| `InpMaxSpreadPoints` | `25.0` | is se zyada spread par entry nahi (`0` = off) |
| `InpMinRR` | `1.5` | target ka R |

### The rule (panel: RULE)

| input | default | matlab |
| --- | --- | --- |
| `InpTimeframe` | `M5` | rule ka bar size (panel se M1/H1 tak) |
| `InpEmaFast` | `50` | tez EMA |
| `InpEmaSlow` | `200` | slow EMA |
| `InpUseTrend` | `true` | trend filter; off kar dein to sirf break chalta hai |
| `InpAtrPeriod` | `14` | ATR ka period, stop isi se |
| `InpORMinutes` | `60` | opening range ki lambai |
| `InpAtrMult` | `0.5` | stop entry se kitne ATR peeche |
| `InpMinRangePoints` | `0.0` | range itne points se tang ho to us din entry nahi (`0` = off) |
| `InpAllowShort` | `false` | neeche break par sell bhi |

### The clock (panel: CLOCK) - New York waqt

| input | default | matlab |
| --- | --- | --- |
| `InpNewYorkTimes` | `true` | neeche ke waqt NY mein (`false` = server) |
| `InpSessionStart` | `03:05` | entry na karne ka waqt shuru |
| `InpSessionEnd` | `19:00` | is ke baad entry nahi |
| `InpFlatBy` | `20:55` | sab band |
| `InpWeekdaysOnly` | `true` | Sat/Sun nahi |
| `InpMaxTradesPerDay` | `1` | din ke entries |
| `InpMaxDailyLoss` | `150.0` | din ka realised loss stop |

### Managing the trade (panel: MANAGE)

| input | default | matlab |
| --- | --- | --- |
| `InpBreakevenAtR` | `1.0` | entry par stop (`0` = off) |
| `InpTrailAtR` | `1.0` | trailing shuru (`0` = off) |
| `InpTrailPoints` | `150` | trail ki doori, points |
| `InpPartialAtR` | `0.0` | partial close ka R (`0` = off) |
| `InpPartialPercent` | `50.0` | kitna % band |

### Alerts (panel: MANAGE)

| input | default | matlab |
| --- | --- | --- |
| `InpAlertPopup` | `true` | `Alert()` popup: fill par aur close par |
| `InpAlertSound` | `false` | `alert2.wav` |
| `InpAlertPush` | `false` | phone par push (MetaQuotes ID chahiye) |

Alert kya kehta hai: `DayTraderMT5: BUY XAUUSD 0.42 lots at 2394.35, stop 2387.40,
target 2404.20` aur close par `DayTraderMT5: 1 position(s) closed on XAUUSD, ...`.
Alerts entry ke waqt nahi, **fill** aur **close** par aate hain.

### Console and panel

| input | default | matlab |
| --- | --- | --- |
| `InpShowPanel` | `true` | dashboard on/off |
| `InpPanelX` | `14` | left se doori, pixels |
| `InpPanelY` | `96` | top se doori, pixels (buy/sell corner ke neeche) |
| `InpHeartbeatMinutes` | `15` | itne minute par `ALIVE` line (0 = off) |
| `InpVerbose` | `false` | har bar par RULE line (panel ka `Every bar`) |

### Plumbing

| input | default | matlab |
| --- | --- | --- |
| `InpDeviationPoints` | `20` | slippage ki ijazat |
| `InpStopBufferPoints` | `10` | broker ki stops level ke upar buffer |

## 13. File ka naksha: kaun function kya karta hai

`DayTraderMT5.mq5` ko 12 hisson mein parhein. Har hissa upar se neeche hai, aur
MQL5 ka rule hai ke helper pehle, call baad mein (compiler forward reference
nahi manta).

| hissa | functions | kaam |
| --- | --- | --- |
| Header | `#property` | version, copyright, link, description |
| Inputs | 39 `input` | 8 groups: gates, risk, rule, clock, manage, alerts, panel, plumbing |
| Globals | `g_*` | inputs ki live copy, handles, counters, page, panel cursor |
| Console | `LogRingPush`, `Log`, `LogRule`, `Clip`, `Money` | ek hi jagah se har line, tag ke sath, aur chart ke liye ring buffer |
| Chhote helpers | `ParseHHMM`, `HHMM`, `MinutesOfDay`, `DayIndexOf`, `WeekdayOf`, `WeekdayOfMonth`, `PeriodDescription`, `RiskWords` | waqt aur text |
| Time | `ToNewYork`, `InWindow`, `PastTime` | server clock se New York, DST ke sath |
| Gates | `IsLiveAccount`, `AccountModeWord`, `TerminalReady` | ijazat hai ya nahi, aur nahi to kyun |
| Data | `LoadRates`, `IndicatorValue`, `TrendUp`, `TrendDown`, `TrendWord`, `AtrValue`, `CreateHandles`, `OpeningRange` | bars, EMA, ATR, opening range; `CreateHandles` panel se retune par dobara banata hai |
| Hisaab | `CountEntriesToday`, `RealisedToday` | aaj ke entries aur P/L, account ki history se |
| Sizing | `MoneyPerLotPerPrice`, `RiskBudget`, `FloorToStep`, `LadderFits`, `VolumeFits`, `MarginFits`, `SizeLots` | lots, broker ki ladder, margin |
| Stops | `MinStopPoints`, `SpreadPoints` | kam se kam doori, spread |
| Positions | `OurPositions`, `MarkName`, `Marked`, `Mark`, `PruneMarks` | sirf apni trades, aur un ki yaaddasht |
| Settings | `ClampD`, `ClampI`, `WrapMinutes`, `Notify`, `SaveSettings`, `CfgHas`, `CfgGet`, `ApplyInputDefaults`, `LoadSettings`, `ForgetSettings`, `ResetSettings`, `AdjustSetting` | panel ke click, global variables mein save, inputs par reset, alerts |
| Entry | `TryEntry` | darwaze, stop, target, size, send |
| Manage | `ManagePositions`, `CloseAllOurs` | breakeven, trailing, partial, flat-by |
| Widgets | `DeletePanel`, `UiRect`, `UiText`, `UiButton`, `Clamp01`, `UiBar`, `UiSection`, `UiLine`, `RowRead`, `RowEdit`, `RowCycle`, `RowToggle` | panel ke teen object types aur un ke rows |
| Self check | `FillingForSymbol`, `PreviewOrder`, `GatePass`, `GatesOpen`, `RunOrderCheck` | 11 gates, order ka preview, aur terminal ka `OrderCheck` (bhejta nahi) |
| Pages | `NyWord`, `SessionFraction`, `OurPosition`, `RuleStateWord`, `Heartbeat`, `LotsPreview`, `JournalToday`, `UiHeader`, `UiTabs`, `UiActions`, `UiFooter`, `UiWide`, `DrawDash`, `DrawRule`, `DrawRisk`, `DrawClock`, `DrawManage`, `DrawLog`, `DrawTest`, `DrawPack`, `DrawHelp`, `UpdatePanel`, `SetPage` | 9 pages, tabs, bottom bar, page badalna, aur `ALIVE` heartbeat |
| Entry points | `OnChartEvent`, `OnInit`, `OnDeinit`, `OnTimer`, `OnTick` | MT5 ke 5 callbacks |

`OnTick` ka order hamesha yahi hai: **naya din check -> flat-by -> manage -> naye
bar par rule -> panel**. Flat-by pehle kyun? Kyunki waqt guzar gaya to sabse pehle
band karna hai, chahe rule kuch bhi kahe.

`OnChartEvent` ka order: **tab click -> chaar buttons -> `[-]` `[+]` `<` `>` `ON/OFF` row**.
Row ka naam `DTMT5_UI_b_<id>_<act>` hota hai, is liye ek hi handler 34 rows sambhal
leta hai; `act` = `_dn`, `_up`, `_nx`, `_pv` yaa `_tg`.

---

## 14. Message se hal tak: ek chhoti table

| console mein ye dikhe | ye karein |
| --- | --- |
| `GATE ... AutoTrading ... off` | toolbar ka AutoTrading button |
| `GATE ... Allow algorithmic trading is off` | `Tools > Options > Expert Advisors` |
| `GATE ... REAL account and InpAllowLive is false` | demo account, ya jaan boojh kar allow |
| `trading is not allowed yet: ...` panel par | wahi teen cheezein |
| `no opening range yet` | thora waqt; chart par bars aa rahe hon |
| `waiting: ... inside the range` | kuch nahi, rule ka kaam |
| `opening range is ... under the floor you set` | RULE tab par `Range floor` kam ya off |
| `BLOCK ... spread is 34 points` | news ke baad dobara; ya ceiling barhayein |
| `BLOCK ... smallest lot risks more` | risk barhayein ya sasta symbol |
| `ERROR ... 10016 invalid stops` | MANAGE tab par `Stop buffer` 20-30 |
| `ERROR ... 10019 no money` | lot/risk/margin cap kam |
| `ERROR ... 10027` | algo trading on |
| `ERROR ... 10018` | market band, kuch nahi |
| kuch bhi nahi aa raha | `Journal` tab dekhein; EA attach hai? AutoTrading on? |
| panel nahi dikh raha | `InpShowPanel`, ya `InpPanelX/Y` screen se bahar |
| panel ke numbers purane lagte hain | 5 second ka timer, ya naya bar; F5 se chart refresh |
| `[+]` dabaya par number wahi | hadd par pahunch gaya (har row ki hadd section 11 mein) |
| `RESET` ne kuch nahi kiya | do click chahiye, 6 second ke andar |
| setting badalne par purani wapas aa gayi | chart par save hota hai; `RESET` se inputs wapas |
| `SURE?` 6 second baad gayab | confirm nahi hua, dobara click karein |
| `CHECK ... accepted the whole order ... Nothing was sent` | sab theek hai: broker is order ko le lega |
| `CHECK ... refused it, 10016 invalid stops` | MANAGE > Stop buffer 20-30, phir dobara check |
| `CHECK ... refused it, 10019 no money` | lot cap / risk kam, ya margin cap |
| `CHECK ... refused it, 10018` | market band hai, session ke waqt check karein |
| `CHECK ... cannot build an order to test: no ATR yet` | chart mein history kam hai; F5 / scroll left |
| `ALIVE` line nahi aa rahi | `InpHeartbeatMinutes = 0` hai, yaa EA chart par nahi |
| `send notification` ka error | `alert_push` off kar dein, ya MetaQuotes ID set karein |

---

## 15. Log file ko baad mein parhna

```text
C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<terminal id>\MQL5\Logs\20261029.log
```

- Ek line mein waqt + tag + baat. Excel/Notepad++ mein khol kar `| SIGNAL |` se
  search karein - din ke saare signals.
- `| BLOCK |` se search: din bhar kis darwaze ne roka.
- `| ORDER |` se search: asli orders, tickets ke sath.
- `| ERROR |` se search: jo kaam nahi hua.

Ye wahi lines hain jo `dtcli` aur Python desk (`trader-mt5/mt5.py history`,
`journal`) parh sakte hain, kyunki wo bhi terminal ki history aur log use karte hain.

---

## 16. Ye internet se baat karta hai? Nahi.

Seedha jawab: **is EA ka koi server nahi hai**. Na hamara, na kisi ka. Wo sirf do
cheezon se baat karta hai:

1. **aap ka MetaTrader 5 terminal** (chart objects, indicators, prices, orders),
2. aur terminal khud **aap ke broker** se.

File mein aisa kuch maujood nahi:

| cheez | file mein? |
| --- | --- |
| `WebRequest()` (HTTP) | nahi |
| `SocketCreate` / `SocketConnect` / `SocketSend` (raw internet) | nahi |
| `URLDownloadToFile()` | nahi |
| `#import` / DLL calls | nahi |
| `FileOpen` se internet | nahi (EA koi file likhta bhi nahi) |
| `#include` | sirf `<Trade\Trade.mqh>`, jo MetaTrader ke sath aata hai |

Do cheezein aap ko "network" jaisi lag sakti hain, dono saaf hain:

- **`SendNotification()`** (phone push) - ye MetaQuotes ke push system se aap ke
  **apne** MetaQuotes ID par jata hai. Default **off** hai (`InpAlertPush = false`);
  jab tak aap khud on na karein, kuch nahi jata. Panel se bhi on/off ho sakta hai.
- **Global variables** (`DTMT5_C_*`, `DTMT5_<magic>_*`) - ye aap ke terminal ki
  apni memory mein rehte hain, disk par terminal ke folder mein. Kahin nahi jate.

Khud tasdeeq karein: MetaEditor mein `Ctrl+F` karke `WebRequest`, `Socket`,
`URLDownload`, `#import` search karein - kuch nahi milega. Automated test bhi
yahi check karta hai (`tests/test_ea.py`, `test_it_is_offline`).

Aur "kya ye trade lega" ka sabse pakka jawab **TEST page** hai (section 11.7):
11 gates PASS/NO, aur `RUN ORDER CHECK` jo terminal se poochta hai ke ye order
qabool hoga ya nahi - bhejta kuch nahi.

---

## 17. Trade kyun nahi le raha? Das second ka check

Sab se pehle **DASH page ki `next:` line** dekhein. Wo jumla hi jawab hai. Iske
mutabiq:

| `next:` line | matlab | kya karein |
| --- | --- | --- |
| `weekend: entries resume on Monday` | New York mein Sat/Sun | somwar ka intezar, ya `Weekdays only` off |
| `closed until 03:05 New York` | session ke bahar | CLOCK page se `Session start` badlein |
| `past flat-by 20:55: entries resume tomorrow` | din khatam | kal |
| `range still forming, ready by 04:05` | aaj ki opening range abhi bani nahi | intezar; CLOCK page se `Opening range` kam karein |
| `long: a M5 close above 2412.30 (shorts off)` | price range ke andar hai | intezar; ya RULE page se `Short entries` on |
| `close above 2412.30 but the trend is down` | break hai, EMA filter khilaaf | RULE page par `Trend filter` off, ya intezar |
| `a signal would be blocked: spread 34 over 25` | spread ceiling tight hai (gold par aam) | RULE page > `Max spread` 40-60, ya 0 (off) |
| `done for the day (1 of 1)` | aaj ki entry ho gayi | kal; `Entries per day` barha sakte hain |
| `daily loss stop: no more entries today` | aaj ka loss limit hit | kal; RISK page par limit dekh lein |
| `in a trade: stop and target are live` | position khuli hai | MANAGE page |
| `paused by you: press RESUME` | aap ne PAUSE dabaya tha | PAUSE dobara dabayein |

Agar `next:` line range break kehti hai (yani sab tayyar hai) par order phir bhi
nahi jata, to log mein **`BLOCK`** line dekhein - wahan ek hi gate ka naam hota
hai. Uske ilawa **TEST page** ke 11 gates hamesha sach batate hain; sab se aam
teen:

1. **REAL account aur `InpAllowLive = false`** - EA jaan boojh kar band hai.
2. **Terminal ka AutoTrading button off** (toolbar ka bara button).
3. **`Tools > Options > Expert Advisors > Allow algorithmic trading`** off.

Aur yaad rakhein rule kaise chalta hai: EA **har naye M5 bar par** ek dafa
dekhta hai (tick par nahi), default **din mein ek entry**, default **sirf long**,
aur entry sirf tab jab **band (closed) bar** range se bahar close kare. Is liye
"abhi tak kuch nahi hua" aksar sahi behaviour hota hai - aur `next:` line us
waqt bhi batati rehti hai ke kis price ka intezar hai.

---

## 18. Yaad rakhein

- Ye **financial advice nahi** hai. Zyada tar day traders paisa kho dete hain.
- Demo par pehle. REAL account `InpAllowLive = true` ke bagair band rehta hai.
- Stop guarantee nahi: gap ya fast market mein fill stop se aage ho sakta hai.
- EA sirf apne magic number ki trades chhoota hai. Aap ki haath se kholi trade
  na band hoti hai na modify.
- Panel sirf dikhata hai; faisla rule karta hai. Button dabane se rule nahi badalta
  (siwae PAUSE aur DRY ke, jo jaan boojh kar aap dabate hain).
