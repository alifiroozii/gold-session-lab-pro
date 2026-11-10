#ifndef GOLD_RESEARCH_LOGGER
#define GOLD_RESEARCH_LOGGER
void LogSetup(const string event,const Setup &setup,const datetime at)
{
   PrintFormat("GLAB|%s|%s|%s|%s|%d|%s",event,TimeToString(at,TIME_DATE|TIME_SECONDS),
               TimeToString(setup.observed,TIME_DATE|TIME_SECONDS),EnumToString(setup.session),
               setup.side,DoubleToString(setup.level,_Digits));
}
#endif
