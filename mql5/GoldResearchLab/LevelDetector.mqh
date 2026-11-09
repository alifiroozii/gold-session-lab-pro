#ifndef GOLD_LEVEL_DETECTOR
#define GOLD_LEVEL_DETECTOR
#include "SessionEngine.mqh"

enum ReferenceKind { REF_ASIA_UTC, REF_ASIA_NY, REF_LONDON, REF_NY_OPEN, REF_PREV_DAY, REF_PREV_WEEK, REF_LONDON_UTC };
struct PriceRange { double low,high,open; };

bool ValidBar(const MqlRates &bar)
{
   return bar.time>0 && MathIsValidNumber(bar.high) && MathIsValidNumber(bar.low) &&
          bar.low>0 && bar.low<=MathMin(bar.open,bar.close) &&
          bar.high>=MathMax(bar.open,bar.close) && bar.tick_volume>0;
}

bool ReferenceWindow(const ReferenceKind kind,const datetime utc,datetime &start,datetime &end)
{
   datetime today=DayStart(utc);
   datetime ny=DayStart(utc+NYOffset(utc));
   datetime london=DayStart(utc+(EuropeSummer(utc)?3600:0));
   switch(kind)
   {
      case REF_ASIA_UTC: start=today; end=today+7*3600; break;
      case REF_ASIA_NY: start=NYToUTC(ny-4*3600); end=NYToUTC(ny); break;
      case REF_LONDON: start=LondonToUTC(london+8*3600); end=LondonToUTC(london+17*3600); break;
      case REF_LONDON_UTC: start=today+7*3600; end=today+13*3600; break;
      case REF_NY_OPEN: start=NYToUTC(ny+9*3600+1800); end=NYToUTC(ny+10*3600); break;
      default: return false;
   }
   return end<=utc;
}

bool ReadRange(const ReferenceKind kind,const datetime known_at,const BrokerClock clock,PriceRange &out)
{
   MqlRates bars[];
   if(kind==REF_PREV_DAY || kind==REF_PREV_WEEK)
   {
      ENUM_TIMEFRAMES period=kind==REF_PREV_DAY ? PERIOD_D1 : PERIOD_W1;
      if(CopyRates(_Symbol,period,1,1,bars)!=1 || !ValidBar(bars[0])) return false;
      out.low=bars[0].low;
      out.high=bars[0].high;
      out.open=bars[0].open;
      return true;
   }
   datetime start=0,end=0;
   if(!ReferenceWindow(kind,known_at,start,end)) return false;
   datetime first=start+ServerOffset(start,clock);
   datetime last=end+ServerOffset(end,clock);
   int expected=(int)((end-start)/300);
   int count=CopyRates(_Symbol,PERIOD_M5,first,last-1,bars);
   if(count<MathCeil(expected*0.80) || count>expected) return false;
   // Record a frozen range only when both edge bars are present.
   if(bars[0].time!=first || bars[count-1].time!=last-300) return false;
   out.low=DBL_MAX;
   out.high=0;
   out.open=bars[0].open;
   for(int i=0;i<count;i++)
   {
      if(!ValidBar(bars[i]) || (bars[i].time-first)%300!=0 ||
         (i>0 && bars[i].time<=bars[i-1].time)) return false;
      out.low=MathMin(out.low,bars[i].low);
      out.high=MathMax(out.high,bars[i].high);
   }
   return out.high>out.low;
}

#endif
