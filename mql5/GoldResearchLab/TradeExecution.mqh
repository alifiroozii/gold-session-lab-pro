#ifndef GOLD_TRADE_EXECUTION
#define GOLD_TRADE_EXECUTION
#include <Trade/Trade.mqh>

bool ResearchTester()
{
   return MQLInfoInteger(MQL_TESTER)!=0 && MQLInfoInteger(MQL_VISUAL_MODE)==0 &&
          MQLInfoInteger(MQL_FORWARD)==0;
}

bool SubmitResearchOrder(CTrade &trade,const Setup &setup,const TradePlan &plan)
{
   if(!ResearchTester()) return false;
   string label="GL_"+IntegerToString(setup.session);
   bool sent=setup.side>0
      ? trade.Buy(plan.lots,_Symbol,plan.entry,plan.stop,plan.target,label)
      : trade.Sell(plan.lots,_Symbol,plan.entry,plan.stop,plan.target,label);
   PrintFormat("GLAB|ORDER|%s|%u|%s|%.2f|%.8f|%.8f|%.8f|%.2f",
               label,trade.ResultRetcode(),trade.ResultRetcodeDescription(),
               plan.lots,plan.entry,plan.stop,plan.target,plan.risk);
   return sent && (trade.ResultRetcode()==TRADE_RETCODE_DONE ||
                   trade.ResultRetcode()==TRADE_RETCODE_DONE_PARTIAL);
}
#endif
