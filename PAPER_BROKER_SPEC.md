# مشخصات فنی و مالی بروکر مجازی داخلی — PAPER_BROKER_SPEC.md
**نام موتور:** Gold Paper Broker  
**واحد پولی حساب:** USD (Virtual)  
**قرارداد پایه طلا:** ۱۰۰ اونس تروا به ازای هر لات استاندارد (Contract Size = 100.0)

---

## ۱. قوانین حسابداری و یکپارچگی دفتر کل (Ledger Invariance)

1. **دفتر کل دوطرفه (Double-Entry Ledger):**
   - موجودی حساب (`balance`) هرگز بدون ایجاد سطر جدید در جدول `wallet_ledger` تغییر نمی‌کند.
   - انواع رویدادهای مالی:
     - `DEPOSIT`: واریز وجه مجازی به حساب.
     - `WITHDRAWAL`: برداشت وجه مجازی مشروط به عدم تجاوز از مارجین آزاد (`free_margin`).
     - `TRADE_PNL`: سود یا زیان قطعی تحقق‌یافته ناشی از بسته شدن معامله.
     - `COMMISSION`: کارمزد معامله (پیش‌فرض ۵ دلار به ازای هر لات استاندارد رفت و برگشت).
     - `RESET`: بازگردانی حساب به وضعیت اولیه ۱۰,۰۰۰ دلاری و بایگانی معاملات پیشین.

---

## ۲. فرمول‌های محاسباتی مارجین، اهرم و سود/زیان

- **مارجین مورد نیاز (Required Margin):**
  $$\text{Required Margin} = \frac{\text{Lots} \times \text{Contract Size} \times \text{Execution Price}}{\text{Leverage}}$$
  *مثال:* برای معامله ۰.۱۰ لات با اهرم ۱۰۰:۱ در قیمت ۲۶۵۰ دلار:
  $$\text{Required Margin} = \frac{0.10 \times 100 \times 2650}{100} = \$265.00$$

- **ارزش حساب (Equity):**
  $$\text{Equity} = \text{Balance} + \text{Unrealized P\&L}$$

- **مارجین آزاد (Free Margin):**
  $$\text{Free Margin} = \text{Equity} - \text{Used Margin}$$

- **سطح مارجین (Margin Level Percentage):**
  $$\text{Margin Level} = \left(\frac{\text{Equity}}{\text{Used Margin}}\right) \times 100\%$$

- **محاسبه سود و زیان (P&L):**
  - معامله خرید (BUY):
    $$\text{P\&L} = (\text{Current Bid} - \text{Entry Price}) \times \text{Lots} \times \text{Contract Size}$$
  - معامله فروش (SELL):
    $$\text{P\&L} = (\text{Entry Price} - \text{Current Ask}) \times \text{Lots} \times \text{Contract Size}$$

---

## ۳. اجرای سفارش‌های شرطی و حد سود/ضرر (SL/TP & Pending Orders)

- **سفارش Buy Limit / Sell Stop:** با رسیدن قیمت Ask به نرخ هدف فعال می‌شود.
- **سفارش Sell Limit / Buy Stop:** با رسیدن قیمت Bid به نرخ هدف فعال می‌شود.
- **حد ضرر متحرک (Trailing Stop):** با رشد قیمت در جهت سود، حد ضرر با فاصله تعیین‌شده به صورت خودکار به سمت بالا/پایین کشیده می‌شود و هرگز به سمت زیان بازنمی‌گردد.
- **توقف زیان اضطراری (Stop Out):** در صورت افت سطح مارجین به زیر ۲۰٪، بزرگ‌ترین معامله زیان‌ده به صورت خودکار بسته می‌شود تا از منفی شدن مانده حساب جلوگیری گردد.
