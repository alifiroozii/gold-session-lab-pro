# گزارش جامع نتایج آزمون‌های خودکار — TEST_REPORT.md
**تاریخ اجرا:** ۲۰۲۶-۱۱-۰۸  
**محیط اجرا:** macOS / Python 3.11  
**ابزارهای تست:** Pytest 9.2.0, Ruff 0.17.4, Mypy 2.4.1

---

## ۱. نتایج تست‌های واحد و یکپارچگی (Pytest Results)

| ماژول تست | تعداد آزمون‌ها | وضعیت | موضوعات تحت پوشش |
| :--- | :---: | :---: | :--- |
| `tests/test_sessions.py` | ۳ | **PASSED** | سشن‌های توکیو، لندن، نیویورک، هم‌پوشانی و تعطیلی آخر هفته طلا |
| `tests/test_dst_fixtures.py` | ۱ | **PASSED** | تغییر ساعت فصول بهار و پاییز آمریکا و انگلستان (DST Transition) |
| `tests/test_market_structure.py` | ۲ | **PASSED** | سویینگ پیوت‌ها بدون نشت آینده، FVG سه کندلی و پوشش شکاف نقدینگی |
| `tests/test_setups.py` | ۱ | **PASSED** | اثبات قطعی ورود در کندل بعد (Next Candle Open) در الگوی Sweep+Reclaim+BOS |
| `tests/test_simulator.py` | ۲ | **PASSED** | اعمال بدترین حالت در برخورد هم‌زمان SL/TP و تعدیل اسپرد/اسلیپیج |
| `tests/test_paper_broker.py` | ۳ | **PASSED** | یکپارچگی دفتر کل، واریز/برداشت مجازی، محاسبه مارجین و سود/زیان |
| `tests/test_engine.py` | ۱ | **PASSED** | اجرای کامل پایپ‌لاین از کندل خام تا آماده‌سازی خروجی داشبورد |
| `tests/test_regression.py` | ۲ | **PASSED** | تشخیص فید قدیمی (Stale) و جهش قیمت گپ آخر هفته جمعه تا یکشنبه |
| `tests/test_api_endpoints.py` | ۶ | **PASSED** | اعتبارسنجی تمام اندپوینت‌های REST و سرویس داشبورد محلی FastAPI |
| **مجموع کل** | **۲۱ آزمون** | **۱۰۰٪ سبز** | **زمان کل اجرا: ۲.۰۶ ثانیه** |

---

## ۲. گزارش تحلیل استاتیک و بازبینی کد (Ruff & Mypy)

- **Ruff Linter:** `All checks passed!` (۰ خطا، فرمت‌بندی استاندارد و مرتب‌سازی ایمپورت‌ها).
- **Mypy Static Type Checker:** `Success: no issues found in 15 source files` (تایپینگ کامل بر مبنای پایتون ۳.۱۱).
