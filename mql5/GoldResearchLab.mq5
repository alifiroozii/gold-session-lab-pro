#property copyright "Gold Session Lab Pro"
#property version "1.10"
#property strict

#include "GoldResearchLab/SessionEngine.mqh"
#include "GoldResearchLab/LevelDetector.mqh"
#include "GoldResearchLab/MarketStructure.mqh"
#include "GoldResearchLab/BreakoutStrategy.mqh"
#include "GoldResearchLab/SweepStrategy.mqh"
#include "GoldResearchLab/RangeReversalStrategy.mqh"
#include "GoldResearchLab/ConfirmationEngine.mqh"
#include "GoldResearchLab/RiskGuardian.mqh"
#include "GoldResearchLab/ResearchLogger.mqh"
#include "GoldResearchLab/TradeExecution.mqh"
#include "GoldResearchLab/PositionManager.mqh"

input string ExpectedSymbol="XAUUSD_o";
input BrokerClock ServerClock=CLOCK_UNSPECIFIED;
input ReferenceKind Reference=REF_ASIA_UTC;
input StrategyKind Strategy=STRATEGY_BREAKOUT;
input EntryMode Mode=MODE_STANDARD;
input bool SignalAuditOnly=true;

// Challenger research parameters (defaults preserve 100% baseline behavior)
input double MaxRangeWidth=30.0;
input double MaxRangeATR=0.0;
input bool OneTradePerSidePerDay=false;
input bool RequireFreshBreakout=false;
input double MinBreakoutBodyRatio=0.0;
input bool RequireH1Trend=false;
input double MinH1ADX=0.0;
input double RiskPerTradePct=3.0;
input double DailyLossLimitPct=6.0;
input int MaxTradesPerDay=10;
input double MinStopATR=0.0;
input double MaxStopATR=0.0;
input double StopBufferATR=0.0;
input double TargetRR=1.5;
input double BreakEvenRR=0.0;
input double TrailRR=0.0;
input double MaxLotCap=0.06;
input bool SkipLondonLateNY=false;
input bool SkipOverlap=false;
input bool SkipNY=false;
input int DynamicSessionRef=0;
input double MinStopBps=0.0;
input double MaxStopBps=0.0;
input double MaxRangeBps=0.0;
input bool SkipWhipsawHours=false;
input ConfirmationMethod Confirmation=CONFIRM_METHOD_NONE;
input EuropeWindowKind EuropeWindow=EUROPE_ALL;
input bool EuropeOnly=false;
input int MinConfidenceScore=0;

CTrade execution;
Setup pending={};
datetime processed=0;
datetime traded_long_day=0;
datetime traded_short_day=0;
int atr_handle=INVALID_HANDLE,ema_handle=INVALID_HANDLE,adx_handle=INVALID_HANDLE;

int OnInit()
{
   if(!ResearchTester()) return INIT_FAILED;
   if(ServerClock==CLOCK_UNSPECIFIED || _Period!=PERIOD_M5 || _Symbol!=ExpectedSymbol ||
      AccountInfoString(ACCOUNT_CURRENCY)!="USD") return INIT_PARAMETERS_INCORRECT;

   atr_handle=iATR(_Symbol,PERIOD_M5,14);
   ema_handle=iMA(_Symbol,PERIOD_H1,50,0,MODE_EMA,PRICE_CLOSE);
   adx_handle=iADXWilder(_Symbol,PERIOD_H1,14);
   if(atr_handle==INVALID_HANDLE || ema_handle==INVALID_HANDLE || adx_handle==INVALID_HANDLE)
      return INIT_FAILED;
   execution.SetExpertMagicNumber(LAB_MAGIC);
   execution.SetDeviationInPoints((ulong)MathFloor(0.10/_Point));
   if(!execution.SetTypeFillingBySymbol(_Symbol)) return INIT_FAILED;

   PrintFormat("GLAB|INIT|%s|%s|%s|%s|%s|contract=%.8f|tick_size=%.8f|tick_value=%.8f|volume_min=%.8f|volume_step=%.8f|volume_max=%.8f|stops=%d|digits=%d|audit=%d",
               _Symbol,EnumToString(ServerClock),EnumToString(Reference),EnumToString(Strategy),EnumToString(Mode),
               SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE),SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),
               SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE),SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),
               SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP),SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),
               (int)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL),_Digits,(int)SignalAuditOnly);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(atr_handle!=INVALID_HANDLE) IndicatorRelease(atr_handle);
   if(ema_handle!=INVALID_HANDLE) IndicatorRelease(ema_handle);
   if(adx_handle!=INVALID_HANDLE) IndicatorRelease(adx_handle);
}

double OnTester()
{
   double net=TesterStatistics(STAT_PROFIT);
   double pf=TesterStatistics(STAT_PROFIT_FACTOR);
   double dd=TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   double trades=TesterStatistics(STAT_TRADES);
   PrintFormat("GLAB|SUMMARY|trades=%.0f|net=%.2f|pf=%.2f|dd=%.2f",trades,net,pf,dd);
   return net;
}

bool FeatureAt(const MqlRates &bars[],const datetime server_open,Features &out)
{
   double atr[1],ema[1],adx[1];
   MqlRates hour[1],structure[];
   ArraySetAsSeries(structure,true);
   if(CopyBuffer(atr_handle,0,2,1,atr)!=1 || CopyBuffer(ema_handle,0,1,1,ema)!=1 ||
      CopyBuffer(adx_handle,0,1,1,adx)!=1 || CopyRates(_Symbol,PERIOD_H1,1,1,hour)!=1 ||
      CopyRates(_Symbol,PERIOD_M15,1,4,structure)!=4) return false;
   if(atr[0]<=0 || ema[0]<=0 || adx[0]<0 || adx[0]>100 ||
      atr[0]==EMPTY_VALUE || ema[0]==EMPTY_VALUE ||
      !MathIsValidNumber(atr[0]) || !MathIsValidNumber(ema[0]) || !MathIsValidNumber(adx[0]) ||
      hour[0].time+3600>server_open || structure[0].time+900>server_open ||
      !ValidBar(hour[0])) return false;
   for(int i=0;i<4;i++) if(!ValidBar(structure[i])) return false;
   out.atr=atr[0];
   out.ema=ema[0];
   out.adx=adx[0];
   out.hour_close=hour[0].close;
   double high=structure[1].high,low=structure[1].low,volume=0;
   for(int i=2;i<4;i++)
   {
      high=MathMax(high,structure[i].high);
      low=MathMin(low,structure[i].low);
   }
   out.m15_break=structure[0].close>high ? 1 : (structure[0].close<low ? -1 : 0);
   for(int i=1;i<=20;i++) volume+=(double)bars[i].tick_volume;
   out.volume_ratio=20.0*(double)bars[0].tick_volume/volume;
   return true;
}

void ClearSetup() { ZeroMemory(pending); }

void Emit(const MqlTick &tick,const datetime utc,const double atr)
{
   LogSetup("ENTRY_READY",pending,utc);
   if(!SignalAuditOnly && !PositionSelect(_Symbol))
   {
      datetime today=DayStart(utc);
      if(OneTradePerSidePerDay)
      {
         if(pending.side>0 && traded_long_day==today) { ClearSetup(); return; }
         if(pending.side<0 && traded_short_day==today) { ClearSetup(); return; }
      }
      TradePlan plan={};
      if(BuildTradePlan(pending,tick,atr,ServerClock,plan,
                        RiskPerTradePct/100.0,DailyLossLimitPct/100.0,MaxTradesPerDay,
                        MinStopATR,MaxStopATR,TargetRR,MaxLotCap,MinStopBps,MaxStopBps))
      {
         if(SubmitResearchOrder(execution,pending,plan))
         {
            if(pending.side>0) traded_long_day=today;
            if(pending.side<0) traded_short_day=today;
         }
      }
      else LogSetup("RISK_REJECTED",pending,utc);
   }
   ClearSetup();
}

void ContinueSetup(const MqlRates &bars[],const Features &features,const MqlTick &tick,
                   const datetime utc,const LabSession session)
{
   if(utc-pending.observed>25*60 || session!=pending.session)
   {
      LogSetup("EXPIRED",pending,utc);
      ClearSetup();
      return;
   }
   if(pending.side*(bars[0].close-pending.stop)<=0)
   {
      LogSetup("INVALIDATED",pending,utc);
      ClearSetup();
      return;
   }
   if(pending.stage==SETUP_NEXT_CANDLE)
   {
      int side=pending.side;
      bool confirmed=(side>0) ? (bars[0].close>bars[1].close && bars[0].close>bars[0].open)
                              : (bars[0].close<bars[1].close && bars[0].close<bars[0].open);
      if(confirmed)
      {
         LogSetup("NEXT_CANDLE_CONFIRMED",pending,utc);
         Emit(tick,utc,features.atr);
      }
      else
      {
         LogSetup("NEXT_CANDLE_FAILED",pending,utc);
         ClearSetup();
      }
      return;
   }
   if(pending.stage==SETUP_SWEEP)
   {
      if(utc-pending.observed!=300 || !Reclaimed(bars[0],pending.range,pending.side) ||
         (Mode!=MODE_FAST && ConfirmationCount(bars[0],bars,features,pending.side)<2))
      {
         LogSetup("SWEEP_REJECTED",pending,utc);
         ClearSetup();
         return;
      }
      LogSetup("RECLAIMED",pending,utc);
      if(Mode==MODE_CONSERVATIVE)
         pending.stage=SETUP_STRUCTURE;
      else
         Emit(tick,utc,features.atr);
      return;
   }
   if(pending.stage==SETUP_STRUCTURE)
   {
      int side=pending.side;
      if(side*(bars[0].close-pending.pivot)>0 && side*(bars[1].close-pending.pivot)<=0)
      {
         pending.level=pending.pivot;
         pending.stage=SETUP_RETEST;
         LogSetup("BOS_CONFIRMED",pending,utc);
      }
      return;
   }
   if(Strategy==STRATEGY_RANGE && (features.adx>=20 || bars[0].high-bars[0].low>1.5*features.atr))
   {
      LogSetup("REGIME_CHANGED",pending,utc);
      ClearSetup();
      return;
   }
   bool retested=(MaxStopATR>0.0) ? RetestedEx(bars[0],pending.level,pending.side,features.atr)
                                  : Retested(bars[0],pending.level,pending.side);
   if(retested)
   {
      LogSetup("RETESTED",pending,utc);
      Emit(tick,utc,features.atr);
   }
}

void EvaluateBar(const MqlRates &bars[],const Features &features,const MqlTick &tick,
                 const datetime utc,const LabSession session)
{
   if(pending.stage!=SETUP_IDLE)
   {
      ContinueSetup(bars,features,tick,utc,session);
      return;
   }

   if(SkipLondonLateNY && session==SESSION_LONDON) return;
   if(SkipOverlap && session==SESSION_OVERLAP) return;
   if(SkipNY && session==SESSION_NY) return;
   if(EuropeOnly)
   {
      int london_min=(int)(((utc+(EuropeSummer(utc)?3600:0))%86400)/60);
      if(session!=SESSION_FRANKFURT && session!=SESSION_LONDON) return;
      if(EuropeWindow==EUROPE_FRANKFURT_ONLY && (london_min<7*60 || london_min>=8*60)) return;
      if(EuropeWindow==EUROPE_LONDON_08_09 && (london_min<8*60 || london_min>=9*60)) return;
      if(EuropeWindow==EUROPE_LONDON_09_10 && (london_min<9*60 || london_min>=10*60)) return;
      if(EuropeWindow==EUROPE_LONDON_10_11 && (london_min<10*60 || london_min>=11*60)) return;
      if(EuropeWindow==EUROPE_LONDON_ALL && (london_min<8*60 || london_min>=11*60)) return;
      if(EuropeWindow==EUROPE_ALL && (london_min<7*60 || london_min>=11*60)) return;
   }
   if(SkipWhipsawHours)
   {
      int london_hr=(int)(((utc+(EuropeSummer(utc)?3600:0))%86400)/3600);
      int ny_hr=(int)(((utc+NYOffset(utc))%86400)/3600);
      if(london_hr==9 || london_hr==11 || ny_hr==11 || ny_hr==13) return;
      if(DynamicSessionRef>=5 && DynamicSessionRef<=7 && ny_hr==12) return;
   }

   // A signal closing at the reference endpoint must open on or after that endpoint.
   ReferenceKind active_ref=Reference;
   if(DynamicSessionRef==1 && (session==SESSION_OVERLAP || session==SESSION_NY))
      active_ref=REF_LONDON_UTC;
   else if(DynamicSessionRef==2 && session==SESSION_NY)
      active_ref=REF_LONDON;
   else if(DynamicSessionRef==3 && (session==SESSION_OVERLAP || session==SESSION_NY))
      active_ref=REF_NY_OPEN;

   PriceRange level={};
   if(!ReadRange(active_ref,utc-300,ServerClock,level)) return;
   double width=level.high-level.low;
   double max_width=(MaxRangeATR>0.0) ? MathMax(MaxRangeWidth,MaxRangeATR*features.atr) : MaxRangeWidth;
   if(MaxRangeBps>0.0 && level.open>0.0)
      max_width=MathMax(max_width,level.open*MaxRangeBps/10000.0);
   if(width<2.0 || width>max_width) return;

   MqlRates bar=bars[0];
   bool use_fresh=(RequireFreshBreakout || (DynamicSessionRef==4 && session!=SESSION_LONDON));
   double use_body=(MinBreakoutBodyRatio>0.0 ? MinBreakoutBodyRatio : (DynamicSessionRef==4 && session!=SESSION_LONDON ? 0.40 : 0.0));
   int side=0;
   if(Strategy==STRATEGY_BREAKOUT)
      side=BreakoutSideEx(bar,bars[1],level,features.atr,use_fresh,use_body);
   if(Strategy==STRATEGY_SWEEP) side=SweepSide(bar,level);
   if(Strategy==STRATEGY_RANGE) side=RangeSide(bar,level,features.adx,features.atr);
   if(side==0) return;

   if(DynamicSessionRef>=5 && DynamicSessionRef<=7 && side<0 && session!=SESSION_LONDON)
   {
      if(!TrendAligned(features,-1,20.0) || BreakoutSideEx(bar,bars[1],level,features.atr,true,0.45)>=0)
         return;
      if(DynamicSessionRef==7 && ConfirmationCount(bar,bars,features,-1)<2)
         return;
   }
   if(DynamicSessionRef==6 || DynamicSessionRef==8 || DynamicSessionRef==10)
   {
      int london_hr=(int)(((utc+(EuropeSummer(utc)?3600:0))%86400)/3600);
      if(session==SESSION_LONDON && london_hr==10 && (!TrendAligned(features,side,20.0) || BodyRatio(bar)<0.45))
         return;
   }
   if((DynamicSessionRef==8 || DynamicSessionRef==10) && session==SESSION_OVERLAP && side<0 && !TrendAligned(features,-1,0.0) && features.m15_break!=-1)
      return;
   if(DynamicSessionRef==10)
   {
      double raw_sl=(bar.high-bar.low)+0.30;
      double est_bps=(bar.close>0.0) ? (raw_sl/bar.close*10000.0) : 0.0;
      if(est_bps>15.0 && (BodyRatio(bar)<0.60 || !TrendAligned(features,side,20.0)))
         return;
   }
   if(DynamicSessionRef==9)
   {
      int london_hr=(int)(((utc+(EuropeSummer(utc)?3600:0))%86400)/3600);
      if(session==SESSION_LONDON && london_hr==10) return;
      if(session==SESSION_OVERLAP && side<0 && !TrendAligned(features,-1,0.0)) return;
   }

   bool use_trend=(RequireH1Trend || MinH1ADX>0.0 || (DynamicSessionRef==4 && session!=SESSION_LONDON));
   if(use_trend && !TrendAligned(features,side,MinH1ADX)) return;

   if(Confirmation==CONFIRM_METHOD_A_CANDLE_QUALITY)
   {
      if(!CandleQualityValid(bar,features.atr,level,side)) return;
   }
   else if(Confirmation==CONFIRM_METHOD_D_FVG)
   {
      if(!FvgConfirmed(bars,side)) return;
   }
   else if(Confirmation==CONFIRM_METHOD_E_M15_BOS)
   {
      if(features.m15_break!=side) return;
   }
   else if(Confirmation==CONFIRM_METHOD_F_LIQUIDITY_SWEEP)
   {
      if(!OpposingAsianSideSwept(bars,level,side)) return;
   }
   else if(Confirmation==CONFIRM_METHOD_G_H1_TREND)
   {
      if(!TrendAligned(features,side,18.0)) return;
   }
   else if(Confirmation==CONFIRM_METHOD_H_MOMENTUM_VOL)
   {
      if(features.volume_ratio<1.15 || (bar.high-bar.low)<0.90*features.atr || BodyRatio(bar)<0.45) return;
   }
   else if(Confirmation==CONFIRM_COMBO_RETEST_FVG)
   {
      if(!FvgConfirmed(bars,side)) return;
   }
   else if(Confirmation==CONFIRM_COMBO_FVG_BOS)
   {
      if(!FvgConfirmed(bars,side) || features.m15_break!=side) return;
   }
   else if(Confirmation==CONFIRM_COMBO_SWEEP_BOS)
   {
      if(!OpposingAsianSideSwept(bars,level,side) || features.m15_break!=side) return;
   }
   else if(Confirmation==CONFIRM_COMBO_QUALITY_SCORE)
   {
      int score=CalculateBreakoutScore(bar,bars,features,level,side);
      int min_sc=(MinConfidenceScore>0 ? MinConfidenceScore : 50);
      if(score<min_sc) return;
   }

   double pivot=Strategy==STRATEGY_SWEEP && Mode==MODE_CONSERVATIVE ? ConfirmedPivot(bars,side) : 0;
   if(Strategy==STRATEGY_SWEEP && Mode==MODE_CONSERVATIVE &&
      (pivot<=0 || side*(bar.close-pivot)>=0)) return;
   if(Mode!=MODE_FAST && Strategy!=STRATEGY_SWEEP &&
      ConfirmationCount(bar,bars,features,side)<2) return;

   pending.observed=utc;
   pending.session=session;
   pending.range=level;
   pending.side=side;
   pending.pivot=pivot;
   bool upper=Strategy==STRATEGY_BREAKOUT ? side>0 : side<0;
   pending.level=upper ? level.high : level.low;
   double anchor=side>0 ? bar.low : bar.high;
   if(Strategy==STRATEGY_RANGE)
   {
      pending.level+=side*width*0.15;
      pending.target=(level.high+level.low)/2.0;
      anchor=side>0 ? MathMin(anchor,level.low) : MathMax(anchor,level.high);
   }
   double stop_buf=(StopBufferATR>0.0) ? MathMax(0.30,StopBufferATR*features.atr) : 0.30;
   pending.stop=anchor-side*stop_buf;
   LogSetup(Strategy==STRATEGY_SWEEP ? "SWEEP_OBSERVED" :
            (Strategy==STRATEGY_BREAKOUT ? "BREAKOUT_CLOSED" : "RANGE_REJECTION"),pending,utc);

   if(Strategy==STRATEGY_SWEEP) pending.stage=SETUP_SWEEP;
   else if(Confirmation==CONFIRM_METHOD_B_NEXT_CANDLE) pending.stage=SETUP_NEXT_CANDLE;
   else if(Confirmation==CONFIRM_METHOD_C_RETEST || Confirmation==CONFIRM_COMBO_RETEST_FVG || Mode==MODE_CONSERVATIVE) pending.stage=SETUP_RETEST;
   else Emit(tick,utc,features.atr);
}

void OnTick()
{
   if(!ResearchTester()) return;
   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick)) return;
   datetime tick_utc=ServerToUTC(tick.time,ServerClock);
   if(!SignalAuditOnly) ManageResearchPosition(execution,tick_utc,ServerClock,BreakEvenRR,TrailRR);

   datetime current=iTime(_Symbol,PERIOD_M5,0);
   if(current<=processed) return;
   // Claim the bar before evaluation. Startup and quote gaps cannot submit a late entry.
   processed=current;
   datetime utc=ServerToUTC(current,ServerClock);
   LabSession session=SessionAt(utc);
   if(session==SESSION_NONE || SessionAt(utc-300)!=session ||
      tick.time<current || tick.time-current>30 || utc<=0)
   {
      if(pending.stage!=SETUP_IDLE) LogSetup("WINDOW_OR_GAP",pending,utc);
      ClearSetup();
      return;
   }
   MqlRates bars[];
   ArraySetAsSeries(bars,true);
   if(CopyRates(_Symbol,PERIOD_M5,1,32,bars)!=32 || bars[0].time!=current-300)
   {
      ClearSetup();
      return;
   }
   for(int i=0;i<32;i++)
   {
      if(!ValidBar(bars[i]) || bars[i].time!=current-(i+1)*300)
      {
         ClearSetup();
         return;
      }
   }
   Features features={};
   if(!FeatureAt(bars,current,features))
   {
      ClearSetup();
      return;
   }
   EvaluateBar(bars,features,tick,utc,session);
}
