"""dtcli: the whole day-trader pack behind one command (and one .exe).

The twelve skills are plain Python files, each with a ``main(argv)``. This
launcher finds them, loads the one you named, and hands over the arguments, so
a single frozen executable can run every tool:

    dtcli list
    dtcli mt5 --replay snapshot.json account
    dtcli lots --write
    dtcli risk
    dtcli ticket show

Frozen (PyInstaller) builds look for the tools in the bundle; a checkout looks
next to this file. ``DAYTRADER_HOME`` overrides both, which is handy when the
tools live somewhere else.

Nothing here changes a tool's behaviour: same arguments, same output, same
exit codes. It is a dispatcher, not a wrapper.
"""
import difflib
import importlib.util
import os
import sys

VERSION = "2.1.0"

# key -> (folder, file, one line). Order is the order `dtcli list` prints.
TOOLS = {
    "mt5": ("trader-mt5", "mt5.py",
            "MetaTrader 5 desk: account, spec, quote, bars, scan, setup, session, snapshot, "
            "positions, orders, history, margin, execute, manage, guard, backtest"),
    "lots": ("trader-budget", "lots.py",
             "size an MT5 trade in lots from your risk budget -> trader/orders.json"),
    "size": ("trader-budget", "size.py",
             "size a share trade from your budget (the US half)"),
    "risk": ("trader-risk", "check.py",
             "PASS or BLOCK against your limits, shares and MT5 orders both"),
    "ticket": ("trader-broker", "ticket.py",
               "the plain-words ticket, your yes, and the exact order that follows"),
    "alerts": ("trader-alerts", "alerts.py",
               "price, stop, target and flat-by alerts"),
    "scan": ("trader-scanner", "scan.py",
             "scan US charts for setups (Yahoo data)"),
    "entry": ("trader-entry", "entry.py",
              "watch one setup bar by bar, offline files included"),
    "exit": ("trader-exit", "exit.py",
             "the stop and the target, written down before the entry"),
    "timemachine": ("trader-timemachine", "timemachine.py",
                    "replay the rest of the session 10,000 times"),
    "news": ("trader-news", "news.py",
             "headlines and filings for a ticker"),
    "analyst": ("trader-analyst", "facts.py",
                "earnings facts from SEC XBRL"),
    "pelosi": ("trader-pelosi", "ptr.py",
               "Congress's stock-trade disclosures"),
}


class ToolMissing(Exception):
    """A tool file is not where the launcher looked."""


def root():
    """Where the twelve folders live."""
    override = os.environ.get("DAYTRADER_HOME")
    if override:
        return os.path.abspath(override)
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tool_path(key):
    folder, filename, _ = TOOLS[key]
    return os.path.join(root(), folder, filename)


def load(key):
    """Import the named tool by path (the folder names have hyphens, so they
    are not importable as packages)."""
    path = tool_path(key)
    if not os.path.isfile(path):
        raise ToolMissing("cannot find %s (looked in %s). If you froze this binary, rebuild it; "
                          "if you are running from a checkout, run it from the repo, or set "
                          "DAYTRADER_HOME to the folder that holds the trader-* folders."
                          % (path, root()))
    folder = os.path.dirname(path)
    if folder not in sys.path:
        sys.path.insert(0, folder)          # so a tool can import its own siblings (mt5lib)
    spec = importlib.util.spec_from_file_location("dtcli_%s" % key, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def usage():
    lines = ["dtcli %s: the day-trader pack in one command" % VERSION, "",
             "usage: dtcli <tool> [the tool's own arguments]", "",
             "tools:"]
    for key in TOOLS:
        folder, filename, what = TOOLS[key]
        lines.append("  %-12s %s" % (key, what))
    lines += ["",
              "examples:",
              "  dtcli mt5 doctor",
              "  dtcli mt5 --replay snapshot.json --now \"2026-10-20 09:35\" account",
              "  dtcli lots --write && dtcli risk && dtcli ticket show",
              "",
              "  dtcli list          this list",
              "  dtcli env           where the tools are, and what this build can reach",
              "  dtcli <tool> --help that tool's own help",
              "",
              "Nothing sends an order without a passing risk check, your recorded yes, and the terminal."]
    return "\n".join(lines)


def environment():
    import platform
    lines = ["dtcli %s" % VERSION,
             "python %s" % platform.python_version(),
             "platform %s" % platform.platform(),
             "frozen %s" % bool(getattr(sys, "frozen", False)),
             "root %s" % root()]
    for key in TOOLS:
        path = tool_path(key)
        lines.append("  %-12s %s" % (key, "ok" if os.path.isfile(path) else "MISSING (%s)" % path))
    try:
        import MetaTrader5                      # noqa: F401
        lines.append("MetaTrader5 package: available (the real terminal works on Windows)")
    except Exception as e:
        lines.append("MetaTrader5 package: not available (%s)" % e)
        lines.append("  the terminal needs it; every read still works with --replay, and sizing and risk "
                     "are pure Python")
    return "\n".join(lines)


def console():
    """Windows consoles are cp1252 by default; a stray arrow must not crash a
    trade report. Ask for UTF-8 and never raise on an unprintable character."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass                       # a StringIO, or a stream that cannot change


def main(argv=None):
    console()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help", "list"):
        print(usage())
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print("dtcli %s" % VERSION)
        return 0
    if argv[0] in ("env", "doctor?"):
        print(environment())
        return 0
    key, rest = argv[0], argv[1:]
    if key not in TOOLS:
        close = difflib.get_close_matches(key, list(TOOLS), n=2)
        hint = (" Did you mean %s?" % " or ".join(close)) if close else ""
        print("dtcli: no tool called %r.%s Run \"dtcli list\" for the twelve." % (key, hint), file=sys.stderr)
        return 2
    try:
        mod = load(key)
    except ToolMissing as e:
        print("dtcli: %s" % e, file=sys.stderr)
        return 1
    try:
        code = mod.main(rest)
    except SystemExit as e:                     # argparse's --help and its errors
        return int(e.code or 0)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 130
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
