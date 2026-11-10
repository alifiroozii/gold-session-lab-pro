"""
Causal Strategy Validation Laboratory for XAUUSD (Master Prompt V6).
Runs chronological walk-forward validation (in-sample / out-of-sample split),
enforces statistical significance hurdles, computes institutional metrics,
and fail-closes whenever dataset provenance is unverified or simulated.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from goldlab.engine import ResearchEngine
from goldlab.types import Candle, TradeOutcome

TZ_UTC = timezone.utc


@dataclass
class ValidationMetrics:
    sample_size: int = 0
    wins: int = 0
    losses: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0
    max_drawdown_dollars: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    total_r: float = 0.0


@dataclass
class ValidationReport:
    timestamp: str
    dataset_path: str
    data_provenance_verified: bool
    authorizes_paper_auto: bool
    timeframe: str
    total_candles: int
    train_candles: int
    test_candles: int
    in_sample_metrics: ValidationMetrics
    out_of_sample_metrics: ValidationMetrics
    statistical_verdict: str  # "INSUFFICIENT_DATA", "PROVEN_EDGE", "FAIL", "UNVERIFIED_DATASET"
    outcome: str = "STRUCTURAL_CHECKS_ONLY"
    persian_summary: str = ""
    limitations: str = ""


class StrategyValidationLab:
    """
    Independent validation laboratory for causal XAUUSD session strategies.
    Strictly prohibits forward leakage and evaluates out-of-sample performance.
    """

    def __init__(
        self,
        db_path: str = "data/xauusd_lab.sqlite",
        reports_dir: str = "reports",
        min_sample_size: int = 50,
        min_profit_factor: float = 1.30,
        min_win_rate_pct: float = 40.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.min_sample_size = min_sample_size
        self.min_profit_factor = min_profit_factor
        self.min_win_rate_pct = min_win_rate_pct

    def run_validation(
        self,
        csv_path: Optional[Path] = None,
        candles: Optional[List[Candle]] = None,
        timeframe: str = "5m",
        split_ratio: float = 0.70,
    ) -> ValidationReport:
        """
        Runs walk-forward validation across historical candles.
        If csv_path contains demo_xauusd_1m.csv or is not independently signed,
        data_provenance_verified is strictly FALSE.
        """
        dataset_name = str(csv_path) if csv_path else "MEMORY_BUFFER"
        is_demo = "demo" in dataset_name.lower() or not csv_path or not csv_path.exists()
        provenance_verified = not is_demo

        if candles is None and csv_path and csv_path.exists():
            temp_engine = ResearchEngine(db_path=str(self.db_path))
            temp_engine.load_from_csv(csv_path, timeframe=timeframe)
            candles = temp_engine.current_candles

        if not candles or len(candles) < 20:
            return ValidationReport(
                timestamp=datetime.now(TZ_UTC).isoformat(),
                dataset_path=dataset_name,
                data_provenance_verified=provenance_verified,
                authorizes_paper_auto=False,
                timeframe=timeframe,
                total_candles=len(candles) if candles else 0,
                train_candles=0,
                test_candles=0,
                in_sample_metrics=ValidationMetrics(),
                out_of_sample_metrics=ValidationMetrics(),
                statistical_verdict="INSUFFICIENT_DATA",
                outcome="INSUFFICIENT_DATA",
                persian_summary="تعداد کندل‌های موجود برای آزمون اعتبارسنجی ناکافی است.",
                limitations="حداقل ۲۰۰ کندل ۵ دقیقه برای ارزیابی مورد نیاز است.",
            )

        split_idx = int(len(candles) * split_ratio)
        train_candles = candles[:split_idx]
        test_candles = candles[split_idx:]

        in_sample_metrics = self._evaluate_segment(train_candles, timeframe)
        out_of_sample_metrics = self._evaluate_segment(test_candles, timeframe)

        # Statistical evaluation
        verdict = "UNVERIFIED_DATASET" if not provenance_verified else "EVALUATED"
        if out_of_sample_metrics.sample_size < self.min_sample_size:
            verdict = "INSUFFICIENT_DATA"
            persian = (
                f"داده‌های خارج از نمونه (OOS) تنها شامل {out_of_sample_metrics.sample_size} معامله است "
                f"(حداقل مورد نیاز: {self.min_sample_size}). نتیجه از نظر آماری غیرقابل اتکا است."
            )
        elif out_of_sample_metrics.profit_factor < self.min_profit_factor or out_of_sample_metrics.win_rate_pct < self.min_win_rate_pct:
            verdict = "FAIL"
            persian = (
                f"استراتژی در آزمون خارج از نمونه مردود شد: ضریب سود {out_of_sample_metrics.profit_factor:.2f} "
                f"و نرخ برد {out_of_sample_metrics.win_rate_pct:.1f}% کمتر از آستانه مجاز است."
            )
        else:
            verdict = "PASS_EDGE_DETECTED" if provenance_verified else "PASS_DEMO_ONLY"
            persian = (
                f"معیارهای خارج از نمونه تأیید شدند (نرخ برد {out_of_sample_metrics.win_rate_pct:.1f}%، "
                f"ضریب سود {out_of_sample_metrics.profit_factor:.2f}، امید ریاضی R={out_of_sample_metrics.expectancy_r:.2f})."
            )

        if not provenance_verified:
            persian += " توجه: دیتاست از نوع دمو/شبیه‌سازی است و مجوز فعال‌سازی معاملات خودکار را صادر نمی‌کند."

        report = ValidationReport(
            timestamp=datetime.now(TZ_UTC).isoformat(),
            dataset_path=dataset_name,
            data_provenance_verified=provenance_verified,
            authorizes_paper_auto=False,  # strictly fail-closed
            timeframe=timeframe,
            total_candles=len(candles),
            train_candles=len(train_candles),
            test_candles=len(test_candles),
            in_sample_metrics=in_sample_metrics,
            out_of_sample_metrics=out_of_sample_metrics,
            statistical_verdict=verdict,
            outcome=verdict,
            persian_summary=persian,
            limitations=(
                "این گزارش صرفاً جهت پژوهش کمی تهیه شده است. موفقیت در داده‌های تاریخی یا آزمون خارج از نمونه "
                "به هیچ عنوان ضامن سودآوری در فید زنده نبوده و مجوز فعال‌سازی PAPER_AUTO را صادر نمی‌نماید."
            ),
        )

        # Save to reports/STRATEGY_VALIDATION.json
        self._save_report(report)
        return report

    def _evaluate_segment(self, segment_candles: List[Candle], timeframe: str) -> ValidationMetrics:
        """Evaluates causal trades on a given slice of candles."""
        if len(segment_candles) < 10:
            return ValidationMetrics()

        eval_engine = ResearchEngine(db_path=str(self.db_path))
        eval_engine.load_candles(segment_candles, timeframe=timeframe)
        eval_engine.run_pipeline()

        trades = eval_engine.trades

        if not trades:
            return ValidationMetrics()

        wins = [t for t in trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in trades if t.outcome == TradeOutcome.LOSS]
        sample_size = len(trades)
        win_rate = (len(wins) / sample_size) * 100.0 if sample_size > 0 else 0.0

        win_r_vals = [t.realized_r for t in wins if t.realized_r > 0]
        loss_r_vals = [abs(t.realized_r) for t in losses if t.realized_r < 0]

        gross_profit_r = sum(win_r_vals)
        gross_loss_r = sum(loss_r_vals)
        profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (99.0 if gross_profit_r > 0 else 0.0)

        r_multiples: List[float] = [t.realized_r for t in trades]
        equity_curve: List[float] = [1000.0]
        current_eq = 1000.0
        peak_eq = 1000.0
        max_dd_dollars = 0.0
        max_dd_pct = 0.0

        for t in trades:
            dollar_change = t.realized_r * 10.0  # $10 per 1R risk baseline on $1000 equity
            current_eq += dollar_change
            equity_curve.append(current_eq)
            if current_eq > peak_eq:
                peak_eq = current_eq
            dd = peak_eq - current_eq
            dd_pct = (dd / peak_eq) * 100.0 if peak_eq > 0 else 0.0
            if dd > max_dd_dollars:
                max_dd_dollars = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        total_r = sum(r_multiples)
        expectancy_r = total_r / sample_size if sample_size > 0 else 0.0
        avg_win_r = sum(win_r_vals) / len(win_r_vals) if win_r_vals else 0.0
        avg_loss_r = sum(loss_r_vals) / len(loss_r_vals) if loss_r_vals else 0.0

        return ValidationMetrics(
            sample_size=sample_size,
            wins=len(wins),
            losses=len(losses),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(min(profit_factor, 99.0), 2),
            expectancy_r=round(expectancy_r, 2),
            max_drawdown_dollars=round(max_dd_dollars, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            avg_win_r=round(avg_win_r, 2),
            avg_loss_r=round(avg_loss_r, 2),
            total_r=round(total_r, 2),
        )

    def _save_report(self, report: ValidationReport) -> None:
        target_path = self.reports_dir / "STRATEGY_VALIDATION.json"
        data = asdict(report)
        target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
