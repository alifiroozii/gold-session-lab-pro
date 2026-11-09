#ifndef GOLD_RANGE_REVERSAL_STRATEGY
#define GOLD_RANGE_REVERSAL_STRATEGY
int RangeSide(const MqlRates &bar,const PriceRange &level,const double adx,const double atr)
{
   if(adx>=20 || bar.high-bar.low>1.5*atr || bar.close<=level.low || bar.close>=level.high)
      return 0;
   double edge=(level.high-level.low)*0.15;
   if(bar.high>=level.high-edge && RejectionWick(bar,-1)>=0.60) return -1;
   if(bar.low<=level.low+edge && RejectionWick(bar,1)>=0.60) return 1;
   return 0;
}
#endif
