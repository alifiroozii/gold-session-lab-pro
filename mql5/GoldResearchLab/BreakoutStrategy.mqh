#ifndef GOLD_BREAKOUT_STRATEGY
#define GOLD_BREAKOUT_STRATEGY
int BreakoutSide(const MqlRates &bar,const PriceRange &level)
{
   if(bar.close>level.high+0.10 && bar.close>bar.open) return 1;
   if(bar.close<level.low-0.10 && bar.close<bar.open) return -1;
   return 0;
}
#endif
