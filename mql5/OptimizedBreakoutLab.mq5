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

input string ExpectedSymbol = "XAUUSD_o";
input BrokerClock ServerClock = CLOCK_LITEFINANCE_EU;
input ReferenceKind Reference = REF_ASIA_NY;
input LotSizeMode LotMode = LOT_FIXED_RESEARCH;
input double FixedLot = 0.10;
input OptimizationModel ModelChoice = MODEL_BALANCED_OPTIMIZED;
input double RiskPerTradePct = 1.0;
input double DailyLossLimitPct = 6.0;
input double TargetRR = 1.5;
input double MaxRangeWidth = 30.0;
input double MinStopBps = 5.8;

// Advanced Exploration Switches (Independent Feature Toggles)
input TimeWindowMode TimeWindow = WINDOW_08_09;
input StopLossTargetMode SLTPMode = SLTP_FIXED_BAR_RR;
input bool OptRequireRetest = false;          // Feature: Retest confirmation
input bool OptUseAtrFilter = false;           // Feature: ATR overextension and minimum displacement
input double OptMinAtrRatio = 0.50;           // Bar range >= MinAtrRatio * ATR
input double OptMaxAtrRatio = 2.50;           // Bar range <= MaxAtrRatio * ATR
input bool OptRequireCloseLocation = false;   // Feature: Close in upper/lower 25% of candle
input double OptVolumeRatioMin = 1.10;        // Feature: Tick volume ratio threshold
input double OptFvgMinSize = 0.20;            // Feature: Minimum FVG gap size in dollars
input bool OptOpposingSweepBonus = false;     // Feature: Prior liquidity sweep confirmation
input bool OptUseRangeWidthFilter = false;    // Feature: MaxRangeWidth filter

// State tracking
int g_atr_handle = INVALID_HANDLE;
int g_ema_handle = INVALID_HANDLE;
int g_adx_handle = INVALID_HANDLE;
datetime g_last_processed_bar = 0;
bool g_traded_today = false;
datetime g_current_day_start = 0;
CTrade g_execution;

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
   
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_atr_handle != INVALID_HANDLE) IndicatorRelease(g_atr_handle);
   if(g_ema_handle != INVALID_HANDLE) IndicatorRelease(g_ema_handle);
   if(g_adx_handle != INVALID_HANDLE) IndicatorRelease(g_adx_handle);
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
   }
   
   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   if(CopyRates(_Symbol, PERIOD_M5, 1, 32, bars) != 32) return;
   
   int london_min = (int)(((utc + (EuropeSummer(utc)?3600:0)) % 86400) / 60);
   bool is_london = (london_min >= 8*60 && london_min < 11*60);
   if(!is_london) return;
   
   // Window check
   bool in_08_09 = (london_min >= 8*60 && london_min < 9*60);
   bool in_custom_window = false;
   switch(TimeWindow)
   {
      case WINDOW_08_09: in_custom_window = (london_min >= 8*60 && london_min < 9*60); break;
      case WINDOW_08_10: in_custom_window = (london_min >= 8*60 && london_min < 10*60); break;
      case WINDOW_08_11: in_custom_window = (london_min >= 8*60 && london_min < 11*60); break;
   }
   
   // Read Asian range REF_ASIA_NY
   PriceRange level_ny={};
   if(!ReadRange(REF_ASIA_NY, utc-300, ServerClock, level_ny)) return;
   
   double range_width = level_ny.high - level_ny.low;
   bool range_ok = (range_width >= 2.0 && range_width <= MaxRangeWidth);
   
   Features features={};
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
   }
}
