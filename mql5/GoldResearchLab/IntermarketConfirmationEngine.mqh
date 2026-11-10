#ifndef GOLD_INTERMARKET_CONFIRMATION_ENGINE
#define GOLD_INTERMARKET_CONFIRMATION_ENGINE

struct IntermarketSignal {
   bool available;
   string proxy_symbol;
   double momentum;     // Positive = EURUSD rising (weak dollar), Negative = EURUSD falling (strong dollar)
   int confirms_gold;   // +1 if confirms Gold BUY, -1 if confirms Gold SELL, 0 if neutral
};

IntermarketSignal CheckIntermarketProxy(const datetime current_time, const int gold_side)
{
   IntermarketSignal sig = {};
   sig.available = false;
   sig.proxy_symbol = "EURUSD_o";
   sig.momentum = 0.0;
   sig.confirms_gold = 0;
   
   MqlRates eurusd_bars[];
   ArraySetAsSeries(eurusd_bars, true);
   
   // Check if EURUSD_o rates are synchronized in tester
   if(CopyRates(sig.proxy_symbol, PERIOD_M5, current_time, 4, eurusd_bars) >= 4)
   {
      sig.available = true;
      double change = eurusd_bars[0].close - eurusd_bars[3].close;
      sig.momentum = change;
      
      // EURUSD up = Dollar down -> Bullish Gold (+1)
      // EURUSD down = Dollar up -> Bearish Gold (-1)
      if(change > 0.0002) sig.confirms_gold = 1;
      else if(change < -0.0002) sig.confirms_gold = -1;
   }
   
   return sig;
}

#endif
