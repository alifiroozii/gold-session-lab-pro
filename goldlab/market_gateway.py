"""
Market Data Gateway for Gold Session Lab Pro (Master Prompt V5).
Implements a strict three-layer data architecture:
- Layer A: TradingView Visual Reference (OANDA:XAUUSD, display-only, official embed metadata)
- Layer B: Verified Execution Quote (licensed provider, e.g. OANDA v20, with strict fail-closed gate)
- Layer C: Comparison Panel (transparent side-by-side audit of symbols, spreads, timestamps, and delta)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional

from goldlab.market_safety import (
    InstrumentSpecification,
    MarketQuote,
    OandaReadOnlyFeed,
    execution_gate,
)
from goldlab.types import Candle

TZ_UTC = timezone.utc


class MarketDataProvider(ABC):
    """Abstract base adapter for executable market data feeds."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for the data provider."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True if credentials and account permissions are present."""
        ...

    @abstractmethod
    def get_latest_quote(self) -> Optional[MarketQuote]:
        """Fetch latest verified executable quote."""
        ...

    @abstractmethod
    def get_historical_m1(self, count: int = 500) -> List[Candle]:
        """Fetch verified closed M1 historical candles."""
        ...


class OandaProviderAdapter(MarketDataProvider):
    """Adapter wrapping OandaReadOnlyFeed for verified spot CFD execution."""

    def __init__(self, feed: Optional[OandaReadOnlyFeed] = None) -> None:
        self.feed = feed or OandaReadOnlyFeed()

    @property
    def provider_id(self) -> str:
        return "OANDA_V20_READ_ONLY"

    @property
    def display_name(self) -> str:
        return "OANDA v20 API (Spot CFD)"

    @property
    def is_configured(self) -> bool:
        return self.feed.configured

    def get_latest_quote(self) -> Optional[MarketQuote]:
        if not self.feed.configured:
            return None
        return self.feed.latest_quote()

    def get_historical_m1(self, count: int = 500) -> List[Candle]:
        if not self.feed.configured:
            return []
        return self.feed.historical_m1(count=count)


@dataclass
class TradingViewReferenceMetadata:
    """Layer A: TradingView display-only reference metadata."""
    symbol: str = "OANDA:XAUUSD"
    display_name: str = "TradingView (OANDA:XAUUSD)"
    market_type: str = "Spot Gold CFD (Reference)"
    timeframe: str = "5m"
    widget_url: str = "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD"
    is_executable: bool = False
    notes: str = (
        "چارت مرجع بصری تریدینگ‌ویو صرفاً جهت پایش چشمی کاربر است. "
        "به دلیل عدم وجود API رسمی ارسال سفارش و شرایط خدمات TradingView، "
        "این مرجع هرگز به عنوان قیمت اجرای سفارش مجازی استفاده نمی‌شود."
    )


@dataclass
class ComparisonItem:
    """Row item in the Layer C Price Comparison Table."""
    source_layer: str
    symbol: str
    provider_name: str
    data_type: str
    last_quote_time: Optional[str]
    bid: Optional[float]
    ask: Optional[float]
    mid: Optional[float]
    spread: Optional[float]
    latency_estimate: str
    quote_validity: str
    is_executable: bool
    notes: str


class MarketDataGateway:
    """
    Central Market Data Gateway coordinating Layers A, B, and C.
    Enforces that unverified references NEVER authorize paper order fills.
    """

    def __init__(
        self,
        execution_provider: Optional[MarketDataProvider] = None,
        spec: Optional[InstrumentSpecification] = None,
    ) -> None:
        self.execution_provider: MarketDataProvider = (
            execution_provider or OandaProviderAdapter()
        )
        self.tv_reference = TradingViewReferenceMetadata()
        self.spec = spec or InstrumentSpecification()
        self._cached_tv_quote: Optional[Dict[str, Any]] = None

    def update_tv_reference_quote(self, quote_data: Optional[Dict[str, Any]]) -> None:
        """Cache only correctly timestamped scanner *reference* data.

        The scanner is not an execution provider; reject bad provenance.
        Revalidate time-to-live when comparison is requested.
        """
        self._cached_tv_quote = None
        if not isinstance(quote_data, dict):
            return
        if quote_data.get("ticker") != self.tv_reference.symbol:
            return
        if (quote_data.get("source") != "TRADINGVIEW_SCANNER_UNVERIFIED"
                or quote_data.get("data_role") != "REFERENCE_ONLY"
                or quote_data.get("verified_for_execution") is not False):
            return
        try:
            price = float(quote_data["price"])
            stamp = datetime.fromisoformat(
                str(quote_data["time_iso"]).replace("Z", "+00:00")
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            return
        if not math.isfinite(price) or price <= 0 or stamp.tzinfo is None:
            return
        self._cached_tv_quote = {
            "price": price,
            "time_iso": stamp.isoformat(),
            "ticker": self.tv_reference.symbol,
            "source": "TRADINGVIEW_SCANNER_UNVERIFIED",
        }

    def evaluate_execution_quote(
        self, quote: Optional[MarketQuote], now: Optional[datetime] = None
    ) -> tuple[bool, str]:
        """Enforces fail-closed Layer B execution check."""
        return execution_gate(quote, now=now)

    def get_comparison_payload(
        self,
        verified_quote: Optional[MarketQuote],
        last_completed_candle_price: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Builds the Layer C Comparison Panel payload comparing:
        1. TradingView Visual Reference (Layer A)
        2. Verified Execution Provider (Layer B)
        """
        now = now or datetime.now(TZ_UTC)
        gate_ok, gate_reason = self.evaluate_execution_quote(verified_quote, now=now)

        # Layer A: unofficial best-effort reference. Never invent a spread.
        tv_price: Optional[float] = None
        tv_time: Optional[str] = None
        if self._cached_tv_quote:
            stamp = datetime.fromisoformat(self._cached_tv_quote["time_iso"])
            age = (now - stamp).total_seconds()
            if -5 <= age <= 30:
                tv_price = float(self._cached_tv_quote["price"])
                tv_time = stamp.isoformat()

        layer_a = ComparisonItem(
            source_layer="لایه A (مرجع بصری)",
            symbol=self.tv_reference.symbol,
            provider_name=self.tv_reference.display_name,
            data_type="اسکنر غیررسمی (فقط مرجع)؛ ویجت رسمی جداگانه",
            last_quote_time=tv_time,
            bid=None,
            ask=None,
            mid=tv_price,
            spread=None,
            latency_estimate="نامشخص؛ سن مظنه با زمان منبع بررسی می‌شود",
            quote_validity=("مرجع تازه اما غیرقابل معامله"
                            if tv_price is not None else
                            "مرجع ناموجود، منقضی یا تأییدنشده"),
            is_executable=False,
            notes=("اسکنر غیررسمی، فید تضمین‌شدهٔ TradingView نیست؛ "
                   "ویجت رسمی مستقل از این داده نمایش داده می‌شود."),
        )

        # Layer B: Execution Feed
        b_bid = verified_quote.bid if verified_quote else None
        b_ask = verified_quote.ask if verified_quote else None
        b_mid = verified_quote.mid if verified_quote else None
        b_spread = verified_quote.spread if verified_quote else None
        b_time = verified_quote.timestamp.isoformat() if verified_quote else None

        exec_validity = (
            "معتبر و مجاز برای معامله مجازی"
            if gate_ok
            else f"غیرمجاز: {gate_reason}"
        )
        if not self.execution_provider.is_configured:
            exec_validity = "پیکربندی نشده (نیاز به توکن OANDA در .env)"

        layer_b = ComparisonItem(
            source_layer="لایه B (مظنه اجرایی تأییدشده)",
            symbol=self.spec.instrument,
            provider_name=self.execution_provider.display_name,
            data_type="مظنه لحظه‌ای Bid/Ask و کندل بسته Mid",
            last_quote_time=b_time,
            bid=b_bid,
            ask=b_ask,
            mid=b_mid,
            spread=b_spread,
            latency_estimate=(
                f"سن مظنه: {(now - verified_quote.timestamp).total_seconds():.1f} ثانیه؛ "
                "تأخیر واقعی شبکه اندازه‌گیری نشده"
                if verified_quote is not None else "بدون مظنه معتبر"
            ),
            quote_validity=exec_validity,
            is_executable=gate_ok,
            notes="منبع قانونی دارای مجوز احراز هویت؛ تنها منبع مجاز برای شبیه‌سازی ورود/خروج.",
        )

        # Price variance / delta calculation
        delta_mid: Optional[float] = None
        if tv_price is not None and b_mid is not None:
            delta_mid = round(b_mid - tv_price, 2)

        return {
            "status": "SUCCESS",
            "timestamp": now.isoformat(),
            "layers": [layer_a.__dict__, layer_b.__dict__],
            "price_delta": {
                "difference_usd": delta_mid,
                "note": (
                    "این اختلاف فقط زمانی محاسبه می‌شود که هر دو مشاهده تازه "
                    "باشند. نوع قیمت (آخرین قیمت در برابر Mid مظنه) ممکن است متفاوت باشد؛ "
                    "هیچ نتیجهٔ قطعی دربارهٔ صحت یا سودآوری نمی‌دهد."
                ),
            },
            "execution_gate": {
                "allowed": gate_ok,
                "reason": gate_reason,
            },
            "last_completed_candle_price": last_completed_candle_price,
            "disclaimer": (
                "هیچ قیمت ساختگی به عنوان داده زنده نمایش داده نمی‌شود. "
                "در صورت قطع بودن فید لایه B، ثبت هرگونه سفارش مجازی متوقف می‌گردد."
            ),
        }
