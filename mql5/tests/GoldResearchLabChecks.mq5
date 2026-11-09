#property strict
#include "../GoldResearchLab/SessionEngine.mqh"
#include "../GoldResearchLab/LevelDetector.mqh"
#include "../GoldResearchLab/MarketStructure.mqh"
#include "../GoldResearchLab/BreakoutStrategy.mqh"
#include "../GoldResearchLab/SweepStrategy.mqh"
#include "../GoldResearchLab/RangeReversalStrategy.mqh"
#include "../GoldResearchLab/ConfirmationEngine.mqh"

int failures=0;
void Check(const bool result,const string label)
{
   if(result) return;
   failures++;
   Print("GLAB_CHECK|FAIL|",label);
}
int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER)) return INIT_FAILED;
   Check(LastSunday(2025,3)==D'2025.03.30 00:00', "last Sunday after January");
   Check(NYOffset(D'2025.03.09 06:59')==-18000 && NYOffset(D'2025.03.09 07:00')==-14400,"NY spring DST");
   Check(!EuropeSummer(D'2025.03.30 00:59') && EuropeSummer(D'2025.03.30 01:00'),"London spring DST");
   Check(ServerToUTC(D'2025.10.26 03:30',CLOCK_LITEFINANCE_EU)==0,"reject repeated broker hour");
   Check(ServerToUTC(D'2025.03.30 03:30',CLOCK_LITEFINANCE_EU)==0,"reject skipped broker hour");
   Check(SessionAt(D'2025.03.12 13:30')==SESSION_OVERLAP,"US/EU mismatch overlap");
   Check(SessionAt(D'2025.03.08 14:30')==SESSION_NONE,"Saturday exclusion");
   datetime start=0,end=0;
   Check(!ReferenceWindow(REF_LONDON,D'2025.03.12 14:00',start,end),"London not finalized at NY open");
   Check(ReferenceWindow(REF_ASIA_NY,D'2025.03.12 08:00',start,end) &&
         start==D'2025.03.12 00:00' && end==D'2025.03.12 04:00',"NY Asia endpoint");
   Check(!ReferenceWindow(REF_ASIA_UTC,D'2025.03.12 06:59',start,end) &&
          ReferenceWindow(REF_ASIA_UTC,D'2025.03.12 07:00',start,end),"UTC Asia finalization");

   PriceRange range={2700,2710,2705};
   MqlRates b={};
   b.open=2709; b.high=2713; b.low=2708; b.close=2712;
   Check(BreakoutSide(b,range)==1 && SweepSide(b,range)==-1 && !Reclaimed(b,range,-1),"close outside cannot reclaim");
   b.open=2712; b.close=2709;
   Check(BreakoutSide(b,range)==0 && Reclaimed(b,range,-1),"short reclaim inside");
   b.open=2709; b.high=2713; b.low=2708; b.close=2708.5;
   Check(RangeSide(b,range,19,4)==-1 && RangeSide(b,range,20,4)==0,"ADX gate");
   b.open=2711; b.high=2712; b.low=2709.9; b.close=2710.8;
   Check(Retested(b,2710,1) && !Retested(b,2700,1),"wick retest");

   MqlRates bars[10];
   for(int i=0;i<10;i++) { bars[i].high=2710; bars[i].low=2705; }
   bars[3].high=2720;
   Check(ConfirmedPivot(bars,1)==0,"decision cannot supply right confirmation");
   bars[3].high=2710;
   bars[4].high=2720;
   Check(ConfirmedPivot(bars,1)==2720,"pivot with 3 closed bars");
   bars[0].low=2711; bars[0].high=2713;
   double low=0,high=0;
   Check(ActiveFVG(bars,1,low,high) && low==2710 && high==2711,"three-bar FVG");
   Print("GLAB_CHECK|",failures==0 ? "PASS" : "FAIL","|failures=",failures);
   return failures==0 ? INIT_SUCCEEDED : INIT_FAILED;
}
double OnTester() { return failures==0 ? 1 : 0; }
void OnTick() {}
