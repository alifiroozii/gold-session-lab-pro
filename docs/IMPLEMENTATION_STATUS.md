# وضعیت واقعی اجرای Gold Session Lab Pro — ۲۰۲۶/۱۱/۰۸

**وضعیت:** پژوهش و معاملات مجازی با دروازه ایمنی. **نه سیستم معاملاتی کاملاً معتبر و نه Agent خودکار متصل ۲۴ساعته.**

## اجراشده و راستی‌آزمایی‌شده در شاخه fix/market-data-safety-session-chart

- حذف بارگذاری خودکار کندل‌های ساختگی؛ فقط با `GOLDLAB_ENABLE_DEMO_REPLAY=1` حالت آموزشی در دسترس است.
- اتصال خواندنی OANDA v20 pricing stream با اعتبارسنجی تازگی (< ۳۰ ثانیه)، کنترل ساعات تعطیلی بازار و سقف اسپرد مجاز ($۲.۵۰).
- تثبیت مشخصات رسمی نماد XAU_USD در `InstrumentSpecification` (دقت ۲ رقم اعشار، Tick Size = 0.01 دلار، قرارداد ۱۰۰ اونس) و انتقال کامل محاسبات مالی به `Decimal`.
- رفع قطعی دو باگ استراتژی (تحویل سیگنال کندل اخیر به ربات و حذف کامل نشت آینده سشن‌ها با `calculate_as_of_session_stats_series`).
- پیاده‌سازی و اعتبارسنجی کامل هر ۸ استراتژی (اضافه شدن ادامه روند نزولی در S7 و پیاده‌سازی کامل استراتژی ترکیبی S8).
- افزودن قابلیت لغو سفارش‌های معلق (`cancel_order`)، توقف اضطراری (`emergency_stop`) و فعال‌سازی مجدد صریح اپراتور در ربات معامله‌گر.
- اعمال سقف معاملات روزانه (`max_daily_trades`)، پیشگیری از سفارش تکراری (Idempotency) و مدیریت کول‌داون پس از زیان‌های متوالی.
- کالبدشکافی ۴ لایه‌ای معاملات (دسته‌بندی A/B/C/D) و استخراج خودکار راهنمای «دفعه بعد چه کار نکنیم؟» در ژورنال تصمیمات.
- پایش امنیتی وب‌سوکت در برابر حملات CSWSH با اعتبارسنجی سخت‌گیرانه Origin.
- مجموعه کامل ۸۴ تست خودکار واحد، یکپارچگی، رگرسیون و بازتولید باگ‌ها همراه با قبولی ۱۰۰٪ در پایپ‌لاین CI گیت‌هاب.

## موارد مهم باقی‌مانده و مرزهای عملیاتی

1. **دسترسی عملیاتی به قیمت زنده OANDA:** نیاز به ثبت کلید دسترسی شخصی و شماره حساب تمرینی/واقعی OANDA کاربر در `.env` جهت دریافت تیک‌های زنده خارج از ساعات تعطیل.
2. **غیرفعال ماندن آگاهانه PAPER_AUTO:** فعال‌سازی معامله خودکار نیازمند تکمیل ارزیابی خارج از نمونه (Out-of-Sample) روی دیتاست معتبر است؛ در وضعیت جاری معاملات دمو منحصراً به‌صورت دستی با قیمت معتبر یا کنترل‌شده اجرا می‌شوند.
3. **اتصال Antigravity محلی:** پل ارتباطی `AgentBridge` مدارک و رویدادها را ثبت می‌کند؛ فعال‌سازی عامل خودمختار Antigravity نیازمند اجرای محلی زمان‌بندی‌شده در کلاینت مک است.
4. **محدودیت سیستم محلی:** برنامه برای اجرا روی مک و به صورت محلی در `127.0.0.1` طراحی شده و در زمان Sleep سیستم متوقف می‌شود.

برای راه‌اندازی و محدودیت‌ها: `docs/LIVE_FEED_AGENT_SETUP.md` و `docs/STRATEGY_VERIFICATION.md`.


## Progress update — 2026-11-08: causal provider candles and session-first UI

**Implemented on the draft PR branch; not merged into main.**

- Removed browser-side `fetchMarketData()` fallback that silently posted `/api/market/load-demo` when verified provider candles were unavailable. The main chart now displays an explicit no-data state.
- Guarded the `/api/market/load-demo` API with `GOLDLAB_ENABLE_DEMO_REPLAY=1`. Synthetic chart replay never authorizes new paper orders, even when a separate provider stream is connected.
- `DataPipeline.aggregate_candles(..., require_complete=True)` rejects duplicated provider M1 timestamps and excludes partial or gapped 5m/15m/1h buckets. `app.py` enables this for OANDA provider candles.
- Uses the **actual timestamp of the verified quote** rather than the historical candle timestamp as the clock for bot feed diagnostics.
- Bot strict-provider path evaluates only newly completed timeframe bars, rejects delayed next-bar signals, and uses durable SQLite `bot_processed_candles` for deduplication across polling and restarts.
- Bot's fake broker trade size is rounded down, never inflated to the minimum 0.01 lot when this would exceed risk. Strict-provider execution sizing derives its SL distance from executable bid/ask rather than an earlier proxy close.
- Persists the UTC day's starting equity and atomically claimed order slots in `bot_daily_limits`, preventing an app restart from resetting the simulated daily loss baseline or the daily order cap.
- Separated chart engine from the bot's fixed 5m strategy engine. Changing the chart to 1m/15m no longer changes the automated research timeframe.
- Asia research range and Tokyo are no longer conflated in session statistics. Asia boxes and signals refer to the explicitly configured **20:00–00:00 New York** reference; chart boxes cross local midnight correctly. Weekend/session logic now follows IANA NY DST rather than a fixed UTC opening.
- Setups 1 and 2 use finalized levels known before breakout/sweep, not levels recalculated after the market move.
- Improved bright chart layout, initial zoom/pan behavior, empty-data messaging, session labels and diagnostic status without inventing live prices.
- A WebSocket TICK can update the displayed quote but cannot bypass the backend trading authorization gate.
- Added regression tests for strict aggregation, session freezing, quote/source truthfulness, restart idempotency, risk cap persistence, and chart vs. bot timeframe isolation.

**Not verified/completed:** A licensed user-connected executable XAU/USD live quote/feed; accurate parity with a user-selected TradingView symbol and quote type; quantitative profitability of any strategy; real paper-auto entry/exit under current market conditions; end-to-end browser screenshot acceptance on the user's Mac; an indefinitely scheduled Antigravity agent. The `PAPER_AUTO` endpoint remains intentionally unavailable until causal, risk, and data-source criteria are independently demonstrated. GitHub Actions `pytest` is a software check, not profitability evidence.

**Local setup:** `git fetch origin && git checkout fix/market-data-safety-session-chart && git pull`; `python -m pytest -q`; `python app.py`. For optional trusted Antigravity IDE/pull handoff, read `docs/NEXT_RELEASE_ACCEPTANCE.md` and `AGENTS.md`.
