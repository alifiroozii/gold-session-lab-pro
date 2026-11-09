#ifndef GOLD_POSITION_MANAGER
#define GOLD_POSITION_MANAGER

void ManageResearchPosition(CTrade &trade,const datetime utc,const BrokerClock clock,
                            const double break_even_rr=0.0,const double trail_rr=0.0)
{
   if(!ResearchTester() || utc<=0 || !PositionSelect(_Symbol) ||
      PositionGetInteger(POSITION_MAGIC)!=(long)LAB_MAGIC) return;
   datetime opened=ServerToUTC((datetime)PositionGetInteger(POSITION_TIME),clock);
   ulong ticket=(ulong)PositionGetInteger(POSITION_TICKET);
   if(opened>0 && utc>=DayStart(opened)+21*3600)
   {
      trade.PositionClose(ticket);
      PrintFormat("GLAB|TIME_EXIT|%u|%s",trade.ResultRetcode(),trade.ResultRetcodeDescription());
      return;
   }

   if(break_even_rr<=0.0 && trail_rr<=0.0) return;

   long pos_type=PositionGetInteger(POSITION_TYPE);
   int side=(pos_type==POSITION_TYPE_BUY) ? 1 : -1;
   double open_price=PositionGetDouble(POSITION_PRICE_OPEN);
   double cur_sl=PositionGetDouble(POSITION_SL);
   double cur_tp=PositionGetDouble(POSITION_TP);
   if(open_price<=0.0 || cur_sl<=0.0 || cur_tp<=0.0) return;

   double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tick_size<=0.0) return;

   // Infer 1R from TP distance or initial SL distance
   double tp_dist=side*(cur_tp-open_price);
   double sl_dist=side*(open_price-cur_sl);
   double one_r=(sl_dist>0.5 ? sl_dist : (tp_dist>0.5 ? tp_dist/2.0 : 0.0));
   if(one_r<=0.0) return;

   MqlTick quote={};
   if(!SymbolInfoTick(_Symbol,quote)) return;
   double price=(side>0) ? quote.bid : quote.ask;
   double profit_dist=side*(price-open_price);
   double min_stop=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;

   double new_sl=cur_sl;
   // Move to Break-Even (+0.15R lock) once profit reaches break_even_rr * 1R
   if(break_even_rr>0.0 && profit_dist>=break_even_rr*one_r)
   {
      double be_sl=SnapPrice(open_price+side*(0.15*one_r),tick_size,side<0);
      if(side*(be_sl-cur_sl)>tick_size) new_sl=be_sl;
   }
   // Trail stop if trail_rr > 0 and profit >= (break_even_rr + 0.5) * 1R
   if(trail_rr>0.0 && profit_dist>=(MathMax(break_even_rr,1.0)+0.4)*one_r)
   {
      double tr_sl=SnapPrice(price-side*(trail_rr*one_r),tick_size,side<0);
      if(side*(tr_sl-new_sl)>tick_size) new_sl=tr_sl;
   }

   if(side*(new_sl-cur_sl)>tick_size && side*(price-new_sl)>min_stop+tick_size)
   {
      trade.PositionModify(ticket,new_sl,cur_tp);
   }
}
#endif
