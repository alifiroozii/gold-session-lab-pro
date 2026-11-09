"""Read English MT5 single-run HTML reports. Keep raw reports for traceability."""
import re
from html.parser import HTMLParser
from pathlib import Path


def read_mt5_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


class ReportCells(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None


def parse_report(path: Path) -> dict:
    report = ReportCells()
    report.feed(read_mt5_text(path))
    labels = {
        cell.rstrip(":"): value
        for cell, value in zip(report.cells, report.cells[1:])
        if cell.endswith(":")
    }

    def number(label):
        value = labels[label]
        if not re.fullmatch(r"-?[0-9][0-9 ]*(?:\.[0-9]+)?", value):
            raise ValueError(f"Invalid {label}: {value}")
        return float(value.replace(" ", ""))

    try:
        trades = number("Total Trades")
        if trades < 0 or not trades.is_integer():
            raise ValueError("Invalid trade count")
        winners = labels["Profit Trades (% of total)"].split(" ")[0]
        if not winners.isdigit() or int(winners) > trades:
            raise ValueError("Invalid winning-trade count")
        drawdown = re.fullmatch(r"([\d .]+)% \(([^)]+)\)", labels["Equity Drawdown Relative"])
        if drawdown is None:
            raise ValueError("Invalid relative equity drawdown")
        percent = float(drawdown[1])
        if not 0 <= percent <= 100:
            raise ValueError("Invalid relative equity drawdown percentage")
        return {
            "symbol": labels["Symbol"],
            "period": labels["Period"],
            "net_profit": number("Total Net Profit"),
            "initial_deposit": number("Initial Deposit"),
            "profit_factor": number("Profit Factor") if number("Gross Loss") < 0 else None,
            "win_rate": int(winners) / trades if trades else None,
            "equity_drawdown_pct": percent,
            "trade_count": int(trades),
        }
    except KeyError as exc:
        raise ValueError(f"Missing MT5 report field: {exc.args[0]}") from exc
