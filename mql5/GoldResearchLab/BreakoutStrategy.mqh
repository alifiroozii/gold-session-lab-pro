#ifndef GOLD_BREAKOUT_STRATEGY
#define GOLD_BREAKOUT_STRATEGY
#include "MarketStructure.mqh"

int BreakoutSide(const MqlRates &bar,const PriceRange &level)
{
   if(bar.close>level.high+0.10 && bar.close>bar.open) return 1;
   if(bar.close<level.low-0.10 && bar.close<bar.open) return -1;
   return 0;
}

int BreakoutSideEx(const MqlRates &bar,const MqlRates &prev_bar,const PriceRange &level,
                   const double atr,const bool require_fresh,const double min_body_ratio)
{
   int side=BreakoutSide(bar,level);
   if(side==0) return 0;
   if(min_body_ratio>0.0 && BodyRatio(bar)<min_body_ratio) return 0;
   if(require_fresh)
   {
      double tolerance=MathMax(0.25,0.35*atr);
      if(side>0 && prev_bar.close>level.high+tolerance) return 0;
      if(side<0 && prev_bar.close<level.low-tolerance) return 0;
      // Avoid exhausted giant spike bars (> 2.8 ATR) that immediately mean-revert
      if(atr>0.0 && (bar.high-bar.low)>2.8*atr) return 0;
   }
   return side;
}
#endif
