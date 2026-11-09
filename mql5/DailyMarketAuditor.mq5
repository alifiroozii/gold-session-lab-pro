#property copyright "Gold Session Lab Pro"
#property version   "2.00"
#property strict

#include "GoldResearchLab/SessionEngine.mqh"
#include "GoldResearchLab/LevelDetector.mqh"
#include "GoldResearchLab/MarketStructure.mqh"
#include "GoldResearchLab/BreakoutStrategy.mqh"
#include "GoldResearchLab/ConfirmationEngine.mqh"
#include "GoldResearchLab/RiskGuardian.mqh"
#include "GoldResearchLab/TradeExecution.mqh"
#include "GoldResearchLab/PositionManager.mqh"

input string ExpectedSymbol="XAUUSD_o";
input BrokerClock ServerClock=CLOCK_LITEFINANCE_EU;
input ReferenceKind Reference=REF_ASIA_NY;
input double RiskPerTradePct=3.0;
input double DailyLossLimitPct=6.0;
input double MaxLotCap=0.06;
input double TargetRR=1.5;
input double MinStopBps=5.8;
input double MaxRangeWidth=30.0;

// Structures for daily audit
struct DailyRecord {
   string date_str;
   string weekday_str;
   int market_open;
   string data_quality;
   double asia_high;
   double asia_low;
   double asia_width;
   int frankfurt_breakout_count;
   int london_breakout_count;
   int ny_breakout_count;
   int valid_breakout_count;
   int false_breakout_count;
   int detected_valid_count;
   int correctly_rejected_false_count;
   int missed_valid_count;
   int false_signals_traded_count;
   int trades_count;
   int winning_trades;
   int losing_trades;
   double daily_gross_profit;
   double daily_commission;
   double daily_swap;
   double daily_net_profit;
   double daily_starting_balance;
   double daily_ending_balance;
   double daily_drawdown;
   string main_day_status;
   string reason;
   string strategy_version;
   int bar_count;
   double day_high;
   double day_low;
   double peak_equity;
   double trough_equity;
};

struct BreakoutEventRecord {
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
   int confidence_score;
   string strategy_version;
   int signal_accepted;
   int executed;
   string decision_reason;
   string market_outcome;
   double trade_pnl;
   
   // Tracking forward state
   int side;
   double entry_price;
   double stop_price;
   double target_price;
   datetime entry_time;
   int bars_held;
   bool reentered_range_3bars;
   bool resolved;
   double ref_high;
   double ref_low;
};

#define MAX_AUDIT_DAYS 800
#define MAX_EVENTS 5000

DailyRecord g_days[MAX_AUDIT_DAYS];
int g_day_count = 0;

BreakoutEventRecord g_events[MAX_EVENTS];
int g_event_count = 0;

CTrade g_execution;
int g_atr_handle = INVALID_HANDLE;
int g_ema_handle = INVALID_HANDLE;
int g_adx_handle = INVALID_HANDLE;

datetime g_last_processed_bar = 0;
datetime g_current_day_start = 0;
int g_current_day_idx = -1;
double g_running_balance = 1000.0;
double g_day_start_balance = 1000.0;
bool g_traded_today = false;

// Forward tracker for pending breakout candidate resolutions
void UpdatePendingEvents(const MqlRates &bar, const int total_bars)
{
   for(int i = 0; i < g_event_count; i++)
   {
      if(g_events[i].resolved) continue;
      
      g_events[i].bars_held++;
      
      // Check if price re-entered Asian range within 3 bars
      if(g_events[i].bars_held <= 3)
      {
         if(g_events[i].side > 0 && bar.close <= g_events[i].ref_high)
            g_events[i].reentered_range_3bars = true;
         if(g_events[i].side < 0 && bar.close >= g_events[i].ref_low)
            g_events[i].reentered_range_3bars = true;
      }
      
      // Check target or stop hit
      bool hit_target = false;
      bool hit_stop = false;
      
      if(g_events[i].side > 0)
      {
         if(bar.high >= g_events[i].target_price) hit_target = true;
         if(bar.low <= g_events[i].stop_price) hit_stop = true;
      }
      else
      {
         if(bar.low <= g_events[i].target_price) hit_target = true;
         if(bar.high >= g_events[i].stop_price) hit_stop = true;
      }
      
      if(hit_target && !hit_stop)
      {
         g_events[i].resolved = true;
         if(!g_events[i].reentered_range_3bars)
            g_events[i].market_outcome = "VALID_BREAKOUT";
         else
            g_events[i].market_outcome = "FALSE_BREAKOUT";
      }
      else if(hit_stop)
      {
         g_events[i].resolved = true;
         g_events[i].market_outcome = "FALSE_BREAKOUT";
      }
      else if(g_events[i].bars_held >= 72) // 6 hours max forward window
      {
         g_events[i].resolved = true;
         g_events[i].market_outcome = "FALSE_BREAKOUT";
      }
   }
}

int GetDayIndex(const datetime time_sec)
{
   datetime dstart = DayStart(time_sec);
   for(int i = 0; i < g_day_count; i++)
   {
      MqlDateTime dt;
      TimeToStruct(dstart, dt);
      string ds = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
      if(g_days[i].date_str == ds) return i;
   }
   if(g_day_count >= MAX_AUDIT_DAYS) return -1;
   
   int idx = g_day_count++;
   MqlDateTime dt;
   TimeToStruct(dstart, dt);
   g_days[idx].date_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
   
   string days_of_week[7] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};
   g_days[idx].weekday_str = days_of_week[dt.day_of_week];
   g_days[idx].market_open = 1;
   g_days[idx].data_quality = "VALID";
   g_days[idx].daily_starting_balance = g_running_balance;
   g_days[idx].daily_ending_balance = g_running_balance;
   g_days[idx].peak_equity = g_running_balance;
   g_days[idx].trough_equity = g_running_balance;
   g_days[idx].strategy_version = "EXP23_London_0809_FVG";
   g_days[idx].main_day_status = "NO_BREAKOUT";
   g_days[idx].reason = "NO_BREAKOUT_INSIDE_RANGE";
   return idx;
}


bool FeatureAt(const MqlRates &bars[],const datetime server_open,Features &out)
{
   double atr[1],ema[1],adx[1];
   MqlRates hour[1],structure[];
   ArraySetAsSeries(structure,true);
   if(CopyBuffer(g_atr_handle,0,2,1,atr)!=1 || CopyBuffer(g_ema_handle,0,1,1,ema)!=1 ||
      CopyBuffer(g_adx_handle,0,1,1,adx)!=1 || CopyRates(_Symbol,PERIOD_H1,1,1,hour)!=1 ||
      CopyRates(_Symbol,PERIOD_M15,1,4,structure)!=4) return false;
   if(atr[0]<=0 || ema[0]<=0 || adx[0]<0 || adx[0]>100 ||
      atr[0]==EMPTY_VALUE || ema[0]==EMPTY_VALUE ||
      !MathIsValidNumber(atr[0]) || !MathIsValidNumber(ema[0]) || !MathIsValidNumber(adx[0]) ||
      hour[0].time+3600>server_open || structure[0].time+900>server_open ||
      !ValidBar(hour[0])) return false;
   for(int i=0;i<4;i++) if(!ValidBar(structure[i])) return false;
   out.atr=atr[0];
   out.ema=ema[0];
   out.adx=adx[0];
   out.hour_close=hour[0].close;
   double high=structure[1].high,low=structure[1].low,volume=0;
   for(int i=2;i<4;i++)
   {
      high=MathMax(high,structure[i].high);
      low=MathMin(low,structure[i].low);
   }
   out.m15_break=structure[0].close>high ? 1 : (structure[0].close<low ? -1 : 0);
   for(int i=1;i<=20;i++) volume+=(double)bars[i].tick_volume;
   out.volume_ratio=20.0*(double)bars[0].tick_volume/volume;
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
   if(g_atr_handle==INVALID_HANDLE || g_ema_handle==INVALID_HANDLE || g_adx_handle==INVALID_HANDLE)
      return INIT_FAILED;

   g_execution.SetExpertMagicNumber(LAB_MAGIC);
   g_execution.SetDeviationInPoints((ulong)MathFloor(0.10/_Point));
   if(!g_execution.SetTypeFillingBySymbol(_Symbol)) return INIT_FAILED;

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_atr_handle!=INVALID_HANDLE) IndicatorRelease(g_atr_handle);
   if(g_ema_handle!=INVALID_HANDLE) IndicatorRelease(g_ema_handle);
   if(g_adx_handle!=INVALID_HANDLE) IndicatorRelease(g_adx_handle);
   
   // Finalize any unresolved events
   for(int i = 0; i < g_event_count; i++)
   {
      if(!g_events[i].resolved)
      {
         g_events[i].resolved = true;
         g_events[i].market_outcome = "FALSE_BREAKOUT";
      }
   }
   
   // Reconcile and calculate day counts and status
   for(int i = 0; i < g_event_count; i++)
   {
      string ev_date = g_events[i].date_str;
      for(int d = 0; d < g_day_count; d++)
      {
         if(g_days[d].date_str == ev_date)
         {
            if(g_events[i].market_outcome == "VALID_BREAKOUT")
            {
               g_days[d].valid_breakout_count++;
               if(g_events[i].signal_accepted == 1)
                  g_days[d].detected_valid_count++;
               else
                  g_days[d].missed_valid_count++;
            }
            else // FALSE_BREAKOUT
            {
               g_days[d].false_breakout_count++;
               if(g_events[i].signal_accepted == 0)
                  g_days[d].correctly_rejected_false_count++;
               else
                  g_days[d].false_signals_traded_count++;
            }
            break;
         }
      }
   }

   // Set MainDayStatus and Reason for each day
   for(int d = 0; d < g_day_count; d++)
   {
      if(g_days[d].trades_count > 0)
      {
         if(g_days[d].daily_net_profit > 0.0)
         {
            g_days[d].main_day_status = "PROFIT";
            g_days[d].reason = StringFormat("PROFIT_TAKEN_LONDON_FVG (+%.2f USD)", g_days[d].daily_net_profit);
         }
         else
         {
            g_days[d].main_day_status = "LOSS";
            g_days[d].reason = StringFormat("STOP_LOSS_HIT_LONDON_FVG (%.2f USD)", g_days[d].daily_net_profit);
         }
      }
      else if(g_days[d].valid_breakout_count > 0 && g_days[d].missed_valid_count > 0)
      {
         g_days[d].main_day_status = "MISSED_VALID_BREAKOUT";
         g_days[d].reason = "VALID_BREAKOUT_REJECTED_BY_FILTER";
      }
      else if(g_days[d].false_breakout_count > 0 && g_days[d].correctly_rejected_false_count > 0)
      {
         g_days[d].main_day_status = "FALSE_BREAKOUT_DETECTED";
         g_days[d].reason = "FALSE_BREAKOUT_FILTERED_NO_TRADE";
      }
      else if(g_days[d].frankfurt_breakout_count + g_days[d].london_breakout_count + g_days[d].ny_breakout_count > 0)
      {
         g_days[d].main_day_status = "BREAKOUT_REJECTED";
         g_days[d].reason = "BREAKOUT_OUTSIDE_CRITERIA";
      }
      else
      {
         g_days[d].main_day_status = "NO_BREAKOUT";
         g_days[d].reason = "NO_BREAKOUT_INSIDE_RANGE";
      }
   }
   
   // Write breakout_events_2025_2026.csv
   int h_ev = FileOpen("breakout_events_2025_2026.csv", FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON);
   if(h_ev != INVALID_HANDLE)
   {
      FileWrite(h_ev,
         "EventId","Date","Time","Session","Direction","ReferenceRange","BrokenLevel",
         "BreakoutPrice","CandleStrength","FVG","Retest","BOS","LiquiditySweep","ATR",
         "ConfidenceScore","StrategyVersion","SignalAccepted","Executed","DecisionReason",
         "MarketOutcome","TradePnL"
      );
      for(int i = 0; i < g_event_count; i++)
      {
         FileWrite(h_ev,
            g_events[i].event_id,
            g_events[i].date_str,
            g_events[i].time_str,
            g_events[i].session_str,
            g_events[i].direction_str,
            g_events[i].ref_range_str,
            DoubleToString(g_events[i].broken_level, 2),
            DoubleToString(g_events[i].breakout_price, 2),
            DoubleToString(g_events[i].candle_strength, 2),
            IntegerToString(g_events[i].fvg),
            IntegerToString(g_events[i].retest),
            IntegerToString(g_events[i].bos),
            IntegerToString(g_events[i].liquidity_sweep),
            DoubleToString(g_events[i].atr, 2),
            IntegerToString(g_events[i].confidence_score),
            g_events[i].strategy_version,
            IntegerToString(g_events[i].signal_accepted),
            IntegerToString(g_events[i].executed),
            g_events[i].decision_reason,
            g_events[i].market_outcome,
            DoubleToString(g_events[i].trade_pnl, 2)
         );
      }
      FileClose(h_ev);
   }

   // Also build calendar map from 2025-01-01 to 2026-11-09 to write daily_market_audit_2025_2026.csv
   datetime cur_cal = StringToTime("2025.01.01 00:00:00");
   datetime end_cal = StringToTime("2026.11.09 23:59:59");
   
   int h_daily = FileOpen("daily_market_audit_2025_2026.csv", FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON);
   if(h_daily != INVALID_HANDLE)
   {
      FileWrite(h_daily,
         "Date","Weekday","MarketOpen","DataQuality","AsiaHigh","AsiaLow","AsiaRangeWidth",
         "FrankfurtBreakoutCount","LondonBreakoutCount","NewYorkBreakoutCount",
         "ValidBreakoutCount","FalseBreakoutCount","DetectedValidCount","CorrectlyRejectedFalseCount",
         "MissedValidCount","FalseSignalsTradedCount","TradesCount","WinningTrades","LosingTrades",
         "DailyGrossProfit","DailyCommission","DailySwap","DailyNetProfit",
         "DailyStartingBalance","DailyEndingBalance","DailyDrawdown",
         "MainDayStatus","Reason","StrategyVersion"
      );
      
      double running_bal = 1000.0;
      while(cur_cal <= end_cal)
      {
         MqlDateTime dt;
         TimeToStruct(cur_cal, dt);
         string d_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
         string days_of_week[7] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};
         string w_str = days_of_week[dt.day_of_week];
         
         // Search in g_days
         int found_idx = -1;
         for(int d = 0; d < g_day_count; d++)
         {
            if(g_days[d].date_str == d_str) { found_idx = d; break; }
         }
         
         if(found_idx >= 0)
         {
            DailyRecord rec = g_days[found_idx];
            running_bal = rec.daily_ending_balance;
            FileWrite(h_daily,
               rec.date_str, rec.weekday_str, IntegerToString(rec.market_open), rec.data_quality,
               DoubleToString(rec.asia_high, 2), DoubleToString(rec.asia_low, 2), DoubleToString(rec.asia_width, 2),
               IntegerToString(rec.frankfurt_breakout_count), IntegerToString(rec.london_breakout_count), IntegerToString(rec.ny_breakout_count),
               IntegerToString(rec.valid_breakout_count), IntegerToString(rec.false_breakout_count),
               IntegerToString(rec.detected_valid_count), IntegerToString(rec.correctly_rejected_false_count),
               IntegerToString(rec.missed_valid_count), IntegerToString(rec.false_signals_traded_count),
               IntegerToString(rec.trades_count), IntegerToString(rec.winning_trades), IntegerToString(rec.losing_trades),
               DoubleToString(rec.daily_gross_profit, 2), DoubleToString(rec.daily_commission, 2), DoubleToString(rec.daily_swap, 2), DoubleToString(rec.daily_net_profit, 2),
               DoubleToString(rec.daily_starting_balance, 2), DoubleToString(rec.daily_ending_balance, 2), DoubleToString(rec.daily_drawdown, 2),
               rec.main_day_status, rec.reason, rec.strategy_version
            );
         }
         else
         {
            // Day without data
            int m_open = 0;
            string d_qual = "HOLIDAY";
            string m_status = "DATA_UNAVAILABLE";
            string r_reason = "HOLIDAY_MARKET_CLOSED";
            
            if(dt.day_of_week == 0 || dt.day_of_week == 6)
            {
               d_qual = "WEEKEND";
               r_reason = "WEEKEND_CLOSED";
            }
            else if(cur_cal >= StringToTime("2026.11.07 00:00:00"))
            {
               d_qual = "DATA_UNAVAILABLE";
               r_reason = "FUTURE_OR_INCOMPLETE_DATA";
            }
            
            FileWrite(h_daily,
               d_str, w_str, IntegerToString(m_open), d_qual,
               "0.00", "0.00", "0.00",
               "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
               "0.00", "0.00", "0.00", "0.00",
               DoubleToString(running_bal, 2), DoubleToString(running_bal, 2), "0.00",
               m_status, r_reason, "EXP23_London_0809_FVG"
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
   
   // Update day stats
   if(g_current_day_idx >= 0)
   {
      g_days[g_current_day_idx].bar_count++;
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      if(eq > g_days[g_current_day_idx].peak_equity) g_days[g_current_day_idx].peak_equity = eq;
      if(eq < g_days[g_current_day_idx].trough_equity) g_days[g_current_day_idx].trough_equity = eq;
      double peak = g_days[g_current_day_idx].peak_equity;
      double trough = g_days[g_current_day_idx].trough_equity;
      if(peak > 0)
         g_days[g_current_day_idx].daily_drawdown = MathMax(g_days[g_current_day_idx].daily_drawdown, (peak - trough)/peak * 100.0);
   }
   
   // Update pending forward tracking events
   UpdatePendingEvents(bars[0], g_days[g_current_day_idx].bar_count);
   
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
   
   if(g_current_day_idx >= 0 && g_days[g_current_day_idx].asia_high == 0.0)
   {
      g_days[g_current_day_idx].asia_high = level_ny.high;
      g_days[g_current_day_idx].asia_low = level_ny.low;
      g_days[g_current_day_idx].asia_width = level_ny.high - level_ny.low;
   }
   
   // Features
   Features features={};
   if(!FeatureAt(bars, current-300, features)) return;
   
   MqlRates bar = bars[0];
   MqlRates prev_bar = bars[1];
   
   // Check candidate breakouts (Close breaches level)
   int breakout_side = 0;
   double broken_level = 0.0;
   if(bar.close > level_ny.high && prev_bar.close <= level_ny.high)
   {
      breakout_side = 1;
      broken_level = level_ny.high;
   }
   else if(bar.close < level_ny.low && prev_bar.close >= level_ny.low)
   {
      breakout_side = -1;
      broken_level = level_ny.low;
   }
   
   if(breakout_side == 0) return;
   
   // Count session breakout
   if(g_current_day_idx >= 0)
   {
      if(is_frankfurt) g_days[g_current_day_idx].frankfurt_breakout_count++;
      if(is_london) g_days[g_current_day_idx].london_breakout_count++;
      if(is_ny) g_days[g_current_day_idx].ny_breakout_count++;
   }
   
   // Extract event features
   double candle_strength = (bar.high - bar.low > _Point) ? MathAbs(bar.close - bar.open) / (bar.high - bar.low) : 0.0;
   bool fvg_ok = FvgConfirmed(bars, breakout_side);
   bool retest_ok = Retested(bar, broken_level, breakout_side);
   int bos_ok = (features.m15_break == breakout_side) ? 1 : 0;
   bool sweep_ok = OpposingAsianSideSwept(bars, level_ny, breakout_side);
   int conf_score = CalculateBreakoutScore(bar, bars, features, level_ny, breakout_side);
   
   // Evaluate champion strategy EXP23 (London 08-09 + FVG + Range <= 30)
   bool in_08_09 = (london_min >= 8*60 && london_min < 9*60);
   bool range_ok = (level_ny.high - level_ny.low >= 2.0 && level_ny.high - level_ny.low <= MaxRangeWidth);
   
   int accepted = 0;
   int executed = 0;
   string reason = "";
   
   if(!is_london)
   {
      reason = "REJECTED_OUTSIDE_LONDON_SESSION";
   }
   else if(!in_08_09)
   {
      reason = "REJECTED_OUTSIDE_08_09_IMPULSE_HOUR";
   }
   else if(!range_ok)
   {
      reason = "REJECTED_ASIAN_RANGE_TOO_WIDE";
   }
   else if(!fvg_ok)
   {
      reason = "REJECTED_NO_FVG_IMBALANCE";
   }
   else
   {
      accepted = 1;
      reason = "ACCEPTED_EXP23_RULES_MET";
      
      if(!g_traded_today && !PositionSelect(_Symbol))
      {
         TradePlan plan={};
         Setup setup={};
         setup.observed = utc;
         setup.session = SESSION_LONDON;
         setup.range = level_ny;
         setup.side = breakout_side;
         setup.level = broken_level;
         double anchor = (breakout_side > 0) ? bar.low : bar.high;
         setup.stop = anchor - breakout_side * 0.30;
         
         if(BuildTradePlan(setup, tick, features.atr, ServerClock, plan,
                           RiskPerTradePct/100.0, DailyLossLimitPct/100.0, 1,
                           0.0, 2.5, TargetRR, MaxLotCap, MinStopBps, 0.0))
         {
            if(SubmitResearchOrder(g_execution, setup, plan))
            {
               executed = 1;
               g_traded_today = true;
               if(g_current_day_idx >= 0) g_days[g_current_day_idx].trades_count++;
            }
         }
      }
   }
   
   // Record Event
   if(g_event_count < MAX_EVENTS)
   {
      int ev_idx = g_event_count++;
      MqlDateTime dt;
      TimeToStruct(bar.time, dt);
      
      g_events[ev_idx].event_id = StringFormat("EVT-%04d%02d%02d-%s-%s-%02d%02d",
                                               dt.year, dt.mon, dt.day,
                                               session_name, (breakout_side > 0 ? "BUY" : "SELL"),
                                               dt.hour, dt.min);
      g_events[ev_idx].date_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
      g_events[ev_idx].time_str = StringFormat("%02d:%02d:%02d", dt.hour, dt.min, dt.sec);
      g_events[ev_idx].session_str = session_name;
      g_events[ev_idx].direction_str = (breakout_side > 0 ? "BUY" : "SELL");
      g_events[ev_idx].ref_range_str = "REF_ASIA_NY";
      g_events[ev_idx].broken_level = broken_level;
      g_events[ev_idx].breakout_price = bar.close;
      g_events[ev_idx].candle_strength = candle_strength;
      g_events[ev_idx].fvg = fvg_ok ? 1 : 0;
      g_events[ev_idx].retest = retest_ok ? 1 : 0;
      g_events[ev_idx].bos = bos_ok;
      g_events[ev_idx].liquidity_sweep = sweep_ok ? 1 : 0;
      g_events[ev_idx].atr = features.atr;
      g_events[ev_idx].confidence_score = conf_score;
      g_events[ev_idx].strategy_version = "EXP23_London_0809_FVG";
      g_events[ev_idx].signal_accepted = accepted;
      g_events[ev_idx].executed = executed;
      g_events[ev_idx].decision_reason = reason;
      g_events[ev_idx].market_outcome = "PENDING";
      g_events[ev_idx].trade_pnl = 0.0;
      
      // Setup tracking targets
      g_events[ev_idx].side = breakout_side;
      g_events[ev_idx].entry_price = bar.close;
      double raw_stop_dist = MathAbs(bar.close - (breakout_side > 0 ? bar.low : bar.high)) + 0.30;
      double min_stop_dist = bar.close * (MinStopBps / 10000.0);
      double stop_dist = MathMax(raw_stop_dist, min_stop_dist);
      
      g_events[ev_idx].stop_price = bar.close - breakout_side * stop_dist;
      g_events[ev_idx].target_price = bar.close + breakout_side * (stop_dist * TargetRR);
      g_events[ev_idx].entry_time = bar.time;
      g_events[ev_idx].bars_held = 0;
      g_events[ev_idx].reentered_range_3bars = false;
      g_events[ev_idx].resolved = false;
      g_events[ev_idx].ref_high = level_ny.high;
      g_events[ev_idx].ref_low = level_ny.low;
   }
}

// OnTradeTransaction to capture realized PnL and commissions directly
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
            
            if(g_current_day_idx >= 0)
            {
               g_days[g_current_day_idx].daily_gross_profit += pnl;
               g_days[g_current_day_idx].daily_commission += comm;
               g_days[g_current_day_idx].daily_swap += swap;
               g_days[g_current_day_idx].daily_net_profit += net;
               g_days[g_current_day_idx].daily_ending_balance = g_running_balance;
               if(net > 0) g_days[g_current_day_idx].winning_trades++;
               else if(net < 0) g_days[g_current_day_idx].losing_trades++;
            }
            
            // Assign trade PnL to the last executed event
            for(int i = g_event_count - 1; i >= 0; i--)
            {
               if(g_events[i].executed == 1 && g_events[i].trade_pnl == 0.0)
               {
                  g_events[i].trade_pnl = net;
                  break;
               }
            }
         }
         else if(deal_entry == DEAL_ENTRY_IN)
         {
            double comm = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
            g_running_balance += comm;
            if(g_current_day_idx >= 0)
            {
               g_days[g_current_day_idx].daily_commission += comm;
               g_days[g_current_day_idx].daily_net_profit += comm;
               g_days[g_current_day_idx].daily_ending_balance = g_running_balance;
            }
         }
      }
   }
}
