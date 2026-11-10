#property copyright "Gold Session Lab Pro - Optimization Phase"
#property link      "https://github.com/alifiroozi/gold-session-mt5-research"
#property version   "3.50"
#property strict

#include "GoldResearchLab/SessionEngine.mqh"
#include "GoldResearchLab/LevelDetector.mqh"
#include "GoldResearchLab/MarketStructure.mqh"
#include "GoldResearchLab/BreakoutStrategy.mqh"
#include "GoldResearchLab/ConfirmationEngine.mqh"
#include "GoldResearchLab/RiskGuardian.mqh"
#include "GoldResearchLab/TradeExecution.mqh"
#include "GoldResearchLab/PositionManager.mqh"
#include "GoldResearchLab/MarketRegimeDetector.mqh"
#include "GoldResearchLab/IntermarketConfirmationEngine.mqh"
#include "GoldResearchLab/ChartVisualizer.mqh"

enum LotSizeMode { LOT_FIXED_RESEARCH, LOT_DYNAMIC_RISK };

enum OptimizationModel {
   MODEL_BALANCED_ORIGINAL,
   MODEL_HEAVY_ORIGINAL,
   MODEL_BALANCED_OPTIMIZED,
   MODEL_HEAVY_OPTIMIZED,
   MODEL_HYBRID
};

enum TimeWindowMode {
   WINDOW_08_09,
   WINDOW_08_10,
   WINDOW_08_11
};

enum StopLossTargetMode {
   SLTP_FIXED_BAR_RR,     // Original: SL at bar low/high + buffer, TP = 1.5R
   SLTP_VOLATILITY_ATR     // Volatility: SL = 1.5*ATR, TP = 2.0*ATR
};

enum DayFilterMode {
   DAY_ALL,                // Trade all days (Mon-Fri)
   DAY_NO_FRIDAY,          // Exclude Friday (Mon-Thu only)
   DAY_CORE_TUE_THU,       // Core days only (Tue, Wed, Thu)
   DAY_NO_MONDAY           // Exclude Monday (Tue-Fri only)
};

input string ExpectedSymbol = "XAUUSD_o";
input BrokerClock ServerClock = CLOCK_LITEFINANCE_EU;
input ReferenceKind Reference = REF_ASIA_UTC;
input LotSizeMode LotMode = LOT_DYNAMIC_RISK;
input double FixedLot = 0.10;
input OptimizationModel ModelChoice = MODEL_HEAVY_OPTIMIZED;
input double RiskPerTradePct = 1.0;
input double DailyLossLimitPct = 6.0;
input double TargetRR = 1.5;
input double MaxRangeWidth = 30.0;
input double MinStopBps = 5.8;

// Advanced Exploration Switches (Independent Feature Toggles)
input TimeWindowMode TimeWindow = WINDOW_08_10;
input StopLossTargetMode SLTPMode = SLTP_FIXED_BAR_RR;
input bool OptRequireRetest = false;          // Feature: Retest confirmation
input bool OptUseAtrFilter = true;            // Feature: ATR overextension and minimum displacement
input double OptMinAtrRatio = 0.50;           // Bar range >= MinAtrRatio * ATR
input double OptMaxAtrRatio = 2.50;           // Bar range <= MaxAtrRatio * ATR
input bool OptRequireCloseLocation = false;   // Feature: Close in upper/lower 25% of candle
input double OptVolumeRatioMin = 1.10;        // Feature: Tick volume ratio threshold
input double OptFvgMinSize = 0.35;            // Feature: Minimum FVG gap size in dollars
input bool OptOpposingSweepBonus = false;     // Feature: Prior liquidity sweep confirmation
input bool OptUseRangeWidthFilter = false;    // Feature: MaxRangeWidth filter
input DayFilterMode DayFilter = DAY_NO_FRIDAY;// Seasonality: Day of Week Filter
input double OptBreakEvenRR = 0.0;            // Feature: Move SL to Breakeven at RR distance (0.0 = disabled)
input double OptTrailRR = 0.0;                // Feature: Trail SL at RR distance (0.0 = disabled)
input bool InpShowVisuals = true;             // Visuals: Draw Asian range, London box and HUD

// State tracking
int g_atr_handle = INVALID_HANDLE;
int g_ema_handle = INVALID_HANDLE;
int g_adx_handle = INVALID_HANDLE;
datetime g_last_processed_bar = 0;
bool g_traded_today = false;
datetime g_current_day_start = 0;
CTrade g_execution;
CChartVisualizer g_visualizer(0);

bool FeatureAt(const MqlRates &bars[], const datetime server_open, Features &out)
{
   double atr[1], ema[1], adx[1];
   MqlRates hour[1], structure[];
   ArraySetAsSeries(structure, true);
   if(CopyBuffer(g_atr_handle, 0, 2, 1, atr) != 1 || CopyBuffer(g_ema_handle, 0, 1, 1, ema) != 1 ||
      CopyBuffer(g_adx_handle, 0, 1, 1, adx) != 1 || CopyRates(_Symbol, PERIOD_H1, 1, 1, hour) != 1 ||
      CopyRates(_Symbol, PERIOD_M15, 1, 4, structure) != 4) return false;
   if(atr[0] <= 0 || ema[0] <= 0 || adx[0] < 0 || adx[0] > 100 ||
      atr[0] == EMPTY_VALUE || ema[0] == EMPTY_VALUE ||
      !MathIsValidNumber(atr[0]) || !MathIsValidNumber(ema[0]) || !MathIsValidNumber(adx[0]) ||
      hour[0].time + 3600 > server_open || structure[0].time + 900 > server_open ||
      !ValidBar(hour[0])) return false;
   for(int i = 0; i < 4; i++) if(!ValidBar(structure[i])) return false;
   out.atr = atr[0];
   out.ema = ema[0];
   out.adx = adx[0];
   out.hour_close = hour[0].close;
   double high = structure[1].high, low = structure[1].low, volume = 0;
   for(int i = 2; i < 4; i++)
   {
      high = MathMax(high, structure[i].high);
      low = MathMin(low, structure[i].low);
   }
   out.m15_break = structure[0].close > high ? 1 : (structure[0].close < low ? -1 : 0);
   for(int i = 1; i <= 20; i++) volume += (double)bars[i].tick_volume;
   out.volume_ratio = 20.0 * (double)bars[0].tick_volume / volume;
   return true;
}

int OnInit()
{
   if(!ResearchTester()) return INIT_FAILED;
   if(ServerClock==CLOCK_UNSPECIFIED || _Period!=PERIOD_M5 || _Symbol!=ExpectedSymbol ||
      AccountInfoString(ACCOUNT_CURRENCY)!="USD") return INIT_PARAMETERS_INCORRECT;

   g_atr_handle = iATR(_Symbol, PERIOD_M5, 14);
   g_ema_handle = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_adx_handle = iADXWilder(_Symbol, PERIOD_H1, 14);
   if(g_atr_handle == INVALID_HANDLE || g_ema_handle == INVALID_HANDLE || g_adx_handle == INVALID_HANDLE)
      return INIT_FAILED;

   g_execution.SetExpertMagicNumber(LAB_MAGIC);
   g_execution.SetDeviationInPoints((ulong)MathFloor(0.10/_Point));
   if(!g_execution.SetTypeFillingBySymbol(_Symbol)) return INIT_FAILED;

   g_last_processed_bar = 0;
   g_traded_today = false;
   g_current_day_start = 0;
   
   PrintFormat("GLAB|INIT|%s|Server:%s|Login:%d|Balance:%.2f",
               (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? "LIVE_DEMO" : "TESTER"),
               AccountInfoString(ACCOUNT_SERVER),
               (int)AccountInfoInteger(ACCOUNT_LOGIN),
               AccountInfoDouble(ACCOUNT_BALANCE));
               
   Comment(StringFormat("=== GOLD SESSION LAB PRO v3.6 (CHAMPION) ===\nMode: %s | Server: %s | Login: %d\nBalance: $%.2f | Initialized successfully.",
               (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? "LIVE DEMO" : "TESTER"),
               AccountInfoString(ACCOUNT_SERVER),
               (int)AccountInfoInteger(ACCOUNT_LOGIN),
               AccountInfoDouble(ACCOUNT_BALANCE)));
               
   if(InpShowVisuals)
   {
      g_visualizer.SetupChartEnvironment();
      EventSetTimer(1);
      UpdateVisualDisplay();
   }
   
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(InpShowVisuals) g_visualizer.ClearVisuals();
   if(g_atr_handle != INVALID_HANDLE) IndicatorRelease(g_atr_handle);
   if(g_ema_handle != INVALID_HANDLE) IndicatorRelease(g_ema_handle);
   if(g_adx_handle != INVALID_HANDLE) IndicatorRelease(g_adx_handle);
}

void SaveTelemetryFile(const DiagnosticTelemetry &d)
{
   int handle = FileOpen("live_telemetry.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle != INVALID_HANDLE)
   {
      string q = CharToString(34);
      string nl = CharToString(10);
      string json = "{" + nl;
      json += "  " + q + "server_time" + q + ": " + q + TimeToString(d.current_time_srv, TIME_DATE|TIME_SECONDS) + q + "," + nl;
      json += "  " + q + "utc_time" + q + ": " + q + TimeToString(d.current_time_utc, TIME_DATE|TIME_SECONDS) + q + "," + nl;
      json += "  " + q + "session_phase" + q + ": " + q + d.session_phase + q + "," + nl;
      json += "  " + q + "in_window" + q + ": " + (d.in_window ? "true" : "false") + "," + nl;
      json += "  " + q + "window_status" + q + ": " + q + d.window_status + q + "," + nl;
      json += "  " + q + "day_filter" + q + ": " + q + d.day_filter_status + q + "," + nl;
      json += "  " + q + "asian_high" + q + ": " + DoubleToString(d.asian_high, 2) + "," + nl;
      json += "  " + q + "asian_low" + q + ": " + DoubleToString(d.asian_low, 2) + "," + nl;
      json += "  " + q + "asian_width" + q + ": " + DoubleToString(d.asian_width, 2) + "," + nl;
      json += "  " + q + "range_valid" + q + ": " + (d.range_valid ? "true" : "false") + "," + nl;
      json += "  " + q + "current_bid" + q + ": " + DoubleToString(d.current_bid, 2) + "," + nl;
      json += "  " + q + "current_ask" + q + ": " + DoubleToString(d.current_ask, 2) + "," + nl;
      json += "  " + q + "breakout_side" + q + ": " + IntegerToString(d.breakout_side) + "," + nl;
      json += "  " + q + "candle_strength" + q + ": " + DoubleToString(d.candle_strength, 2) + "," + nl;
      json += "  " + q + "candle_strength_ok" + q + ": " + (d.candle_strength_ok ? "true" : "false") + "," + nl;
      json += "  " + q + "bos_m15" + q + ": " + IntegerToString(d.bos_m15) + "," + nl;
      json += "  " + q + "fvg_gap_size" + q + ": " + DoubleToString(d.fvg_gap_size, 2) + "," + nl;
      json += "  " + q + "fvg_ok" + q + ": " + (d.fvg_ok ? "true" : "false") + "," + nl;
      json += "  " + q + "volume_ratio" + q + ": " + DoubleToString(d.volume_ratio, 2) + "," + nl;
      json += "  " + q + "volume_ok" + q + ": " + (d.volume_ok ? "true" : "false") + "," + nl;
      json += "  " + q + "atr_ratio" + q + ": " + DoubleToString(d.atr_ratio, 2) + "," + nl;
      json += "  " + q + "atr_ok" + q + ": " + (d.atr_ok ? "true" : "false") + "," + nl;
      json += "  " + q + "decision" + q + ": " + q + d.decision_summary + q + "," + nl;
      json += "  " + q + "reason_en" + q + ": " + q + d.reason_detail + q + "," + nl;
      json += "  " + q + "account_balance" + q + ": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "," + nl;
      json += "  " + q + "account_equity" + q + ": " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + nl;
      json += "}" + nl;
      
      FileWriteString(handle, json);
      FileClose(handle);
   }

   // Append periodic snapshot to live journal (every 10 seconds or state change)
   static datetime last_journal_time = 0;
   if(d.current_time_srv - last_journal_time >= 10 || last_journal_time == 0)
   {
      last_journal_time = d.current_time_srv;
      int jhandle = FileOpen("live_decisions_journal.csv", FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(jhandle != INVALID_HANDLE)
      {
         FileSeek(jhandle, 0, SEEK_END);
         if(FileSize(jhandle) == 0)
         {
            FileWrite(jhandle, "UTC_Time", "Server_Time", "Bid", "Asian_Range", "Window", "Day_Filter", "Breakout", "Candle_Body", "BOS_M15", "FVG", "Vol_Ratio", "ATR_Ratio", "Decision", "Reason");
         }
         string brk_str = (d.breakout_side == 1 ? "BULLISH" : (d.breakout_side == -1 ? "BEARISH" : "NONE"));
         string range_str = StringFormat("%.2f-%.2f ($%.2f)", d.asian_high, d.asian_low, d.asian_width);
         FileWrite(jhandle,
                   TimeToString(d.current_time_utc, TIME_MINUTES|TIME_SECONDS),
                   TimeToString(d.current_time_srv, TIME_MINUTES|TIME_SECONDS),
                   DoubleToString(d.current_bid, 2),
                   range_str,
                   d.window_status,
                   d.day_filter_status,
                   brk_str,
                   DoubleToString(d.candle_strength * 100.0, 1) + "%",
                   IntegerToString(d.bos_m15),
                   DoubleToString(d.fvg_gap_size, 2),
                   DoubleToString(d.volume_ratio, 2),
                   DoubleToString(d.atr_ratio, 2),
                   d.decision_summary,
                   d.reason_detail);
         FileClose(jhandle);
      }
   }
}

void UpdateVisualDisplay()
{
   if(!InpShowVisuals) return;
   
   datetime current = TimeCurrent();
   datetime utc = ServerToUTC(current, ServerClock);
   
   int london_min = (int)(((utc + (EuropeSummer(utc)?3600:0)) % 86400) / 60);
   bool is_london = (london_min >= 8*60 && london_min < 11*60);
   
   string status_str = g_traded_today ? "TRADED TODAY (Max 1 Trade/Day Limit Reached)" :
                       (is_london ? "IN LONDON WINDOW - Active Breakout Monitoring" : "Outside London Window - Waiting for 08:00 UTC");

   PriceRange level_ny={};
   if(!ReadRange(Reference, utc-300, ServerClock, level_ny))
      ReadRange(REF_ASIA_UTC, utc-300, ServerClock, level_ny);

   double atr_val = 0.0;
   if(g_atr_handle != INVALID_HANDLE)
   {
      double atr_buf[];
      ArraySetAsSeries(atr_buf, true);
      if(CopyBuffer(g_atr_handle, 0, 0, 1, atr_buf) > 0) atr_val = atr_buf[0];
   }

   g_visualizer.DrawSessions(current, ServerClock);
   g_visualizer.DrawHUD(status_str, level_ny, atr_val);

   // Populate Live Diagnostics Telemetry
   DiagnosticTelemetry diag;
   ZeroMemory(diag);
   diag.current_time_srv = current;
   diag.current_time_utc = utc;

   MqlDateTime dt;
   TimeToStruct(utc, dt);

   string day_names[7] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
   string day_name = (dt.day_of_week >= 0 && dt.day_of_week < 7) ? day_names[dt.day_of_week] : "Unknown";

   bool day_passed = true;
   string day_rule = "ALLOWED";
   if(DayFilter == DAY_NO_FRIDAY && dt.day_of_week == 5)
   {
      day_passed = false;
      day_rule = "BLOCK (No-Friday)";
   }
   else if(DayFilter == DAY_CORE_TUE_THU && (dt.day_of_week == 1 || dt.day_of_week == 5))
   {
      day_passed = false;
      day_rule = "BLOCK (Tue-Thu only)";
   }
   else if(DayFilter == DAY_NO_MONDAY && dt.day_of_week == 1)
   {
      day_passed = false;
      day_rule = "BLOCK (No-Monday)";
   }
   diag.day_filter_status = StringFormat("%s: %s [%s]", day_name, day_passed ? "PASS" : "BLOCK", day_rule);

   bool in_08_10 = (london_min >= 8*60 && london_min < 10*60);
   diag.in_window = in_08_10;
   if(london_min < 7*60)
   {
      diag.session_phase = "ASIAN SESSION (Active)";
      int left_mins = 8*60 - london_min;
      diag.window_status = StringFormat("PRE-SESSION (Window in %dh %02dm)", left_mins / 60, left_mins % 60);
   }
   else if(london_min < 8*60)
   {
      diag.session_phase = "PRE-LONDON (Standby)";
      int left_mins = 8*60 - london_min;
      diag.window_status = StringFormat("COUNTDOWN (Window in %d min)", left_mins);
   }
   else if(in_08_10)
   {
      diag.session_phase = "⚡ LONDON BREAKOUT (Active)";
      int left_mins = 10*60 - london_min;
      diag.window_status = StringFormat("ACTIVE HUNTING (%d min left)", left_mins);
   }
   else
   {
      diag.session_phase = "POST-BREAKOUT (Closed)";
      diag.window_status = "CLOSED (Next session tomorrow)";
   }

   diag.asian_high = level_ny.high;
   diag.asian_low = level_ny.low;
   diag.asian_width = level_ny.high - level_ny.low;
   diag.range_valid = (level_ny.high > level_ny.low && (!OptUseRangeWidthFilter || (diag.asian_width >= 2.0 && diag.asian_width <= MaxRangeWidth)));

   MqlTick tick={};
   SymbolInfoTick(_Symbol, tick);
   diag.current_bid = tick.bid;
   diag.current_ask = tick.ask;

   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   int copied = CopyRates(_Symbol, PERIOD_M5, 1, 32, bars);

   if(copied >= 32)
   {
      Features feat={};
      FeatureAt(bars, current-300, feat);

      MqlRates bar = bars[0];
      if(bar.close > level_ny.high + 0.10 && bar.close > bar.open)
         diag.breakout_side = 1;
      else if(bar.close < level_ny.low - 0.10 && bar.close < bar.open)
         diag.breakout_side = -1;
      else
         diag.breakout_side = 0;

      diag.candle_strength = (bar.high - bar.low > _Point) ? MathAbs(bar.close - bar.open) / (bar.high - bar.low) : 0.0;
      diag.candle_strength_ok = (diag.candle_strength >= 0.45);

      diag.bos_m15 = feat.m15_break;
      diag.fvg_ok = (diag.breakout_side != 0) ? QualityFvgConfirmed(bars, diag.breakout_side, OptFvgMinSize) : false;
      diag.fvg_gap_size = diag.fvg_ok ? OptFvgMinSize : 0.0;

      diag.volume_ratio = feat.volume_ratio;
      diag.volume_ok = (feat.volume_ratio >= OptVolumeRatioMin);

      double bar_rng = bar.high - bar.low;
      diag.atr_ratio = (feat.atr > 0.0) ? (bar_rng / feat.atr) : 1.0;
      diag.atr_ok = (diag.atr_ratio >= OptMinAtrRatio && diag.atr_ratio <= OptMaxAtrRatio);
   }

   if(g_traded_today)
   {
      diag.decision_summary = "LIMIT REACHED: 1 Trade/Day";
      diag.reason_detail = "Maximum 1 trade per day executed. Robot protecting capital.";
      diag.reason_persian = "سقف ۱ معامله در روز انجام شده؛ ربات در حال محافظت از سرمایه است.";
      diag.status_color = clrGold;
   }
   else if(!day_passed)
   {
      diag.decision_summary = "FILTERED: Seasonality Day Block";
      diag.reason_detail = StringFormat("%s blocked by quantitative seasonality rules.", day_name);
      diag.reason_persian = "امروز طبق فیلتر فصلی معامله نمی شود (کاهش ریسک برگشت).";
      diag.status_color = clrCrimson;
   }
   else if(!diag.in_window)
   {
      diag.decision_summary = "IDLE: Outside London Window";
      diag.reason_detail = "Breakout triggers activate only 08:00-10:00 UTC (11:30-13:30 Tehran).";
      diag.reason_persian = "خارج از پنجره ۰۸:۰۰ تا ۱۰:۰۰ لندن؛ ربات در انتظار زمان شکار است.";
      diag.status_color = clrOrange;
   }
   else if(OptUseRangeWidthFilter && !diag.range_valid)
   {
      diag.decision_summary = "FILTERED: Asian Range Invalid";
      diag.reason_detail = StringFormat("Asian width $%.2f exceeds max limit $%.2f.", diag.asian_width, MaxRangeWidth);
      diag.reason_persian = "عرض رنج آسیا از سقف مجاز فراتر رفته است.";
      diag.status_color = clrOrangeRed;
   }
   else if(diag.breakout_side == 0)
   {
      diag.decision_summary = "SCANNING: Price Inside Asian Range";
      diag.reason_detail = StringFormat("Price %.2f within bounds (%.2f - %.2f). Awaiting M5 close.", diag.current_bid, diag.asian_low, diag.asian_high);
      diag.reason_persian = "قیمت درون رنج آسیا است؛ در انتظار شکست معتبر کندل M5.";
      diag.status_color = clrCyan;
   }
   else
   {
      if(!diag.candle_strength_ok)
      {
         diag.decision_summary = "FILTERED: Weak Candle Body";
         diag.reason_detail = StringFormat("Candle body ratio %.1f%% < 45%% minimum. Fakeout risk.", diag.candle_strength * 100.0);
         diag.reason_persian = "بدنه کندل بریک اوت ضعیف است؛ احتمال تله و فیک بریک بالاست.";
         diag.status_color = clrYellow;
      }
      else if(!diag.fvg_ok)
      {
         diag.decision_summary = "FILTERED: FVG Imbalance Missing";
         diag.reason_detail = StringFormat("Fair Value Gap < %.2f pts. Institutional confirmation missing.", OptFvgMinSize);
         diag.reason_persian = "ناحیه FVG کافی تشکیل نشده؛ تاییدیه جریان نقدینگی غایب است.";
         diag.status_color = clrYellow;
      }
      else if(diag.bos_m15 != diag.breakout_side)
      {
         diag.decision_summary = "FILTERED: M15 Structure (BOS) Mismatch";
         diag.reason_detail = "M15 timeframe market structure did not confirm breakout.";
         diag.reason_persian = "ساختار مارکت تایم فریم M15 جهت شکست را تایید نکرده است.";
         diag.status_color = clrYellow;
      }
      else if(!diag.volume_ok)
      {
         diag.decision_summary = "FILTERED: Low Tick Volume Ratio";
         diag.reason_detail = StringFormat("Volume ratio %.2fx < %.2fx threshold. Momentum weak.", diag.volume_ratio, OptVolumeRatioMin);
         diag.reason_persian = "نسبت حجم تیک کمتر از ۱.۱۰ است؛ فشار خرید/فروش کافی نیست.";
         diag.status_color = clrYellow;
      }
      else if(!diag.atr_ok)
      {
         diag.decision_summary = "FILTERED: ATR Bounds Anomaly";
         diag.reason_detail = "Bar range is outside 0.50x - 2.50x ATR normal bounds.";
         diag.reason_persian = "دامنه کندل با نوسان ATR همخوانی ندارد (بیش از حد کشیده).";
         diag.status_color = clrYellow;
      }
      else
      {
         diag.decision_summary = "🟢 SIGNAL CONFIRMED: Executing Order!";
         diag.reason_detail = StringFormat("All institutional breakout conditions met! Entering %s.", diag.breakout_side > 0 ? "BUY" : "SELL");
         diag.reason_persian = "تمام فیلترها و نقدینگی تایید شدند؛ معامله اجرا می شود.";
         diag.status_color = clrLimeGreen;
      }
   }

   g_visualizer.DrawDiagnosticsHUD(diag);
   SaveTelemetryFile(diag);
}

void OnTimer()
{
   UpdateVisualDisplay();
}

double OnTester()
{
   return TesterStatistics(STAT_PROFIT);
}

// Robust Dynamic Lot Calculator using MT5 OrderCalcProfit & Symbol Properties
bool CalculateDynamicLot(const int order_type, const double entry_price, const double stop_price, double &out_lot, string &reject_reason)
{
   if(LotMode == LOT_FIXED_RESEARCH)
   {
      out_lot = FixedLot;
      return true;
   }
   
   // Equity-based risk calculation
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0) equity = AccountInfoDouble(ACCOUNT_BALANCE);
   if(equity <= 0.0)
   {
      reject_reason = "REJECT_NO_EQUITY";
      return false;
   }
   
   double risk_budget = equity * (RiskPerTradePct / 100.0);
   if(risk_budget <= 0.0)
   {
      reject_reason = "REJECT_ZERO_RISK_BUDGET";
      return false;
   }
   
   // Calculate exact loss for 1.0 lot using MT5 OrderCalcProfit
   ENUM_ORDER_TYPE ot = (order_type > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double profit_one_lot = 0.0;
   if(!OrderCalcProfit(ot, _Symbol, 1.0, entry_price, stop_price, profit_one_lot) || profit_one_lot >= 0.0)
   {
      // Fallback calculation using tick value and points
      double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double tick_sz = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      double dist = MathAbs(entry_price - stop_price);
      if(tick_sz > 0.0 && tick_val > 0.0)
      {
         profit_one_lot = -(dist / tick_sz) * tick_val;
      }
      else
      {
         profit_one_lot = -dist * 100.0; // standard 100oz contract
      }
   }
   
   double loss_per_lot = MathAbs(profit_one_lot);
   // Add typical round-turn commission (~$7-$10 per lot)
   loss_per_lot += 7.0;
   
   if(loss_per_lot <= 0.0)
   {
      reject_reason = "REJECT_INVALID_STOP_DISTANCE";
      return false;
   }
   
   double raw_lot = risk_budget / loss_per_lot;
   
   // Query broker symbol constraints
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lot_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(lot_step <= 0.0) lot_step = 0.01;
   if(min_lot <= 0.0) min_lot = 0.01;
   if(max_lot <= 0.0) max_lot = 100.0;
   
   // Floor to volume step
   double rounded_lot = MathFloor(raw_lot / lot_step) * lot_step;
   
   // MANDATORY RULE: If rounded lot is below min_lot, taking min_lot would EXCEED the risk budget!
   if(rounded_lot < min_lot)
   {
      reject_reason = "REJECT_RISK_EXCEEDED_BY_MIN_LOT";
      return false;
   }
   
   if(rounded_lot > max_lot) rounded_lot = max_lot;
   
   out_lot = NormalizeDouble(rounded_lot, 2);
   return true;
}

// Check if bar close is in extreme quartile of candle
bool IsCloseInExtremeQuartile(const MqlRates &bar, const int side)
{
   double range = bar.high - bar.low;
   if(range <= _Point) return false;
   if(side > 0)
   {
      // Long: close should be in upper 25% (upper quartile)
      return (bar.close >= bar.high - 0.25 * range);
   }
   else
   {
      // Short: close should be in lower 25% (lower quartile)
      return (bar.close <= bar.low + 0.25 * range);
   }
}

// Higher quality FVG verification
bool QualityFvgConfirmed(const MqlRates &bars[], const int side, const double min_gap)
{
   double low = 0, high = 0;
   if(!ActiveFVG(bars, side, low, high)) return false;
   return (high - low >= min_gap);
}

void OnTick()
{
   if(!ResearchTester()) return;
   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol, tick)) return;
   
   datetime tick_utc = ServerToUTC(tick.time, ServerClock);
   ManageResearchPosition(g_execution, tick_utc, ServerClock, OptBreakEvenRR, OptTrailRR);
   
   datetime current = iTime(_Symbol, PERIOD_M5, 0);
   if(current <= g_last_processed_bar) return;
   g_last_processed_bar = current;
   
   datetime utc = ServerToUTC(current, ServerClock);
   if(utc <= 0) return;
   
   datetime day_start = DayStart(utc);
   if(day_start != g_current_day_start)
   {
      g_current_day_start = day_start;
      g_traded_today = false;
   }
   
   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   if(CopyRates(_Symbol, PERIOD_M5, 1, 32, bars) != 32) return;
   
   PriceRange level_ny={};
   if(!ReadRange(Reference, utc-300, ServerClock, level_ny))
      ReadRange(REF_ASIA_UTC, utc-300, ServerClock, level_ny);
   double range_width = level_ny.high - level_ny.low;

   int london_min = (int)(((utc + (EuropeSummer(utc)?3600:0)) % 86400) / 60);
   bool is_london = (london_min >= 8*60 && london_min < 11*60);
   
   // Live chart HUD status
   string status_str = g_traded_today ? "TRADED TODAY (Max 1 Trade/Day Limit Reached)" :
                       (is_london ? "IN LONDON WINDOW - Active Breakout Monitoring" : "Outside London Window - Waiting for 08:00 UTC");

   Features features={};
   FeatureAt(bars, current-300, features);

   if(InpShowVisuals) UpdateVisualDisplay();

   Comment(StringFormat(
      "=====================================================\n" +
      " GOLD SESSION LAB PRO v3.6 (CHAMPION MODEL)\n" +
      "=====================================================\n" +
      " Mode: %s\n" +
      " Account: %s | Login: %d | Currency: %s\n" +
      " Balance: $%.2f | Equity: $%.2f | Leverage: 1:%d\n" +
      " Strategy: HEAVY OPTIMIZED (London 08-10 UTC, No-Friday)\n" +
      " Sizing: %s (Value: %.2f)\n" +
      " Asian Range High: %.2f | Low: %.2f | Width: $%.2f\n" +
      " Current Server Time: %s | UTC: %s\n" +
      " Execution Status: %s\n" +
      "=====================================================",
      (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? "LIVE DEMO ACCOUNT" : "STRATEGY TESTER"),
      AccountInfoString(ACCOUNT_SERVER), (int)AccountInfoInteger(ACCOUNT_LOGIN), AccountInfoString(ACCOUNT_CURRENCY),
      AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY), (int)AccountInfoInteger(ACCOUNT_LEVERAGE),
      (LotMode == LOT_FIXED_RESEARCH ? "Fixed Lot" : "Dynamic Risk %"), (LotMode == LOT_FIXED_RESEARCH ? FixedLot : RiskPerTradePct),
      level_ny.high, level_ny.low, range_width,
      TimeToString(current, TIME_DATE|TIME_MINUTES), TimeToString(utc, TIME_DATE|TIME_MINUTES),
      status_str
   ));

   if(!is_london) return;
   
   // Day-of-week seasonality filter
   MqlDateTime dt;
   TimeToStruct(utc, dt);
   if(DayFilter == DAY_NO_FRIDAY && dt.day_of_week == 5) return;
   if(DayFilter == DAY_CORE_TUE_THU && (dt.day_of_week == 1 || dt.day_of_week == 5)) return;
   if(DayFilter == DAY_NO_MONDAY && dt.day_of_week == 1) return;
   
   // Window check
   bool in_08_09 = (london_min >= 8*60 && london_min < 9*60);
   bool in_custom_window = false;
   switch(TimeWindow)
   {
      case WINDOW_08_09: in_custom_window = (london_min >= 8*60 && london_min < 9*60); break;
      case WINDOW_08_10: in_custom_window = (london_min >= 8*60 && london_min < 10*60); break;
      case WINDOW_08_11: in_custom_window = (london_min >= 8*60 && london_min < 11*60); break;
   }
   
   // Validate range validity
   if(level_ny.high <= level_ny.low) return;
   bool range_ok = (range_width >= 2.0 && range_width <= MaxRangeWidth);
   if(!FeatureAt(bars, current-300, features)) return;
   
   MqlRates bar = bars[0];
   
   // Raw Breakout Detection
   int breakout_side = 0;
   double broken_level = 0.0;
   if(bar.close > level_ny.high + 0.10 && bar.close > bar.open)
   {
      breakout_side = 1;
      broken_level = level_ny.high;
   }
   else if(bar.close < level_ny.low - 0.10 && bar.close < bar.open)
   {
      breakout_side = -1;
      broken_level = level_ny.low;
   }
   if(breakout_side == 0) return;
   
   // Feature extractions
   double candle_strength = (bar.high - bar.low > _Point) ? MathAbs(bar.close - bar.open) / (bar.high - bar.low) : 0.0;
   double bar_range = bar.high - bar.low;
   bool fvg_orig_ok = FvgConfirmed(bars, breakout_side);
   bool fvg_quality_ok = QualityFvgConfirmed(bars, breakout_side, OptFvgMinSize);
   bool retest_ok = Retested(bar, broken_level, breakout_side);
   int bos_ok = (features.m15_break == breakout_side) ? 1 : 0;
   bool sweep_ok = OpposingAsianSideSwept(bars, level_ny, breakout_side);
   bool close_extreme_ok = IsCloseInExtremeQuartile(bar, breakout_side);
   bool atr_bounds_ok = (features.atr > 0.0 && bar_range >= OptMinAtrRatio * features.atr && bar_range <= OptMaxAtrRatio * features.atr);
   
   // Model Signal Decision
   bool signal_accepted = false;
   string strat_tag = "";
   
   switch(ModelChoice)
   {
      case MODEL_BALANCED_ORIGINAL:
         // Exact Original: London 08-09, Candle strength >= 0.45, BOS M15 OR Trend H1 (NO range width restriction)
         if(in_08_09 && candle_strength >= 0.45 &&
            (bos_ok == 1 || TrendAligned(features, breakout_side, 14.0)))
         {
            signal_accepted = true;
            strat_tag = "BALANCED_ORIG";
         }
         break;
         
      case MODEL_HEAVY_ORIGINAL:
         // Exact Original: London 08-09, FVG >= 0.20, BOS M15, Volume ratio >= 1.10 (NO range width restriction)
         if(in_08_09 && fvg_orig_ok && bos_ok == 1 && features.volume_ratio >= 1.10)
         {
            signal_accepted = true;
            strat_tag = "HEAVY_ORIG";
         }
         break;
         
      case MODEL_BALANCED_OPTIMIZED:
         // Optimized Balanced:
         // 1. Time window selectable
         // 2. Candle strength >= 0.45
         // 3. Optional Range Width filter
         // 4. Optional ATR bounds check
         // 5. Optional Close in extreme quartile
         // 6. BOS or Trend alignment
         // 7. Optional Retest
         if(in_custom_window && candle_strength >= 0.45 &&
            (!OptUseRangeWidthFilter || range_ok) &&
            (!OptUseAtrFilter || atr_bounds_ok) &&
            (!OptRequireCloseLocation || close_extreme_ok) &&
            (bos_ok == 1 || TrendAligned(features, breakout_side, 14.0)))
         {
            if(!OptRequireRetest || retest_ok)
            {
               signal_accepted = true;
               strat_tag = "BALANCED_OPT";
            }
         }
         break;
         
      case MODEL_HEAVY_OPTIMIZED:
         // Optimized Heavy:
         // 1. Time window selectable
         // 2. FVG with quality gap size >= OptFvgMinSize
         // 3. BOS M15 confirmed
         // 4. Volume ratio >= OptVolumeRatioMin (e.g. 1.15)
         // 5. Optional Range Width filter
         // 6. Optional Prior Opposing Sweep bonus
         // 7. Optional ATR bounds check
         if(in_custom_window && fvg_quality_ok && bos_ok == 1 && features.volume_ratio >= OptVolumeRatioMin &&
            (!OptUseRangeWidthFilter || range_ok) &&
            (!OptUseAtrFilter || atr_bounds_ok))
         {
            if(!OptOpposingSweepBonus || sweep_ok)
            {
               signal_accepted = true;
               strat_tag = "HEAVY_OPT";
            }
         }
         break;
         
      case MODEL_HYBRID:
         // Hybrid Model:
         // Priority 1: Heavy check
         if(in_custom_window && fvg_quality_ok && bos_ok == 1 && features.volume_ratio >= OptVolumeRatioMin &&
            (!OptUseRangeWidthFilter || range_ok) && (!OptUseAtrFilter || atr_bounds_ok))
         {
            signal_accepted = true;
            strat_tag = "HYBRID_HEAVY";
         }
         // Priority 2: Balanced check if Heavy is not present
         else if(in_custom_window && candle_strength >= 0.45 &&
                 (!OptUseRangeWidthFilter || range_ok) &&
                 (!OptUseAtrFilter || atr_bounds_ok) &&
                 (!OptRequireCloseLocation || close_extreme_ok) &&
                 (bos_ok == 1 || TrendAligned(features, breakout_side, 14.0)))
         {
            if(!OptRequireRetest || retest_ok)
            {
               signal_accepted = true;
               strat_tag = "HYBRID_BALANCED";
            }
         }
         break;
   }
   
   if(!signal_accepted) return;
   if(g_traded_today || PositionSelect(_Symbol)) return;
   
   // Calculate Stop & Target
   double stop_price = 0.0;
   double target_price = 0.0;
   
   if(SLTPMode == SLTP_FIXED_BAR_RR)
   {
      double anchor = (breakout_side > 0) ? bar.low : bar.high;
      double raw_stop_dist = MathAbs(bar.close - anchor) + 0.30;
      double min_stop_dist = bar.close * (MinStopBps / 10000.0);
      double stop_dist = MathMax(raw_stop_dist, min_stop_dist);
      stop_price = bar.close - breakout_side * stop_dist;
      target_price = bar.close + breakout_side * (stop_dist * TargetRR);
   }
   else // SLTP_VOLATILITY_ATR
   {
      double atr_stop = (features.atr > 0.0) ? (1.50 * features.atr) : 2.50;
      double min_stop_dist = bar.close * (MinStopBps / 10000.0);
      double stop_dist = MathMax(atr_stop, min_stop_dist);
      stop_price = bar.close - breakout_side * stop_dist;
      target_price = bar.close + breakout_side * (2.00 * stop_dist);
   }
   
   // Calculate Lot Size
   double trade_lot = 0.0;
   string lot_reject_reason = "";
   if(!CalculateDynamicLot(breakout_side, bar.close, stop_price, trade_lot, lot_reject_reason))
   {
      // Trade rejected by risk manager
      return;
   }
   
   // Check Margin
   double required_margin = 0.0;
   ENUM_ORDER_TYPE order_type = (breakout_side > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcMargin(order_type, _Symbol, trade_lot, bar.close, required_margin) ||
      required_margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
   {
      return;
   }
   
   // Send Order
   string comment = "OPT_" + strat_tag;
   bool sent = (breakout_side > 0)
      ? g_execution.Buy(trade_lot, _Symbol, bar.close, stop_price, target_price, comment)
      : g_execution.Sell(trade_lot, _Symbol, bar.close, stop_price, target_price, comment);
      
   if(sent && (g_execution.ResultRetcode() == TRADE_RETCODE_DONE || g_execution.ResultRetcode() == TRADE_RETCODE_DONE_PARTIAL))
   {
      g_traded_today = true;
      if(InpShowVisuals)
      {
         g_visualizer.DrawTradeSignal(breakout_side, bar.time, bar.close, stop_price, target_price);
      }
   }
}
