#property copyright "Gold Session Lab Pro"
#property version "1.00"
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

CTrade execution;
Setup pending={};
datetime processed=0;
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
      TradePlan plan={};
      if(BuildTradePlan(pending,tick,atr,ServerClock,plan)) SubmitResearchOrder(execution,pending,plan);
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
   if(Retested(bars[0],pending.level,pending.side))
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

   // A signal closing at the reference endpoint must open on or after that endpoint.
   PriceRange level={};
   if(!ReadRange(Reference,utc-300,ServerClock,level)) return;
   double width=level.high-level.low;
   if(width<2.0 || width>30.0) return;
   MqlRates bar=bars[0];
   int side=0;
   if(Strategy==STRATEGY_BREAKOUT) side=BreakoutSide(bar,level);
   if(Strategy==STRATEGY_SWEEP) side=SweepSide(bar,level);
   if(Strategy==STRATEGY_RANGE) side=RangeSide(bar,level,features.adx,features.atr);
   if(side==0) return;
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
   pending.stop=anchor-side*0.30;
   LogSetup(Strategy==STRATEGY_SWEEP ? "SWEEP_OBSERVED" :
            (Strategy==STRATEGY_BREAKOUT ? "BREAKOUT_CLOSED" : "RANGE_REJECTION"),pending,utc);

   if(Strategy==STRATEGY_SWEEP) pending.stage=SETUP_SWEEP;
   else if(Mode==MODE_CONSERVATIVE) pending.stage=SETUP_RETEST;
   else Emit(tick,utc,features.atr);
}

void OnTick()
{
   if(!ResearchTester()) return;
   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick)) return;
   datetime tick_utc=ServerToUTC(tick.time,ServerClock);
   if(!SignalAuditOnly) ManageResearchPosition(execution,tick_utc,ServerClock);

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
