#!/usr/bin/env python3
"""Run the specialist Gold research agents and write an auditable report.

  python3 factory.py demo --output /tmp/gold-demo
  python3 factory.py backtest --data XAUUSD_H1.csv --output /tmp/gold-single
  python3 factory.py walk-forward --data XAUUSD_H1.csv --output /tmp/gold-wf
  python3 factory.py review-ea

No command places a trade. Real tick validation must be repeated in MT5.
"""

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile

from gold import __version__
from gold.agents import BacktestAgent, DataAgent, EAAgent, RiskAgent, StrategyAgent, ValidationAgent
from gold.data import iso_time, parse_iso_date, synthetic_bars, timestamp
from gold.models import GoldError


ROOT = os.path.dirname(os.path.abspath(__file__))
EA_PATH = os.path.join(ROOT, "mt5", "GoldProfessionalEA.mq5")
TRADE_FIELDS = (
    "direction", "entry_time", "exit_time", "entry", "exit", "initial_volume", "exit_volume",
    "initial_stop", "initial_target", "exit_reason", "gross_pnl", "commission", "net_pnl",
    "r_multiple", "bars_held", "partial_pnl",
)


def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as exc:
        raise GoldError("Could not read config %s: %s" % (path, exc))
    for section in ("data", "account", "execution", "strategy", "risk", "exits", "validation"):
        if section not in config:
            raise GoldError("Config is missing the %s section" % section)
    return config


def override(config: dict, dotted: str, raw: str) -> None:
    parts = dotted.split(".")
    if len(parts) != 2 or parts[0] not in config:
        raise GoldError("Overrides use section.key, for example strategy.signal_timeframe=M15")
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw
    config[parts[0]][parts[1]] = value


def write_json(path: str, value: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def write_trades(path: str, trades: list) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.as_dict())


def write_equity(path: str, equity: list) -> None:
    if not equity:
        return
    # Preserve the first, last and all daily closes while bounding very large CSVs.
    selected = []
    previous_day = None
    for point in equity:
        day = str(iso_time(int(point["time"])))[:10]
        if day != previous_day:
            selected.append(point)
            previous_day = day
        elif selected:
            selected[-1] = point
    if selected[-1] != equity[-1]:
        selected.append(equity[-1])
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("time", "equity", "balance"))
        writer.writeheader()
        for point in selected:
            row = dict(point)
            row["time"] = iso_time(int(point["time"]))
            writer.writerow(row)


def summary_markdown(report: dict) -> str:
    validation = report["validation"]
    summary = validation["summary"]
    lines = [
        "# Gold EA research result",
        "",
        "Status: **%s**" % report["status"],
        "Deployment: **%s**" % report["deployment_status"],
        "",
        "This is an automated research result, not financial advice or a promise of profit.",
        "",
        "## Evidence",
        "",
        "- Mode: %s" % report["mode"],
        "- Data rows: %s" % report["data"]["rows"],
        "- Data coverage: %s to %s" % (report["data"]["start"], report["data"]["end"]),
        "- Data SHA-256: `%s`" % report["data"]["sha256"],
        "- Method: %s" % validation["method"],
        "- Equity file: concatenated per-fold OOS equity; each fold restarts from the configured initial balance",
        "- Resolved config SHA-256: `%s`" % report["config_hash"],
        "",
        "## Validation summary",
        "",
        "```json",
        json.dumps(summary, indent=2, sort_keys=True),
        "```",
        "",
        "## Gates",
        "",
    ]
    for name, passed in validation["checks"].items():
        lines.append("- %s: %s" % (name, "PASS" if passed else "FAIL"))
    lines.extend([
        "- data_coverage: %s" % ("PASS" if report["data"].get("coverage_pass", False) else "FAIL"),
        "- mt5_compile_and_real_tick_test: NOT RUN",
        "- demo_forward_test: NOT RUN",
        "",
        "## Required next step",
        "",
        "Use broker-specific XAUUSD data, compile the EA in MetaEditor, then run MT5 Every tick based on real ticks with variable spread. Keep new entries disabled until independent out-of-sample and demo forward tests are acceptable.",
        "",
        "The Python engine uses bars and a stop-first ambiguity rule. Its results can differ from MT5 tick execution, swaps, broker contract size, news blackout behavior and actual slippage.",
        "",
    ])
    return "\n".join(lines)


def execute(args: argparse.Namespace) -> dict:
    config = load_config(args.config)
    for item in args.override or []:
        if "=" not in item:
            raise GoldError("Overrides use section.key=value")
        key, raw = item.split("=", 1)
        override(config, key, raw)
    if getattr(args, "base_timeframe", None):
        config["data"]["base_timeframe"] = args.base_timeframe.upper()
    risk_agent = RiskAgent()
    risk_warnings = risk_agent.validate(config)
    strategy_agent = StrategyAgent()
    strategy_agent.candidates(config, False)
    trace = [{"agent": risk_agent.name, "status": "PASS", "warnings": risk_warnings},
             {"agent": strategy_agent.name, "status": "PASS", "rule": "closed_bar_donchian_with_completed_htf_ema"}]
    synthetic = args.command == "demo"
    if synthetic:
        bars = synthetic_bars(args.years, config["data"]["base_timeframe"], args.seed)
        identity = "synthetic:%d:%s:%d" % (args.years, config["data"]["base_timeframe"], args.seed)
        metadata = {
            "path": None, "sha256": hashlib.sha256(identity.encode("ascii")).hexdigest(),
            "rows": len(bars), "start": iso_time(bars[0].start), "end": iso_time(bars[-1].end),
            "base_timeframe": config["data"]["base_timeframe"], "coverage_pass": False,
            "required_start": config["validation"].get("require_data_since"),
            "warnings": ["Synthetic data is for software testing only, never strategy validation"],
            "synthetic": True, "seed": args.seed,
        }
        trace.append({"agent": "Data Agent", "status": "SYNTHETIC_ONLY", "rows": len(bars)})
    else:
        bars, metadata = DataAgent().load(args.data, config)
        metadata["source_url"] = args.source_url
        metadata["source_description"] = args.source_description
        metadata["synthetic"] = False
        trace.append({"agent": "Data Agent", "status": "PASS" if metadata["coverage_pass"] else "COVERAGE_FAIL",
                      "rows": len(bars), "warnings": metadata["warnings"]})
    validator = ValidationAgent(config)
    if args.command == "backtest":
        start = timestamp(parse_iso_date(args.start)) if args.start else None
        end = timestamp(parse_iso_date(args.end)) if args.end else None
        result = BacktestAgent().run(bars, config, start, end)
        validation = {
            "status": "RESEARCH_ONLY", "checks": {"out_of_sample_validation": False},
            "summary": result.metrics, "fold_details": [], "latest_training_parameters": {},
            "oos_trades": result.trades, "equity": result.equity, "blocks": result.blocks,
            "parameters": result.parameters, "method": "Single research run; no unseen-data gate",
        }
    else:
        validation = validator.walk_forward(bars, not args.no_optimize, args.keep_leaderboard)
    trades = validation.pop("oos_trades")
    equity = validation.pop("equity", [])
    blocks = validation.pop("blocks", {})
    trace.append({"agent": "Backtest Agent", "status": "COMPLETE", "trades": len(trades)})
    trace.append({"agent": "Validation Agent", "status": validation["status"], "checks": validation["checks"]})
    ea_review = EAAgent().review(EA_PATH)
    trace.append({"agent": "EA Review Agent", "status": "STATIC_PASS" if ea_review["static_pass"] else "STATIC_FAIL",
                  "compiled": False, "mt5_tick_test_passed": False})
    status = validation["status"]
    if synthetic:
        status = "SYNTHETIC_ONLY"
    elif not metadata["coverage_pass"] or not ea_review["static_pass"]:
        status = "RESEARCH_ONLY"
    validation["checks"]["data_coverage"] = bool(metadata["coverage_pass"])
    validation["checks"]["ea_static_review"] = bool(ea_review["static_pass"])
    validation["checks"]["mt5_compile_and_real_tick_test"] = False
    validation["checks"]["demo_forward_test"] = False
    config_blob = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    output = os.path.abspath(args.output)
    os.makedirs(output, exist_ok=True)
    write_json(os.path.join(output, "resolved_config.json"), config)
    write_json(os.path.join(output, "data_provenance.json"), metadata)
    write_trades(os.path.join(output, "trades.csv"), trades)
    write_equity(os.path.join(output, "equity.csv"), equity)
    EAAgent().write_set(os.path.join(output, "GoldProfessionalEA.research.set"), config,
                        validation.get("latest_training_parameters") or {})
    report = {
        "schema_version": 1,
        "factory_version": __version__,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mode": args.command,
        "status": status,
        "deployment_status": "MT5_VALIDATION_REQUIRED",
        "config_hash": hashlib.sha256(config_blob).hexdigest(),
        "data": metadata,
        "risk_warnings": risk_warnings,
        "entry_blocks": blocks,
        "validation": validation,
        "ea_review": ea_review,
        "agent_trace": trace,
        "limitations": [
            "No strategy can be certified profitable or professional by an in-sample or walk-forward backtest alone",
            "Python Bid-bar results are not MT5 real-tick results and do not include swaps or broker-specific contract changes",
            "The live calendar news filter is not reproduced by this CSV engine",
            "A PAPER_CANDIDATE still requires MT5 compilation, real-tick testing and demo forward validation",
            "New entries are disabled in the generated MT5 set file",
        ],
    }
    write_json(os.path.join(output, "report.json"), report)
    with open(os.path.join(output, "summary.md"), "w", encoding="utf-8") as handle:
        handle.write(summary_markdown(report))
    return report


def default_output(prefix: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return os.path.join(tempfile.gettempdir(), "gold-factory", "%s-%s" % (prefix, stamp))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--config", default=os.path.join(ROOT, "config.example.json"), help="JSON configuration")
    result.add_argument("--override", action="append", help="Override one section.key=value; repeatable")
    sub = result.add_subparsers(dest="command", required=True)
    for name, help_text in (("demo", "Run walk-forward research on synthetic bars"),
                            ("backtest", "Run one CSV backtest, without an OOS pass claim"),
                            ("walk-forward", "Optimize on training windows and test unseen windows")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--output", default=default_output(name), help="Artifact directory")
        if name == "demo":
            command.add_argument("--years", type=int, default=8)
            command.add_argument("--seed", type=int, default=19)
        else:
            command.add_argument("--data", required=True, help="OHLC CSV or CSV.gz")
            command.add_argument("--base-timeframe", help="Input CSV timeframe, for example M1, H1 or D1")
            command.add_argument("--source-url", help="Data provenance URL")
            command.add_argument("--source-description", help="Provider and instrument details")
        if name == "backtest":
            command.add_argument("--start", help="Optional ISO entry start")
            command.add_argument("--end", help="Optional ISO entry end")
        else:
            command.add_argument("--no-optimize", action="store_true", help="Use baseline parameters in every fold")
            command.add_argument("--keep-leaderboard", action="store_true", help="Include all training scores in report.json")
    review = sub.add_parser("review-ea", help="Run static MT5 source checks")
    review.add_argument("--output", default=default_output("ea-review"))
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "review-ea":
            review = EAAgent().review(EA_PATH)
            os.makedirs(os.path.abspath(args.output), exist_ok=True)
            write_json(os.path.join(os.path.abspath(args.output), "ea_review.json"), review)
            print(json.dumps(review, indent=2, sort_keys=True))
            return 0 if review["static_pass"] else 1
        report = execute(args)
        summary = report["validation"]["summary"]
        print("Status: %s" % report["status"])
        print("Deployment: %s" % report["deployment_status"])
        print("Artifacts: %s" % os.path.abspath(args.output))
        print("Validation: %s" % json.dumps(summary, sort_keys=True))
        if not report["data"].get("coverage_pass", False) and args.command != "demo":
            print("Coverage gate failed: the data does not start at the requested 2000 date.")
        print("No live approval: compile and run real-tick MT5 tests, then demo forward test.")
        return 0
    except GoldError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
