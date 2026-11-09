#ifndef GOLD_RISK_GUARDIAN
#define GOLD_RISK_GUARDIAN

const ulong LAB_MAGIC=4511726;
struct TradePlan { double entry,stop,target,lots,risk; };

double SnapPrice(const double value,const double tick_size,const bool up)
{
   double ticks=value/tick_size;
   return NormalizeDouble((up ? MathCeil(ticks-1e-9) : MathFloor(ticks+1e-9))*tick_size,_Digits);
}

bool DailyBudget(const datetime from,const datetime now,double &remaining,
                 const double risk_pct=0.03,const double day_loss_pct=0.06,const int max_entries=10)
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
   remaining=MathMin(risk_pct*equity,day_loss_pct*(balance-net)+MathMin(0,net));
   return entries<max_entries && remaining>0;
}

bool BuildTradePlan(const Setup &setup,const MqlTick &quote,const double atr,
                    const BrokerClock clock,TradePlan &plan,
                    const double risk_pct=0.03,const double day_loss_pct=0.06,
                    const int max_entries=10,const double min_stop_atr=0.0,
                    const double max_stop_atr=0.0,const double target_rr=1.5,
                    const double max_lot_cap=0.06,const double min_stop_bps=0.0,
                    const double max_stop_bps=0.0)
{
   int side=setup.side;
   double spread=quote.ask-quote.bid;
   double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(tick_size<=0 || step<=0 || quote.bid<=0 || spread<=0 || spread>0.80) return false;

   plan.entry=side>0 ? quote.ask : quote.bid;
   if(side*(plan.entry-setup.level)>0.50*atr) return false;

   plan.stop=SnapPrice(setup.stop,tick_size,side<0);
   double distance=side*(plan.entry-plan.stop);
   double min_dist=min_stop_atr>0.0 ? MathMax(1.50,min_stop_atr*atr) : 1.50;
   double max_dist=max_stop_atr>0.0 ? MathMax(9.0,max_stop_atr*atr) : 9.0;
   if(distance<min_dist || distance>max_dist || spread>0.15*distance) return false;
   if(min_stop_bps>0.0 && (distance/plan.entry*10000.0)<min_stop_bps) return false;
   if(max_stop_bps>0.0 && (distance/plan.entry*10000.0)>max_stop_bps) return false;

   double rr=(target_rr>0.0 ? target_rr : 1.5);
   double target=setup.target>0 ? setup.target : plan.entry+side*rr*distance;
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
   if(!DailyBudget(start+ServerOffset(start,clock),quote.time,budget,risk_pct,day_loss_pct,max_entries)) return false;
   ENUM_ORDER_TYPE type=side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double adverse=0;
   if(!OrderCalcProfit(type,_Symbol,1.0,plan.entry,plan.stop-side*0.20,adverse) ||
      !MathIsValidNumber(adverse) || adverse>=0) return false;
   double loss_per_lot=-adverse+10.0; // USD sizing reserve, separate from actual tester commissions.
   double cap=MathMin(max_lot_cap>0.0 ? max_lot_cap : 0.06,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   plan.lots=NormalizeDouble(MathFloor(MathMin(cap,budget/loss_per_lot)/step+1e-9)*step,8);
   if(plan.lots<=0 || plan.lots<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN)) return false;
   plan.risk=plan.lots*loss_per_lot;
   double margin=0;
   return plan.risk<=budget && OrderCalcMargin(type,_Symbol,plan.lots,plan.entry,margin) &&
          MathIsValidNumber(margin) && margin<=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
}
#endif
