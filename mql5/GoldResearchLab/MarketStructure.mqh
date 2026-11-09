#ifndef GOLD_MARKET_STRUCTURE
#define GOLD_MARKET_STRUCTURE

double BodyRatio(const MqlRates &bar)
{
   return bar.high>bar.low ? MathAbs(bar.close-bar.open)/(bar.high-bar.low) : 0;
}

double RejectionWick(const MqlRates &bar,const int side)
{
   if(bar.high<=bar.low) return 0;
   double wick=side>0 ? MathMin(bar.open,bar.close)-bar.low : bar.high-MathMax(bar.open,bar.close);
   return wick/(bar.high-bar.low);
}

double ConfirmedPivot(const MqlRates &bars[],const int side)
{
   // Series index 0 is the decision bar. It cannot confirm its own pivot.
   for(int i=4;i<ArraySize(bars)-3;i++)
   {
      bool pivot=true;
      for(int j=1;j<=3;j++)
      {
         if(side>0 && (bars[i].high<=bars[i-j].high || bars[i].high<=bars[i+j].high)) pivot=false;
         if(side<0 && (bars[i].low>=bars[i-j].low || bars[i].low>=bars[i+j].low)) pivot=false;
      }
      if(pivot) return side>0 ? bars[i].high : bars[i].low;
   }
   return 0;
}

bool ActiveFVG(const MqlRates &bars[],const int side,double &low,double &high)
{
   for(int i=0;i<6 && i+2<ArraySize(bars);i++)
   {
      low=side>0 ? bars[i+2].high : bars[i].high;
      high=side>0 ? bars[i].low : bars[i+2].low;
      if(high-low<0.20) continue;
      bool intact=true;
      for(int j=0;j<i;j++)
         if((side>0 && bars[j].low<=low) || (side<0 && bars[j].high>=high)) intact=false;
      if(intact) return true;
   }
   low=0;
   high=0;
   return false;
}

#endif
