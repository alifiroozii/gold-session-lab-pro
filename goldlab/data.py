"""
Data pipeline for XAUUSD Session Research Lab.
Handles CSV ingestion (MT4, MT5, cTrader, Dukascopy), deterministic time-frame aggregation
(1m -> 5m, 15m, 1h), SQLite local caching, and comprehensive feed diagnostics (stale/gap/outlier).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from goldlab.types import Candle

TZ_UTC = timezone.utc


class DataFeedDiagnostics:
    """Monitors data feed integrity and identifies anomalies."""

    def __init__(self, stale_threshold_minutes: int = 15) -> None:
        self.stale_threshold_minutes = stale_threshold_minutes

    def check_feed_status(
        self, candles: List[Candle], current_time: Optional[datetime] = None
    ) -> Dict[str, str]:
        """
        Determines current feed health:
        - 'LOCAL_LIVE_OK'
        - 'FEED_STALE'
        - 'MARKET_CLOSED'
        - 'OFFLINE_EMPTY'
        """
        if not candles:
            return {"status": "OFFLINE_EMPTY", "detail": "هیچ داده‌ای بارگذاری نشده است."}

        last_candle_time = candles[-1].timestamp
        now = current_time or datetime.now(TZ_UTC)

        # Check weekend market closure (Friday 22:00 UTC to Sunday 22:00 UTC)
        weekday = now.weekday()
        if (weekday == 4 and now.time().hour >= 22) or weekday == 5 or (weekday == 6 and now.time().hour < 22):
            return {"status": "MARKET_CLOSED", "detail": "بازار طلا در روزهای تعطیل آخر هفته بسته است."}

        # Check for stale feed
        diff = (now - last_candle_time).total_seconds() / 60.0
        if diff > self.stale_threshold_minutes:
            return {
                "status": "FEED_STALE",
                "detail": f"داده قدیمی است (STALE)؛ آخرین کندل دریافت شده مربوط به {int(diff)} دقیقه پیش است.",
            }

        return {"status": "LOCAL_LIVE_OK", "detail": "فید محلی فعال و به‌روز است."}

    def detect_gaps_and_outliers(
        self, candles: List[Candle], expected_interval_min: int = 1
    ) -> Tuple[List[Dict[str, str]], List[int]]:
        """
        Identifies time gaps between bars and price spike outliers.
        """
        anomalies: List[Dict[str, str]] = []
        outlier_indices: List[int] = []

        for i in range(1, len(candles)):
            c_prev = candles[i - 1]
            c_curr = candles[i]

            # Time Gap
            delta_min = (c_curr.timestamp - c_prev.timestamp).total_seconds() / 60.0
            if delta_min > expected_interval_min * 1.5:
                # Exclude weekend gap
                if not (c_prev.timestamp.weekday() == 4 and c_curr.timestamp.weekday() == 6):
                    anomalies.append(
                        {
                            "type": "TIME_GAP",
                            "index": str(i),
                            "detail": f"شکاف زمانی {delta_min:.1f} دقیقه‌ای بین {c_prev.timestamp} و {c_curr.timestamp}",
                        }
                    )

            # Price Outlier Spike (Range > 6x previous ATR)
            if c_prev.atr14 > 0 and c_curr.range > c_prev.atr14 * 6.0:
                outlier_indices.append(i)
                anomalies.append(
                    {
                        "type": "PRICE_OUTLIER",
                        "index": str(i),
                        "detail": f"پرش غیرعادی قیمت به میزان {c_curr.range:.2f} در مقایسه با ATR={c_prev.atr14:.2f}",
                    }
                )

        return anomalies, outlier_indices


class DataPipeline:
    """Manages CSV parsing, SQLite storage, and deterministic resampling."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.diagnostics = DataFeedDiagnostics()
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initializes SQLite schema for local persistent candle storage."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candles_1m (
                    timestamp TEXT PRIMARY KEY,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    source TEXT NOT NULL,
                    schema_version INTEGER DEFAULT 1
                )
                """
            )
            conn.commit()

    def parse_csv(self, file_path: Path, source_label: str = "CSV_IMPORT") -> List[Candle]:
        """
        Parses multi-format CSV files (MT5, MT4, Dukascopy, cTrader).
        Expected columns: Date/Time (or separate Date, Time), Open, High, Low, Close, Volume.
        """
        df = pd.read_csv(file_path)
        # Normalize column headers
        df.columns = [c.strip().lower() for c in df.columns]

        # Handle Date / Time parsing
        time_col = None
        for col in ["timestamp", "datetime", "time", "date"]:
            if col in df.columns:
                time_col = col
                break

        if time_col is None and "date" in df.columns and "time" in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
        elif time_col:
            df["timestamp"] = pd.to_datetime(df[time_col])
        else:
            raise ValueError(f"Could not find valid datetime columns in {file_path}")

        # Ensure UTC timezone
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")

        # Map OHLCV
        df = df.rename(
            columns={
                "<open>": "open",
                "<high>": "high",
                "<low>": "low",
                "<close>": "close",
                "<vol>": "volume",
                "<tickvol>": "volume",
                "vol": "volume",
                "tick_volume": "volume",
            }
        )

        candles: List[Candle] = []
        for _, row in df.iterrows():
            candles.append(
                Candle(
                    timestamp=row["timestamp"].to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    is_closed=True,
                )
            )

        candles.sort(key=lambda c: c.timestamp)
        return candles

    def save_to_sqlite(self, candles: List[Candle], source_label: str = "CSV") -> None:
        """Stores candles in local SQLite database with provenance."""
        with sqlite3.connect(self.db_path) as conn:
            records = [
                (
                    c.timestamp.isoformat(),
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                    source_label,
                    1,
                )
                for c in candles
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO candles_1m (timestamp, open, high, low, close, volume, source, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            conn.commit()

    def aggregate_candles(self, candles_1m: List[Candle], timeframe: str, *, require_complete: bool = False) -> List[Candle]:
        """
        Deterministically aggregates 1m candles into 5m, 15m, or 1h candles.
        Prevents lookahead leakage by strictly binning based on left-closed intervals.
        """
        if not candles_1m or timeframe == "1m":
            return [c for c in candles_1m if c.is_closed] if require_complete else candles_1m

        freq_map = {"5m": "5min", "15m": "15min", "1h": "1h"}
        if timeframe not in freq_map:
            raise ValueError(f"Unsupported aggregation timeframe: {timeframe}")

        data = [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "is_closed": bool(c.is_closed),
            }
            for c in candles_1m
        ]
        df = pd.DataFrame(data).set_index("timestamp")

        if require_complete:
            # Incomplete last bins and interrupted bins must not become closed
            # 5m/15m/1h decision candles. This mode is only for provider M1.
            if any(c.timestamp.tzinfo is None or not c.is_closed for c in candles_1m):
                raise ValueError("Live aggregation requires timezone-aware completed M1 candles")
            if any(c.timestamp.second or c.timestamp.microsecond for c in candles_1m):
                raise ValueError("Live M1 candle timestamps must align to full minutes")
            if len(df.index.unique()) != len(df.index):
                raise ValueError("Duplicate M1 timestamps in provider data")

        resampled = (
            df.resample(freq_map[timeframe], closed="left", label="left")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last",
                  "volume": "sum", "is_closed": "sum"})
            .dropna()
        )
        if require_complete:
            needed = {"5m": 5, "15m": 15, "1h": 60}[timeframe]
            resampled = resampled[resampled["is_closed"] == needed]

        aggregated: List[Candle] = []
        for ts, row in resampled.iterrows():
            aggregated.append(
                Candle(
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    is_closed=True,
                )
            )

        return aggregated
