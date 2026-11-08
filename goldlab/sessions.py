"""
Session Management and IANA Timezone Handling.
Guarantees daylight saving time (DST) safety across London, New York, and Tokyo.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from goldlab.types import Candle, SessionName

# Official IANA Timezone Identifiers
TZ_TOKYO = ZoneInfo("Asia/Tokyo")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_UTC = timezone.utc


class SessionConfig:
    """Configurable Session Parameters with DST safety."""

    def __init__(
        self,
        tokyo_start: time = time(9, 0),
        tokyo_end: time = time(18, 0),
        london_start: time = time(8, 0),
        london_end: time = time(17, 0),
        ny_start: time = time(8, 0),
        ny_end: time = time(17, 0),
        # Asia Reference Range in New York Time (Baseline test: 20:00 - 00:00 NY)
        asia_ref_ny_start: time = time(20, 0),
        asia_ref_ny_end: time = time(0, 0),
    ) -> None:
        self.tokyo_start = tokyo_start
        self.tokyo_end = tokyo_end
        self.london_start = london_start
        self.london_end = london_end
        self.ny_start = ny_start
        self.ny_end = ny_end
        self.asia_ref_ny_start = asia_ref_ny_start
        self.asia_ref_ny_end = asia_ref_ny_end


class SessionManager:
    """Determines session windows and computes high/low/midline levels accurately."""

    def __init__(self, config: Optional[SessionConfig] = None) -> None:
        self.config = config or SessionConfig()

    def is_market_closed(self, dt_utc: datetime) -> bool:
        """Conservative spot-gold schedule in New York local time (DST-safe).

        Never use a fixed 22:00 UTC opening: it changes during DST.
        Provider tradeable status remains authoritative for execution.
        """
        if dt_utc.tzinfo is None:
            raise ValueError("Market timestamps must be timezone-aware")
        ny = dt_utc.astimezone(TZ_NEW_YORK)
        day, clock = ny.weekday(), ny.time()
        if day == 5:
            return True
        if day == 4 and clock >= time(17, 0):
            return True
        if day == 6 and clock < time(18, 0):
            return True
        if day in (0, 1, 2, 3) and time(17, 0) <= clock < time(18, 0):
            return True
        return False

    def get_candle_sessions(self, dt_utc: datetime) -> List[SessionName]:
        """Returns the active sessions for a given UTC timestamp."""
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=TZ_UTC)

        active: List[SessionName] = []

        # 1. Tokyo session (09:00 - 18:00 Asia/Tokyo)
        tokyo_local = dt_utc.astimezone(TZ_TOKYO).time()
        if self.config.tokyo_start <= tokyo_local < self.config.tokyo_end:
            active.append(SessionName.TOKYO)

        # 2. London session (08:00 - 17:00 Europe/London)
        london_local = dt_utc.astimezone(TZ_LONDON).time()
        is_london = self.config.london_start <= london_local < self.config.london_end
        if is_london:
            active.append(SessionName.LONDON)

        # 3. New York session (08:00 - 17:00 America/New_York)
        ny_dt = dt_utc.astimezone(TZ_NEW_YORK)
        ny_local = ny_dt.time()
        is_ny = self.config.ny_start <= ny_local < self.config.ny_end
        if is_ny:
            active.append(SessionName.NEW_YORK)

        # 4. Overlap (London + NY)
        if is_london and is_ny:
            active.append(SessionName.LONDON_NY_OVERLAP)

        # 5. Asia Reference Range (Configurable, default: 20:00 - 00:00 NY time)
        # Note: 20:00 to 00:00 wraps to midnight
        if self.config.asia_ref_ny_start > self.config.asia_ref_ny_end:
            # Crosses midnight: 20:00 - 23:59:59
            if ny_local >= self.config.asia_ref_ny_start or (
                self.config.asia_ref_ny_end != time(0, 0) and ny_local < self.config.asia_ref_ny_end
            ):
                active.append(SessionName.ASIA_REFERENCE)
        else:
            if self.config.asia_ref_ny_start <= ny_local < self.config.asia_ref_ny_end:
                active.append(SessionName.ASIA_REFERENCE)

        return active

    def get_trading_day(self, dt_utc: datetime) -> str:
        """Determines the Forex/Gold trading day in New York time.

        Daily rollover is at 18:00 NY time (starts the next trading day).
        Sunday 18:00 NY rollover is Monday's trading day.
        """
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=TZ_UTC)
        ny = dt_utc.astimezone(TZ_NEW_YORK)
        if ny.time() >= time(18, 0):
            d = ny.date() + timedelta(days=1)
            if d.weekday() == 5:
                d += timedelta(days=2)
            elif d.weekday() == 6:
                d += timedelta(days=1)
            return d.isoformat()
        return ny.date().isoformat()

    def calculate_as_of_session_stats_series(
        self, candles: List[Candle]
    ) -> List[Dict[str, Dict[str, Optional[float]]]]:
        """Calculates point-in-time session levels for each candle in sequence.

        Guarantees zero lookahead: for candle i, only candles 0..i are used.
        """
        if not candles:
            return []

        series: List[Dict[str, Dict[str, Optional[float]]]] = []
        n = len(candles)

        # Precompute trading day and session membership for each candle
        candle_meta = []
        for c in candles:
            tday = self.get_trading_day(c.timestamp)
            sess = set(self.get_candle_sessions(c.timestamp))
            candle_meta.append((tday, sess))

        days_seen: List[str] = []
        day_candle_indices: Dict[str, List[int]] = {}

        for i in range(n):
            c = candles[i]
            tday, _ = candle_meta[i]

            if not days_seen or days_seen[-1] != tday:
                days_seen.append(tday)
                day_candle_indices[tday] = []
            day_candle_indices[tday].append(i)

            # Previous completed trading day high/low
            pd_high: Optional[float] = None
            pd_low: Optional[float] = None
            if len(days_seen) > 1:
                prev_tday = days_seen[-2]
                prev_indices = day_candle_indices[prev_tday]
                if prev_indices:
                    pd_high = round(max(candles[k].high for k in prev_indices), 4)
                    pd_low = round(min(candles[k].low for k in prev_indices), 4)

            # Current trading day sessions up to bar i
            curr_indices = day_candle_indices[tday]

            asia_bars = [
                candles[k]
                for k in curr_indices
                if SessionName.ASIA_REFERENCE in candle_meta[k][1]
            ]
            london_bars = [
                candles[k]
                for k in curr_indices
                if SessionName.LONDON in candle_meta[k][1]
            ]
            ny_bars = [
                candles[k]
                for k in curr_indices
                if SessionName.NEW_YORK in candle_meta[k][1]
            ]

            def _fmt_hl(bars: List[Candle]) -> Dict[str, Optional[float]]:
                if not bars:
                    return {"high": None, "low": None, "midline": None}
                h = round(max(b.high for b in bars), 4)
                low_val = round(min(b.low for b in bars), 4)
                return {"high": h, "low": low_val, "midline": round((h + low_val) / 2.0, 4)}

            stats_i: Dict[str, Dict[str, Optional[float]]] = {
                "asia": _fmt_hl(asia_bars),
                # 20:00–00:00 NY research range is distinct from Tokyo's
                # 09:00–18:00 local session.  No signal may use its final
                # levels before 00:00 NY on that trading day.
                "asia_complete": (
                    c.timestamp.astimezone(TZ_NEW_YORK).time() <
                    self.config.asia_ref_ny_start
                    and c.timestamp.astimezone(TZ_NEW_YORK).time() >=
                    self.config.asia_ref_ny_end
                ),
                "london": _fmt_hl(london_bars),
                "ny": _fmt_hl(ny_bars),
                "pd": {
                    "high": pd_high,
                    "low": pd_low,
                    "midline": round((pd_high + pd_low) / 2.0, 4)
                    if pd_high is not None and pd_low is not None
                    else None,
                },
                "pw": {"high": None, "low": None, "midline": None},
            }
            series.append(stats_i)

        return series

    def calculate_session_stats(
        self, candles: List[Candle]
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """Calculates PDH/PDL, Asia H/L, London H/L, NY H/L and midline from candle history.

        Uses as-of calculation on the latest candle to prevent lookahead leakage.
        """
        stats: Dict[str, Dict[str, Optional[float]]] = {
            "asia": {"high": None, "low": None, "midline": None},
            "asia_complete": False,
            "london": {"high": None, "low": None, "midline": None},
            "ny": {"high": None, "low": None, "midline": None},
            "pd": {"high": None, "low": None, "midline": None},
            "pw": {"high": None, "low": None, "midline": None},
        }

        if not candles:
            return stats

        series = self.calculate_as_of_session_stats_series(candles)
        return series[-1] if series else stats

    def calculate_session_boxes(self, candles: List[Candle], days: int = 4) -> List[Dict[str, object]]:
        """Time-bounded Asia/London/New York + overlap rectangles, including prior days.

        Price bounds use only candles inside each session; no future candles are
        used to finalize a session. Chart overlays are research-only.
        """
        if not candles:
            return []
        from collections import defaultdict

        definitions = [
            ("asia", SessionName.TOKYO, TZ_TOKYO, self.config.tokyo_start, self.config.tokyo_end),
            ("london", SessionName.LONDON, TZ_LONDON, self.config.london_start, self.config.london_end),
            ("new_york", SessionName.NEW_YORK, TZ_NEW_YORK, self.config.ny_start, self.config.ny_end),
        ]
        grouped: Dict[tuple, List[Candle]] = defaultdict(list)
        for candle in candles:
            sessions = self.get_candle_sessions(candle.timestamp)
            for name, enum, zone, _start, _end in definitions:
                if enum in sessions:
                    grouped[(name, candle.timestamp.astimezone(zone).date())].append(candle)
            if SessionName.LONDON_NY_OVERLAP in sessions:
                grouped[("overlap", candle.timestamp.astimezone(TZ_NEW_YORK).date())].append(candle)

        last_observed = max(c.timestamp for c in candles)
        result = []
        for (name, session_date), bars in grouped.items():
            if name == "overlap":
                london_start = datetime.combine(session_date, self.config.london_start, TZ_LONDON).astimezone(TZ_UTC)
                london_end = datetime.combine(session_date, self.config.london_end, TZ_LONDON).astimezone(TZ_UTC)
                ny_start = datetime.combine(session_date, self.config.ny_start, TZ_NEW_YORK).astimezone(TZ_UTC)
                ny_end = datetime.combine(session_date, self.config.ny_end, TZ_NEW_YORK).astimezone(TZ_UTC)
                start_utc, end_utc = max(london_start, ny_start), min(london_end, ny_end)
            else:
                definition = next(d for d in definitions if d[0] == name)
                _, _enum, zone, local_start, local_end = definition
                start_utc = datetime.combine(session_date, local_start, zone).astimezone(TZ_UTC)
                end_utc = datetime.combine(session_date, local_end, zone).astimezone(TZ_UTC)
            if end_utc <= start_utc:
                continue
            high, low = max(bar.high for bar in bars), min(bar.low for bar in bars)
            completed = last_observed >= end_utc
            result.append({
                "id": f"{name}-{session_date.isoformat()}",
                "session": name,
                "date": session_date.isoformat(),
                "start": int(start_utc.timestamp()),
                "end": int((end_utc if completed else min(last_observed, end_utc)).timestamp()),
                "high": round(high, 4), "low": round(low, 4),
                "completed": completed,
                "bars": len(bars),
            })

        # Preserve a compact number of recent windows per session, incl. preceding day.
        limited = []
        for name in ("asia", "london", "new_york", "overlap"):
            matching = sorted((b for b in result if b["session"] == name),
                              key=lambda b: b["start"], reverse=True)
            limited.extend(matching[:days])
        return sorted(limited, key=lambda b: (b["start"], b["session"]))
