#ifndef GOLD_SWEEP_STRATEGY
#define GOLD_SWEEP_STRATEGY
int SweepSide(const MqlRates &bar,const PriceRange &level)
{
   bool above=bar.high>level.high+0.10;
   bool below=bar.low<level.low-0.10;
   if(above==below) return 0;
   return below ? 1 : -1;
}
bool Reclaimed(const MqlRates &bar,const PriceRange &level,const int side)
{
   return bar.close>level.low && bar.close<level.high && side*(bar.close-bar.open)>0;
}
#endif
