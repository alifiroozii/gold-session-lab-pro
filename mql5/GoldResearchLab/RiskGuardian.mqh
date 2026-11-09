#ifndef GOLD_RISK_GUARDIAN
#define GOLD_RISK_GUARDIAN

const ulong LAB_MAGIC=4511726;
struct TradePlan { double entry,stop,target,lots,risk; };

double SnapPrice(const double value,const double tick_size,const bool up)
{
   double ticks=value/tick_size;
   return NormalizeDouble((up ? MathCeil(ticks-1e-9) : MathFloor(ticks+1e-9))*tick_size,_Digits);
}

bool DailyBudget(const datetime from,const datetime now,double &remaining)
{
   if(!HistorySelect(from,now)) return false;
   double net=0;
   int entries=0;
   for(int i=0;i<HistoryDealsTotal();i++)
   {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) return false;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol ||
         HistoryDealGetInteger(deal,DEAL_MAGIC)!=(long)LAB_MAGIC) continue;
      if(HistoryDealGetInteger(deal,DEAL_ENTRY)==DEAL_ENTRY_IN) entries++;
      net+=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_SWAP)+
           HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_FEE);
   }
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   remaining=MathMin(0.03*equity,0.06*(balance-net)+MathMin(0,net));
   return entries<10 && remaining>0;
}

bool BuildTradePlan(const Setup &setup,const MqlTick &quote,const double atr,
                    const BrokerClock clock,TradePlan &plan)
{
   int side=setup.side;
   double spread=quote.ask-quote.bid;
   double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(tick_size<=0 || step<=0 || quote.bid<=0 || spread<=0 || spread>0.80) return false;

   plan.entry=side>0 ? quote.ask : quote.bid;
   if(side*(plan.entry-setup.level)>0.5*atr) return false;
   plan.stop=SnapPrice(setup.stop,tick_size,side<0);
   double distance=side*(plan.entry-plan.stop);
   if(distance<1.50 || distance>9.0 || spread>0.15*distance) return false;
   double target=setup.target>0 ? setup.target : plan.entry+side*1.5*distance;
   plan.target=SnapPrice(target,tick_size,side<0);
   double minimum_stop=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   double exit_quote=side>0 ? quote.bid : quote.ask;
   if(side*(exit_quote-plan.stop)<minimum_stop ||
      side*(plan.target-exit_quote)<minimum_stop ||
      side*(plan.target-plan.entry)<1.2*distance) return false;

   datetime utc=ServerToUTC(quote.time,clock);
   if(utc<=0) return false;
   datetime start=DayStart(utc);
   double budget=0;
   if(!DailyBudget(start+ServerOffset(start,clock),quote.time,budget)) return false;
   ENUM_ORDER_TYPE type=side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double adverse=0;
   if(!OrderCalcProfit(type,_Symbol,1.0,plan.entry,plan.stop-side*0.20,adverse) ||
      !MathIsValidNumber(adverse) || adverse>=0) return false;
   double loss_per_lot=-adverse+10.0; // USD sizing reserve, separate from actual tester commissions.
   double cap=MathMin(0.06,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   plan.lots=NormalizeDouble(MathFloor(MathMin(cap,budget/loss_per_lot)/step+1e-9)*step,8);
   if(plan.lots<=0 || plan.lots<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN)) return false;
   plan.risk=plan.lots*loss_per_lot;
   double margin=0;
   return plan.risk<=budget && OrderCalcMargin(type,_Symbol,plan.lots,plan.entry,margin) &&
          MathIsValidNumber(margin) && margin<=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
}
#endif
