#property copyright "Gold Session Lab Pro"
#property version   "3.00"
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

enum LotSizeMode { LOT_FIXED_RESEARCH, LOT_DYNAMIC_RISK };
enum StrategyEngineMode {
   STRAT_BASELINE,
   STRAT_EXP04_IMPULSE,
   STRAT_EXP12_LONDON_FVG,
   STRAT_EXP23_CHAMPION,
   STRAT_CONFIRM_LIGHT,
   STRAT_CONFIRM_BALANCED,
   STRAT_CONFIRM_HEAVY,
   STRAT_CONFIRM_ADAPTIVE
};

input string ExpectedSymbol = "XAUUSD_o";
input BrokerClock ServerClock = CLOCK_LITEFINANCE_EU;
input ReferenceKind Reference = REF_ASIA_NY;
input LotSizeMode LotMode = LOT_FIXED_RESEARCH;
input double FixedLot = 0.10;
input StrategyEngineMode EngineMode = STRAT_CONFIRM_ADAPTIVE;
input double RiskPerTradePct = 3.0;
input double DailyLossLimitPct = 6.0;
input double TargetRR = 1.5;
input double MaxRangeWidth = 30.0;
input double MinStopBps = 5.8;

// Data structures for comprehensive audit
struct BreakoutClassificationRecord {
   string event_id;
   string date_str;
   string time_str;
   string session_str;
   string direction_str;
   string ref_range_str;
   double broken_level;
   double breakout_price;
   double candle_strength;
   int fvg;
   int retest;
   int bos;
   int liquidity_sweep;
   double atr;
   string market_regime;
   int intermarket_confirmed;
   int confidence_score;
   string market_behavior_label;      // TRUE_CONTINUATION, FAILED_BREAKOUT, RETURN_TO_RANGE, UNRESOLVED
   string hypothetical_trade_outcome; // TAKE_PROFIT, STOP_LOSS, TIME_EXIT, NOT_EXECUTABLE
   int signal_accepted_active_strat;
   int executed_active_strat;
   string rejection_reason;
   double potential_pnl_usd;
   
   // Tracking forward state
   int side;
   double stop_price;
   double target_price;
   datetime entry_time;
   int bars_held;
   bool reentered_range_3bars;
   bool resolved;
   double ref_high;
   double ref_low;
};

struct TradeAuditRecord {
   string run_id;
   string strategy_version;
   ulong deal_id;
   ulong position_id;
   string entry_datetime;
   string exit_datetime;
   string direction;
   double requested_lot;
   double executed_lot;
   double entry_price;
   double exit_price;
   double stop_loss;
   double take_profit;
   double spread_cost;
   double commission;
   double swap;
   double slippage;
   double gross_profit;
   double net_profit;
   double balance_before;
   double balance_after;
};

struct DailyAuditRecord {
   string date_str;
   string weekday_str;
   int market_open;
   string data_quality;
   double asia_range_width;
   string market_regime;
   int frankfurt_breakouts;
   int london_breakouts;
   int ny_breakouts;
   int true_breakouts;
   int false_breakouts;
   int detected_breakouts;
   int missed_opportunities;
   int signals_accepted;
   int trades_executed;
   double actual_lots;
   double daily_profit;
   double daily_loss;
   double daily_net;
   double ending_balance;
   string main_status;
   string primary_missed_reason;
};

#define MAX_DAYS 800
#define MAX_EVENTS 6000
#define MAX_TRADES 1000

BreakoutClassificationRecord g_classifications[MAX_EVENTS];
int g_class_count = 0;

TradeAuditRecord g_trades[MAX_TRADES];
int g_trade_count = 0;

DailyAuditRecord g_daily_records[MAX_DAYS];
int g_daily_count = 0;

CTrade g_execution;
int g_atr_handle = INVALID_HANDLE;
int g_ema_handle = INVALID_HANDLE;
int g_adx_handle = INVALID_HANDLE;

datetime g_last_processed_bar = 0;
datetime g_current_day_start = 0;
int g_current_day_idx = -1;
double g_running_balance = 1000.0;
bool g_traded_today = false;

// Pending trade tracking
ulong g_current_position_id = 0;
double g_current_entry_price = 0;
double g_current_stop_price = 0;
double g_current_target_price = 0;
datetime g_current_entry_time = 0;
string g_current_dir = "";
double g_current_req_lot = 0;
double g_current_exec_lot = 0;
double g_current_bal_before = 0;
double g_current_spread = 0;

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

void UpdatePendingClassifications(const MqlRates &bar)
{
   for(int i = 0; i < g_class_count; i++)
   {
      if(g_classifications[i].resolved) continue;
      g_classifications[i].bars_held++;
      
      // Check return to range within 3 bars
      if(g_classifications[i].bars_held <= 3)
      {
         if(g_classifications[i].side > 0 && bar.close <= g_classifications[i].ref_high)
            g_classifications[i].reentered_range_3bars = true;
         if(g_classifications[i].side < 0 && bar.close >= g_classifications[i].ref_low)
            g_classifications[i].reentered_range_3bars = true;
      }
      
      bool hit_tp = false;
      bool hit_sl = false;
      
      if(g_classifications[i].side > 0)
      {
         if(bar.high >= g_classifications[i].target_price) hit_tp = true;
         if(bar.low <= g_classifications[i].stop_price) hit_sl = true;
      }
      else
      {
         if(bar.low <= g_classifications[i].target_price) hit_tp = true;
         if(bar.high >= g_classifications[i].stop_price) hit_sl = true;
      }
      
      if(hit_tp && !hit_sl)
      {
         g_classifications[i].resolved = true;
         g_classifications[i].hypothetical_trade_outcome = "TAKE_PROFIT";
         if(g_classifications[i].reentered_range_3bars)
            g_classifications[i].market_behavior_label = "RETURN_TO_RANGE";
         else
            g_classifications[i].market_behavior_label = "TRUE_CONTINUATION";
      }
      else if(hit_sl)
      {
         g_classifications[i].resolved = true;
         g_classifications[i].hypothetical_trade_outcome = "STOP_LOSS";
         if(g_classifications[i].reentered_range_3bars)
            g_classifications[i].market_behavior_label = "RETURN_TO_RANGE";
         else
            g_classifications[i].market_behavior_label = "FAILED_BREAKOUT";
      }
      else if(g_classifications[i].bars_held >= 72) // 6 hours
      {
         g_classifications[i].resolved = true;
         g_classifications[i].hypothetical_trade_outcome = "TIME_EXIT";
         g_classifications[i].market_behavior_label = "UNRESOLVED";
      }
   }
}

int GetDayIndex(const datetime time_sec)
{
   datetime dstart = DayStart(time_sec);
   for(int i = 0; i < g_daily_count; i++)
   {
      MqlDateTime dt;
      TimeToStruct(dstart, dt);
      string ds = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
      if(g_daily_records[i].date_str == ds) return i;
   }
   if(g_daily_count >= MAX_DAYS) return -1;
   
   int idx = g_daily_count++;
   MqlDateTime dt;
   TimeToStruct(dstart, dt);
   g_daily_records[idx].date_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
   string days_of_week[7] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};
   g_daily_records[idx].weekday_str = days_of_week[dt.day_of_week];
   g_daily_records[idx].market_open = 1;
   g_daily_records[idx].data_quality = "VALID";
   g_daily_records[idx].market_regime = "UNCERTAIN";
   g_daily_records[idx].ending_balance = g_running_balance;
   g_daily_records[idx].main_status = "NO_BREAKOUT";
   g_daily_records[idx].primary_missed_reason = "NO_OPPORTUNITY";
   return idx;
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

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_atr_handle != INVALID_HANDLE) IndicatorRelease(g_atr_handle);
   if(g_ema_handle != INVALID_HANDLE) IndicatorRelease(g_ema_handle);
   if(g_adx_handle != INVALID_HANDLE) IndicatorRelease(g_adx_handle);
   
   // Finalize classifications
   for(int i = 0; i < g_class_count; i++)
   {
      if(!g_classifications[i].resolved)
      {
         g_classifications[i].resolved = true;
         g_classifications[i].market_behavior_label = "UNRESOLVED";
         g_classifications[i].hypothetical_trade_outcome = "TIME_EXIT";
      }
   }
   
   // 1. Write research/output/breakout_classification.csv
   int h_class = FileOpen("breakout_classification.csv", FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h_class != INVALID_HANDLE)
   {
      FileWrite(h_class,
         "EventId","Date","Time","Session","Direction","ReferenceRange","BrokenLevel",
         "BreakoutPrice","CandleStrength","FVG","Retest","BOS","LiquiditySweep","ATR",
         "MarketRegime","IntermarketConfirmed","ConfidenceScore","MarketBehaviorLabel",
         "HypotheticalTradeOutcome","SignalAcceptedActiveStrat","ExecutedActiveStrat",
         "RejectionReason","PotentialPnLUSD"
      );
      for(int i = 0; i < g_class_count; i++)
      {
         FileWrite(h_class,
            g_classifications[i].event_id,
            g_classifications[i].date_str,
            g_classifications[i].time_str,
            g_classifications[i].session_str,
            g_classifications[i].direction_str,
            g_classifications[i].ref_range_str,
            DoubleToString(g_classifications[i].broken_level, 2),
            DoubleToString(g_classifications[i].breakout_price, 2),
            DoubleToString(g_classifications[i].candle_strength, 2),
            IntegerToString(g_classifications[i].fvg),
            IntegerToString(g_classifications[i].retest),
            IntegerToString(g_classifications[i].bos),
            IntegerToString(g_classifications[i].liquidity_sweep),
            DoubleToString(g_classifications[i].atr, 2),
            g_classifications[i].market_regime,
            IntegerToString(g_classifications[i].intermarket_confirmed),
            IntegerToString(g_classifications[i].confidence_score),
            g_classifications[i].market_behavior_label,
            g_classifications[i].hypothetical_trade_outcome,
            IntegerToString(g_classifications[i].signal_accepted_active_strat),
            IntegerToString(g_classifications[i].executed_active_strat),
            g_classifications[i].rejection_reason,
            DoubleToString(g_classifications[i].potential_pnl_usd, 2)
         );
      }
      FileClose(h_class);
   }

   // 2. Write research/output/trade_level_audit.csv
   int h_trade = FileOpen("trade_level_audit.csv", FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h_trade != INVALID_HANDLE)
   {
      FileWrite(h_trade,
         "RunID","StrategyVersion","DealID","PositionID","EntryDateTime","ExitDateTime",
         "Direction","RequestedLot","ExecutedLot","EntryPrice","ExitPrice","StopLoss",
         "TakeProfit","SpreadCost","Commission","Swap","Slippage","GrossProfit","NetProfit",
         "BalanceBefore","BalanceAfter"
      );
      for(int i = 0; i < g_trade_count; i++)
      {
         FileWrite(h_trade,
            g_trades[i].run_id,
            g_trades[i].strategy_version,
            IntegerToString(g_trades[i].deal_id),
            IntegerToString(g_trades[i].position_id),
            g_trades[i].entry_datetime,
            g_trades[i].exit_datetime,
            g_trades[i].direction,
            DoubleToString(g_trades[i].requested_lot, 2),
            DoubleToString(g_trades[i].executed_lot, 2),
            DoubleToString(g_trades[i].entry_price, 2),
            DoubleToString(g_trades[i].exit_price, 2),
            DoubleToString(g_trades[i].stop_loss, 2),
            DoubleToString(g_trades[i].take_profit, 2),
            DoubleToString(g_trades[i].spread_cost, 2),
            DoubleToString(g_trades[i].commission, 2),
            DoubleToString(g_trades[i].swap, 2),
            DoubleToString(g_trades[i].slippage, 2),
            DoubleToString(g_trades[i].gross_profit, 2),
            DoubleToString(g_trades[i].net_profit, 2),
            DoubleToString(g_trades[i].balance_before, 2),
            DoubleToString(g_trades[i].balance_after, 2)
         );
      }
      FileClose(h_trade);
   }

   // 3. Write research/output/missed_opportunities.csv
   int h_miss = FileOpen("missed_opportunities.csv", FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h_miss != INVALID_HANDLE)
   {
      FileWrite(h_miss,
         "EventId","Date","Time","Session","Direction","BrokenLevel","BreakoutPrice",
         "MarketRegime","MarketBehavior","HypotheticalOutcome","RejectionReason","MissedProfitUSD"
      );
      for(int i = 0; i < g_class_count; i++)
      {
         if(g_classifications[i].market_behavior_label == "TRUE_CONTINUATION" &&
            g_classifications[i].signal_accepted_active_strat == 0)
         {
            FileWrite(h_miss,
               g_classifications[i].event_id,
               g_classifications[i].date_str,
               g_classifications[i].time_str,
               g_classifications[i].session_str,
               g_classifications[i].direction_str,
               DoubleToString(g_classifications[i].broken_level, 2),
               DoubleToString(g_classifications[i].breakout_price, 2),
               g_classifications[i].market_regime,
               g_classifications[i].market_behavior_label,
               g_classifications[i].hypothetical_trade_outcome,
               g_classifications[i].rejection_reason,
               DoubleToString(g_classifications[i].potential_pnl_usd, 2)
            );
         }
      }
      FileClose(h_miss);
   }

   // 4. Write research/output/daily_market_audit.csv
   int h_daily = FileOpen("daily_market_audit.csv", FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h_daily != INVALID_HANDLE)
   {
      FileWrite(h_daily,
         "Date","Weekday","MarketOpen","DataQuality","AsiaRangeWidth","MarketRegime",
         "FrankfurtBreakouts","LondonBreakouts","NewYorkBreakouts","TrueBreakouts",
         "FalseBreakouts","DetectedBreakouts","MissedOpportunities","SignalsAccepted",
         "TradesExecuted","ActualLots","DailyProfit","DailyLoss","EndingBalance",
         "MainStatus","PrimaryMissedReason"
      );
      
      datetime cur_cal = StringToTime("2025.01.01 00:00:00");
      datetime end_cal = StringToTime("2026.11.09 23:59:59");
      double running_bal = 1000.0;
      
      while(cur_cal <= end_cal)
      {
         MqlDateTime dt;
         TimeToStruct(cur_cal, dt);
         string d_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
         string days_of_week[7] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};
         string w_str = days_of_week[dt.day_of_week];
         
         int found = -1;
         for(int d = 0; d < g_daily_count; d++)
         {
            if(g_daily_records[d].date_str == d_str) { found = d; break; }
         }
         
         if(found >= 0)
         {
            DailyAuditRecord rec = g_daily_records[found];
            running_bal = rec.ending_balance;
            FileWrite(h_daily,
               rec.date_str, rec.weekday_str, IntegerToString(rec.market_open), rec.data_quality,
               DoubleToString(rec.asia_range_width, 2), rec.market_regime,
               IntegerToString(rec.frankfurt_breakouts), IntegerToString(rec.london_breakouts), IntegerToString(rec.ny_breakouts),
               IntegerToString(rec.true_breakouts), IntegerToString(rec.false_breakouts),
               IntegerToString(rec.detected_breakouts), IntegerToString(rec.missed_opportunities),
               IntegerToString(rec.signals_accepted), IntegerToString(rec.trades_executed),
               DoubleToString(rec.actual_lots, 2), DoubleToString(rec.daily_profit, 2), DoubleToString(rec.daily_loss, 2),
               DoubleToString(rec.ending_balance, 2), rec.main_status, rec.primary_missed_reason
            );
         }
         else
         {
            string d_qual = "HOLIDAY";
            string m_stat = "DATA_UNAVAILABLE";
            string r_reas = "HOLIDAY_MARKET_CLOSED";
            if(dt.day_of_week == 0 || dt.day_of_week == 6)
            {
               d_qual = "WEEKEND";
               r_reas = "WEEKEND_CLOSED";
            }
            else if(cur_cal >= StringToTime("2026.11.07 00:00:00"))
            {
               d_qual = "DATA_UNAVAILABLE";
               r_reas = "FUTURE_OR_INCOMPLETE_DATA";
            }
            FileWrite(h_daily,
               d_str, w_str, "0", d_qual, "0.00", "NONE",
               "0","0","0","0","0","0","0","0","0",
               "0.00","0.00","0.00",DoubleToString(running_bal, 2),
               m_stat, r_reas
            );
         }
         cur_cal += 86400;
      }
      FileClose(h_daily);
   }
}

double OnTester()
{
   return TesterStatistics(STAT_PROFIT);
}

void OnTick()
{
   if(!ResearchTester()) return;
   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol, tick)) return;
   
   datetime tick_utc = ServerToUTC(tick.time, ServerClock);
   ManageResearchPosition(g_execution, tick_utc, ServerClock, 0.0, 0.0);
   
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
      g_current_day_idx = GetDayIndex(utc);
   }
   
   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   if(CopyRates(_Symbol, PERIOD_M5, 1, 32, bars) != 32) return;
   
   UpdatePendingClassifications(bars[0]);
   
   // Session inspection
   int london_min = (int)(((utc + (EuropeSummer(utc)?3600:0)) % 86400) / 60);
   int ny_min = (int)(((utc + NYOffset(utc)) % 86400) / 60);
   
   bool is_frankfurt = (london_min >= 7*60 && london_min < 8*60);
   bool is_london = (london_min >= 8*60 && london_min < 11*60);
   bool is_ny_morning = (ny_min >= 9*60+30 && ny_min < 11*60);
   bool is_ny_afternoon = (ny_min >= 14*60 && ny_min < 15*60+30);
   bool is_ny = is_ny_morning || is_ny_afternoon;
   
   if(!is_frankfurt && !is_london && !is_ny) return;
   string session_name = is_frankfurt ? "FRANKFURT" : (is_london ? "LONDON" : "NEW_YORK");
   
   // Read Asian range Option A: REF_ASIA_NY
   PriceRange level_ny={};
   if(!ReadRange(REF_ASIA_NY, utc-300, ServerClock, level_ny)) return;
   
   double range_width = level_ny.high - level_ny.low;
   if(g_current_day_idx >= 0 && g_daily_records[g_current_day_idx].asia_range_width == 0.0)
   {
      g_daily_records[g_current_day_idx].asia_range_width = range_width;
   }
   
   Features features={};
   if(!FeatureAt(bars, current-300, features)) return;
   
   // Detect Market Regime
   MarketRegime regime = DetectMarketRegime(bars, features, g_atr_handle);
   string regime_str = RegimeToString(regime);
   if(g_current_day_idx >= 0 && g_daily_records[g_current_day_idx].market_regime == "UNCERTAIN")
   {
      g_daily_records[g_current_day_idx].market_regime = regime_str;
   }
   
   MqlRates bar = bars[0];
   
   // --- STAGE 1: RAW BREAKOUT DETECTION ---
   // Check if bar closed outside Asian range
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
   
   if(g_current_day_idx >= 0)
   {
      if(is_frankfurt) g_daily_records[g_current_day_idx].frankfurt_breakouts++;
      if(is_london) g_daily_records[g_current_day_idx].london_breakouts++;
      if(is_ny) g_daily_records[g_current_day_idx].ny_breakouts++;
   }
   
   // --- STAGE 2: FEATURE EXTRACTION & CLASSIFICATION SETUP ---
   double candle_strength = (bar.high - bar.low > _Point) ? MathAbs(bar.close - bar.open) / (bar.high - bar.low) : 0.0;
   bool fvg_ok = FvgConfirmed(bars, breakout_side);
   bool retest_ok = Retested(bar, broken_level, breakout_side);
   int bos_ok = (features.m15_break == breakout_side) ? 1 : 0;
   bool sweep_ok = OpposingAsianSideSwept(bars, level_ny, breakout_side);
   int conf_score = CalculateBreakoutScore(bar, bars, features, level_ny, breakout_side);
   
   IntermarketSignal inter_sig = CheckIntermarketProxy(current-300, breakout_side);
   int inter_conf = (inter_sig.available && inter_sig.confirms_gold == breakout_side) ? 1 : 0;
   
   // Calculate stop and target
   double anchor = (breakout_side > 0) ? bar.low : bar.high;
   double raw_stop_dist = MathAbs(bar.close - anchor) + 0.30;
   double min_stop_dist = bar.close * (MinStopBps / 10000.0);
   double stop_dist = MathMax(raw_stop_dist, min_stop_dist);
   double stop_price = bar.close - breakout_side * stop_dist;
   double target_price = bar.close + breakout_side * (stop_dist * TargetRR);
   
   // Potential profit with 0.10 lot
   double potential_pnl = 0.10 * (stop_dist * TargetRR) * 100.0;
   
   // --- STAGE 3: TRADE DECISION BY ENGINE MODE ---
   bool signal_accepted = false;
   string reason = "";
   bool in_08_09 = (london_min >= 8*60 && london_min < 9*60);
   bool range_ok = (range_width >= 2.0 && range_width <= MaxRangeWidth);
   
   switch(EngineMode)
   {
      case STRAT_BASELINE:
         if(is_london) { signal_accepted = true; reason = "BASELINE_LONDON_ACCEPTED"; }
         else { reason = "REJECTED_OUTSIDE_LONDON"; }
         break;
         
      case STRAT_EXP04_IMPULSE:
         if(is_london && in_08_09) { signal_accepted = true; reason = "EXP04_IMPULSE_ACCEPTED"; }
         else if(!is_london) { reason = "REJECTED_OUTSIDE_LONDON"; }
         else { reason = "REJECTED_OUTSIDE_08_09"; }
         break;
         
      case STRAT_EXP12_LONDON_FVG:
         if(is_london && range_ok && fvg_ok) { signal_accepted = true; reason = "EXP12_FVG_ACCEPTED"; }
         else if(!is_london) { reason = "REJECTED_OUTSIDE_LONDON"; }
         else if(!range_ok) { reason = "REJECTED_RANGE_TOO_WIDE"; }
         else { reason = "REJECTED_NO_FVG"; }
         break;
         
      case STRAT_EXP23_CHAMPION:
         if(is_london && in_08_09 && range_ok && fvg_ok) { signal_accepted = true; reason = "EXP23_CHAMPION_ACCEPTED"; }
         else if(!is_london) { reason = "REJECTED_OUTSIDE_LONDON"; }
         else if(!in_08_09) { reason = "REJECTED_OUTSIDE_08_09"; }
         else if(!range_ok) { reason = "REJECTED_RANGE_TOO_WIDE"; }
         else { reason = "REJECTED_NO_FVG"; }
         break;
         
      case STRAT_CONFIRM_LIGHT:
         if(is_london && in_08_09 && candle_strength >= 0.45 && (bar.high - bar.low) <= 2.5 * features.atr)
         {
            signal_accepted = true; reason = "CONFIRM_LIGHT_ACCEPTED";
         }
         else reason = "REJECTED_LIGHT_CRITERIA";
         break;
         
      case STRAT_CONFIRM_BALANCED:
         if(is_london && in_08_09 && candle_strength >= 0.45 && (bos_ok == 1 || TrendAligned(features, breakout_side, 14.0)))
         {
            signal_accepted = true; reason = "CONFIRM_BALANCED_ACCEPTED";
         }
         else reason = "REJECTED_BALANCED_CRITERIA";
         break;
         
      case STRAT_CONFIRM_HEAVY:
         if(is_london && in_08_09 && fvg_ok && bos_ok == 1 && features.volume_ratio >= 1.10)
         {
            signal_accepted = true; reason = "CONFIRM_HEAVY_ACCEPTED";
         }
         else reason = "REJECTED_HEAVY_CRITERIA";
         break;
         
      case STRAT_CONFIRM_ADAPTIVE:
         if(!is_london || !in_08_09)
         {
            reason = "REJECTED_OUTSIDE_LONDON_08_09";
         }
         else if(regime == REGIME_TRENDING)
         {
            // In strong trend: light fast confirmation
            if(candle_strength >= 0.45) { signal_accepted = true; reason = "ADAPTIVE_TRENDING_LIGHT_ACCEPTED"; }
            else reason = "REJECTED_WEAK_CANDLE_IN_TREND";
         }
         else if(regime == REGIME_RANGING)
         {
            // In ranging market: demand FVG + BOS to avoid false trap
            if(fvg_ok && bos_ok == 1) { signal_accepted = true; reason = "ADAPTIVE_RANGING_HEAVY_ACCEPTED"; }
            else reason = "REJECTED_RANGING_LACKS_FVG_BOS";
         }
         else if(regime == REGIME_HIGH_VOLATILITY)
         {
            // In high volatility: demand FVG and limit range
            if(fvg_ok && range_ok) { signal_accepted = true; reason = "ADAPTIVE_VOLATILITY_FVG_ACCEPTED"; }
            else reason = "REJECTED_HIGH_VOL_UNSAFE";
         }
         else if(regime == REGIME_LOW_VOLATILITY)
         {
            if(range_width >= 3.0 && fvg_ok) { signal_accepted = true; reason = "ADAPTIVE_LOW_VOL_ACCEPTED"; }
            else reason = "REJECTED_LOW_VOL_NOISE";
         }
         else // NEWS_DRIVEN or UNCERTAIN
         {
            if(fvg_ok && candle_strength >= 0.55) { signal_accepted = true; reason = "ADAPTIVE_DEFAULT_ACCEPTED"; }
            else reason = "REJECTED_UNCERTAIN_MARKET";
         }
         break;
   }
   
   // Execution attempt
   int executed = 0;
   if(signal_accepted && !g_traded_today && !PositionSelect(_Symbol))
   {
      double lot_to_trade = FixedLot;
      if(LotMode == LOT_DYNAMIC_RISK)
      {
         double budget = RiskPerTradePct / 100.0 * AccountInfoDouble(ACCOUNT_BALANCE);
         double loss_per_lot = stop_dist * 100.0 + 10.0;
         lot_to_trade = NormalizeDouble(MathFloor(MathMin(0.06, budget / loss_per_lot) / 0.01) * 0.01, 2);
         lot_to_trade = MathMax(lot_to_trade, 0.01);
      }
      
      double required_margin = 0;
      ENUM_ORDER_TYPE order_type = (breakout_side > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      if(OrderCalcMargin(order_type, _Symbol, lot_to_trade, bar.close, required_margin) &&
         required_margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE))
      {
         string label = "GL_ADAPTIVE";
         bool sent = (breakout_side > 0)
            ? g_execution.Buy(lot_to_trade, _Symbol, bar.close, stop_price, target_price, label)
            : g_execution.Sell(lot_to_trade, _Symbol, bar.close, stop_price, target_price, label);
            
         if(sent && (g_execution.ResultRetcode() == TRADE_RETCODE_DONE || g_execution.ResultRetcode() == TRADE_RETCODE_DONE_PARTIAL))
         {
            executed = 1;
            g_traded_today = true;
            
            g_current_position_id = g_execution.ResultOrder();
            g_current_entry_price = bar.close;
            g_current_stop_price = stop_price;
            g_current_target_price = target_price;
            g_current_entry_time = bar.time;
            g_current_dir = (breakout_side > 0 ? "BUY" : "SELL");
            g_current_req_lot = FixedLot;
            g_current_exec_lot = lot_to_trade;
            g_current_bal_before = AccountInfoDouble(ACCOUNT_BALANCE);
            g_current_spread = (tick.ask - tick.bid) * lot_to_trade * 100.0;
            
            if(g_current_day_idx >= 0)
            {
               g_daily_records[g_current_day_idx].trades_executed++;
               g_daily_records[g_current_day_idx].actual_lots += lot_to_trade;
            }
         }
         else reason = "EXECUTION_REJECTED_BROKER_ERROR";
      }
      else reason = "EXECUTION_REJECTED_INSUFFICIENT_MARGIN";
   }
   else if(signal_accepted && g_traded_today)
   {
      reason = "SKIPPED_ALREADY_TRADED_TODAY";
   }
   else if(signal_accepted && PositionSelect(_Symbol))
   {
      reason = "SKIPPED_POSITION_ALREADY_OPEN";
   }

   // Record Classification Event
   if(g_class_count < MAX_EVENTS)
   {
      int ev_idx = g_class_count++;
      MqlDateTime dt;
      TimeToStruct(bar.time, dt);
      
      g_classifications[ev_idx].event_id = StringFormat("EVT-%04d%02d%02d-%s-%s-%02d%02d",
                                                        dt.year, dt.mon, dt.day,
                                                        session_name, (breakout_side > 0 ? "BUY" : "SELL"),
                                                        dt.hour, dt.min);
      g_classifications[ev_idx].date_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
      g_classifications[ev_idx].time_str = StringFormat("%02d:%02d:%02d", dt.hour, dt.min, dt.sec);
      g_classifications[ev_idx].session_str = session_name;
      g_classifications[ev_idx].direction_str = (breakout_side > 0 ? "BUY" : "SELL");
      g_classifications[ev_idx].ref_range_str = "REF_ASIA_NY";
      g_classifications[ev_idx].broken_level = broken_level;
      g_classifications[ev_idx].breakout_price = bar.close;
      g_classifications[ev_idx].candle_strength = candle_strength;
      g_classifications[ev_idx].fvg = fvg_ok ? 1 : 0;
      g_classifications[ev_idx].retest = retest_ok ? 1 : 0;
      g_classifications[ev_idx].bos = bos_ok;
      g_classifications[ev_idx].liquidity_sweep = sweep_ok ? 1 : 0;
      g_classifications[ev_idx].atr = features.atr;
      g_classifications[ev_idx].market_regime = regime_str;
      g_classifications[ev_idx].intermarket_confirmed = inter_conf;
      g_classifications[ev_idx].confidence_score = conf_score;
      g_classifications[ev_idx].market_behavior_label = "PENDING";
      g_classifications[ev_idx].hypothetical_trade_outcome = "PENDING";
      g_classifications[ev_idx].signal_accepted_active_strat = signal_accepted ? 1 : 0;
      g_classifications[ev_idx].executed_active_strat = executed;
      g_classifications[ev_idx].rejection_reason = reason;
      g_classifications[ev_idx].potential_pnl_usd = potential_pnl;
      
      g_classifications[ev_idx].side = breakout_side;
      g_classifications[ev_idx].stop_price = stop_price;
      g_classifications[ev_idx].target_price = target_price;
      g_classifications[ev_idx].entry_time = bar.time;
      g_classifications[ev_idx].bars_held = 0;
      g_classifications[ev_idx].reentered_range_3bars = false;
      g_classifications[ev_idx].resolved = false;
      g_classifications[ev_idx].ref_high = level_ny.high;
      g_classifications[ev_idx].ref_low = level_ny.low;
      
      if(g_current_day_idx >= 0 && signal_accepted)
      {
         g_daily_records[g_current_day_idx].signals_accepted++;
      }
   }
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      ulong deal_ticket = trans.deal;
      if(HistoryDealSelect(deal_ticket))
      {
         long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
         if(deal_entry == DEAL_ENTRY_OUT)
         {
            double pnl = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
            double comm = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
            double swap = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
            double net = pnl + comm + swap;
            
            g_running_balance += net;
            
            if(g_trade_count < MAX_TRADES)
            {
               int t_idx = g_trade_count++;
               g_trades[t_idx].run_id = "RUN_ADAPTIVE_010";
               g_trades[t_idx].strategy_version = EnumToString(EngineMode);
               g_trades[t_idx].deal_id = deal_ticket;
               g_trades[t_idx].position_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
               g_trades[t_idx].entry_datetime = TimeToString(g_current_entry_time, TIME_DATE|TIME_SECONDS);
               g_trades[t_idx].exit_datetime = TimeToString(HistoryDealGetInteger(deal_ticket, DEAL_TIME), TIME_DATE|TIME_SECONDS);
               g_trades[t_idx].direction = g_current_dir;
               g_trades[t_idx].requested_lot = g_current_req_lot;
               g_trades[t_idx].executed_lot = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
               g_trades[t_idx].entry_price = g_current_entry_price;
               g_trades[t_idx].exit_price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
               g_trades[t_idx].stop_loss = g_current_stop_price;
               g_trades[t_idx].take_profit = g_current_target_price;
               g_trades[t_idx].spread_cost = g_current_spread;
               g_trades[t_idx].commission = comm;
               g_trades[t_idx].swap = swap;
               g_trades[t_idx].slippage = 0.0;
               g_trades[t_idx].gross_profit = pnl;
               g_trades[t_idx].net_profit = net;
               g_trades[t_idx].balance_before = g_current_bal_before;
               g_trades[t_idx].balance_after = g_running_balance;
            }
            
            if(g_current_day_idx >= 0)
            {
               if(net > 0) g_daily_records[g_current_day_idx].daily_profit += net;
               else g_daily_records[g_current_day_idx].daily_loss += net;
               g_daily_records[g_current_day_idx].daily_net += net;
               g_daily_records[g_current_day_idx].ending_balance = g_running_balance;
               
               if(net > 0)
               {
                  g_daily_records[g_current_day_idx].main_status = "PROFIT";
                  g_daily_records[g_current_day_idx].primary_missed_reason = "NONE_PROFITABLE_DAY";
               }
               else
               {
                  g_daily_records[g_current_day_idx].main_status = "LOSS";
                  g_daily_records[g_current_day_idx].primary_missed_reason = "STOP_LOSS_REACHED";
               }
            }
         }
         else if(deal_entry == DEAL_ENTRY_IN)
         {
            double comm = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
            g_running_balance += comm;
            if(g_current_day_idx >= 0)
            {
               g_daily_records[g_current_day_idx].daily_loss += comm;
               g_daily_records[g_current_day_idx].daily_net += comm;
               g_daily_records[g_current_day_idx].ending_balance = g_running_balance;
            }
         }
      }
   }
}
