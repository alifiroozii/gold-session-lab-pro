#ifndef GOLD_CONFIRMATION_ENGINE
#define GOLD_CONFIRMATION_ENGINE

enum StrategyKind { STRATEGY_BREAKOUT, STRATEGY_SWEEP, STRATEGY_RANGE };
enum EntryMode { MODE_FAST, MODE_STANDARD, MODE_CONSERVATIVE };
enum SetupStage { SETUP_IDLE, SETUP_SWEEP, SETUP_STRUCTURE, SETUP_RETEST };
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

bool Retested(const MqlRates &bar,const double level,const int side)
{
   return bar.low<=level+0.25 && bar.high>=level-0.25 &&
          side*(bar.close-level)>0 && RejectionWick(bar,side)>=0.35;
}
#endif
