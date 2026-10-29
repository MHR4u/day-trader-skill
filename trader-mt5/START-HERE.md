# START HERE (Hinglish): 10 minute mein chalu karein

Ye poora `day-trader-skill` pack hai, MetaTrader 5 desk ke sath (12 skills).
Sab kuch plain Python 3.8+ hai. MT5 ke asli terminal ke liye **Windows** chahiye;
baqi sab (sizing, risk, backtest, tests) har OS par chalta hai.

---

## 1. Folder kholein

Zip se nikala hua folder, ya `git clone` kiya hua repo. Us folder mein terminal
(`cmd`, PowerShell, ya bash) kholein.

## 2. Python check

```bash
python3 --version        # Windows par: python --version
# 3.8 ya us se naya
```

## 3. Pehle bina terminal: sab kuch chal raha hai ya nahi

```bash
python3 -m unittest discover -s tests
# Ran 391 tests ... OK
```

Ye ek synthetic demo broker (GMT+3) par chalta hai, internet ki zaroorat nahi.
Agar 391 OK aaye to pack theek hai.

## 4. MetaTrader 5 se jodna (Windows)

1. MetaTrader 5 kholein, **demo** account se login karein, terminal khula rakhein.
2. Terminal mein: `Tools > Options > Expert Advisors > Allow algorithmic trading` ON,
   toolbar ka **AutoTrading** button bhi ON.
3. Python package (sirf Windows):
   ```bash
   python -m pip install MetaTrader5
   ```
4. Pack folder mein:
   ```bash
   python trader-mt5/mt5.py doctor
   #   account: 5001234 DEMO on Broker-Demo, balance 5000 USD
   #   server offset: UTC+3 (detected from a tick)
   #   account trading allowed: True, algo trading: True
   python trader-mt5/mt5.py init --write           # trader/config.json ban jata hai
   python trader-mt5/mt5.py symbols --search EUR   # broker ke asli naam: EURUSD.a ...
   ```

Agar `doctor` mein `MetaTrader5 package: NOT available` aaye to step 3 dobara karein,
aur `initialize failed` aaye to terminal khula + logged in hona chahiye.

## 5. Apna config set karein

`trader/config.json` kholein aur apne broker ke hisaab se badlein:

```json
"max_loss_per_trade_usd": 50,
"max_daily_loss_usd": 150,
"min_reward_risk": 1.0,
"paper": true,
"mt5": {
  "allow_live": false,
  "commission_per_lot": 7.0,
  "symbols": ["EURUSD.a", "XAUUSD"],
  "max_spread_pips": 2.0,
  "max_margin_use_pct": 40
}
```

`allow_live` ko `false` hi rakhein jab tak demo par tassalli na ho.

## 6. Ek trade, 8 commands

```bash
# 1) aaj kis symbol mein setup hai
python trader-mt5/mt5.py scan --symbols EURUSD,XAUUSD --tf M15

# 2) plan + snapshot
python trader-mt5/mt5.py setup EURUSD --tf M15 --write-plan
python trader-mt5/mt5.py snapshot --write

# 3) lots
python trader-budget/lots.py --write

# 4) risk check
python trader-risk/check.py

# 5) ticket + aap ka yes
python trader-broker/ticket.py show
python trader-broker/ticket.py approve --index 1 --reply "yes"

# 6) send (teesra darwaza)
python trader-mt5/mt5.py execute --index 1

# 7) manage
python trader-mt5/mt5.py positions
python trader-mt5/mt5.py manage breakeven --symbol EURUSD --at-r 1 --yes "yes"
python trader-mt5/mt5.py manage close --symbol EURUSD --yes "yes"

# 8) hisaab
python trader-mt5/mt5.py history --days 30 --write
```

Har order ke liye teen cheezein lazmi hain: `check.py` ka **PASS**, aap ka saaf
**"yes"**, aur `mt5.py execute`. "sure" ya "ok" kaam nahi karta.

## 7. Bina Windows / bina terminal (macOS, Linux, ya sirf seekhne ke liye)

Pack ke sath ek demo snapshot hai, usi par sab commands chalti hain:

```bash
python3 trader-mt5/mt5.py --replay tests/fixtures/trader-mt5/context.json \
  --now "2026-10-20 09:35" account
python3 trader-mt5/mt5.py --replay tests/fixtures/trader-mt5/context.json \
  --now "2026-10-20 09:35" scan --tf M5
python3 trader-mt5/mt5.py --replay tests/fixtures/trader-mt5/positions.json \
  --now "2026-10-20 09:35" positions
```

`--replay` har read us file se leta hai; `execute` bhi replay par test ho sakta hai.

## 8. Claude mein use karna

Pack `~/.claude/skills/` mein daal dein (ya project ke `.claude/skills/` mein):

```bash
cp -r trader-* ~/.claude/skills/
```

Phir Claude mein: `/trader-mt5`, `/trader-risk`, `/trader-budget`, `/trader-broker`.
Bina Claude Code ke: `trader-mt5/SKILL.md` ko chat ke shuru mein paste kar dein.

## 9. Files

| file | kya hai |
| --- | --- |
| `README.md` | poore pack ka overview (12 skills) |
| `trader-mt5/SKILL.md` | MT5 desk ka poora manual |
| `trader-mt5/GUIDE-urdu.md` | yehi cheez Urdu/Hinglish mein, detail ke sath |
| `trader-mt5/mt5.py` | terminal, data, execute, manage, guard, backtest |
| `trader-budget/lots.py` | lots sizing |
| `trader-budget/config.example.json` | default limits + `mt5` block |
| `tests/` | 391 tests + demo broker fixtures |

## 10. Yaad rakhein

- Ye **financial advice nahi** hai. Zyada tar day traders paisa kho dete hain.
- Demo pehle; `allow_live: false` default hai, REAL account us ke bagair block rehta hai.
- Stop guarantee nahi: fast market ya gap mein fill us se aage ho sakta hai.
- MT5 package Windows-only hai; baqi sab pure Python hai.
