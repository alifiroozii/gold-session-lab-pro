#ifndef GOLD_CHART_VISUALIZER
#define GOLD_CHART_VISUALIZER

#include "SessionEngine.mqh"
#include "LevelDetector.mqh"

#define VIS_PREFIX "GSLP_"

datetime UTCToServer(const datetime utc, const BrokerClock clock)
{
   return utc + ServerOffset(utc, clock);
}


struct DiagnosticTelemetry
{
   datetime current_time_srv;
   datetime current_time_utc;
   string   session_phase;
   string   day_filter_status;
   bool     in_window;
   string   window_status;
   double   asian_high;
   double   asian_low;
   double   asian_width;
   bool     range_valid;
   int      breakout_side;
   double   current_bid;
   double   current_ask;
   double   candle_strength;
   bool     candle_strength_ok;
   int      bos_m15;
   double   fvg_gap_size;
   bool     fvg_ok;
   double   volume_ratio;
   bool     volume_ok;
   double   atr_ratio;
   bool     atr_ok;
   string   decision_summary;
   string   reason_detail;
   string   reason_persian;
   color    status_color;
};

class CChartVisualizer
{
private:
   long m_chart_id;
   color m_asian_color;
   color m_london_color;
   color m_hud_bg;
   color m_hud_border;
   
   void CreateOrUpdateRect(const string name, const datetime t1, const double p1,
                           const datetime t2, const double p2, const color clr,
                           const int width=1, const ENUM_LINE_STYLE style=STYLE_SOLID, const bool fill=true)
   {
      if(ObjectFind(m_chart_id, name) < 0)
      {
         ObjectCreate(m_chart_id, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
      }
      else
      {
         ObjectSetInteger(m_chart_id, name, OBJPROP_TIME, 0, t1);
         ObjectSetDouble(m_chart_id, name, OBJPROP_PRICE, 0, p1);
         ObjectSetInteger(m_chart_id, name, OBJPROP_TIME, 1, t2);
         ObjectSetDouble(m_chart_id, name, OBJPROP_PRICE, 1, p2);
      }
      ObjectSetInteger(m_chart_id, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(m_chart_id, name, OBJPROP_WIDTH, width);
      ObjectSetInteger(m_chart_id, name, OBJPROP_STYLE, style);
      ObjectSetInteger(m_chart_id, name, OBJPROP_FILL, fill);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BACK, true);
      ObjectSetInteger(m_chart_id, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_HIDDEN, true);
   }

   void CreateOrUpdateTrend(const string name, const datetime t1, const double p1,
                            const datetime t2, const double p2, const color clr,
                            const int width=2, const ENUM_LINE_STYLE style=STYLE_SOLID, const bool ray=false)
   {
      if(ObjectFind(m_chart_id, name) < 0)
      {
         ObjectCreate(m_chart_id, name, OBJ_TREND, 0, t1, p1, t2, p2);
      }
      else
      {
         ObjectSetInteger(m_chart_id, name, OBJPROP_TIME, 0, t1);
         ObjectSetDouble(m_chart_id, name, OBJPROP_PRICE, 0, p1);
         ObjectSetInteger(m_chart_id, name, OBJPROP_TIME, 1, t2);
         ObjectSetDouble(m_chart_id, name, OBJPROP_PRICE, 1, p2);
      }
      ObjectSetInteger(m_chart_id, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(m_chart_id, name, OBJPROP_WIDTH, width);
      ObjectSetInteger(m_chart_id, name, OBJPROP_STYLE, style);
      ObjectSetInteger(m_chart_id, name, OBJPROP_RAY_RIGHT, ray);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BACK, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_HIDDEN, true);
   }

   void CreateOrUpdateText(const string name, const datetime t, const double p,
                           const string text, const color clr, const int font_sz=9,
                           const string font_nm="Trebuchet MS", const ENUM_ANCHOR_POINT anchor=ANCHOR_LEFT_LOWER)
   {
      if(ObjectFind(m_chart_id, name) < 0)
      {
         ObjectCreate(m_chart_id, name, OBJ_TEXT, 0, t, p);
      }
      else
      {
         ObjectSetInteger(m_chart_id, name, OBJPROP_TIME, 0, t);
         ObjectSetDouble(m_chart_id, name, OBJPROP_PRICE, 0, p);
      }
      ObjectSetString(m_chart_id, name, OBJPROP_TEXT, text);
      ObjectSetString(m_chart_id, name, OBJPROP_FONT, font_nm);
      ObjectSetInteger(m_chart_id, name, OBJPROP_FONTSIZE, font_sz);
      ObjectSetInteger(m_chart_id, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(m_chart_id, name, OBJPROP_ANCHOR, anchor);
      ObjectSetInteger(m_chart_id, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_HIDDEN, true);
   }

   void CreateOrUpdateLabel(const string name, const int x, const int y,
                            const string text, const color clr, const int font_sz=9,
                            const string font_nm="Trebuchet MS",
                            const ENUM_BASE_CORNER corner=CORNER_LEFT_UPPER,
                            const ENUM_ANCHOR_POINT anchor=ANCHOR_LEFT_UPPER)
   {
      if(ObjectFind(m_chart_id, name) < 0)
      {
         ObjectCreate(m_chart_id, name, OBJ_LABEL, 0, 0, 0);
      }
      ObjectSetInteger(m_chart_id, name, OBJPROP_CORNER, corner);
      ObjectSetInteger(m_chart_id, name, OBJPROP_ANCHOR, anchor);
      ObjectSetInteger(m_chart_id, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(m_chart_id, name, OBJPROP_YDISTANCE, y);
      ObjectSetString(m_chart_id, name, OBJPROP_TEXT, text);
      ObjectSetString(m_chart_id, name, OBJPROP_FONT, font_nm);
      ObjectSetInteger(m_chart_id, name, OBJPROP_FONTSIZE, font_sz);
      ObjectSetInteger(m_chart_id, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BACK, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_HIDDEN, true);
   }

   void CreateOrUpdatePanel(const string name, const int x, const int y,
                            const int w, const int h, const color bg_clr, const color border_clr,
                            const ENUM_BASE_CORNER corner=CORNER_LEFT_UPPER)
   {
      if(ObjectFind(m_chart_id, name) < 0)
      {
         ObjectCreate(m_chart_id, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      }
      ObjectSetInteger(m_chart_id, name, OBJPROP_CORNER, corner);
      ObjectSetInteger(m_chart_id, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(m_chart_id, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(m_chart_id, name, OBJPROP_XSIZE, w);
      ObjectSetInteger(m_chart_id, name, OBJPROP_YSIZE, h);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BGCOLOR, bg_clr);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BORDER_COLOR, border_clr);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(m_chart_id, name, OBJPROP_BACK, true);
      ObjectSetInteger(m_chart_id, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart_id, name, OBJPROP_HIDDEN, true);
   }

public:
   CChartVisualizer(long chart_id=0)
   {
      m_chart_id = chart_id;
      m_asian_color = C'20,38,68';
      m_london_color = C'80,60,20';
      m_hud_bg = C'12,18,28';
      m_hud_border = C'35,55,85';
   }

   void SetupChartEnvironment()
   {
      ChartSetInteger(m_chart_id, CHART_BRING_TO_TOP, true);
      ChartSetInteger(m_chart_id, CHART_MODE, CHART_CANDLES);
      ChartSetInteger(m_chart_id, CHART_COLOR_BACKGROUND, C'10,14,20');
      ChartSetInteger(m_chart_id, CHART_COLOR_FOREGROUND, C'200,210,225');
      ChartSetInteger(m_chart_id, CHART_COLOR_GRID, C'22,30,42');
      ChartSetInteger(m_chart_id, CHART_COLOR_CANDLE_BULL, C'40,180,100');
      ChartSetInteger(m_chart_id, CHART_COLOR_CANDLE_BEAR, C'235,70,80');
      ChartSetInteger(m_chart_id, CHART_COLOR_CHART_UP, C'40,180,100');
      ChartSetInteger(m_chart_id, CHART_COLOR_CHART_DOWN, C'235,70,80');
      ChartSetInteger(m_chart_id, CHART_SHOW_GRID, true);
      ChartSetInteger(m_chart_id, CHART_SHIFT, true);
      ChartSetDouble(m_chart_id, CHART_SHIFT_SIZE, 18.0);
      ChartSetInteger(m_chart_id, CHART_AUTOSCROLL, true);
      ChartRedraw(m_chart_id);
   }

   void DrawSessions(const datetime current_srv, const BrokerClock clock)
   {
      datetime current_utc = ServerToUTC(current_srv, clock);
      datetime today_start_utc = (current_utc / 86400) * 86400;

      int london_min = (int)(((current_utc + (EuropeSummer(current_utc)?3600:0)) % 86400) / 60);
      bool is_london_today = (london_min >= 8*60 && london_min < 11*60);

      // Render recent 3 days of session boxes
      for(int d = 2; d >= 0; d--)
      {
         datetime eval_utc = current_utc - d * 86400;
         datetime day_start_utc = (eval_utc / 86400) * 86400;
         datetime eval_srv = UTCToServer(eval_utc, clock);

         PriceRange range={0,0,0};
         if(!ReadRange(REF_ASIA_NY, eval_srv, clock, range))
         {
            if(!ReadRange(REF_ASIA_UTC, eval_srv, clock, range)) continue;
         }

         if(range.high <= range.low) continue;

         datetime asia_start_srv   = UTCToServer(day_start_utc + 0 * 3600, clock);
         datetime asia_end_srv     = UTCToServer(day_start_utc + 6 * 3600, clock);
         datetime london_start_srv = UTCToServer(day_start_utc + 8 * 3600, clock);
         datetime london_end_srv   = UTCToServer(day_start_utc + 10 * 3600, clock);
         datetime eod_srv          = UTCToServer(day_start_utc + 21 * 3600, clock);

         double range_w = range.high - range.low;
         string suffix = StringFormat("_D%d", d);

         // 1. Asian Session Box
         string asia_box = VIS_PREFIX + "ASIA_BOX" + suffix;
         color box_clr = (d == 0 ? C'20,38,68' : C'16,26,42');
         CreateOrUpdateRect(asia_box, asia_start_srv, range.high, asia_end_srv, range.low, box_clr, 1, STYLE_SOLID, true);

         // 2. High / Low Reference Lines
         string hi_line = VIS_PREFIX + "ASIA_HI" + suffix;
         CreateOrUpdateTrend(hi_line, asia_start_srv, range.high, eod_srv, range.high, (d == 0 ? clrDodgerBlue : C'50,90,140'), (d == 0 ? 2 : 1), STYLE_SOLID, false);

         string lo_line = VIS_PREFIX + "ASIA_LO" + suffix;
         CreateOrUpdateTrend(lo_line, asia_start_srv, range.low, eod_srv, range.low, (d == 0 ? clrCrimson : C'140,50,65'), (d == 0 ? 2 : 1), STYLE_SOLID, false);

         // 3. London Breakout Window Box
         string lon_box = VIS_PREFIX + "LON_WINDOW" + suffix;
         double lon_pad = MathMax(range_w * 0.25, 1.50);
         bool in_lon = (d == 0 && is_london_today);
         color lon_clr = in_lon ? C'95,75,25' : (d == 0 ? C'48,42,22' : C'32,30,18');
         CreateOrUpdateRect(lon_box, london_start_srv, range.high + lon_pad, london_end_srv, range.low - lon_pad, lon_clr, 1, STYLE_DOT, true);

         // 4. Labels for today
         if(d == 0)
         {
            CreateOrUpdateText(VIS_PREFIX + "LBL_ASIA_HI", london_start_srv, range.high + 0.35,
                               StringFormat("▲ Asian High: %.2f (Range: $%.2f)", range.high, range_w),
                               clrDodgerBlue, 9, "Trebuchet MS", ANCHOR_LEFT_LOWER);

            CreateOrUpdateText(VIS_PREFIX + "LBL_ASIA_LO", london_start_srv, range.low - 0.35,
                               StringFormat("▼ Asian Low: %.2f", range.low),
                               clrCrimson, 9, "Trebuchet MS", ANCHOR_LEFT_UPPER);

            CreateOrUpdateText(VIS_PREFIX + "LBL_LONDON", london_start_srv, range.high + lon_pad + 0.30,
                               in_lon ? "⚡ LONDON BREAKOUT WINDOW (ACTIVE)" : "⌛ LONDON WINDOW (08:00-10:00 UTC)",
                               in_lon ? clrGold : clrDarkGray, 9, "Trebuchet MS", ANCHOR_LEFT_LOWER);
         }
      }
   }

   void DrawTradeSignal(const int side, const datetime signal_time,
                        const double entry, const double sl, const double tp,
                        const double fvg_gap_size=0.0)
   {
      string arr_name = VIS_PREFIX + "SIG_ARROW";
      if(ObjectFind(m_chart_id, arr_name) < 0)
      {
         ObjectCreate(m_chart_id, arr_name, side > 0 ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, signal_time, entry);
      }
      ObjectSetInteger(m_chart_id, arr_name, OBJPROP_COLOR, side > 0 ? clrLimeGreen : clrCrimson);
      ObjectSetInteger(m_chart_id, arr_name, OBJPROP_WIDTH, 4);

      // Entry, SL, TP lines
      datetime t_end = signal_time + 4 * 3600;
      CreateOrUpdateTrend(VIS_PREFIX + "SIG_ENTRY", signal_time, entry, t_end, entry, clrWhite, 2, STYLE_SOLID);
      CreateOrUpdateTrend(VIS_PREFIX + "SIG_SL", signal_time, sl, t_end, sl, clrCrimson, 2, STYLE_DASH);
      CreateOrUpdateTrend(VIS_PREFIX + "SIG_TP", signal_time, tp, t_end, tp, clrLimeGreen, 2, STYLE_DASH);

      CreateOrUpdateText(VIS_PREFIX + "SIG_LBL_ENTRY", signal_time, entry, StringFormat(" ENTRY %.2f", entry), clrWhite, 9);
      CreateOrUpdateText(VIS_PREFIX + "SIG_LBL_SL", signal_time, sl, StringFormat(" SL %.2f", sl), clrCrimson, 9);
      CreateOrUpdateText(VIS_PREFIX + "SIG_LBL_TP", signal_time, tp, StringFormat(" TP %.2f", tp), clrLimeGreen, 9);
   }

   void DrawHUD(const string status_msg, const PriceRange &level_ny, const double atr)
   {
      int x = 16, y = 30;
      int w = 345, h = 245;

      // Background glass card
      CreateOrUpdatePanel(VIS_PREFIX + "HUD_BG", x, y, w, h, m_hud_bg, m_hud_border);
      CreateOrUpdatePanel(VIS_PREFIX + "HUD_HEADER", x, y, w, 28, C'20,38,62', m_hud_border);

      // Header Text
      CreateOrUpdateLabel(VIS_PREFIX + "HUD_TITLE", x + 12, y + 6,
                          "✦ GOLD SESSION LAB PRO v3.6 ✦", clrGold, 10, "Trebuchet MS");

      // Content Rows
      string mode_str = (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? "LIVE DEMO" : "TESTER");
      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R1", x + 14, y + 36,
                          StringFormat("ACCOUNT: %s | %s (#%d)", mode_str, AccountInfoString(ACCOUNT_SERVER), (int)AccountInfoInteger(ACCOUNT_LOGIN)),
                          clrLimeGreen, 8);

      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R2", x + 14, y + 56,
                          StringFormat("BALANCE: $%.2f | EQUITY: $%.2f", AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY)),
                          clrWhite, 9);

      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R3", x + 14, y + 78,
                          "MODEL: HEAVY OPTIMIZED (No-Friday Seasonality)",
                          clrCyan, 8);

      double range_w = level_ny.high - level_ny.low;
      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R4", x + 14, y + 98,
                          StringFormat("ASIAN RANGE: $%.2f - $%.2f ($%.2f)", level_ny.high, level_ny.low, range_w),
                          clrGold, 8);

      long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R5", x + 14, y + 118,
                          StringFormat("ATR(14): %.2f | SPREAD: %d pts | TF: M5", atr, spread),
                          clrSilver, 8);

      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R6", x + 14, y + 142,
                          "EXECUTION STATUS:", clrDodgerBlue, 8);

      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R7", x + 14, y + 162,
                          status_msg,
                          StringFind(status_msg, "ACTIVE") >= 0 ? clrLimeGreen : (StringFind(status_msg, "Limit") >= 0 ? clrOrange : clrYellow),
                          9);

      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R8", x + 14, y + 195,
                          StringFormat("TIME (UTC): %s", TimeToString(TimeGMT(), TIME_DATE|TIME_MINUTES|TIME_SECONDS)),
                          clrLightSteelBlue, 8);

      CreateOrUpdateLabel(VIS_PREFIX + "HUD_R9", x + 14, y + 215,
                          StringFormat("SERVER: %s | LEV: 1:%d", TimeToString(TimeCurrent(), TIME_MINUTES|TIME_SECONDS), (int)AccountInfoInteger(ACCOUNT_LEVERAGE)),
                          clrDarkGray, 7);

      ChartRedraw(m_chart_id);
   }


   void DrawDiagnosticsHUD(const DiagnosticTelemetry &diag)
   {
      int x_panel = 16, y = 30;
      int w = 425, h = 345;
      int lx = 425; // 425px from right edge (left margin of right HUD)

      // Background glass card on the right
      CreateOrUpdatePanel(VIS_PREFIX + "DIAG_BG", x_panel, y, w, h, C'14,16,28', C'45,45,75', CORNER_RIGHT_UPPER);
      CreateOrUpdatePanel(VIS_PREFIX + "DIAG_HEADER", x_panel, y, w, 28, C'28,26,55', C'65,55,115', CORNER_RIGHT_UPPER);

      // Header Text
      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_TITLE", lx, y + 6,
                          "✦ LIVE REASONING & TELEMETRY ✦", clrGold, 10, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      // Content Rows (CORNER_RIGHT_UPPER: lx distance is from right border)
      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R1", lx, y + 36,
                          StringFormat("SESSION: %s", diag.session_phase),
                          clrLightSteelBlue, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R2", lx, y + 54,
                          StringFormat("DAY FILTER: %s", diag.day_filter_status),
                          clrLimeGreen, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R3", lx, y + 72,
                          StringFormat("WINDOW (08-10 UTC): %s", diag.window_status),
                          diag.in_window ? clrLimeGreen : clrOrange, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R4", lx, y + 90,
                          StringFormat("ASIAN RANGE: $%.2f - $%.2f ($%.2f) %s",
                                       diag.asian_high, diag.asian_low, diag.asian_width,
                                       diag.range_valid ? "[PASS]" : "[INVALID]"),
                          diag.range_valid ? clrCyan : clrRed, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      string brk_str = (diag.breakout_side == 1 ? "▲ BULLISH BREAKOUT" : (diag.breakout_side == -1 ? "▼ BEARISH BREAKOUT" : "INSIDE RANGE (No Breakout)"));
      color brk_clr = (diag.breakout_side != 0 ? clrGold : clrSilver);
      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R5", lx, y + 108,
                          StringFormat("BREAKOUT: %s (Bid: %.2f)", brk_str, diag.current_bid),
                          brk_clr, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R6", lx, y + 126,
                          StringFormat("CANDLE BODY: %.1f%% %s (Req >= 45%%)",
                                       diag.candle_strength * 100.0,
                                       diag.candle_strength_ok ? "[PASS]" : "[PENDING]"),
                          diag.candle_strength_ok ? clrLimeGreen : clrSilver, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      string bos_str = (diag.bos_m15 == 1 ? "BULLISH BOS [PASS]" : (diag.bos_m15 == -1 ? "BEARISH BOS [PASS]" : "PENDING"));
      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R7", lx, y + 144,
                          StringFormat("STRUCTURE (M15 BOS): %s", bos_str),
                          diag.bos_m15 != 0 ? clrLimeGreen : clrSilver, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R8", lx, y + 162,
                          StringFormat("FAIR VALUE GAP (FVG): %.2f pts %s (>= 0.35)",
                                       diag.fvg_gap_size, diag.fvg_ok ? "[PASS]" : "[WAITING]"),
                          diag.fvg_ok ? clrLimeGreen : clrSilver, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R9", lx, y + 180,
                          StringFormat("VOLUME RATIO: %.2fx %s (Req >= 1.10x)",
                                       diag.volume_ratio, diag.volume_ok ? "[PASS]" : "[WAITING]"),
                          diag.volume_ok ? clrLimeGreen : clrSilver, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_R10", lx, y + 198,
                          StringFormat("ATR BOUNDS: Ratio %.2f %s (0.50 - 2.50)",
                                       diag.atr_ratio, diag.atr_ok ? "[PASS]" : "[CHECK]"),
                          diag.atr_ok ? clrLimeGreen : clrSilver, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      // Status Decision Banner Box inside right HUD
      CreateOrUpdatePanel(VIS_PREFIX + "DIAG_STATUS_BOX", x_panel + 8, y + 220, w - 16, 114, C'20,24,40', diag.status_color, CORNER_RIGHT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_DECISION", lx - 6, y + 226,
                          StringFormat("DECISION: %s", diag.decision_summary),
                          diag.status_color, 9, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_WHY_EN", lx - 6, y + 248,
                          StringFormat("WHY: %s", diag.reason_detail),
                          clrWhite, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_WHY_FA", lx - 6, y + 270,
                          StringFormat("دلیل: %s", diag.reason_persian),
                          clrGold, 8, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      CreateOrUpdateLabel(VIS_PREFIX + "DIAG_TELEMETRY", lx - 6, y + 294,
                          StringFormat("TELEMETRY: LIVE DEMO | UTC %s", TimeToString(diag.current_time_utc, TIME_MINUTES|TIME_SECONDS)),
                          clrSilver, 7, "Trebuchet MS", CORNER_RIGHT_UPPER, ANCHOR_LEFT_UPPER);

      ChartRedraw(m_chart_id);
   }

   void ClearVisuals()
   {
      ObjectsDeleteAll(m_chart_id, VIS_PREFIX);
      ChartRedraw(m_chart_id);
   }
};

#endif
