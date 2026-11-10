#ifndef GOLD_CONFIRMATION_ENGINE
#define GOLD_CONFIRMATION_ENGINE

enum StrategyKind { STRATEGY_BREAKOUT, STRATEGY_SWEEP, STRATEGY_RANGE };
enum EntryMode { MODE_FAST, MODE_STANDARD, MODE_CONSERVATIVE };
enum SetupStage { SETUP_IDLE, SETUP_SWEEP, SETUP_STRUCTURE, SETUP_RETEST, SETUP_NEXT_CANDLE };
enum ConfirmationMethod {
   CONFIRM_METHOD_NONE = 0,             // Pure breakout baseline (fast)
   CONFIRM_METHOD_A_CANDLE_QUALITY,     // Method A: BodyRatio>=0.45, wick<=0.35, 0.6-2.5 ATR
   CONFIRM_METHOD_B_NEXT_CANDLE,        // Method B: Follow-through next candle
   CONFIRM_METHOD_C_RETEST,             // Method C: Retest of broken level
   CONFIRM_METHOD_D_FVG,                // Method D: Valid FVG in breakout direction
   CONFIRM_METHOD_E_M15_BOS,            // Method E: M15 Structure Break (BOS)
   CONFIRM_METHOD_F_LIQUIDITY_SWEEP,    // Method F: Swept opposing Asian side first (Judas Swing)
   CONFIRM_METHOD_G_H1_TREND,           // Method G: H1 EMA50 + ADX>=18
   CONFIRM_METHOD_H_MOMENTUM_VOL,       // Method H: Vol ratio>=1.15x + Displacement>=0.9 ATR
   CONFIRM_COMBO_RETEST_FVG,            // Combo 1: Retest + FVG
   CONFIRM_COMBO_FVG_BOS,               // Combo 2: FVG + M15 BOS
   CONFIRM_COMBO_SWEEP_BOS,             // Combo 3: Opposite Sweep + M15 BOS
   CONFIRM_COMBO_QUALITY_SCORE          // Empirical Breakout Quality Score (with NO TRADE)
};
struct Setup
{
   SetupStage stage;
   datetime observed;
   LabSession session;
   PriceRange range;
   int side;
   double level,stop,target,pivot;
};
struct Features { double atr,adx,ema,hour_close,volume_ratio; int m15_break; };

int ConfirmationCount(const MqlRates &bar,const MqlRates &bars[],const Features &features,const int side)
{
   double low=0,high=0;
   bool trend=side>0 ? features.hour_close>=features.ema : features.hour_close<features.ema-1.0;
   bool fvg=ActiveFVG(bars,side,low,high);
   bool momentum=features.volume_ratio>=0.60 && bar.high-bar.low>=features.atr && BodyRatio(bar)>=0.45;
   return (int)trend+(int)fvg+(int)momentum+(int)(features.m15_break==side);
}

bool TrendAligned(const Features &features,const int side,const double min_adx)
{
   if(min_adx>0.0 && features.adx<min_adx) return false;
   if(side>0 && features.hour_close<features.ema) return false;
   if(side<0 && features.hour_close>features.ema) return false;
   return true;
}

bool Retested(const MqlRates &bar,const double level,const int side)
{
   return bar.low<=level+0.25 && bar.high>=level-0.25 &&
          side*(bar.close-level)>0 && RejectionWick(bar,side)>=0.35;
}

bool RetestedEx(const MqlRates &bar,const double level,const int side,const double atr)
{
   double tol=MathMax(0.25,0.20*atr);
   return bar.low<=level+tol && bar.high>=level-tol &&
          side*(bar.close-level)>0 && RejectionWick(bar,side)>=0.30;
}

bool OpposingAsianSideSwept(const MqlRates &bars[], const PriceRange &range, const int side)
{
   int limit = MathMin(ArraySize(bars), 72);
   for(int i=1; i<limit; i++)
   {
      if(side > 0 && bars[i].low < range.low - 0.10 && bars[i].close > range.low) return true;
      if(side < 0 && bars[i].high > range.high + 0.10 && bars[i].close < range.high) return true;
   }
   return false;
}

bool CandleQualityValid(const MqlRates &bar, const double atr, const PriceRange &range, const int side)
{
   double body = BodyRatio(bar);
   if(body < 0.45) return false;
   double wick = side > 0 ? (bar.high - MathMax(bar.open, bar.close)) : (MathMin(bar.open, bar.close) - bar.low);
   double wick_ratio = (bar.high > bar.low) ? (wick / (bar.high - bar.low)) : 1.0;
   if(wick_ratio > 0.35) return false;
   double bar_range = bar.high - bar.low;
   if(atr > 0.0 && (bar_range < 0.60 * atr || bar_range > 2.60 * atr)) return false;
   double dist = side > 0 ? (bar.close - range.high) : (range.low - bar.close);
   if(atr > 0.0 && dist > 1.80 * atr) return false;
   return true;
}

bool FvgConfirmed(const MqlRates &bars[], const int side)
{
   double low = 0, high = 0;
   return ActiveFVG(bars, side, low, high) && (high - low >= 0.20);
}

int CalculateBreakoutScore(const MqlRates &bar, const MqlRates &bars[], const Features &features,
                           const PriceRange &range, const int side)
{
   int score = 0;
   if(CandleQualityValid(bar, features.atr, range, side)) score += 25;
   else if(BodyRatio(bar) >= 0.40) score += 12;

   if(OpposingAsianSideSwept(bars, range, side)) score += 25;
   if(FvgConfirmed(bars, side)) score += 15;
   if(features.m15_break == side) score += 15;
   if(TrendAligned(features, side, 18.0)) score += 15;
   if(features.volume_ratio >= 1.15 && (bar.high - bar.low) >= 0.90 * features.atr) score += 10;
   return score;
}
#endif
