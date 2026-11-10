"""Auditable, conservative lessons from observed paper-trading safety events.

This is deterministic rule memory, NOT an LLM and NOT evidence of profitability.
Antigravity may later inspect these events and propose a tested change, but never
edits active risk gates or sends orders on its own.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

UTC = timezone.utc

SAFETY_GUIDANCE = {
    "OANDA_NOT_CONFIGURED": "تا زمان اتصال منبع قیمت تأییدشده XAU/USD، معامله نکن.",
    "NO_VERIFIED_LIVE_QUOTE": "بدون Bid/Ask معتبر و دارای زمان، هیچ ورودی ثبت نکن.",
    "LIVE_STREAM_UNAVAILABLE": "هنگام قطع استریم قیمت، ورود جدید را متوقف و وضعیت اتصال را بررسی کن.",
    "LIVE_STREAM_DISCONNECTED": "تا وصل‌شدن مجدد استریم و دریافت Quote تازه، معامله نکن.",
    "QUOTE_STALE_OR_FUTURE": "با قیمت قدیمی یا زمان غیرمعتبر معامله نکن؛ منتظر Quote تازه باش.",
    "PROVIDER_MARKET_CLOSED": "وقتی ارائه‌دهنده نماد را غیرقابل معامله اعلام می‌کند، ورود نکن.",
    "WEEKEND_MARKET_CLOSED": "هنگام بسته‌بودن بازار در تعطیلات آخر هفته سفارش جدید نزن.",
    "DAILY_MARKET_BREAK": "در وقفه روزانه بازار طلا، ورود جدید ثبت نکن.",
    "UNTRUSTED_DATA_SOURCE": "برای معامله از داده نمونه، تاریخی یا منبع نامعتبر استفاده نکن.",
    "INVALID_BID_ASK": "با Bid/Ask نامعتبر یا اسپرد غیرمنطقی معامله نکن.",
    "INVALID_PROVIDER_PRICE": "پاسخ خراب یا ناقص فید نباید تبدیل به سیگنال ورود شود.",
    "LIVE_FEED_ERROR": "در خطای اتصال قیمت، معاملات را متوقف و منبع را بررسی کن.",
    "MARKET_WATCHDOG_ERROR": "تا رفع خطای پایش ایمنی، ورود خودکار را متوقف نگه دار.",
    "PAPER_AUTO_UNVERIFIED": "تا رفع نشت آینده و تأیید ورود کندل بعد، Paper Auto را فعال نکن.",
}


class DecisionJournal:
    """Deduplicated daily safety memory with non-fabricated review actions."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS safety_lessons (
                    event_id TEXT PRIMARY KEY,
                    first_seen_utc TEXT NOT NULL,
                    category TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    guidance TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    confidence TEXT NOT NULL
                )
            """)
            conn.commit()

    def record_block(self, reason: str, evidence: str = "",
                     now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
        if reason == "VERIFIED_LIVE_PRICE":
            return None
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        guidance = SAFETY_GUIDANCE.get(reason)
        if not guidance:
            # Unknown status is a review task, not an unearned AI lesson.
            guidance = "علت این وضعیت باید بررسی شود؛ تا تأیید، از ورود جدید خودداری کن."
        event_id = "SAFE-" + now.astimezone(UTC).date().isoformat() + "-" + reason
        data = (event_id, now.astimezone(UTC).isoformat(), "EXECUTION_GATE",
                reason, guidance, evidence[:256], "DETERMINISTIC_SAFETY_RULE")
        with sqlite3.connect(self.db_path) as conn:
            added = conn.execute(
                "INSERT OR IGNORE INTO safety_lessons VALUES (?, ?, ?, ?, ?, ?, ?)", data
            ).rowcount
            conn.commit()
        return {
            "event_id": event_id, "timestamp": data[1], "reason": reason,
            "guidance": guidance, "evidence": data[5],
            "confidence": "DETERMINISTIC_SAFETY_RULE",
        } if added else None

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT event_id, first_seen_utc AS timestamp, category, reason,"
                " guidance, evidence, confidence"
                " FROM safety_lessons ORDER BY first_seen_utc DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(x) for x in rows]
