# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one executable for the whole day-trader pack.

Build it on the platform you want the binary for (PyInstaller does not cross
compile). On Windows, with MetaTrader5 installed first, the frozen binary can
talk to a running terminal; without it the binary still reads snapshots.

    python -m pip install pyinstaller MetaTrader5
    pyinstaller --clean --noconfirm trader-mt5/daytrader.spec

The result: dist/dtcli.exe (Windows) or dist/dtcli (macOS/Linux).
"""
import glob
import os

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(SPEC_DIR)                 # the folder holding trader-*/

# Every tool is a plain file loaded at runtime by dtcli, so PyInstaller cannot
# see their imports. Ship the files, and name the standard library modules they
# reach for, so urllib, csv, gzip and friends are inside the bundle.
datas = []
for folder in sorted(glob.glob(os.path.join(ROOT, "trader-*"))):
    if not os.path.isdir(folder):
        continue
    name = os.path.basename(folder)
    for pattern in ("*.py", "*.json"):
        for path in sorted(glob.glob(os.path.join(folder, pattern))):
            if os.path.basename(path) == "dtcli.py":
                continue                     # that one is the entry point
            datas.append((path, name))

hidden = [
    "argparse", "csv", "datetime", "decimal", "difflib", "email", "gzip", "hashlib",
    "importlib", "io", "json", "math", "os", "platform", "random", "re", "shutil",
    "statistics", "subprocess", "sys", "time", "urllib", "urllib.request", "urllib.parse",
    "urllib.error", "http.client", "http", "ssl", "socket", "xml", "xml.etree.ElementTree",
    "zipfile", "encodings.idna", "encodings.ascii",
]
try:
    import MetaTrader5                              # noqa: F401
    hidden.append("MetaTrader5")
except Exception:
    pass                                            # a replay-only build, still useful

a = Analysis(
    [os.path.join(SPEC_DIR, "dtcli.py")],
    pathex=[ROOT, SPEC_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "doctest", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="dtcli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                                   # a CLI: it must print
    disable_windowed_traceback=False,
)
