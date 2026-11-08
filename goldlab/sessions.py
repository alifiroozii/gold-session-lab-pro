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
        """
        Forex Gold market closes Friday evening (approx 22:00 UTC / 17:00 NY)
        and re-opens Sunday evening (approx 22:00 UTC / 18:00 NY).
        """
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=TZ_UTC)
        weekday = dt_utc.weekday()  # Monday=0, Sunday=6

        # Friday after 22:00 UTC
        if weekday == 4 and dt_utc.time() >= time(22, 0):
            return True
        # Saturday all day
        if weekday == 5:
            return True
        # Sunday before 22:00 UTC
        if weekday == 6 and dt_utc.time() < time(22, 0):
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

    def calculate_session_stats(
        self, candles: List[Candle]
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """
        Calculates PDH/PDL, Asia H/L, London H/L, NY H/L and midline from candle history.
        """
        stats: Dict[str, Dict[str, Optional[float]]] = {
            "asia": {"high": None, "low": None, "midline": None},
            "london": {"high": None, "low": None, "midline": None},
            "ny": {"high": None, "low": None, "midline": None},
            "pd": {"high": None, "low": None, "midline": None},
            "pw": {"high": None, "low": None, "midline": None},
        }

        if not candles:
            return stats

        # Find today's date in NY timezone
        last_dt = candles[-1].timestamp.astimezone(TZ_NEW_YORK)
        today_ny = last_dt.date()
        yesterday_ny = today_ny - timedelta(days=1)
        prev_week = last_dt.isocalendar().week - 1

        asia_high, asia_low = -float("inf"), float("inf")
        london_high, london_low = -float("inf"), float("inf")
        ny_high, ny_low = -float("inf"), float("inf")
        pd_high, pd_low = -float("inf"), float("inf")
        pw_high, pw_low = -float("inf"), float("inf")

        for c in candles:
            c_ny = c.timestamp.astimezone(TZ_NEW_YORK)
            c_date = c_ny.date()
            c_week = c_ny.isocalendar().week
            sessions = self.get_candle_sessions(c.timestamp)

            # Previous Day High / Low
            if c_date == yesterday_ny:
                pd_high = max(pd_high, c.high)
                pd_low = min(pd_low, c.low)

            # Previous Week High / Low
            if c_week == prev_week:
                pw_high = max(pw_high, c.high)
                pw_low = min(pw_low, c.low)

            # Today's session levels
            if c_date == today_ny:
                if SessionName.ASIA_REFERENCE in sessions:
                    asia_high = max(asia_high, c.high)
                    asia_low = min(asia_low, c.low)
                if SessionName.LONDON in sessions:
                    london_high = max(london_high, c.high)
                    london_low = min(london_low, c.low)
                if SessionName.NEW_YORK in sessions:
                    ny_high = max(ny_high, c.high)
                    ny_low = min(ny_low, c.low)

        def _format_hl(h: float, low_val: float) -> Dict[str, Optional[float]]:
            if h == -float("inf") or low_val == float("inf"):
                return {"high": None, "low": None, "midline": None}
            return {"high": round(h, 4), "low": round(low_val, 4), "midline": round((h + low_val) / 2.0, 4)}

        stats["asia"] = _format_hl(asia_high, asia_low)
        stats["london"] = _format_hl(london_high, london_low)
        stats["ny"] = _format_hl(ny_high, ny_low)
        stats["pd"] = _format_hl(pd_high, pd_low)
        stats["pw"] = _format_hl(pw_high, pw_low)

        return stats

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
