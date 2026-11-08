"""
Quantitative Performance Analytics and Risk Verification.
Calculates Expectancy R, Profit Factor, Drawdown, MAE/MFE, Bootstrap Confidence Intervals,
and Sensitivity Matrices.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from goldlab.types import BacktestSummary, TradeOrder, TradeOutcome


class MetricsCalculator:
    """Computes rigorous statistical metrics from simulated trade sequences."""

    @staticmethod
    def calculate_summary(trades: List[TradeOrder]) -> BacktestSummary:
        summary = BacktestSummary(total_trades=len(trades), trades=trades)
        if not trades:
            return summary

        closed_trades = [t for t in trades if t.outcome != TradeOutcome.OPEN]
        if not closed_trades:
            return summary

        wins = [t for t in closed_trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in closed_trades if t.outcome == TradeOutcome.LOSS]
        bes = [t for t in closed_trades if t.outcome == TradeOutcome.BREAK_EVEN]

        summary.winning_trades = len(wins)
        summary.losing_trades = len(losses)
        summary.break_even_trades = len(bes)

        summary.win_rate_pct = round((len(wins) / len(closed_trades)) * 100.0, 2)

        total_gain_r = sum(t.realized_r for t in wins)
        total_loss_r = abs(sum(t.realized_r for t in losses))

        summary.profit_factor = round(total_gain_r / total_loss_r, 2) if total_loss_r > 0 else 999.0
        summary.expectancy_r = round(
            sum(t.realized_r for t in closed_trades) / len(closed_trades), 2
        )

        # Drawdown in R multiples
        cumulative_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        for t in closed_trades:
            cumulative_r += t.realized_r
            peak_r = max(peak_r, cumulative_r)
            dd = peak_r - cumulative_r
            max_dd_r = max(max_dd_r, dd)

        summary.max_drawdown_r = round(max_dd_r, 2)

        # Average MAE and MFE
        summary.avg_mae = round(float(np.mean([t.mae_pips for t in closed_trades])), 2)
        summary.avg_mfe = round(float(np.mean([t.mfe_pips for t in closed_trades])), 2)

        # Breakdown by day of week
        day_map = {0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنج‌شنبه", 4: "جمعه", 6: "یکشنبه"}
        for t in closed_trades:
            d_name = day_map.get(t.entry_time.weekday(), "نامشخص")
            summary.distribution_by_day[d_name] = summary.distribution_by_day.get(d_name, 0) + 1

        return summary

    @staticmethod
    def bootstrap_expectancy_ci(
        trades: List[TradeOrder], n_bootstraps: int = 1000, ci_level: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculates non-parametric Bootstrap Confidence Interval for Expectancy R.
        Exposes strategy fragility and data snooping bias.
        """
        closed_r = [t.realized_r for t in trades if t.outcome != TradeOutcome.OPEN]
        if len(closed_r) < 5:
            return 0.0, 0.0

        sample_means = []
        n = len(closed_r)
        np_arr = np.array(closed_r)

        for _ in range(n_bootstraps):
            resample = np.random.choice(np_arr, size=n, replace=True)
            sample_means.append(float(np.mean(resample)))

        lower_pct = ((1.0 - ci_level) / 2.0) * 100.0
        upper_pct = (1.0 - (1.0 - ci_level) / 2.0) * 100.0

        ci_lower = round(float(np.percentile(sample_means, lower_pct)), 2)
        ci_upper = round(float(np.percentile(sample_means, upper_pct)), 2)

        return ci_lower, ci_upper

    @staticmethod
    def run_sensitivity_matrix(
        trades: List[TradeOrder], spread_variations: List[float] = [0.20, 0.35, 0.50]
    ) -> List[Dict[str, Any]]:
        """
        Evaluates sensitivity of Expectancy R against differing spread regimes.
        """
        results = []
        for sp in spread_variations:
            # Approximate degradation of R due to wider spread
            adjusted_trades = []
            for t in trades:
                deg_r = (sp - 0.25) * 0.1  # Sensitivity slope
                new_r = t.realized_r - deg_r if t.outcome == TradeOutcome.WIN else t.realized_r - deg_r
                adjusted_trades.append(new_r)

            exp_r = round(float(np.mean(adjusted_trades)), 2) if adjusted_trades else 0.0
            results.append({"spread_tested": sp, "expected_r": exp_r})

        return results
