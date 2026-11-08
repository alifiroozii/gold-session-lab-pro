"""
Economic News Blackout Calendar for High-Impact Macro Releases.
Covers CPI, PCE, NFP, and FOMC releases with strict timezone awareness.
Requirement: If no verified calendar is loaded, status MUST be reported as 'UNKNOWN',
never falsely assuming 'Today is free of news'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

TZ_UTC = timezone.utc


@dataclass
class EconomicEvent:
    name: str  # e.g., 'US CPI', 'US NFP', 'FOMC Rate Decision', 'Core PCE'
    release_time: datetime  # UTC aware
    impact: str = "HIGH"  # HIGH / MEDIUM / LOW


class MacroNewsCalendar:
    """Manages high-impact economic events and blackout filters."""

    def __init__(self, events: Optional[List[EconomicEvent]] = None) -> None:
        self.events: List[EconomicEvent] = events if events is not None else []
        self.has_verified_calendar: bool = events is not None and len(events) > 0

    def is_blackout(
        self,
        dt_utc: datetime,
        buffer_minutes_before: int = 30,
        buffer_minutes_after: int = 30,
    ) -> Tuple[bool, str]:
        """
        Returns:
            (is_blocked, status_reason)
            If no verified calendar is loaded, status is 'UNKNOWN_CALENDAR_UNVERIFIED'.
        """
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=TZ_UTC)

        if not self.has_verified_calendar:
            return True, "UNKNOWN (تقویم اقتصادی معتبر بارگذاری نشده است - حالت ایمن: عدم ترید)"

        for event in self.events:
            ev_time = event.release_time
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=TZ_UTC)

            start_block = ev_time - timedelta(minutes=buffer_minutes_before)
            end_block = ev_time + timedelta(minutes=buffer_minutes_after)

            if start_block <= dt_utc <= end_block:
                return (
                    True,
                    f"BLACKOUT_ACTIVE: رویداد کلان مهم ({event.name}) در ساعت {ev_time.strftime('%H:%M')} UTC",
                )

        return False, "CLEAR (خارج از پنجره اخبار با تاثیر بالا)"
