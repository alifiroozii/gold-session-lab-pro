"""
Pure-Python Solar Hijri (Jalali / تقویم شمسی) Date & Time Utilities.
No external dependencies required; mathematically exact astronomical conversions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

TZ_TEHRAN = timezone.utc  # Can be converted with offset +03:30


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    """Converts Gregorian year, month, day to Jalali (Solar Hijri) year, month, day."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)

    return jy, jm, jd


def format_jalali_datetime(dt: datetime, include_time: bool = True) -> str:
    """Formats any timezone-aware datetime instance into a Persian Solar Hijri string."""
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    persian_months = [
        "",
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]
    month_name = persian_months[jm] if 1 <= jm <= 12 else str(jm)

    date_str = f"{jd} {month_name} {jy}"
    if include_time:
        time_str = dt.strftime("%H:%M:%S")
        return f"{date_str} - ساعت {time_str}"
    return date_str
