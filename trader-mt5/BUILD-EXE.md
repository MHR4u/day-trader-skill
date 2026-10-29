# dtcli.exe: the pack as one program (Hinglish)

Ek hi executable jo poore pack ki 13 tools chalata hai: `mt5`, `lots`, `size`,
`risk`, `ticket`, `alerts`, `scan`, `entry`, `exit`, `timemachine`, `news`,
`analyst`, `pelosi`.

```bat
dtcli.exe list
dtcli.exe mt5 doctor
dtcli.exe mt5 --replay snapshot.json --now "2026-10-20 09:35" account
dtcli.exe lots --write
dtcli.exe risk
dtcli.exe ticket show
```

Har tool apne **wahi** arguments leta hai jo script leta tha, aur wahi output
deta hai. `dtcli` sirf dispatcher hai.

---

## A. Seedha download (kuch install nahi)

GitHub Actions Windows par `dtcli.exe` bana kar rakhta hai:

1. GitHub par **Actions** tab kholein.
2. Left se **build-exe** workflow, phir latest green run.
3. Neeche **Artifacts** se `dtcli-windows.zip` download karein, extract karein:
   andar `dtcli.exe` hai. Bas.

## B. Khud build karein (Windows, 1 command)

Python 3.8+ installed hona chahiye ("Add python.exe to PATH" tick ho).

```bat
trader-mt5\build-exe.bat
```

Ye PyInstaller aur `MetaTrader5` install karta hai, phir:

```
dist\dtcli.exe
```

Agar `MetaTrader5` install nahi hota (ya aap build nahi karna chahte), binary
phir bhi kaam karta hai: `--replay` se sab reads, sizing, risk, backtest sab
chalte hain. Sirf live terminal ke liye package chahiye.

## C. Bina exe (sirf scripts)

```bat
python trader-mt5\mt5.py doctor
python trader-mt5\dtcli.py list
```

`dtcli.py` waise hi chalta hai jab Python installed ho. Exe sirf Python ki
zaroorat khatam karta hai.

---

## Exe ke saath kya, kya nahi

| andar hai | bahar hai (jaan boojh kar) |
| --- | --- |
| 12 skills ke saare Python tools | `trader/config.json` (aap banate hain: `dtcli.exe mt5 init --write`) |
| `config.example.json` jaise examples | `trader/` state folder: exe usi folder mein banata hai jahan se chalayein |
| Python runtime, `urllib`, `csv`, `gzip`, `xml` sab | `MetaTrader5` package, agar build ke waqt install na ho |
| `MetaTrader5` package, agar build ke waqt install ho | Claude skills ke taur par use karna (us ke liye `~/.claude/skills/`) |

**Yahan state jata hai:** `<jis folder se chalaya>/trader/`. Is liye apna trading
folder banayein, `dtcli.exe` wahan se chalayein, aur wo folder backup rakhein.

## Windows par pehli baar

```bat
cd C:\trading
C:\path\to\dtcli.exe mt5 doctor
C:\path\to\dtcli.exe mt5 init --write
C:\path\to\dtcli.exe env
```

`dtcli.exe env` batata hai: python version, platform, aur `MetaTrader5 package:
available` ya `not available`. Agar "not available" ho aur aap live terminal
chahte hain, to GitHub se wala artifact lein (us mein package andar hai), ya
section B se khud build karein.

## Test jo build ke baad chalte hain

- `dtcli.exe env` har tool ki file dhoondta hai (13/13 `ok`).
- `dtcli.exe mt5 --replay tests\fixtures\trader-mt5\context.json account` account dikhata hai.
- `dtcli.exe scan` aur `dtcli.exe news` load hote hain, yani `urllib` bundle mein hai.
- Poora suite build machine par pehle chalta hai: 391 tests.

## Chhoti baatein

- PyInstaller **cross compile nahi** karta: Windows exe Windows par banta hai,
  Linux par Linux binary. Is liye workflow `windows-latest` par chalta hai.
- Exe ~12-18 MB ka hota hai (onefile). Pehli baar chalne par thoda slow khulta
  hai (khud ko temp mein kholta hai), phir normal.
- Antivirus kabhi PyInstaller binaries ko flag karta hai (false positive).
  Chahein to `--onedir` se folder banayein, wo kam flag hota hai.
- `dtcli.exe` ke andar koi order khud se nahi jata: PASS + aap ka yes + terminal.
