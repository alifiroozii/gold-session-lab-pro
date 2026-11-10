"""Prepare bounded MT5 runs and retain raw evidence in a local SQLite registry."""
import argparse
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

from research.parse_report import parse_report, read_mt5_text

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "XAUUSD_o"
SPLITS = {
    "training": (date(2024, 11, 1), date(2025, 11, 1)),
    "validation": (date(2025, 11, 1), date(2026, 5, 1)),
    "holdout": (date(2026, 5, 1), date(2026, 11, 1)),
}
STRATEGIES = ("breakout", "sweep", "range")
MODES = ("fast", "standard", "conservative")
REFERENCES = ("asia-utc", "asia-ny", "london", "ny-open", "previous-day", "previous-week", "london-utc")
VARIANT_KEYS = ("source_sha256", "strategy", "mode", "reference", "broker", "leverage")


def months(start, end):
    cursor = start.replace(day=1)
    while cursor < end:
        yield cursor.strftime("%Y%m")
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def source_hash():
    digest = hashlib.sha256()
    for path in sorted((ROOT / "mql5").rglob("*")):
        if path.suffix in {".mq5", ".mqh"} and "tests" not in path.relative_to(ROOT / "mql5").parts:
            digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def settings(config):
    return (
        f"ExpectedSymbol={SYMBOL}\nServerClock=2\n"
        f"Reference={REFERENCES.index(config['reference'])}\n"
        f"Strategy={STRATEGIES.index(config['strategy'])}\nMode={MODES.index(config['mode'])}\n"
        "SignalAuditOnly=false\n"
    )


def tester_ini(config, experiment_id):
    start, end = SPLITS[config["split"]]
    return (
        "[Common]\nNewsEnable=0\n"
        "[Experts]\nAllowLiveTrading=0\nAllowDllImport=0\nEnabled=0\n"
        "[Tester]\nExpert=GoldResearchLab.ex5\n"
        f"ExpertParameters={experiment_id}.set\nSymbol={SYMBOL}\nPeriod=M5\n"
        f"Model=4\nFromDate={start:%Y.%m.%d}\nToDate={end:%Y.%m.%d}\n"
        f"Deposit=1000\nCurrency=USD\nLeverage=1:{config['leverage']}\nExecutionMode=0\n"
        "Optimization=0\nForwardMode=0\nVisual=0\nUseLocal=1\nUseRemote=0\nUseCloud=0\n"
        f"Report=Reports\\{experiment_id}.htm\nReplaceReport=0\nShutdownTerminal=1\n"
    )


def registry(path):
    path.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path / "experiments.sqlite")
    db.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY, config TEXT NOT NULL, status TEXT NOT NULL,
            detail TEXT NOT NULL, summary TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return db


def prepare(args):
    start, end = SPLITS[args.split]
    config = dict(
        split=args.split, from_inclusive=start.isoformat(), to_exclusive=end.isoformat(),
        symbol=SYMBOL, broker=args.broker, strategy=args.strategy, mode=args.mode, reference=args.reference,
        leverage=args.leverage, hypothesis=args.hypothesis, source_sha256=source_hash(),
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        currency="USD", deposit=1000, tester_model=4, visual=False, execution_mode=0,
        risk_pct=3, day_loss_pct=6, max_entries_per_day=10, max_lot=0.06,
        commission_reserve_per_lot=10, slippage_reserve_price=0.20,
    )
    # Hypothesis wording and metadata commits do not create duplicate experiments.
    identity = {key: config[key] for key in (*VARIANT_KEYS, "split")}
    experiment_id = "gl-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    if args.tick_cache.parts[-3:] != (args.broker, "ticks", SYMBOL):
        raise ValueError("Point --tick-cache to the named broker's ticks/XAUUSD_o directory")
    missing = [
        month for month in months(start, end)
        if not (args.tick_cache / f"{month}.tkc").is_file()
        or (args.tick_cache / f"{month}.tkc").stat().st_size == 0
    ]
    status = "MISSING_TICKS" if missing else "COVERAGE_REVIEW_REQUIRED"
    detail = {"missing_months": missing, "tick_cache": str(args.tick_cache.resolve())}
    with closing(registry(args.output)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT status FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if row and row[0] not in {"MISSING_TICKS", "COVERAGE_REVIEW_REQUIRED"}:
            raise ValueError(f"Experiment already recorded as {row[0]}")
        if args.split == "holdout":
            validation = db.execute(
                "SELECT config,status FROM experiments WHERE id=?", (args.frozen_validation,)
            ).fetchone()
            if not validation or validation[1] != "REVIEWABLE":
                raise ValueError("Holdout requires a frozen, reviewable validation experiment")
            validated = json.loads(validation[0])
            if validated["split"] != "validation" or any(validated[key] != config[key] for key in VARIANT_KEYS):
                raise ValueError("Holdout parameters differ from frozen validation")
            other = db.execute(
                "SELECT id FROM experiments WHERE json_extract(config,'$.split')='holdout' AND id!=?",
                (experiment_id,),
            ).fetchone()
            if other:
                raise ValueError("A different holdout candidate was already frozen in this registry")
            config["frozen_validation"] = args.frozen_validation
        if not row:
            variants = {
                tuple(item[key] for key in VARIANT_KEYS)
                for (stored,) in db.execute("SELECT config FROM experiments")
                for item in (json.loads(stored),)
            }
            variant = tuple(config[key] for key in VARIANT_KEYS)
            if variant not in variants and len(variants) >= 21:
                raise ValueError("Campaign cap reached: nine initial variants and twelve additional variants")
        folder = args.output / "results" / experiment_id
        folder.mkdir(parents=True, exist_ok=True)
        ini = folder / "tester.ini"
        preset = folder / f"{experiment_id}.set"
        if missing:
            ini.unlink(missing_ok=True)
            preset.unlink(missing_ok=True)
        else:
            ini.write_text(tester_ini(config, experiment_id), encoding="ascii")
            preset.write_text(settings(config), encoding="ascii")
        db.execute(
            """INSERT INTO experiments(id,config,status,detail) VALUES(?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET config=excluded.config,status=excluded.status,detail=excluded.detail""",
            (experiment_id, json.dumps(config, sort_keys=True), status, json.dumps(detail)),
        )
    return {"id": experiment_id, "status": status, "folder": str(folder.resolve()), **detail}


FALLBACK = re.compile(
    r"(?:real ticks (?:absent|discarded|mismatch)|generation (?:is )?used|"
    r"generated ticks|no real ticks|start time changed)", re.I
)


def import_result(args):
    if not re.fullmatch(r"gl-[0-9a-f]{20}", args.experiment_id):
        raise ValueError("Invalid experiment ID")
    with closing(registry(args.output)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT config,status FROM experiments WHERE id=?", (args.experiment_id,)
        ).fetchone()
        if not row or row[1] != "COVERAGE_REVIEW_REQUIRED":
            raise ValueError("Prepare an experiment with all required tick cache months first")
        config = json.loads(row[0])
        coverage = json.loads(args.coverage.read_text(encoding="utf-8"))
        required = {
            "symbol": config["symbol"], "broker": config["broker"],
            "from_inclusive": config["from_inclusive"], "to_exclusive": config["to_exclusive"],
            "missing_trading_minutes": 0, "generated_ticks": 0, "visual": False,
        }
        if (any(coverage.get(key) != value for key, value in required.items())
            or not coverage.get("evidence")
            or not re.fullmatch(r"[0-9a-f]{64}", coverage.get("data_sha256", ""))):
            raise ValueError("Coverage record does not attest zero missing trading minutes for this period")
        evidence = read_mt5_text(args.journal)
        start, end = SPLITS[config["split"]]
        period = f"{start:%Y.%m.%d} - {end:%Y.%m.%d}"
        expected_init = (
            f"GLAB|INIT|{SYMBOL}|CLOCK_LITEFINANCE_EU|REF_{config['reference'].upper().replace('-', '_')}|"
            f"STRATEGY_{config['strategy'].upper()}|MODE_{config['mode'].upper()}|"
        )
        if (FALLBACK.search(evidence) or not re.search(r"real ticks", evidence, re.I)
            or not re.search(r"\btest passed\b|\btesting finished\b", evidence, re.I)
            or not any(expected_init in line and "|audit=0" in line for line in evidence.splitlines())):
            raise ValueError("Journal lacks completed real-tick execution proof or shows a fallback")
        summary = parse_report(args.report)
        if (summary["symbol"] != SYMBOL or "M5" not in summary["period"] or period not in summary["period"]
            or summary["initial_deposit"] != config["deposit"]):
            raise ValueError("Report does not match experiment symbol, timeframe, dates, or deposit")
        summary["average_trades_per_week"] = summary["trade_count"] * 7 / (end-start).days
        summary["net_return_pct"] = 100 * summary["net_profit"] / config["deposit"]
        summary["expectancy_r"] = None
        summary["performance_by_session"] = None
        summary["decision"] = "PENDING_REVIEW" if summary["trade_count"] else "REJECTED_EMPTY"
        status = "REVIEWABLE" if summary["trade_count"] else "EMPTY"
        folder = args.output / "results" / args.experiment_id / "evidence"
        folder.mkdir(exist_ok=False)
        for source, name in (
            (args.report, "report.htm"), (args.journal, "journal.log"), (args.coverage, "coverage.json"),
        ):
            shutil.copyfile(source, folder / name)
        (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        db.execute("UPDATE experiments SET status=?,summary=? WHERE id=?",
                   (status, json.dumps(summary), args.experiment_id))
    return {"id": args.experiment_id, "status": status, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "research" / "output")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--split", choices=SPLITS, required=True)
    prep.add_argument("--strategy", choices=STRATEGIES, required=True)
    prep.add_argument("--mode", choices=MODES, required=True)
    prep.add_argument("--reference", choices=REFERENCES, required=True)
    prep.add_argument("--broker", choices=("LiteFinance-MT5-Live", "LiteFinance-MT5-Demo"), required=True)
    prep.add_argument("--tick-cache", type=Path, required=True)
    prep.add_argument("--leverage", type=int, choices=(100,), default=100)
    prep.add_argument("--hypothesis", required=True)
    prep.add_argument("--frozen-validation")
    imp = sub.add_parser("import")
    imp.add_argument("experiment_id")
    for key in ("report", "journal", "coverage"):
        imp.add_argument(f"--{key}", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps((prepare if args.command == "prepare" else import_result)(args), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
