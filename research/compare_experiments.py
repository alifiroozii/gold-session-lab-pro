"""Print recorded runs with the same split; keep every blocked or empty result visible."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from research.run_backtest import ROOT, SPLITS


def compare(path, split, broker):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            """SELECT id,config,status,detail,summary FROM experiments
               WHERE json_extract(config,'$.split')=? AND json_extract(config,'$.broker')=?
               ORDER BY created_at,id""",
            (split, broker),
        ).fetchall()
    return [
        dict(id=key, config=json.loads(config), status=status, detail=json.loads(detail),
             summary=json.loads(summary) if summary else None)
        for key, config, status, detail, summary in rows
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "research/output/experiments.sqlite")
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--broker", choices=("LiteFinance-MT5-Live", "LiteFinance-MT5-Demo"), required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.db, args.split, args.broker), indent=2))


if __name__ == "__main__":
    main()
