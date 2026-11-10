#ifndef GOLD_MARKET_REGIME_DETECTOR
#define GOLD_MARKET_REGIME_DETECTOR

enum MarketRegime {
   REGIME_UNCERTAIN = 0,
   REGIME_TRENDING = 1,
   REGIME_RANGING = 2,
   REGIME_HIGH_VOLATILITY = 3,
   REGIME_LOW_VOLATILITY = 4,
   REGIME_NEWS_DRIVEN = 5
};

string RegimeToString(const MarketRegime regime)
{
   switch(regime)
   {
      case REGIME_TRENDING:        return "TRENDING";
      case REGIME_RANGING:         return "RANGING";
      case REGIME_HIGH_VOLATILITY: return "HIGH_VOLATILITY";
      case REGIME_LOW_VOLATILITY:  return "LOW_VOLATILITY";
      case REGIME_NEWS_DRIVEN:     return "NEWS_DRIVEN";
      default:                     return "UNCERTAIN";
   }
}

MarketRegime DetectMarketRegime(const MqlRates &bars[], const Features &features, const int atr_handle)
{
   if(features.atr <= 0 || features.adx < 0) return REGIME_UNCERTAIN;
   
   // 1. Calculate ATR ratio relative to longer-term ATR (50 periods)
   double atr_long[10];
   double avg_atr = features.atr;
   if(CopyBuffer(atr_handle, 0, 5, 10, atr_long) == 10)
   {
      double sum = 0;
      for(int i = 0; i < 10; i++) sum += atr_long[i];
      avg_atr = sum / 10.0;
   }
   double atr_ratio = (avg_atr > 0) ? (features.atr / avg_atr) : 1.0;
   
   // 2. Check for News / Abnormal Momentum Spikes
   MqlRates cur = bars[0];
   double bar_range = cur.high - cur.low;
   if(features.volume_ratio >= 2.50 || bar_range >= 2.20 * features.atr)
   {
      return REGIME_NEWS_DRIVEN;
   }
   
   // 3. Check for Extreme Volatility
   if(atr_ratio >= 1.35)
   {
      return REGIME_HIGH_VOLATILITY;
   }
   if(atr_ratio <= 0.70)
   {
      return REGIME_LOW_VOLATILITY;
   }
   
   // 4. Check for Trending vs Ranging
   double dist_from_ema = MathAbs(features.hour_close - features.ema);
   if(features.adx >= 22.0 && dist_from_ema >= 1.0 * features.atr)
   {
      return REGIME_TRENDING;
   }
   if(features.adx < 18.0 && dist_from_ema < 1.0 * features.atr)
   {
      return REGIME_RANGING;
   }
   
   return REGIME_UNCERTAIN;
}

#endif
