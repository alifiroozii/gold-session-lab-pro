#ifndef GOLD_SESSION_ENGINE
#define GOLD_SESSION_ENGINE

enum BrokerClock { CLOCK_UNSPECIFIED, CLOCK_UTC, CLOCK_LITEFINANCE_EU };
enum LabSession { SESSION_NONE, SESSION_LONDON, SESSION_OVERLAP, SESSION_NY, SESSION_FRANKFURT };
enum EuropeWindowKind {
   EUROPE_ALL,            // 07:00 - 11:00 London (Frankfurt + London full)
   EUROPE_FRANKFURT_ONLY, // 07:00 - 08:00 London
   EUROPE_LONDON_08_09,   // 08:00 - 09:00 London (London Open Impulse)
   EUROPE_LONDON_09_10,   // 09:00 - 10:00 London
   EUROPE_LONDON_10_11,   // 10:00 - 11:00 London
   EUROPE_LONDON_ALL      // 08:00 - 11:00 London (London 3 hours)
};

datetime CalendarTime(const int year, const int month, const int day, const int hour=0)
{
   MqlDateTime parts={};
   parts.year=year;
   parts.mon=month;
   parts.day=day;
   parts.hour=hour;
   return StructToTime(parts);
}

datetime Sunday(const int year,const int month,const int occurrence)
{
   datetime first=CalendarTime(year,month,1);
   MqlDateTime parts={};
   TimeToStruct(first,parts);
   return first+((7-parts.day_of_week)%7+7*(occurrence-1))*86400;
}

datetime LastSunday(const int year,const int month)
{
   datetime last=CalendarTime(year,month+1,1)-86400;
   MqlDateTime parts={};
   TimeToStruct(last,parts);
   return last-parts.day_of_week*86400;
}

bool EuropeSummer(const datetime utc)
{
   MqlDateTime parts={};
   TimeToStruct(utc,parts);
   return utc>=LastSunday(parts.year,3)+3600 && utc<LastSunday(parts.year,10)+3600;
}

int NYOffset(const datetime utc)
{
   MqlDateTime parts={};
   TimeToStruct(utc,parts);
   bool summer=utc>=Sunday(parts.year,3,2)+7*3600 && utc<Sunday(parts.year,11,1)+6*3600;
   return summer ? -4*3600 : -5*3600;
}

int ServerOffset(const datetime utc,const BrokerClock clock)
{
   if(MQLInfoInteger(MQL_TESTER) == 0 && TimeGMT() > 0)
   {
      int diff = (int)(TimeCurrent() - TimeGMT());
      return (int)MathRound((double)diff / 3600.0) * 3600;
   }
   if(clock==CLOCK_LITEFINANCE_EU)
      return EuropeSummer(utc) ? 3*3600 : 2*3600;
   return 0;
}

datetime ServerToUTC(const datetime server,const BrokerClock clock)
{
   // In live or demo trading, automatically detect broker UTC offset from TimeGMT():
   if(MQLInfoInteger(MQL_TESTER) == 0 && TimeGMT() > 0)
   {
      int diff = (int)(TimeCurrent() - TimeGMT());
      int hours_offset = (int)MathRound((double)diff / 3600.0);
      return server - hours_offset * 3600;
   }

   if(clock==CLOCK_UTC) return server;
   if(clock!=CLOCK_LITEFINANCE_EU) return 0;
   datetime winter=server-2*3600, summer=server-3*3600;
   bool winter_valid=ServerOffset(winter,clock)==2*3600;
   bool summer_valid=ServerOffset(summer,clock)==3*3600;
   // Reject nonexistent and ambiguous local hours around the clock transition.
   if(winter_valid==summer_valid) return 0;
   return winter_valid ? winter : summer;
}

datetime DayStart(const datetime time) { return time-time%86400; }

datetime NYToUTC(const datetime local)
{
   // Used only for windows whose endpoints are outside the repeated/skipped hour.
   return local-NYOffset(local+5*3600);
}

datetime LondonToUTC(const datetime local)
{
   return local-(EuropeSummer(local) ? 3600 : 0);
}

LabSession SessionAt(const datetime utc)
{
   if(utc<=0) return SESSION_NONE;
   MqlDateTime day={};
   TimeToStruct(utc,day);
   if(day.day_of_week==0 || day.day_of_week==6) return SESSION_NONE;
   int london=(int)((utc+(EuropeSummer(utc)?3600:0))%86400)/60;
   int ny=(int)((utc+NYOffset(utc))%86400)/60;
   bool london_open=london>=8*60 && london<17*60;
   bool ny_open=ny>=9*60+30 && ny<15*60+30;
   if(london>=7*60 && london<8*60) return SESSION_FRANKFURT;
   if(london_open && ny_open) return SESSION_OVERLAP;
   if(ny_open) return SESSION_NY;
   if(london_open && london<12*60) return SESSION_LONDON;
   return SESSION_NONE;
}

#endif
