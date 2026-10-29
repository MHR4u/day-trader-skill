# CONSOLE.md - DayTraderMT5 ka console aur dashboard, ek ek chez

Ye file sirf `DayTraderMT5.mq5` ke bare mein hai. Do hisse hain:

1. **Console** - jo lines `Experts` tab mein aati hain (aur log file mein rehti hain).
2. **Dashboard** - jo chart par panel banta hai, teen buttons ke sath.

Dono ka ek hi maqsad: aapko har waqt pata ho ke EA ne kya dekha, kya socha,
kya kiya, aur agar kuch nahi kiya to kyun nahi kiya.

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
| `INIT` | EA chart par lagte waqt | version, symbol, account, magic, banner |
| `CONF` | wahin, startup par | poora config: rule, stop, clock, risk, limits, broker levels, manage |
| `GATE` | startup par, aur jab trade rukta ho | terminal/account/broker ki ijazat, ya `InpAllowLive` ki deewar |
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

---

## 4. Startup par jo aata hai

```
2026.10.29 13:58:02 | INIT  | -------------------------------------------------------------
2026.10.29 13:58:02 | INIT  | DayTraderMT5 v1.10 on XAUUSD M5, account DEMO #5001234, magic 20261019
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
2026.10.29 13:58:02 | INIT  | dashboard: on the chart, with PAUSE, DRY and CLOSE OURS
2026.10.29 13:58:02 | INIT  | -------------------------------------------------------------
```

Ye poora block **har attach par** aata hai. Isay parh kar aap 10 second mein
jaan jate hain ke EA kis cheez par chal raha hai. Agar yahan kuch ajeeb ho (galat
symbol, galat session, `long only` jab aap short bhi chahte hain), to `Inputs` se
theek karein - baad mein dhoondna nahi parega.

`GATE` ki do aur shakalein:

```
| GATE  | trading is not allowed yet: the AutoTrading button in the toolbar is off
| GATE  | REAL account and InpAllowLive is false: this EA will read and log, and will not trade.
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

## 11. Dashboard: chart par panel

Panel chart objects se banta hai: koi DLL nahi, koi file nahi, koi resource nahi.
Ek dafa banta hai, phir sirf text badalta hai. Isi liye ye chart ko slow nahi karta.

```
+----------------------------------------------------+
| DayTraderMT5                              DEMO     |   <- header, account ka type
+----------------------------------------------------+
| = MARKET                                           |
|   Symbol / rule   XAUUSD  M5                       |
|   New York        2026.10.29 14:05  EDT            |
|   Session         03:05-19:00  OPEN                |
|   [======================--------------]           |   <- session ka kitna hissa guzra
| = OPENING RANGE                                    |
|   High / low      2393.40  2388.10                 |
|   Mid             2390.75                          |
|   Width / bars    530 pts, 12 bars                 |
| = INDICATORS                                       |
|   EMA 50/200      2394.80  2380.10                 |
|   Trend           up                               |
|   ATR / spread    2.00  /  12 pts  (max 25)        |
| = TODAY                                            |
|   Entries         1 of 1                           |
|   Realised        34.20 USD                        |
|   Loss room       115.80 of 150.00                 |
| = POSITION                                         |
|   Ticket / side   #132889001  BUY                  |
|   Lots / entry    0.42  @  2394.10                 |
|   Stop / target   2387.40  2404.20                 |
|   Progress        0.72R, 21.60 USD                 |
|   [=============-----------------------]           |   <- 1R tak ka safar
| = RISK AND SIZE                                    |
|   Budget / trade  50.00 USD                        |
|   Caps            2.00 lots, 40% margin, 1.50R     |
| = STATUS                                           |
|   Trading         yes                              |
|   Mode            DEMO  1 open                     |
|   Last            SIGNAL  BUY signal: M5 closed...  |
|                                                    |
|  [ PAUSE ]  [ DRY: OFF ]  [ CLOSE OURS ]           |
| magic 20261019, quiet log, v1.10                   |
+----------------------------------------------------+
```

### 11.1 Har khaane ka matlab

| khaana | matlab | rang |
| --- | --- | --- |
| header ka naam | panel EA ka hai | safaid |
| header ka `DEMO` / `REAL` / `CONTEST` | account ka type | `DEMO` hara, `REAL` lal, `CONTEST` peela |
| `Symbol / rule` | symbol aur rule ka timeframe (`InpTimeframe`, chart ka nahi) | - |
| `New York` | New York ka waqt aur `EDT`/`EST`; `server` likha ho to `InpNewYorkTimes = false` | - |
| `Session` | window aur `OPEN`/`closed` | khula hara, band bhoora |
| session bar | window ka kitna hissa guzar gaya | neela |
| `High / low` | aaj ke opening range ke do kinare; `still forming` ka matlab range ban raha hai | peela jab tak ban raha ho |
| `Mid` | range ka beech; stop is se tight nahi hota | - |
| `Width / bars` | range kitne points chaura, kis kitne bar se bana | - |
| `EMA 50/200` | dono EMA ki abhi ki value (last closed bar) | - |
| `Trend` | `up`, `down`, `flat` (aur `flat (no EMA yet)`) | up hara, down lal |
| `ATR / spread` | ATR ki value, spread points mein, aur aap ki max | spread max se zyada ho to lal |
| `Entries` | aaj ke entries / `InpMaxTradesPerDay` | quota poora ho to peela |
| `Realised` | aaj ka band shuda nafa/nuqsan (commission aur swap ke sath) | nafa hara, nuqsan lal |
| `Loss room` | daily loss stop tak kitni gunjaish bachi | khatam ho to lal, `STOPPED for the day` |
| `Ticket / side` | apni khuli position, `#ticket  BUY/SELL` | BUY hara, SELL lal |
| `Lots / entry` | volume aur entry price | - |
| `Stop / target` | SL aur TP; `none` agar set nahi | - |
| `Progress` | 1R ke hisaab se kitna chala, aur abhi ka P/L | R positive safaid, negative lal |
| R bar | 1R tak ka safar (1R par bharta hai) | hara |
| `Budget / trade` | `InpRiskPercent`/`InpRiskMoney` mein se jo chhota ho, rupees/dollar mein | - |
| `Caps` | lot cap, margin cap, R multiple | - |
| `Trading` | `yes`, ya wajah: `paused from the panel`, `dry run, nothing is sent`, `no: <wajah>` | yes hara, pause/dry peela, no lal |
| `Mode` | account type + `LIVE BLOCKED` + `DRY` + `PAUSED` + kitni position khuli | LIVE BLOCKED lal |
| `Last` | sabse aakhri console line (chhoti kar ke) | bhoora |
| footer | magic number, log mode, version | bhoora |

`Trading` ka `no:` hissa wahi wajah hai jo `GATE` / `BLOCK` line mein aati hai,
bas yahan hamesha nazar aati hai - scroll karne ki zaroorat nahi.

### 11.2 Teen button

| button | pehla click | rang | kya band nahi hota |
| --- | --- | --- | --- |
| `PAUSE` / `RESUME` | naye entries band/chalu | pause par peela | management, breakeven, trailing, flat-by - sab jari rehta hai |
| `DRY: OFF` / `DRY: ON` | `InpDryRun` ko live badalta hai | on par peela | `InpAllowLive` ki deewar nahi hatti |
| `CLOSE OURS` | sirf arm hota hai; 6 second ke andar doosra click band karta hai | armed par lal, `CONFIRM?` | doosri company ki ya haath se kholi trade ko chhoota nahi |

`CLOSE OURS` par do click kyun? Kyunki ek ghalti se poora din ka kaam band ho
jana chahiye nahi. 6 second mein doosra click na aaye to kuch nahi hota, aur
console par (quiet) line aati hai.

Button dabane par panel foran update hota hai - 5 second ka intezar nahi.

### 11.3 Panel ko hataana / jagah badalna

- `InpShowPanel = false` - panel bilkul nahi banega.
- `InpPanelX`, `InpPanelY` - pixels mein doori, left/top se. Chart ke doosre corner
  mein chahiye to dono barha dein.
- Panel `ChartRedraw` ke sath update hota hai: naya bar, har 5 second, aur har click.

---

## 12. Har input, ek ek

33 inputs, 7 groups. Dialog mein har input ke aage comment bhi likha hai.

### Group: The gates

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpAllowLive` | `false` | REAL account par trade ki ijazat | sirf demo par tassalli ke baad |
| `InpDryRun` | `false` | sirf log, order nahi | pehle din, ya test ke liye |
| `InpMagic` | `20261019` | EA ki apni label | do EA ek chart par hon to alag |

### Group: Risk and size

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpRiskPercent` | `1.0` | equity ka %, per trade | account ke hisaab se |
| `InpRiskMoney` | `50.0` | fixed amount, per trade | chhote account par |
| `InpMaxLots` | `2.0` | ek order ka hard cap | bade account par |
| `InpMaxMarginPct` | `40.0` | free margin ka max % | conservative rehne ke liye kam |
| `InpMaxSpreadPoints` | `25.0` | is se zyada spread par entry nahi | symbol ke hisaab se (`0` = off) |
| `InpMinRR` | `1.5` | target ka R | 1.0 se kam na karein |

Note: percent aur money dono `0` na hon; dono diye hon to **chhota** jeetta hai.

### Group: The rule

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpTimeframe` | `M5` | rule ka timeframe | M1 (tez) ya M15 (kam signal) |
| `InpEmaFast` | `50` | tez EMA | 20 for scalping |
| `InpEmaSlow` | `200` | slow EMA | 100 for zyada signal |
| `InpORMinutes` | `60` | opening range ki lambai | 30 for tez din |
| `InpAtrMult` | `0.5` | ATR ka kitna hissa stop mein | 0.75 wide stop |
| `InpAllowShort` | `false` | neeche break par sell | chahein to `true` |

### Group: The clock (New York waqt)

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpNewYorkTimes` | `true` | neeche ke waqt NY mein | `false` = server time |
| `InpSessionStart` | `03:05` | entry na karne ka waqt shuru | pre-market 04:00 chahiye to |
| `InpSessionEnd` | `19:00` | is ke baad entry nahi | closing bell 16:00 |
| `InpFlatBy` | `20:55` | sab band | 15:55 agar regular hours |
| `InpWeekdaysOnly` | `true` | Sat/Sun nahi | off karne ki wajah nahi |
| `InpMaxTradesPerDay` | `1` | din ke entries | 2-3 agar zyada chahiye |
| `InpMaxDailyLoss` | `150.0` | din ka realised loss stop | apne account ka 1-3% |

### Group: Managing the trade

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpBreakevenAtR` | `1.0` | entry par stop | `0` = off |
| `InpTrailAtR` | `1.0` | trailing shuru | `1.5` = late |
| `InpTrailPoints` | `150` | trail ki doori (points) | symbol ke ATR ke hisaab se |
| `InpPartialAtR` | `0.0` | partial close ka R | `2.0` = 2R par |
| `InpPartialPercent` | `50.0` | kitna % band | 33 ya 50 |

### Group: Console and panel

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpShowPanel` | `true` | chart par dashboard | off agar chart saaf chahiye |
| `InpPanelX` | `14` | left se doori | doosre corner ke liye |
| `InpPanelY` | `24` | top se doori | wahi |
| `InpVerbose` | `false` | har bar par RULE line | debugging ke din ke liye |

### Group: Plumbing

| input | default | matlab | kab badlein |
| --- | --- | --- | --- |
| `InpDeviationPoints` | `20` | slippage ki ijazat | fast market mein 30-40 |
| `InpStopBufferPoints` | `10` | broker ki stops level ke upar buffer | `10016` aaye to 20-30 |

---

## 13. File ka naksha: kaun function kya karta hai

`DayTraderMT5.mq5` ko 10 hisson mein parhein. Har hissa upar se neeche hai, aur
MQL5 ka rule hai ke helper pehle, call baad mein.

| hissa | functions | kaam |
| --- | --- | --- |
| Header | `#property` | version, copyright, link, description |
| Inputs | 33 `input` | groups: gates, risk, rule, clock, manage, panel, plumbing |
| Globals | `g_*` | inputs ki copy, handles, counters, panel cursor |
| Console | `Log`, `LogRule`, `Clip`, `Money` | ek hi jagah se har line, tag ke sath |
| Chhote helpers | `ParseHHMM`, `HHMM`, `MinutesOfDay`, `DayIndexOf`, `WeekdayOf`, `WeekdayOfMonth`, `PeriodDescription`, `RiskWords` | waqt aur text ki chhoti cheezein |
| Time | `ToNewYork`, `InWindow`, `PastTime` | server clock se New York, DST ke sath |
| Gates | `IsLiveAccount`, `AccountModeWord`, `TerminalReady` | kya trading ki ijazat hai, aur nahi to kyun |
| Data | `LoadRates`, `IndicatorValue`, `TrendUp`, `TrendDown`, `TrendWord`, `AtrValue`, `OpeningRange` | bars, EMA, ATR, opening range |
| Hisaab | `CountEntriesToday`, `RealisedToday` | aaj ke entries aur P/L, account ki history se |
| Sizing | `MoneyPerLotPerPrice`, `RiskBudget`, `FloorToStep`, `LadderFits`, `VolumeFits`, `MarginFits`, `SizeLots` | lots, broker ki ladder, margin |
| Stops | `MinStopPoints`, `SpreadPoints` | broker ki kam se kam doori, spread |
| Positions | `OurPositions`, `MarkName`, `Marked`, `Mark`, `PruneMarks` | siraf apni trades, breakeven/trail/partial ki yaaddasht |
| Entry | `TryEntry` | 6 darwaze, stop, target, size, send |
| Manage | `ManagePositions`, `CloseAllOurs` | breakeven, trailing, partial, flat-by |
| Dashboard | `DeletePanel`, `UiRect`, `UiText`, `UiButton`, `Clamp01`, `UiBar`, `UiSection`, `UiRow`, `NyWord`, `SessionFraction`, `OurPosition`, `UpdatePanel` | panel ke sab objects |
| Entry points | `OnChartEvent`, `OnInit`, `OnDeinit`, `OnTimer`, `OnTick` | MT5 ke 5 callbacks |

`OnTick` ka order hamesha yahi hai: **naya din check -> flat-by -> manage -> naye
bar par rule -> panel**. Flat-by pehle kyun? Kyunki waqt guzar gaya to sabse pehle
band karna hai, chahe rule kuch bhi kahe.

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
| `BLOCK ... spread is 34 points` | news ke baad dobara; ya ceiling barhayein |
| `BLOCK ... smallest lot risks more` | risk barhayein ya sasta symbol |
| `ERROR ... 10016 invalid stops` | `InpStopBufferPoints = 20` |
| `ERROR ... 10019 no money` | lot/risk/margin cap kam |
| `ERROR ... 10027` | algo trading on |
| `ERROR ... 10018` | market band, kuch nahi |
| kuch bhi nahi aa raha | `Journal` tab dekhein; EA attach hai? AutoTrading on? |
| panel nahi dikh raha | `InpShowPanel`, ya `InpPanelX/Y` screen se bahar |
| panel ke numbers purane lagte hain | 5 second ka timer, ya naya bar; F5 se chart refresh |

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

## 16. Yaad rakhein

- Ye **financial advice nahi** hai. Zyada tar day traders paisa kho dete hain.
- Demo par pehle. REAL account `InpAllowLive = true` ke bagair band rehta hai.
- Stop guarantee nahi: gap ya fast market mein fill stop se aage ho sakta hai.
- EA sirf apne magic number ki trades chhoota hai. Aap ki haath se kholi trade
  na band hoti hai na modify.
- Panel sirf dikhata hai; faisla rule karta hai. Button dabane se rule nahi badalta
  (siwae PAUSE aur DRY ke, jo jaan boojh kar aap dabate hain).
