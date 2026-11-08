# معماری فنی و مهندسی سیستم — ARCHITECTURE.md
**پروژه:** Gold Session Lab Pro (XAUUSD Quantitative Research & Internal Paper Broker)  
**نسخه:** 1.0.0  
**محیط اجرایی:** macOS Localhost (`127.0.0.1`)

---

## ۱. اصول طراحی معماری
1. **جداسازی کامل لایه‌ها (Clean Decoupled Architecture):**
   - **Market Data Pipeline:** دریافت، اعتبارسنجی کیفیت، تشخیص گپ/پرش قیمت و تجمیع قطعی کندل‌ها بدون نشت آینده.
   - **Session & Structure Engine:** محاسبه سشن‌های IANA (توکیو، لندن، نیویورک)، بازه مرجع آسیا و پیوت‌های سویینگ تاییدشده بعد از `right_bars`.
   - **Strategy Engine:** ۸ استراتژی مستقل با قوانین ریاضی صریح و قابل فعال/غیرفعال‌سازی ماژولار.
   - **Internal Paper Broker:** بروکر داخلی با دفتر کل دوطرفه (Double-Entry Ledger)، محاسبات اهرم/مارجین دقیق و اجرای سفارش‌های مارکت، لیمیت و استاپ.
   - **Automated Paper Bot:** ربات معامله‌گر با ماشین وضعیت، فیلتر اخبار اقتصادی و محدودیت‌های مدیریت ریسک (سقف ضرر روزانه، سقف پوزیشن، استراحت بعد از باخت متوالی).
   - **Backtesting Engine:** شبیه‌ساز رویدادمحور با مدل اسپرد، اسلیپیج و کارمزد، تفکیک زمانی داده‌ها (Train/Validation/OOS) و آزمون بوت‌استرپ.
   - **FastAPI & UI Layer:** سرور وب محلی و داشبورد تم روشن تعاملی با کتابخانه Lightweight Charts و طراحی RTL.

2. **عدم وابستگی به اینترنت یا سرورهای ابری خارجی:**
   - برنامه تمام داده‌ها و لاگ‌ها را در پایگاه داده SQLite با حالت WAL ذخیره کرده و روی لپ‌تاپ مک اجرا می‌شود.
   - هیچ پروسه‌ای در زمان Sleep یا خاموشی سیستم در پس‌زمینه ابری اجرا نمی‌گردد.

---

## ۲. دیاگرام جریان داده (Data Flow)

```
[ منبع داده / CSV / تیک لایو ]
               │
               ▼
     [ Data Pipeline & Diagnostics ]  --> [ SQLite / WAL: candles_1m ]
               │
               ▼
     [ Timeframe Aggregator: 5m, 15m, 1h ]
               │
               ▼
     [ Session Engine (IANA ZoneInfo) ]
               │
               ▼
     [ Market Structure Engine (Zero-Lookahead Swings, FVG, OB Proxies) ]
               │
               ▼
     [ Strategy Engine: S1..S8 Modular Setups ]
               │
               ▼ (سیگنال‌های تاییدشده در کلوز کندل t)
     [ Automated Bot & Risk Engine ]
               │
               ▼ (ارسال سفارش آزمایشی در اپن کندل t+1)
     [ Internal Gold Paper Broker ]
               │
       ┌───────┴───────┐
       ▼               ▼
[ Paper Positions ] [ Wallet Ledger (تراکنش‌های تغییر مانده) ]
       │
       ▼
[ FastAPI Local REST / WebSocket ]
       │
       ▼
[ Responsive Light Dashboard (TradingView Lightweight Charts) ]
```

---

## ۳. امنیت و قابلیت اطمینان (Security & Reliability)
- **محدودسازی دسترسی شبکه:** CORS و آدرس سرور اکیداً روی `127.0.0.1` قفل است.
- **تراکنش‌های پایگاه داده:** تراکنش‌های مالی و دفتر کل در تراکنش‌های اتمیک SQLite ثبت می‌شوند تا مانده حساب و سود/زیان هرگز دچار دوگانگی یا مغایرت نشود.
- **ایزوله‌سازی از بازار واقعی:** هیچ ماژولی برای احراز هویت لایو یا اتصال به کلیدهای API حساب واقعی وجود ندارد.
