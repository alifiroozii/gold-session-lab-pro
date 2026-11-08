"""Read-only XAU/USD quote adapter and fail-closed market execution gate.

No real order endpoints are imported or called in this module.
Historical and demo candles are NEVER execution quotes.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketQuote:
    bid: float
    ask: float
    timestamp: datetime
    source: str
    instrument: str = "XAU_USD"
    tradeable: bool = False


def execution_gate(quote: Optional[MarketQuote], now: Optional[datetime] = None,
                   max_age_seconds: int = 30) -> tuple[bool, str]:
    """Must pass for every manual/automatic order AND every paper price update."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        return False, "CLOCK_NOT_TIMEZONE_AWARE"
    if quote is None:
        return False, "NO_VERIFIED_LIVE_QUOTE"
    if quote.source != "OANDA_V20_READ_ONLY" or quote.instrument != "XAU_USD":
        return False, "UNTRUSTED_DATA_SOURCE"
    if not quote.tradeable:
        return False, "PROVIDER_MARKET_CLOSED"
    if quote.timestamp.tzinfo is None:
        return False, "QUOTE_TIMESTAMP_MISSING_TZ"
    if not all(map(math.isfinite, (quote.bid, quote.ask))):
        return False, "INVALID_QUOTE"
    if quote.bid <= 0 or quote.ask <= quote.bid:
        return False, "INVALID_BID_ASK"
    age = (now - quote.timestamp).total_seconds()
    if age < -5 or age > max_age_seconds:
        return False, "QUOTE_STALE_OR_FUTURE"
    local = now.astimezone(NEW_YORK)
    # Conservative spot-gold session guard. Provider tradeable flag also required.
    if local.weekday() == 5 or (local.weekday() == 4 and local.time() >= time(17)) or (
        local.weekday() == 6 and local.time() < time(18)
    ):
        return False, "WEEKEND_MARKET_CLOSED"
    if local.weekday() in (0, 1, 2, 3) and time(17) <= local.time() < time(18):
        return False, "DAILY_MARKET_BREAK"
    return True, "VERIFIED_LIVE_PRICE"


class OandaReadOnlyFeed:
    """Practice/Live pricing GET calls only; never connects to a real broker order API."""

    def __init__(self) -> None:
        self.token = os.getenv("OANDA_API_TOKEN", "").strip()
        self.account_id = os.getenv("OANDA_ACCOUNT_ID", "").strip()
        self.environment = os.getenv("OANDA_ENV", "practice").strip().lower()
        if self.environment not in ("practice", "live"):
            raise ValueError("OANDA_ENV must be practice or live")
        self.host = ("https://api-fxpractice.oanda.com" if self.environment == "practice"
                     else "https://api-fxtrade.oanda.com")
        self.configured = bool(self.token and self.account_id)

    def _get(self, path: str) -> dict:
        if not self.configured:
            raise RuntimeError("OANDA_READ_ONLY_NOT_CONFIGURED")
        request = Request(self.host + path, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
        }, method="GET")
        try:
            with urlopen(request, timeout=8) as response:
                return cast(Dict[str, Any], json.load(response))
        except (HTTPError, URLError, TimeoutError) as err:
            raise RuntimeError("OANDA_PRICE_FEED_UNAVAILABLE") from err

    def latest_quote(self) -> MarketQuote:
        raw = self._get(f"/v3/accounts/{self.account_id}/pricing?instruments=XAU_USD")
        records = [p for p in raw.get("prices", []) if p.get("instrument") == "XAU_USD"]
        if not records:
            raise RuntimeError("XAU_USD_UNAVAILABLE_FOR_THIS_ACCOUNT")
        p = records[0]
        bids, asks = p.get("bids") or [], p.get("asks") or []
        if not bids or not asks:
            raise RuntimeError("OANDA_HAS_NO_BID_ASK")
        ts = datetime.fromisoformat(p["time"].replace("Z", "+00:00"))
        return MarketQuote(
            bid=float(bids[0]["price"]), ask=float(asks[0]["price"]),
            timestamp=ts, source="OANDA_V20_READ_ONLY",
            tradeable=(p.get("tradeable") is True or
                       (p.get("status") == "tradeable" and p.get("tradeable") is not False)),
        )

    def historical_m1(self, count: int = 5000) -> list:
        """Return completed, real M1 candles (not ticks, not a live quote)."""
        from goldlab.types import Candle
        count = max(1, min(int(count), 5000))
        raw = self._get(
            f"/v3/accounts/{self.account_id}/instruments/XAU_USD/candles"
            f"?granularity=M1&count={count}&price=M"
        )
        result = []
        for item in raw.get("candles", []):
            if not item.get("complete") or not item.get("mid"):
                continue
            p = item["mid"]
            result.append(Candle(
                timestamp=datetime.fromisoformat(item["time"].replace("Z", "+00:00")),
                open=float(p["o"]), high=float(p["h"]), low=float(p["l"]),
                close=float(p["c"]), volume=float(item.get("volume", 0)),
            ))
        return sorted(result, key=lambda c: c.timestamp)
