#ifndef GOLD_POSITION_MANAGER
#define GOLD_POSITION_MANAGER

void ManageResearchPosition(CTrade &trade,const datetime utc,const BrokerClock clock)
{
   if(!ResearchTester() || utc<=0 || !PositionSelect(_Symbol) ||
      PositionGetInteger(POSITION_MAGIC)!=(long)LAB_MAGIC) return;
   datetime opened=ServerToUTC((datetime)PositionGetInteger(POSITION_TIME),clock);
   if(opened<=0 || utc<DayStart(opened)+21*3600) return;
   ulong ticket=(ulong)PositionGetInteger(POSITION_TICKET);
   trade.PositionClose(ticket);
   PrintFormat("GLAB|TIME_EXIT|%u|%s",trade.ResultRetcode(),trade.ResultRetcodeDescription());
}
#endif
