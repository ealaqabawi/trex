//+------------------------------------------------------------------+
//| TrexScalpLab.mq5                                                  |
//| Research / alert EA for six scalping and day-trading methods.     |
//| It NEVER sends orders: every trade is virtual and is charged the  |
//| live (or tester real-tick) spread, so Strategy Tester results     |
//| appear in the Journal and in a CSV file, not in the Backtest tab. |
//+------------------------------------------------------------------+
#property version     "1.10"
#property description "Trex Scalp Lab - signals and virtual trades only. Contains no order-sending code."

//--- methods
enum ENUM_LAB_MODE
  {
   LAB_ALL          = 0, // All methods side by side
   LAB_TREX_SWEEP   = 1, // Trex failed-breakout sweep
   LAB_ORB          = 2, // Opening-range breakout (first 5-min candle)
   LAB_RSI2         = 3, // RSI(2) mean reversion with trend filter
   LAB_EMA_PULLBACK = 4, // EMA trend pullback
   LAB_AMD          = 5, // AMD / Power of Three (Asia range sweep)
   LAB_INTRADAY_MOM = 6  // Intraday momentum: first half hour -> last half hour (Gao et al. 2018)
  };
#define LAB_N 7

input group "General"
input ENUM_LAB_MODE   Mode             = LAB_ALL;
input ENUM_TIMEFRAMES Tf               = PERIOD_M5;
input int             ServerToUtcHours = 3;     // broker server time minus UTC (compare Market Watch clock with UTC)
input double          MaxSpreadOfRisk  = 0.15;  // skip a signal if spread > this share of the stop distance
input int             AtrPeriod        = 14;
input int             TrendEmaPeriod   = 200;
input bool            AlertsOn         = true;
input bool            PushToPhone      = true;  // needs MetaQuotes ID in Tools > Options > Notifications
input bool            WriteCsv         = true;  // Common\Files\TrexScalpLab_<symbol>.csv

input group "1. Trex sweep (failed breakout)"
input int    SweepLookback   = 20;
input int    SweepWindow     = 3;
input double SweepBufAtr     = 0.25;
input double SweepMaxStopAtr = 2.0;
input double SweepRR         = 2.0;
input int    SweepCooldown   = 3;

input group "2. Opening-range breakout (Zarattini/Aziz style)"
input bool   OrbNewYorkClock = true; // true = 09:30 New York time, US summer/winter time handled automatically
input int    OrbOpenHourUtc = 13;   // used only when OrbNewYorkClock = false
input int    OrbOpenMinUtc  = 30;
input int    OrbRangeBars   = 1;    // 1 = direction of the first candle after the open
input double OrbRR          = 10.0; // the paper uses 10R or the session close
input int    OrbHoldHours   = 6;    // flat this many hours after the open

input group "3. RSI(2) mean reversion"
input int    RsiPeriod   = 2;
input double RsiLow      = 5.0;
input double RsiHigh     = 95.0;
input int    ExitSma     = 5;      // exit when price closes back over this SMA
input double Rsi2StopAtr = 1.5;
input int    Rsi2MaxBars = 24;

input group "4. EMA trend pullback"
input int    PbFast      = 20;
input int    PbMid       = 50;
input double PbRR        = 2.0;
input int    PbSwingBars = 5;
input double PbMaxStopAtr = 2.5;

input group "5. AMD / Power of Three"
input int    AsiaStartUtc = 0;
input int    AsiaEndUtc   = 7;    // accumulation = Asian range
input int    ManipEndUtc  = 10;   // manipulation window = London open
input int    DistEndUtc   = 20;   // flat by this hour
input double AmdSweepAtr  = 0.10;
input double AmdBufAtr    = 0.10;
input double AmdRR        = 2.0;

input group "6. Intraday momentum (US index open -> close)"
input double ImStopAtr    = 2.0;  // protective stop for the last-half-hour trade
input double ImMinMovePct = 0.0;  // ignore days when |close->10:00 NY return| is below this % (0 = trade every day)

//--- virtual trade and statistics per method (index 1..5)
struct VTrade
  {
   bool     open;
   int      dir;
   double   entry;
   double   stop;
   double   target;
   double   spread;
   datetime opened;
   int      bars;
   int      maxBars;
   datetime flatAt;
  };

struct LabStats
  {
   int    trades;
   int    wins;
   double sumR;
   double winR;
   double lossR;
   double equity;
   double peak;
   double maxDD;
   int    skipped;
  };

string   NAMES[LAB_N] = {"ALL", "TREX_SWEEP", "ORB", "RSI2", "EMA_PULLBACK", "AMD", "INTRADAY_MOM"};
VTrade   g_trade[LAB_N];
LabStats g_stats[LAB_N];

int hAtr = INVALID_HANDLE, hTrend = INVALID_HANDLE, hRsi = INVALID_HANDLE, hSma = INVALID_HANDLE;
int hFast = INVALID_HANDLE, hMid = INVALID_HANDLE;

datetime g_lastBar = 0;
long     g_barNo   = 0;

//--- Trex sweep state
long   sw_upBar = -1, sw_dnBar = -1, sw_lastSig = -1000000;
double sw_upLvl = 0, sw_upExt = 0, sw_dnLvl = 0, sw_dnExt = 0;

//--- ORB state
long     orb_day = -1;
int      orb_count = 0;
bool     orb_done = false;
double   orb_hi = 0, orb_lo = 0, orb_firstOpen = 0;
datetime orb_openTime = 0;

//--- AMD state
long     amd_day = -1;
bool     amd_ready = false, amd_sweptHi = false, amd_sweptLo = false, amd_done = false;
double   amd_hi = 0, amd_lo = 0, amd_manHi = 0, amd_manLo = 0;
datetime amd_dayStartUtc = 0;

//--- intraday momentum state
long   im_day = -1;
double im_prevClose = 0.0, im_lastClose = 0.0, im_r1 = 0.0;
bool   im_haveR1 = false, im_done = false;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(SweepLookback < 2 || AtrPeriod < 2 || TrendEmaPeriod < 2 || MaxSpreadOfRisk <= 0.0 || OrbRangeBars < 1)
     {
      Print("Invalid inputs.");
      return INIT_PARAMETERS_INCORRECT;
     }
   hAtr   = iATR(_Symbol, Tf, AtrPeriod);
   hTrend = iMA(_Symbol, Tf, TrendEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   hRsi   = iRSI(_Symbol, Tf, RsiPeriod, PRICE_CLOSE);
   hSma   = iMA(_Symbol, Tf, ExitSma, 0, MODE_SMA, PRICE_CLOSE);
   hFast  = iMA(_Symbol, Tf, PbFast, 0, MODE_EMA, PRICE_CLOSE);
   hMid   = iMA(_Symbol, Tf, PbMid, 0, MODE_EMA, PRICE_CLOSE);
   if(hAtr == INVALID_HANDLE || hTrend == INVALID_HANDLE || hRsi == INVALID_HANDLE ||
      hSma == INVALID_HANDLE || hFast == INVALID_HANDLE || hMid == INVALID_HANDLE)
     {
      Print("Could not create indicator handles.");
      return INIT_FAILED;
     }
   for(int i = 0; i < LAB_N; i++)
     {
      ZeroMemory(g_trade[i]);
      ZeroMemory(g_stats[i]);
     }
   Print("Trex Scalp Lab started on ", _Symbol, " ", EnumToString(Tf), " | mode ", EnumToString(Mode),
         " | signal-only: no orders are ever sent.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   PrintSummary();
   IndicatorRelease(hAtr);
   IndicatorRelease(hTrend);
   IndicatorRelease(hRsi);
   IndicatorRelease(hSma);
   IndicatorRelease(hFast);
   IndicatorRelease(hMid);
  }

//+------------------------------------------------------------------+
double OnTester()
  {
   double total = 0.0;
   for(int id = 1; id < LAB_N; id++)
      if(Enabled(id))
         total += g_stats[id].sumR;
   return total; // use "Custom max" in the optimizer to rank by net R
  }

//+------------------------------------------------------------------+
bool Enabled(const int id)
  {
   return (Mode == LAB_ALL || (int)Mode == id);
  }

double Buf(const int handle, const int shift)
  {
   double v[1];
   if(CopyBuffer(handle, 0, shift, 1, v) != 1)
      return EMPTY_VALUE;
   return v[0];
  }

datetime ToUtc(const datetime serverTime)
  {
   return serverTime - ServerToUtcHours * 3600;
  }

//--- US daylight saving time: second Sunday of March to first Sunday of November (approximated at 07:00 UTC)
datetime NthSundayUtc(const int year, const int month, const int nth)
  {
   MqlDateTime d;
   ZeroMemory(d);
   d.year = year;
   d.mon  = month;
   d.day  = 1;
   datetime first = StructToTime(d);
   TimeToStruct(first, d);
   int add = (7 - d.day_of_week) % 7;            // days to the first Sunday
   return first + (add + 7 * (nth - 1)) * 86400 + 7 * 3600;
  }

bool UsDst(const datetime utc)
  {
   MqlDateTime d;
   TimeToStruct(utc, d);
   return utc >= NthSundayUtc(d.year, 3, 2) && utc < NthSundayUtc(d.year, 11, 1);
  }

//--- New York local hh:mm -> minutes after 00:00 UTC on that day
int NyToUtcMinutes(const datetime utc, const int nyHour, const int nyMin)
  {
   return (nyHour + (UsDst(utc) ? 4 : 5)) * 60 + nyMin;
  }

string Px(const double price)
  {
   return DoubleToString(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime t0 = iTime(_Symbol, Tf, 0);
   if(t0 == 0 || t0 == g_lastBar)
      return;
   g_lastBar = t0;
   g_barNo++;

   int need = MathMax(SweepLookback, PbSwingBars) + 5;
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, Tf, 0, need, r) < need)
      return;
   if(Bars(_Symbol, Tf) < TrendEmaPeriod + 50)
      return;

   double atr1   = Buf(hAtr, 1);
   double trend1 = Buf(hTrend, 1);
   double rsi1   = Buf(hRsi, 1);
   double sma1   = Buf(hSma, 1);
   double fast1  = Buf(hFast, 1);
   double fast2  = Buf(hFast, 2);
   double mid1   = Buf(hMid, 1);
   if(atr1 == EMPTY_VALUE || trend1 == EMPTY_VALUE || rsi1 == EMPTY_VALUE || sma1 == EMPTY_VALUE ||
      fast1 == EMPTY_VALUE || fast2 == EMPTY_VALUE || mid1 == EMPTY_VALUE || atr1 <= 0.0)
      return;

   // 1) manage virtual trades with the candle that just closed (r[1])
   for(int id = 1; id < LAB_N; id++)
      if(Enabled(id))
         Manage(id, r[1], sma1);

   // 2) look for new signals on r[1]; entries happen now, at the open of r[0]
   if(Enabled((int)LAB_TREX_SWEEP))
      SignalSweep(r, atr1, trend1);
   if(Enabled((int)LAB_ORB))
      SignalOrb(r[1]);
   if(Enabled((int)LAB_RSI2))
      SignalRsi2(r[1], atr1, trend1, rsi1);
   if(Enabled((int)LAB_EMA_PULLBACK))
      SignalPullback(r, atr1, trend1, fast1, fast2, mid1);
   if(Enabled((int)LAB_AMD))
      SignalAmd(r[1], atr1);
   if(Enabled((int)LAB_INTRADAY_MOM))
      SignalIntradayMom(r[1], atr1);
  }

//+------------------------------------------------------------------+
//| Virtual trade handling                                            |
//+------------------------------------------------------------------+
bool OpenVirtual(const int id, const int dir, const double stop, const double rr,
                 const int maxBars, const datetime flatAt, const string why)
  {
   if(g_trade[id].open)
      return false;
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk) || tk.ask <= 0.0 || tk.bid <= 0.0)
      return false;
   double entry = (dir > 0) ? tk.ask : tk.bid;
   double spr   = tk.ask - tk.bid;
   double risk  = (dir > 0) ? entry - stop : stop - entry;
   if(risk <= 0.0)
      return false;
   if(spr / risk > MaxSpreadOfRisk)
     {
      g_stats[id].skipped++;
      return false;
     }
   double target = (rr > 0.0) ? entry + dir * rr * risk : 0.0;

   g_trade[id].open    = true;
   g_trade[id].dir     = dir;
   g_trade[id].entry   = entry;
   g_trade[id].stop    = stop;
   g_trade[id].target  = target;
   g_trade[id].spread  = spr;
   g_trade[id].opened  = TimeCurrent();
   g_trade[id].bars    = 0;
   g_trade[id].maxBars = maxBars;
   g_trade[id].flatAt  = flatAt;

   string msg = StringFormat("TREX LAB %s | %s %s %s @ %s | SL %s | TP %s | spread %.1f%% of risk | %s | research signal, not an order",
                             NAMES[id], _Symbol, EnumToString(Tf), (dir > 0 ? "BUY" : "SELL"), Px(entry), Px(stop),
                             (target > 0.0 ? Px(target) : "rule exit"), 100.0 * spr / risk, why);
   Print(msg);
   if(AlertsOn && !MQLInfoInteger(MQL_TESTER))
     {
      Alert(msg);
      if(PushToPhone && TerminalInfoInteger(TERMINAL_NOTIFICATIONS_ENABLED))
         SendNotification(StringSubstr(msg, 0, 255));
     }
   return true;
  }

void Manage(const int id, const MqlRates &b, const double sma1)
  {
   if(!g_trade[id].open)
      return;
   g_trade[id].bars++;
   int    dir  = g_trade[id].dir;
   double spr  = g_trade[id].spread;
   double risk = MathAbs(g_trade[id].entry - g_trade[id].stop);
   // chart candles are bid prices: a sell closes at the ask (bid + spread)
   double hi = (dir > 0) ? b.high : b.high + spr;
   double lo = (dir > 0) ? b.low  : b.low + spr;
   double cl = (dir > 0) ? b.close : b.close + spr;
   double op = (dir > 0) ? b.open  : b.open + spr;
   double exitPx = 0.0;
   string why = "";

   bool hitStop = (dir > 0) ? lo <= g_trade[id].stop : hi >= g_trade[id].stop;
   bool hitTgt  = g_trade[id].target > 0.0 && ((dir > 0) ? hi >= g_trade[id].target : lo <= g_trade[id].target);
   bool gapStop = (dir > 0) ? op < g_trade[id].stop : op > g_trade[id].stop;
   bool gapTgt  = g_trade[id].target > 0.0 && ((dir > 0) ? op > g_trade[id].target : op < g_trade[id].target);
   if(gapStop)                 // candle opened beyond the stop (gap): filled at the open, worse than the stop
     { exitPx = op; why = "stop (gap)"; }
   else if(gapTgt)
     { exitPx = op; why = "target (gap)"; }
   else if(hitStop)            // stop counts first if both are inside one candle
     { exitPx = g_trade[id].stop; why = "stop"; }
   else if(hitTgt)
     { exitPx = g_trade[id].target; why = "target"; }
   else if(id == (int)LAB_RSI2 && ((dir > 0 && b.close > sma1) || (dir < 0 && b.close < sma1)))
     { exitPx = cl; why = "back to SMA"; }
   else if(g_trade[id].maxBars > 0 && g_trade[id].bars >= g_trade[id].maxBars)
     { exitPx = cl; why = "time stop"; }
   else if(g_trade[id].flatAt > 0 && b.time + PeriodSeconds(Tf) >= g_trade[id].flatAt)
     { exitPx = cl; why = "session end"; }

   if(why == "")
      return;
   double R = dir * (exitPx - g_trade[id].entry) / risk;
   CloseVirtual(id, R, exitPx, why);
  }

void CloseVirtual(const int id, const double R, const double exitPx, const string why)
  {
   g_stats[id].trades++;
   if(R > 0.0)
     {
      g_stats[id].wins++;
      g_stats[id].winR += R;
     }
   else
      g_stats[id].lossR += -R;
   g_stats[id].sumR   += R;
   g_stats[id].equity += R;
   if(g_stats[id].equity > g_stats[id].peak)
      g_stats[id].peak = g_stats[id].equity;
   double dd = g_stats[id].peak - g_stats[id].equity;
   if(dd > g_stats[id].maxDD)
      g_stats[id].maxDD = dd;

   if(WriteCsv)
     {
      string fn = "TrexScalpLab_" + _Symbol + ".csv";
      int fh = FileOpen(fn, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
      if(fh != INVALID_HANDLE)
        {
         if(FileSize(fh) == 0)
            FileWrite(fh, "method", "symbol", "dir", "opened", "closed", "entry", "stop", "target", "exit", "spread", "R", "reason");
         FileSeek(fh, 0, SEEK_END);
         FileWrite(fh, NAMES[id], _Symbol, (g_trade[id].dir > 0 ? "BUY" : "SELL"),
                   TimeToString(g_trade[id].opened), TimeToString(TimeCurrent()),
                   Px(g_trade[id].entry), Px(g_trade[id].stop), Px(g_trade[id].target), Px(exitPx),
                   Px(g_trade[id].spread), DoubleToString(R, 2), why);
         FileClose(fh);
        }
     }
   g_trade[id].open = false;
  }

void PrintSummary()
  {
   Print("===== Trex Scalp Lab results on ", _Symbol, " ", EnumToString(Tf),
         " (virtual trades, spread charged, no commission/swap) =====");
   for(int id = 1; id < LAB_N; id++)
     {
      if(!Enabled(id))
         continue;
      int n = g_stats[id].trades;
      double pf = (g_stats[id].lossR > 0.0) ? g_stats[id].winR / g_stats[id].lossR : 0.0;
      PrintFormat("%-13s trades %4d | win %5.1f%% | net %+7.2fR | avg %+6.3fR | PF %5.2f | maxDD %6.2fR | skipped (spread) %d",
                  NAMES[id], n, (n > 0 ? 100.0 * g_stats[id].wins / n : 0.0), g_stats[id].sumR,
                  (n > 0 ? g_stats[id].sumR / n : 0.0), pf, g_stats[id].maxDD, g_stats[id].skipped);
     }
  }

//+------------------------------------------------------------------+
//| 1. Trex failed-breakout sweep                                     |
//+------------------------------------------------------------------+
void SignalSweep(const MqlRates &r[], const double atr1, const double trend1)
  {
   MqlRates b = r[1];
   double hiRef = r[2].high, loRef = r[2].low;
   for(int k = 3; k <= SweepLookback + 1; k++)
     {
      hiRef = MathMax(hiRef, r[k].high);
      loRef = MathMin(loRef, r[k].low);
     }
   if(b.high > hiRef)
     {
      if(sw_upBar < 0 || g_barNo - sw_upBar > SweepWindow)
        { sw_upLvl = hiRef; sw_upExt = b.high; }
      else
         sw_upExt = MathMax(sw_upExt, b.high);
      sw_upBar = g_barNo;
     }
   if(b.low < loRef)
     {
      if(sw_dnBar < 0 || g_barNo - sw_dnBar > SweepWindow)
        { sw_dnLvl = loRef; sw_dnExt = b.low; }
      else
         sw_dnExt = MathMin(sw_dnExt, b.low);
      sw_dnBar = g_barNo;
     }
   if(g_trade[(int)LAB_TREX_SWEEP].open || g_barNo - sw_lastSig <= SweepCooldown)
      return;

   bool sell = sw_upBar >= 0 && g_barNo - sw_upBar <= SweepWindow && b.close < sw_upLvl && b.close < b.open && b.close < trend1;
   bool buy  = sw_dnBar >= 0 && g_barNo - sw_dnBar <= SweepWindow && b.close > sw_dnLvl && b.close > b.open && b.close > trend1;
   if(sell)
     {
      double stop = sw_upExt + SweepBufAtr * atr1;
      if(stop - b.close > 0.0 && stop - b.close <= SweepMaxStopAtr * atr1 &&
         OpenVirtual((int)LAB_TREX_SWEEP, -1, stop, SweepRR, 0, 0, "swept " + Px(sw_upLvl)))
        { sw_lastSig = g_barNo; sw_upBar = -1; }
     }
   else if(buy)
     {
      double stop = sw_dnExt - SweepBufAtr * atr1;
      if(b.close - stop > 0.0 && b.close - stop <= SweepMaxStopAtr * atr1 &&
         OpenVirtual((int)LAB_TREX_SWEEP, 1, stop, SweepRR, 0, 0, "swept " + Px(sw_dnLvl)))
        { sw_lastSig = g_barNo; sw_dnBar = -1; }
     }
  }

//+------------------------------------------------------------------+
//| 2. Opening-range breakout                                         |
//+------------------------------------------------------------------+
void SignalOrb(const MqlRates &b)
  {
   datetime u = ToUtc(b.time);
   long day = (long)(u / 86400);
   MqlDateTime dt;
   TimeToStruct(u, dt);
   if(dt.day_of_week == 0 || dt.day_of_week == 6)
      return;
   int openUtc = OrbNewYorkClock ? NyToUtcMinutes(u, 9, 30) : OrbOpenHourUtc * 60 + OrbOpenMinUtc;
   int minsFromOpen = (dt.hour * 60 + dt.min) - openUtc;

   if(day != orb_day)
     {
      orb_day = day;
      orb_count = 0;
      orb_done = false;
     }
   if(orb_done || minsFromOpen < 0)
      return;
   if(orb_count == 0 && minsFromOpen != 0)
     {
      orb_done = true; // first candle after the open is missing (holiday/data gap): skip the day
      return;
     }
   if(orb_count < OrbRangeBars)
     {
      if(orb_count == 0)
        {
         orb_hi = b.high;
         orb_lo = b.low;
         orb_firstOpen = b.open;
         orb_openTime = b.time;
        }
      else
        {
         orb_hi = MathMax(orb_hi, b.high);
         orb_lo = MathMin(orb_lo, b.low);
        }
      orb_count++;
      if(orb_count < OrbRangeBars)
         return;
      orb_done = true;
      int dir = (b.close > orb_firstOpen) ? 1 : (b.close < orb_firstOpen ? -1 : 0);
      if(dir == 0)
         return;
      double stop = (dir > 0) ? orb_lo : orb_hi;
      OpenVirtual((int)LAB_ORB, dir, stop, OrbRR, 0, orb_openTime + OrbHoldHours * 3600, "opening range " + Px(orb_lo) + "-" + Px(orb_hi));
     }
  }

//+------------------------------------------------------------------+
//| 3. RSI(2) mean reversion in the direction of the trend            |
//+------------------------------------------------------------------+
void SignalRsi2(const MqlRates &b, const double atr1, const double trend1, const double rsi1)
  {
   if(g_trade[(int)LAB_RSI2].open)
      return;
   if(b.close > trend1 && rsi1 < RsiLow)
      OpenVirtual((int)LAB_RSI2, 1, b.close - Rsi2StopAtr * atr1, 0.0, Rsi2MaxBars, 0, StringFormat("RSI(%d)=%.1f in uptrend", RsiPeriod, rsi1));
   else if(b.close < trend1 && rsi1 > RsiHigh)
      OpenVirtual((int)LAB_RSI2, -1, b.close + Rsi2StopAtr * atr1, 0.0, Rsi2MaxBars, 0, StringFormat("RSI(%d)=%.1f in downtrend", RsiPeriod, rsi1));
  }

//+------------------------------------------------------------------+
//| 4. EMA trend pullback                                             |
//+------------------------------------------------------------------+
void SignalPullback(const MqlRates &r[], const double atr1, const double trend1,
                    const double fast1, const double fast2, const double mid1)
  {
   if(g_trade[(int)LAB_EMA_PULLBACK].open)
      return;
   MqlRates b = r[1];
   bool up   = mid1 > trend1 && fast1 > mid1;
   bool down = mid1 < trend1 && fast1 < mid1;
   if(up && r[2].low <= fast2 && b.close > fast1 && b.close > b.open)
     {
      double swing = b.low;
      for(int k = 2; k <= PbSwingBars; k++)
         swing = MathMin(swing, r[k].low);
      double stop = swing - 0.1 * atr1;
      if(b.close - stop > 0.0 && b.close - stop <= PbMaxStopAtr * atr1)
         OpenVirtual((int)LAB_EMA_PULLBACK, 1, stop, PbRR, 0, 0, "pullback to EMA" + IntegerToString(PbFast));
     }
   else if(down && r[2].high >= fast2 && b.close < fast1 && b.close < b.open)
     {
      double swing = b.high;
      for(int k = 2; k <= PbSwingBars; k++)
         swing = MathMax(swing, r[k].high);
      double stop = swing + 0.1 * atr1;
      if(stop - b.close > 0.0 && stop - b.close <= PbMaxStopAtr * atr1)
         OpenVirtual((int)LAB_EMA_PULLBACK, -1, stop, PbRR, 0, 0, "pullback to EMA" + IntegerToString(PbFast));
     }
  }

//+------------------------------------------------------------------+
//| 5. AMD / Power of Three                                           |
//+------------------------------------------------------------------+
void SignalAmd(const MqlRates &b, const double atr1)
  {
   datetime u = ToUtc(b.time);
   long day = (long)(u / 86400);
   MqlDateTime dt;
   TimeToStruct(u, dt);
   int h = dt.hour;

   if(day != amd_day)
     {
      amd_day = day;
      amd_ready = false;
      amd_sweptHi = false;
      amd_sweptLo = false;
      amd_done = false;
      amd_dayStartUtc = (datetime)(day * 86400);
     }
   // A: build the Asian range
   if(h >= AsiaStartUtc && h < AsiaEndUtc)
     {
      if(!amd_ready)
        { amd_hi = b.high; amd_lo = b.low; amd_ready = true; }
      else
        { amd_hi = MathMax(amd_hi, b.high); amd_lo = MathMin(amd_lo, b.low); }
      return;
     }
   if(!amd_ready || amd_done || h >= DistEndUtc)
      return;
   // M: London sweeps one side
   if(h < ManipEndUtc)
     {
      if(b.high > amd_hi + AmdSweepAtr * atr1)
        { amd_manHi = amd_sweptHi ? MathMax(amd_manHi, b.high) : b.high; amd_sweptHi = true; }
      if(b.low < amd_lo - AmdSweepAtr * atr1)
        { amd_manLo = amd_sweptLo ? MathMin(amd_manLo, b.low) : b.low; amd_sweptLo = true; }
     }
   if(g_trade[(int)LAB_AMD].open)
      return;
   // D: close back inside after a one-sided sweep
   datetime flat = amd_dayStartUtc + DistEndUtc * 3600 + ServerToUtcHours * 3600; // back to server time
   if(amd_sweptHi && !amd_sweptLo && b.close < amd_hi && b.close < b.open)
     {
      if(OpenVirtual((int)LAB_AMD, -1, amd_manHi + AmdBufAtr * atr1, AmdRR, 0, flat, "Asia high swept"))
         amd_done = true;
     }
   else if(amd_sweptLo && !amd_sweptHi && b.close > amd_lo && b.close > b.open)
     {
      if(OpenVirtual((int)LAB_AMD, 1, amd_manLo - AmdBufAtr * atr1, AmdRR, 0, flat, "Asia low swept"))
         amd_done = true;
     }
  }
//+------------------------------------------------------------------+
//| 6. Intraday momentum (Gao, Han, Li & Zhou, JFE 2018)              |
//| The return from yesterday's 16:00 New York close to 10:00 today   |
//| predicts the direction of the last half hour (15:30-16:00).       |
//| Trade that direction at 15:30 NY, flat at 16:00 NY.               |
//+------------------------------------------------------------------+
void SignalIntradayMom(const MqlRates &b, const double atr1)
  {
   datetime u = ToUtc(b.time);
   datetime closeT = u + PeriodSeconds(Tf);          // the moment this candle closed (UTC)
   MqlDateTime dt;
   TimeToStruct(closeT, dt);
   long day = (long)(closeT / 86400);
   int  m   = dt.hour * 60 + dt.min;
   int  t10 = NyToUtcMinutes(closeT, 10, 0);
   int  t1530 = NyToUtcMinutes(closeT, 15, 30);
   int  t16 = NyToUtcMinutes(closeT, 16, 0);

   if(day != im_day)
     {
      im_day = day;
      im_haveR1 = false;
      im_done = false;
     }
   if(dt.day_of_week == 0 || dt.day_of_week == 6)
      return;
   if(m == t10 && im_prevClose > 0.0)
     {
      im_r1 = b.close / im_prevClose - 1.0;
      im_haveR1 = true;
     }
   if(m == t16)
      im_prevClose = b.close;                         // today's close becomes tomorrow's reference
   if(!im_haveR1 || im_done || m != t1530 || g_trade[(int)LAB_INTRADAY_MOM].open)
      return;
   im_done = true;
   if(MathAbs(im_r1) * 100.0 < ImMinMovePct || im_r1 == 0.0)
      return;
   int dir = (im_r1 > 0.0) ? 1 : -1;
   double stop = (dir > 0) ? b.close - ImStopAtr * atr1 : b.close + ImStopAtr * atr1;
   datetime flat = b.time + (t16 - t1530) * 60;       // server time of 16:00 NY
   OpenVirtual((int)LAB_INTRADAY_MOM, dir, stop, 0.0, 0, flat + PeriodSeconds(Tf),
               StringFormat("close->10:00 NY return %+.2f%%", im_r1 * 100.0));
  }
//+------------------------------------------------------------------+
