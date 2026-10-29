//+------------------------------------------------------------------+
//|                                              DayTraderMT5.mq5    |
//|        the day-trader pack as one Expert Advisor                 |
//|                                                                  |
//|  The Python desk in trader-mt5/ reads the terminal, sizes in     |
//|  lots, checks your rules and sends one order after your yes.     |
//|  This EA is the same idea living inside MetaTrader, for people   |
//|  who want the terminal to trade on its own:                      |
//|                                                                  |
//|    a trend-filtered opening-range breakout,                      |
//|    a stop half an ATR behind the range (never tighter than the   |
//|      range mid), a target at an R multiple,                      |
//|    risk-percent sizing from the symbol's own tick value,         |
//|    the volume ladder, the broker's stops level and the spread    |
//|      checked before anything is sent,                            |
//|    one trade a day, a daily loss stop, a session window,         |
//|    breakeven, a trailing stop, a partial take-profit, and a      |
//|      flat-by time.                                               |
//|                                                                  |
//|  It talks to you in two places: a tagged console line for every  |
//|  decision (time | TAG | what happened) in the Experts log, and   |
//|  a dashboard on the chart with every number the rule used, plus  |
//|  three buttons: PAUSE, DRY and CLOSE OURS.                       |
//|                                                                  |
//|  It cannot place a trade on a REAL-money account unless you set  |
//|  InpAllowLive to true. Run it on a demo first.                   |
//|                                                                  |
//|  It only touches trades with its own magic number, so it will    |
//|  not disturb anything you opened by hand.                        |
//|                                                                  |
//|  Education and tooling, not financial advice. Most people who    |
//|  day trade lose money. A stop is a plan, not a guarantee.        |
//+------------------------------------------------------------------+
#property copyright "day-trader-skill, MIT"
#property link      "https://github.com/MHR4u/day-trader-skill"
#property version   "1.22"
#property description "Trend-filtered opening-range breakout with ATR stop, R target, risk-percent sizing,"
#property description "spread and stops-level gates, one trade a day, a daily loss stop, breakeven, trailing,"
#property description "partial take-profit and a flat-by time. Demo by default: a REAL account needs InpAllowLive."
#property description "Offline. A tagged console line for every decision, and a nine page dashboard where every number is one click away, with a TEST page that proves the order before it is sent."

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group "The gates"
input bool             InpAllowLive        = false;    // Allow a REAL-money account (leave false)
input bool             InpDryRun           = false;    // Signal only: log the trade, send nothing
input long             InpMagic            = 20261019; // Magic number: this EA only touches its own trades

input group "Risk and size"
input double           InpRiskPercent      = 1.0;      // Risk per trade, % of equity (0 = use the fixed amount)
input double           InpRiskMoney        = 50.0;     // Risk per trade, account money (0 = use the percent)
input double           InpMaxLots          = 2.0;      // Hard cap on volume per order
input double           InpMaxMarginPct     = 40.0;     // Never use more than this % of free margin
input double           InpMaxSpreadPoints  = 25.0;     // Skip the entry when the spread is wider (0 = off)
input double           InpMinRR            = 1.5;      // Reward:risk the target is built from

input group "The rule"
input ENUM_TIMEFRAMES  InpTimeframe        = PERIOD_M5; // Bar size the rule reads
input int              InpEmaFast          = 50;        // Fast EMA period
input int              InpEmaSlow          = 200;       // Slow EMA period
input bool             InpUseTrend         = true;      // Trend filter: fast EMA above slow for a buy
input int              InpAtrPeriod        = 14;        // ATR period, used for the stop
input int              InpORMinutes        = 60;        // Opening range length, minutes
input double           InpAtrMult          = 0.5;       // Stop: this many ATR behind the entry
input double           InpMinRangePoints   = 0.0;       // Skip the day when the range is narrower (0 = off)
input bool             InpAllowShort       = false;     // Also take the downside break

input group "The clock"
input bool             InpNewYorkTimes     = true;      // Read the times below as New York, not server time
input string           InpSessionStart     = "03:05";   // No entries before this time
input string           InpSessionEnd       = "19:00";   // No entries after this time
input string           InpFlatBy           = "20:55";   // Close everything at this time
input bool             InpWeekdaysOnly     = true;      // No entries on Saturday and Sunday
input int              InpMaxTradesPerDay  = 1;         // Entries allowed per day
input double           InpMaxDailyLoss     = 150.0;     // Stop for the day after this much realised loss (0 = off)

input group "Managing the trade"
input double           InpBreakevenAtR     = 1.0;       // Move the stop to the entry at this R (0 = off)
input double           InpTrailAtR         = 1.0;       // Start trailing at this R (0 = off)
input int              InpTrailPoints      = 150;       // Trail distance, points
input double           InpPartialAtR       = 0.0;       // Take part of the position at this R (0 = off)
input double           InpPartialPercent   = 50.0;      // Percent of the volume to close there

input group "Alerts"
input bool             InpAlertPopup       = true;      // Alert() popup on a fill and on a close
input bool             InpAlertSound       = false;     // A sound with it
input bool             InpAlertPush        = false;     // Push to the phone (needs the MetaQuotes ID)

input group "Console and panel"
input bool             InpShowPanel        = true;      // Draw the dashboard on the chart
input int              InpPanelX           = 14;        // Dashboard distance from the left edge, pixels
input int              InpPanelY           = 96;        // Dashboard distance from the top edge, below the buy/sell corner
input bool             InpVerbose          = false;     // Log every closed bar, not only the changes
input int              InpHeartbeatMinutes = 15;        // An ALIVE line this often while it runs (0 = off)

input group "Plumbing"
input int              InpDeviationPoints  = 20;        // Slippage allowed, points
input int              InpStopBufferPoints = 10;        // Extra room on top of the broker's stops level

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
CTrade   g_trade;

int      g_emaFast      = INVALID_HANDLE;
int      g_emaSlow      = INVALID_HANDLE;
int      g_atr          = INVALID_HANDLE;

double   g_riskPct      = 0.0;
double   g_riskMoney    = 0.0;
double   g_minRR        = 1.5;
long     g_magic        = 0;
int      g_maxTrades    = 1;
int      g_orMinutes    = 60;
double   g_atrMult      = 0.5;
double   g_spreadMax    = 0.0;
double   g_maxLots      = 2.0;
double   g_maxMarginPct = 40.0;
int      g_trailPoints  = 150;
double   g_beAtR        = 0.0;
double   g_trailAtR     = 0.0;
double   g_partialAtR   = 0.0;
double   g_partialPct   = 50.0;
int      g_deviation    = 20;
int      g_stopBuffer   = 10;
int      g_sessionStart = 0;      // minutes of the day
int      g_sessionEnd   = 0;
int      g_flatBy       = 0;
bool     g_newYork      = true;
bool     g_weekdaysOnly = true;
bool     g_dryRun       = false;
bool     g_allowLive    = false;
bool     g_showPanel    = true;
bool     g_shorts       = false;
double   g_maxDailyLoss = 150.0;

bool     g_liveBlocked  = false;
datetime g_lastBarTime  = 0;      // the last bar the rule looked at
int      g_lastDay      = -1;     // New York day number, for the once-a-day housekeeping

ENUM_TIMEFRAMES g_tf     = PERIOD_M5;   // the rule's bar size, clickable on the chart
int      g_emaFastPeriod = 50;
int      g_emaSlowPeriod = 200;
bool     g_useTrend     = true;   // the trend filter can be switched off from the panel
int      g_atrPeriod    = 14;
double   g_minRangePoints = 0.0;  // a range narrower than this skips the day
bool     g_alertPopup   = true;
bool     g_alertSound   = false;
bool     g_alertPush    = false;
int      g_page         = 0;      // 0 dash, 1 rule, 2 risk, 3 clock, 4 manage, 5 log, 6 test, 7 pack, 8 help
bool     g_confirmReset = false;
datetime g_confirmResetAt = 0;
string   g_lastCheck    = "-";             // the terminal's answer to the order check
datetime g_lastBeat     = 0;               // the last ALIVE line
int      g_heartbeat    = 15;              // minutes between ALIVE lines, 0 = off
string   g_lastRetcode  = "-";    // the broker's last answer, for the pack page
bool     g_verbose      = false;  // log every bar, not only the changes
bool     g_paused       = false;  // entries paused from the dashboard
int      g_panelX       = 14;
int      g_panelY       = 24;
bool     g_confirmClose = false;  // the second click on CLOSE OURS
datetime g_confirmAt    = 0;
string   g_ruleKey      = "";     // the last rule state we logged
string   g_lastEvent    = "waking up";
string   g_lastEventAt  = "";
int      g_uiX          = 14;     // dashboard cursor
int      g_uiY          = 24;
int      g_nyOffset     = -5;     // New York's offset from GMT, set by ToNewYork
datetime g_flatTry      = 0;      // the last flat-by attempt, so it is not repeated on every tick

#define GATE_PREFIX "DTMT5_"

// the dashboard: chart objects only, so no DLL, no resources, no files
#define PANEL_TAG   "DTMT5_UI_"
#define PANEL_W     352
#define PANEL_PAD   10
#define ROW_H       15
#define EROW_H      19
#define SECT_H      17
#define CLR_BG      C'18,24,34'
#define CLR_HEAD    C'27,54,86'
#define CLR_SECT    C'88,166,255'
#define CLR_LABEL   C'139,148,158'
#define CLR_VALUE   C'230,237,243'
#define CLR_GOOD    C'63,185,80'
#define CLR_BAD     C'248,81,73'
#define CLR_WARN    C'210,153,34'
#define CLR_LINE    C'48,54,61'
#define CLR_BTN     C'31,58,95'
#define CLR_DANGER  C'122,38,38'

#define PAGE_COUNT  9
#define LOG_RING    12
#define CFG_PREFIX  "DTMT5_C_"

string   g_logRing[LOG_RING];   // the console, mirrored on the chart
int      g_logCount = 0;

//+------------------------------------------------------------------+
//| Small helpers                                                    |
//+------------------------------------------------------------------+
// the chart's own copy of the console: newest first, so the log page can
// show what just happened without opening the terminal's log file
void LogRingPush(const string line)
{
   for(int i = LOG_RING - 1; i > 0; i--)
      g_logRing[i] = g_logRing[i - 1];
   g_logRing[0] = line;
   if(g_logCount < LOG_RING)
      g_logCount++;
}

// every console line is the same shape:  time | TAG | what happened
// the tag is padded to five characters so the column stays straight in the
// Experts log and in the terminal's own log file
void Log(const string tag, const string text, const bool quiet = false)
{
   string t = tag;
   while(StringLen(t) < 5)
      t += " ";
   string line = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + " | " + t + " | " + text;
   Print(line);
   LogRingPush(line);
   if(!quiet)
   {
      g_lastEvent   = tag + "  " + text;
      g_lastEventAt = TimeToString(TimeCurrent(), TIME_MINUTES | TIME_SECONDS);
   }
}

// the rule says the same thing on bar after bar: say it once, unless verbose
void LogRule(const string key, const string text)
{
   if(key == g_ruleKey && !g_verbose)
      return;
   g_ruleKey = key;
   Log("RULE", text);
}

// ASCII only, so the log stays readable in any code page
string Clip(const string text, const int maxChars)
{
   if(maxChars < 2 || StringLen(text) <= maxChars)
      return text;
   return StringSubstr(text, 0, maxChars - 1) + "~";
}

string Money(const double value)
{
   return DoubleToString(value, 2) + " " + AccountInfoString(ACCOUNT_CURRENCY);
}

bool ParseHHMM(const string text, int &minutesOfDay)
{
   string parts[];
   int n = StringSplit(text, ':', parts);
   if(n != 2)
      return false;
   int h = (int)StringToInteger(parts[0]);
   int m = (int)StringToInteger(parts[1]);
   if(h < 0 || h > 23 || m < 0 || m > 59)
      return false;
   minutesOfDay = h * 60 + m;
   return true;
}

string HHMM(const int minutesOfDay)
{
   int h = minutesOfDay / 60;
   int m = minutesOfDay % 60;
   return StringFormat("%02d:%02d", h, m);
}

int MinutesOfDay(const datetime value)
{
   MqlDateTime t;
   TimeToStruct(value, t);
   return t.hour * 60 + t.min;
}

int DayIndexOf(const datetime value)
{
   MqlDateTime t;
   TimeToStruct(value, t);
   return t.year * 10000 + t.mon * 100 + t.day;
}

int WeekdayOf(const datetime value)
{
   MqlDateTime t;
   TimeToStruct(value, t);
   return t.day_of_week;      // 0 = Sunday
}

int WeekdayOfMonth(const int year, const int month, const int weekday, const int nth)
{
   MqlDateTime first;
   first.year = year;
   first.mon = month;
   first.day = 1;
   first.hour = 0;
   first.min = 0;
   first.sec = 0;
   first.day_of_week = 0;
   first.day_of_year = 0;
   datetime stamp = StructToTime(first);
   MqlDateTime got;
   TimeToStruct(stamp, got);
   int delta = (weekday - got.day_of_week + 7) % 7;
   return 1 + delta + 7 * (nth - 1);
}

string PeriodDescription(const ENUM_TIMEFRAMES tf)
{
   string name = EnumToString(tf);
   StringReplace(name, "PERIOD_", "");
   return name;
}

string RiskWords()
{
   string text = "";
   if(g_riskPct > 0.0)
      text = DoubleToString(g_riskPct, 2) + "% of equity";
   if(g_riskMoney > 0.0)
      text += (text == "" ? "" : " and ") + DoubleToString(g_riskMoney, 2) + " " + AccountInfoString(ACCOUNT_CURRENCY);
   return text;
}

//+------------------------------------------------------------------+
//| Time: the server clock is not your clock and not New York's      |
//+------------------------------------------------------------------+
datetime ToNewYork(const datetime serverTime)
{
   int offset = (int)(TimeCurrent() - TimeGMT());          // the server's offset from GMT, seconds
   datetime gmt = serverTime - offset;
   if(!g_newYork)
   {
      g_nyOffset = 0;
      return serverTime;
   }
   MqlDateTime g;
   TimeToStruct(gmt, g);
   int startDay = WeekdayOfMonth(g.year, 3, 0, 2);         // second Sunday of March
   int endDay   = WeekdayOfMonth(g.year, 11, 0, 1);        // first Sunday of November
   MqlDateTime a, b;
   a.year = g.year; a.mon = 3;  a.day = startDay; a.hour = 7; a.min = 0; a.sec = 0; a.day_of_week = 0; a.day_of_year = 0;
   b.year = g.year; b.mon = 11; b.day = endDay;   b.hour = 6; b.min = 0; b.sec = 0; b.day_of_week = 0; b.day_of_year = 0;
   bool summer = (gmt >= StructToTime(a) && gmt < StructToTime(b));
   g_nyOffset = (summer ? -4 : -5);
   return gmt + g_nyOffset * 3600;
}

bool InWindow(const int minutesOfDay, const int from, const int to)
{
   if(from <= to)
      return (minutesOfDay >= from && minutesOfDay < to);
   return (minutesOfDay >= from || minutesOfDay < to);      // a window over midnight
}

bool PastTime(const int minutesOfDay, const int at)
{
   return (minutesOfDay >= at);
}

//+------------------------------------------------------------------+
//| Account and terminal gates                                       |
//+------------------------------------------------------------------+
bool IsLiveAccount()
{
   return (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL);
}

string AccountModeWord()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode == ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO";
   if(mode == ACCOUNT_TRADE_MODE_CONTEST)
      return "CONTEST";
   if(mode == ACCOUNT_TRADE_MODE_REAL)
      return "REAL";
   return "UNKNOWN";
}

bool TerminalReady(string &why)
{
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      why = "the AutoTrading button in the toolbar is off";
      return false;
   }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      why = "Tools > Options > Expert Advisors > Allow algorithmic trading is off";
      return false;
   }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      why = "this account is not allowed to trade (investor password, or the broker closed it)";
      return false;
   }
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      why = "the broker disabled expert advisors on this account";
      return false;
   }
   if(g_liveBlocked)
   {
      why = "this is a REAL-money account and InpAllowLive is false";
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Indicators and the opening range                                 |
//+------------------------------------------------------------------+
bool LoadRates(const int count, MqlRates &rates[])
{
   int got = CopyRates(_Symbol, g_tf, 0, count, rates);
   if(got < 10)
      return false;
   ArraySetAsSeries(rates, true);
   return true;
}

double IndicatorValue(const int handle)
{
   double buffer[];
   if(CopyBuffer(handle, 0, 1, 1, buffer) != 1)
      return 0.0;
   return buffer[0];
}

bool TrendUp()
{
   if(!g_useTrend)
      return true;                        // the filter is off: the break alone decides
   double fast = IndicatorValue(g_emaFast);
   double slow = IndicatorValue(g_emaSlow);
   if(fast <= 0.0 || slow <= 0.0)
      return false;
   return (fast > slow);
}

bool TrendDown()
{
   if(!g_useTrend)
      return true;
   double fast = IndicatorValue(g_emaFast);
   double slow = IndicatorValue(g_emaSlow);
   if(fast <= 0.0 || slow <= 0.0)
      return false;
   return (fast < slow);
}

string TrendWord()
{
   if(!g_useTrend)
      return "filter off";
   double fast = IndicatorValue(g_emaFast);
   double slow = IndicatorValue(g_emaSlow);
   if(fast <= 0.0 || slow <= 0.0)
      return "flat (no EMA yet)";
   if(fast > slow)
      return "up";
   if(fast < slow)
      return "down";
   return "flat";
}

double AtrValue()
{
   double buffer[];
   if(CopyBuffer(g_atr, 0, 1, 1, buffer) != 1)
      return 0.0;
   return buffer[0];
}

// the handlers follow the settings: retune an EMA or the bar size from the
// panel and this rebuilds them, so the next bar is read with the new numbers
bool CreateHandles()
{
   if(g_emaFast != INVALID_HANDLE)
      IndicatorRelease(g_emaFast);
   if(g_emaSlow != INVALID_HANDLE)
      IndicatorRelease(g_emaSlow);
   if(g_atr != INVALID_HANDLE)
      IndicatorRelease(g_atr);

   g_emaFast = iMA(_Symbol, g_tf, MathMax(2, g_emaFastPeriod), 0, MODE_EMA, PRICE_CLOSE);
   g_emaSlow = iMA(_Symbol, g_tf, MathMax(5, g_emaSlowPeriod), 0, MODE_EMA, PRICE_CLOSE);
   g_atr     = iATR(_Symbol, g_tf, MathMax(2, g_atrPeriod));

   g_lastBarTime = 0;                     // the next tick re-reads the rule
   return (g_emaFast != INVALID_HANDLE && g_emaSlow != INVALID_HANDLE && g_atr != INVALID_HANDLE);
}

// the opening range of today's session: the high and the low of the bars
// that fall inside the first InpORMinutes of the session, in New York time
bool OpeningRange(double &rangeHigh, double &rangeLow, double &rangeMid, int &barsUsed)
{
   rangeHigh = 0.0;
   rangeLow  = 0.0;
   rangeMid  = 0.0;
   barsUsed  = 0;

   MqlRates rates[];
   if(!LoadRates(600, rates))
      return false;

   datetime nyNow = ToNewYork(TimeCurrent());
   int today = DayIndexOf(nyNow);
   int to    = g_sessionStart + g_orMinutes;

   for(int i = ArraySize(rates) - 1; i >= 0; i--)
   {
      datetime nyBar = ToNewYork(rates[i].time);
      if(DayIndexOf(nyBar) != today)
         continue;
      int mod = MinutesOfDay(nyBar);
      if(mod < g_sessionStart || mod >= to)
         continue;
      if(rangeHigh == 0.0 || rates[i].high > rangeHigh)
         rangeHigh = rates[i].high;
      if(rangeLow == 0.0 || rates[i].low < rangeLow)
         rangeLow = rates[i].low;
      barsUsed++;
   }

   if(barsUsed < 2 || rangeHigh <= 0.0 || rangeLow <= 0.0)
      return false;
   rangeMid = (rangeHigh + rangeLow) / 2.0;
   return true;
}

//+------------------------------------------------------------------+
//| The day's counters, from the account's own history               |
//+------------------------------------------------------------------+
int CountEntriesToday()
{
   datetime nyNow = ToNewYork(TimeCurrent());
   datetime from = nyNow - 3 * 86400;
   if(!HistorySelect(from, TimeCurrent() + 60))
      return 0;

   int count = 0;
   int today = DayIndexOf(nyNow);
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != g_magic)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      datetime nyDeal = ToNewYork((datetime)HistoryDealGetInteger(ticket, DEAL_TIME));
      if(DayIndexOf(nyDeal) == today)
         count++;
   }
   return count;
}

double RealisedToday()
{
   datetime nyNow = ToNewYork(TimeCurrent());
   datetime from = nyNow - 3 * 86400;
   if(!HistorySelect(from, TimeCurrent() + 60))
      return 0.0;

   double profit = 0.0;
   int today = DayIndexOf(nyNow);
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != g_magic)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      datetime nyDeal = ToNewYork((datetime)HistoryDealGetInteger(ticket, DEAL_TIME));
      if(DayIndexOf(nyDeal) != today)
         continue;
      profit += HistoryDealGetDouble(ticket, DEAL_PROFIT);
      profit += HistoryDealGetDouble(ticket, DEAL_SWAP);
      profit += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      profit += HistoryDealGetDouble(ticket, DEAL_FEE);
   }
   return profit;
}

//+------------------------------------------------------------------+
//| Sizing: the symbol's own tick value, then the volume ladder      |
//+------------------------------------------------------------------+
double MoneyPerLotPerPrice()
{
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;
   return tickValue / tickSize;            // account money for one lot, one full price unit
}

double RiskBudget()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double byPercent = (g_riskPct > 0.0 ? equity * g_riskPct / 100.0 : 0.0);
   double byMoney = g_riskMoney;
   if(byPercent > 0.0 && byMoney > 0.0)
      return MathMin(byPercent, byMoney);
   return (byPercent > 0.0 ? byPercent : byMoney);
}

double FloorToStep(const double volume)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;
   double lots = MathFloor(volume / step + 0.0000001) * step;
   return NormalizeDouble(lots, 2);
}

// the broker's own ladder: a close has to pass this, and only an entry also
// has to pass InpMaxLots
bool LadderFits(const double volume, string &why)
{
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(volume + 0.0000001 < vmin)
   {
      why = "under the broker's smallest lot (" + DoubleToString(vmin, 2) + ")";
      return false;
   }
   if(volume > vmax + 0.0000001)
   {
      why = "over the broker's largest lot (" + DoubleToString(vmax, 2) + ")";
      return false;
   }
   return true;
}

bool VolumeFits(const double volume, string &why)
{
   if(!LadderFits(volume, why))
      return false;
   if(volume > g_maxLots + 0.0000001)
   {
      why = "over InpMaxLots (" + DoubleToString(g_maxLots, 2) + ")";
      return false;
   }
   return true;
}

// how much margin this volume needs, and whether it fits our share of the free margin
bool MarginFits(const ENUM_ORDER_TYPE type, const double volume, const double price, string &why)
{
   double margin = 0.0;
   if(!OrderCalcMargin(type, _Symbol, volume, price, margin))
   {
      why = "the terminal could not price the margin";
      return false;
   }
   double free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double allowed = free * g_maxMarginPct / 100.0;
   if(margin > allowed)
   {
      why = "it needs " + DoubleToString(margin, 2) + " of margin, over " +
            DoubleToString(g_maxMarginPct, 0) + "% of free margin";
      return false;
   }
   return true;
}

// the volume whose risk at this stop is the risk budget, shrunk until it fits
double SizeLots(const double stopDistance, string &note)
{
   note = "";
   double budget = RiskBudget();
   double perLot = MoneyPerLotPerPrice() * stopDistance;
   if(budget <= 0.0 || perLot <= 0.0)
   {
      note = "no risk budget or no tick value";
      return 0.0;
   }
   double raw = budget / perLot;
   double lots = FloorToStep(raw);
   if(lots <= 0.0)
   {
      note = "the smallest lot risks more than the budget";
      return 0.0;
   }
   note = "risk budget " + DoubleToString(budget, 2) + ", " + DoubleToString(perLot, 2) + " per lot";
   return lots;
}

//+------------------------------------------------------------------+
//| The stops the broker will accept                                 |
//+------------------------------------------------------------------+
double MinStopPoints()
{
   double stopsLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double freeze = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double fromSpread = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return MathMax(stopsLevel, MathMax(freeze, fromSpread)) + (double)g_stopBuffer;
}

double SpreadPoints()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return 0.0;
   if(_Point <= 0.0)
      return 0.0;
   return (tick.ask - tick.bid) / _Point;
}

//+------------------------------------------------------------------+
//| Positions of ours                                                |
//+------------------------------------------------------------------+
int OurPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != g_magic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      count++;
   }
   return count;
}

string MarkName(const ulong ticket, const string what)
{
   return GATE_PREFIX + IntegerToString(g_magic) + "_" + IntegerToString((long)ticket) + "_" + what;
}

bool Marked(const ulong ticket, const string what)
{
   return GlobalVariableCheck(MarkName(ticket, what));
}

void Mark(const ulong ticket, const string what)
{
   GlobalVariableSet(MarkName(ticket, what), (double)TimeCurrent());
}

// forget the marks of positions that are gone, once a day
void PruneMarks()
{
   string prefix = GATE_PREFIX + IntegerToString(g_magic) + "_";
   int total = GlobalVariablesTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      string name = GlobalVariableName(i);
      if(StringFind(name, prefix) != 0)
         continue;
      string rest = StringSubstr(name, StringLen(prefix));
      string bits[];
      if(StringSplit(rest, '_', bits) < 2)
         continue;
      ulong ticket = (ulong)StringToInteger(bits[0]);
      if(!PositionSelectByTicket(ticket))
         GlobalVariableDel(name);
   }
}

//+------------------------------------------------------------------+
//| The self check: can it trade, and what exactly would it send     |
//+------------------------------------------------------------------+
//  Two questions every trader asks before trusting an EA: does it
//  actually talk to the terminal, and would the broker take its order?
//  The first is answered by the gates below, the second by sending the
//  exact request through the terminal's own OrderCheck(), which prices
//  and validates it and sends nothing at all.
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING FillingForSymbol()
{
   long modes = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((modes & SYMBOL_FILLING_FOK) != 0)
      return ORDER_FILLING_FOK;
   if((modes & SYMBOL_FILLING_IOC) != 0)
      return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

// the order the rule would build at this moment, for the TEST page and for
// the order check: same stop maths, same sizing, same target
bool PreviewOrder(string &side, double &lots, double &entry, double &stop, double &target,
                  double &distance, double &margin, string &why)
{
   side = "BUY";
   lots = 0.0;
   entry = 0.0;
   stop = 0.0;
   target = 0.0;
   distance = 0.0;
   margin = 0.0;
   why = "";

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
   {
      why = "no tick from the terminal";
      return false;
   }
   double atr = AtrValue();
   if(atr <= 0.0)
   {
      why = "the ATR is not ready yet";
      return false;
   }

   bool sell = (g_shorts && TrendDown() && !TrendUp());
   if(sell)
      side = "SELL";

   distance = MathMax(atr * g_atrMult, MinStopPoints() * _Point);
   if(distance <= 0.0)
   {
      why = "no stop distance";
      return false;
   }

   if(sell)
   {
      entry  = NormalizeDouble(tick.bid, _Digits);
      stop   = NormalizeDouble(entry + distance, _Digits);
      target = NormalizeDouble(entry - g_minRR * distance, _Digits);
   }
   else
   {
      entry  = NormalizeDouble(tick.ask, _Digits);
      stop   = NormalizeDouble(entry - distance, _Digits);
      target = NormalizeDouble(entry + g_minRR * distance, _Digits);
   }

   string note = "";
   lots = SizeLots(distance, note);
   if(lots <= 0.0)
   {
      lots = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
      why  = "the budget cannot cover one lot at this stop: " + note;
   }

   ENUM_ORDER_TYPE type = (sell ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
   if(!OrderCalcMargin(type, _Symbol, lots, entry, margin))
      why = (why == "" ? "the terminal could not price the margin" : why);

   return true;
}

// the eleven gates the EA checks before it sends anything, one at a time,
// so the chart can show which one is closed instead of a vague "no"
bool GatePass(const int which, string &detail)
{
   detail = "";
   datetime nyNow = ToNewYork(TimeCurrent());
   int minutes = MinutesOfDay(nyNow);

   if(which == 0)
   {
      bool ok = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
      detail = (ok ? "on" : "the AutoTrading button");
      return ok;
   }
   if(which == 1)
   {
      bool ok = MQLInfoInteger(MQL_TRADE_ALLOWED);
      detail = (ok ? "on" : "Options > Expert Advisors");
      return ok;
   }
   if(which == 2)
   {
      bool ok = AccountInfoInteger(ACCOUNT_TRADE_ALLOWED);
      detail = (ok ? AccountModeWord() : "the account cannot trade");
      return ok;
   }
   if(which == 3)
   {
      bool ok = AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
      detail = (ok ? "allowed" : "the broker disabled EAs");
      return ok;
   }
   if(which == 4)
   {
      bool ok = !g_liveBlocked;
      detail = (ok ? (IsLiveAccount() ? "REAL, InpAllowLive on" : "demo, never blocked") : "REAL and InpAllowLive is false");
      return ok;
   }
   if(which == 5)
   {
      bool weekend = (WeekdayOf(nyNow) == 0 || WeekdayOf(nyNow) == 6);
      bool ok = (!g_weekdaysOnly || !weekend);
      detail = (ok ? "a weekday" : "the weekend in New York");
      return ok;
   }
   if(which == 6)
   {
      bool ok = InWindow(minutes, g_sessionStart, g_sessionEnd);
      detail = (ok ? "inside " + HHMM(g_sessionStart) + "-" + HHMM(g_sessionEnd)
                   : "outside " + HHMM(g_sessionStart) + "-" + HHMM(g_sessionEnd));
      return ok;
   }
   if(which == 7)
   {
      int used = CountEntriesToday();
      bool ok = (used < g_maxTrades);
      detail = (ok ? IntegerToString(used) + " of " + IntegerToString(g_maxTrades)
                   : "the day's entries are used");
      return ok;
   }
   if(which == 8)
   {
      double realised = RealisedToday();
      bool ok = !(g_maxDailyLoss > 0.0 && realised <= -g_maxDailyLoss);
      detail = (ok ? Money(realised) : "the daily loss stop is hit");
      return ok;
   }
   if(which == 9)
   {
      double spread = SpreadPoints();
      bool ok = !(g_spreadMax > 0.0 && spread > g_spreadMax);
      detail = (ok ? DoubleToString(spread, 0) + " points" : "over the ceiling");
      return ok;
   }
   if(which == 10)
   {
      MqlRates rates[];
      bool ok = (LoadRates(10, rates) && AtrValue() > 0.0);
      detail = (ok ? "bars and ATR ready" : "no bars or no ATR yet");
      return ok;
   }
   detail = "unknown gate";
   return false;
}

// how many of the eleven are open, and the first one that is not
int GatesOpen(string &firstFail)
{
   firstFail = "";
   int open = 0;
   string detail = "";
   for(int i = 0; i < 11; i++)
   {
      if(GatePass(i, detail))
         open++;
      else if(firstFail == "")
         firstFail = detail;
   }
   return open;
}

// ask the terminal to validate the exact order, without sending it
void RunOrderCheck()
{
   string side = "";
   string why = "";
   double lots = 0.0, entry = 0.0, stop = 0.0, target = 0.0, distance = 0.0, margin = 0.0;
   if(!PreviewOrder(side, lots, entry, stop, target, distance, margin, why))
   {
      g_lastCheck = "no: " + why;
      Log("CHECK", "cannot build an order to test: " + why);
      return;
   }

   MqlTradeRequest      request;
   MqlTradeCheckResult  result;      // OrderCheck fills a check result, not a trade result
   ZeroMemory(request);
   ZeroMemory(result);

   request.action       = TRADE_ACTION_DEAL;
   request.symbol       = _Symbol;
   request.volume       = lots;
   request.type         = (side == "SELL" ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
   request.price        = entry;
   request.sl           = stop;
   request.tp           = target;
   request.deviation    = (ulong)g_deviation;
   request.magic        = (ulong)g_magic;
   request.comment      = "DayTraderMT5 order check, never sent";
   request.type_filling = FillingForSymbol();

   bool ok = OrderCheck(request, result);
   if(ok && (result.retcode == TRADE_RETCODE_DONE || result.retcode == 0))
   {
      g_lastCheck = "ok: margin " + Money(result.margin);
      Log("CHECK", StringFormat("%s %s %s lots at %s, stop %s, target %s: the terminal accepted the whole order and priced the margin at %s. Nothing was sent.",
                                side, _Symbol, DoubleToString(lots, 2), DoubleToString(entry, _Digits),
                                DoubleToString(stop, _Digits), DoubleToString(target, _Digits),
                                Money(result.margin)));
      return;
   }

   g_lastCheck = "no: " + IntegerToString((int)result.retcode) + " " + result.comment;
   Log("CHECK", StringFormat("%s %s %s lots: the terminal refused it, %d %s. Nothing was sent.",
                             side, _Symbol, DoubleToString(lots, 2), (int)result.retcode, result.comment));
}

//+------------------------------------------------------------------+
//| Settings: the panel can retune every number, and remember it     |
//+------------------------------------------------------------------+
//  Every click on the chart writes the whole table to the terminal's
//  global variables (DTMT5_C_<id>), so a chart change or a restart
//  keeps what you set. The inputs are still the factory defaults:
//  RESET puts them back.
//+------------------------------------------------------------------+
double ClampD(const double value, const double low, const double high)
{
   if(value < low)
      return low;
   if(value > high)
      return high;
   return value;
}

int ClampI(const int value, const int low, const int high)
{
   if(value < low)
      return low;
   if(value > high)
      return high;
   return value;
}

int WrapMinutes(const int minutes)
{
   int m = minutes % 1440;
   if(m < 0)
      m += 1440;
   return m;
}

void Notify(const string text)
{
   if(g_alertPopup)
      Alert(text);
   if(g_alertSound)
      PlaySound("alert2.wav");
   if(g_alertPush)
      SendNotification(text);
}

void SaveSettings()
{
   GlobalVariableSet(CFG_PREFIX + "risk_pct",    g_riskPct);
   GlobalVariableSet(CFG_PREFIX + "risk_money",  g_riskMoney);
   GlobalVariableSet(CFG_PREFIX + "max_lots",    g_maxLots);
   GlobalVariableSet(CFG_PREFIX + "margin_pct",  g_maxMarginPct);
   GlobalVariableSet(CFG_PREFIX + "spread_max",  g_spreadMax);
   GlobalVariableSet(CFG_PREFIX + "min_rr",      g_minRR);
   GlobalVariableSet(CFG_PREFIX + "daily_loss",  g_maxDailyLoss);
   GlobalVariableSet(CFG_PREFIX + "max_trades",  (double)g_maxTrades);
   GlobalVariableSet(CFG_PREFIX + "or_min",      (double)g_orMinutes);
   GlobalVariableSet(CFG_PREFIX + "atr_mult",    g_atrMult);
   GlobalVariableSet(CFG_PREFIX + "atr_period",  (double)g_atrPeriod);
   GlobalVariableSet(CFG_PREFIX + "min_range",   g_minRangePoints);
   GlobalVariableSet(CFG_PREFIX + "ema_fast",    (double)g_emaFastPeriod);
   GlobalVariableSet(CFG_PREFIX + "ema_slow",    (double)g_emaSlowPeriod);
   GlobalVariableSet(CFG_PREFIX + "tf",          (double)g_tf);
   GlobalVariableSet(CFG_PREFIX + "trend",       (g_useTrend ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "shorts",      (g_shorts ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "ny",          (g_newYork ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "weekdays",    (g_weekdaysOnly ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "ses_start",   (double)g_sessionStart);
   GlobalVariableSet(CFG_PREFIX + "ses_end",     (double)g_sessionEnd);
   GlobalVariableSet(CFG_PREFIX + "flat_by",     (double)g_flatBy);
   GlobalVariableSet(CFG_PREFIX + "be_r",        g_beAtR);
   GlobalVariableSet(CFG_PREFIX + "trail_r",     g_trailAtR);
   GlobalVariableSet(CFG_PREFIX + "trail_pts",   (double)g_trailPoints);
   GlobalVariableSet(CFG_PREFIX + "part_r",      g_partialAtR);
   GlobalVariableSet(CFG_PREFIX + "part_pct",    g_partialPct);
   GlobalVariableSet(CFG_PREFIX + "deviation",   (double)g_deviation);
   GlobalVariableSet(CFG_PREFIX + "stop_buffer", (double)g_stopBuffer);
   GlobalVariableSet(CFG_PREFIX + "alert_popup", (g_alertPopup ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "alert_sound", (g_alertSound ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "alert_push",  (g_alertPush ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "verbose",     (g_verbose ? 1.0 : 0.0));
   GlobalVariableSet(CFG_PREFIX + "heartbeat",   (double)g_heartbeat);
}

bool CfgHas(const string id)
{
   return GlobalVariableCheck(CFG_PREFIX + id);
}

double CfgGet(const string id, const double fallback)
{
   if(!CfgHas(id))
      return fallback;
   return GlobalVariableGet(CFG_PREFIX + id);
}

void ApplyInputDefaults()
{
   g_tf             = InpTimeframe;
   g_emaFastPeriod  = MathMax(2, InpEmaFast);
   g_emaSlowPeriod  = MathMax(5, InpEmaSlow);
   g_useTrend       = InpUseTrend;
   g_atrPeriod      = MathMax(2, InpAtrPeriod);
   g_minRangePoints = MathMax(0.0, InpMinRangePoints);
   g_riskPct        = MathMax(0.0, InpRiskPercent);
   g_riskMoney      = MathMax(0.0, InpRiskMoney);
   g_maxLots        = MathMax(0.01, InpMaxLots);
   g_maxMarginPct   = MathMin(100.0, MathMax(1.0, InpMaxMarginPct));
   g_spreadMax      = MathMax(0.0, InpMaxSpreadPoints);
   g_minRR          = MathMax(0.1, InpMinRR);
   g_maxDailyLoss   = MathMax(0.0, InpMaxDailyLoss);
   g_maxTrades      = MathMax(1, InpMaxTradesPerDay);
   g_orMinutes      = MathMax(5, InpORMinutes);
   g_atrMult        = MathMax(0.1, InpAtrMult);
   g_shorts         = InpAllowShort;
   g_newYork        = InpNewYorkTimes;
   g_weekdaysOnly   = InpWeekdaysOnly;
   g_beAtR          = MathMax(0.0, InpBreakevenAtR);
   g_trailAtR       = MathMax(0.0, InpTrailAtR);
   g_trailPoints    = MathMax(10, InpTrailPoints);
   g_partialAtR     = MathMax(0.0, InpPartialAtR);
   g_partialPct     = MathMin(90.0, MathMax(10.0, InpPartialPercent));
   g_deviation      = MathMax(1, InpDeviationPoints);
   g_stopBuffer     = MathMax(0, InpStopBufferPoints);
   g_alertPopup     = InpAlertPopup;
   g_alertSound     = InpAlertSound;
   g_alertPush      = InpAlertPush;
   g_verbose        = InpVerbose;
   g_heartbeat      = MathMax(0, InpHeartbeatMinutes);
   g_panelX         = (int)MathMax(0, InpPanelX);
   g_panelY         = (int)MathMax(0, InpPanelY);
   g_showPanel      = InpShowPanel;
   g_dryRun         = InpDryRun;
   g_allowLive      = InpAllowLive;
   g_magic          = InpMagic;
}

// anything the panel saved overrides the input, with the same clamps
void LoadSettings()
{
   int restored = 0;
   if(CfgHas("risk_pct"))    { g_riskPct      = ClampD(CfgGet("risk_pct", g_riskPct), 0.0, 100.0); restored++; }
   if(CfgHas("risk_money"))  { g_riskMoney    = ClampD(CfgGet("risk_money", g_riskMoney), 0.0, 10000000.0); restored++; }
   if(CfgHas("max_lots"))    { g_maxLots      = ClampD(CfgGet("max_lots", g_maxLots), 0.01, 1000.0); restored++; }
   if(CfgHas("margin_pct"))  { g_maxMarginPct = ClampD(CfgGet("margin_pct", g_maxMarginPct), 1.0, 100.0); restored++; }
   if(CfgHas("spread_max"))  { g_spreadMax    = ClampD(CfgGet("spread_max", g_spreadMax), 0.0, 100000.0); restored++; }
   if(CfgHas("min_rr"))      { g_minRR        = ClampD(CfgGet("min_rr", g_minRR), 0.1, 100.0); restored++; }
   if(CfgHas("daily_loss"))  { g_maxDailyLoss = ClampD(CfgGet("daily_loss", g_maxDailyLoss), 0.0, 10000000.0); restored++; }
   if(CfgHas("max_trades"))  { g_maxTrades    = ClampI((int)CfgGet("max_trades", g_maxTrades), 1, 100); restored++; }
   if(CfgHas("or_min"))      { g_orMinutes    = ClampI((int)CfgGet("or_min", g_orMinutes), 5, 600); restored++; }
   if(CfgHas("atr_mult"))    { g_atrMult      = ClampD(CfgGet("atr_mult", g_atrMult), 0.1, 20.0); restored++; }
   if(CfgHas("atr_period"))  { g_atrPeriod    = ClampI((int)CfgGet("atr_period", g_atrPeriod), 2, 200); restored++; }
   if(CfgHas("min_range"))   { g_minRangePoints = ClampD(CfgGet("min_range", g_minRangePoints), 0.0, 100000.0); restored++; }
   if(CfgHas("ema_fast"))    { g_emaFastPeriod = ClampI((int)CfgGet("ema_fast", g_emaFastPeriod), 2, 1000); restored++; }
   if(CfgHas("ema_slow"))    { g_emaSlowPeriod = ClampI((int)CfgGet("ema_slow", g_emaSlowPeriod), 5, 2000); restored++; }
   if(CfgHas("tf"))          { g_tf = (ENUM_TIMEFRAMES)ClampI((int)CfgGet("tf", (double)g_tf), 1, 49153); restored++; }
   if(CfgHas("trend"))       { g_useTrend     = (CfgGet("trend", 1.0) > 0.5); restored++; }
   if(CfgHas("shorts"))      { g_shorts       = (CfgGet("shorts", 0.0) > 0.5); restored++; }
   if(CfgHas("ny"))          { g_newYork      = (CfgGet("ny", 1.0) > 0.5); restored++; }
   if(CfgHas("weekdays"))    { g_weekdaysOnly = (CfgGet("weekdays", 1.0) > 0.5); restored++; }
   if(CfgHas("ses_start"))   { g_sessionStart = WrapMinutes((int)CfgGet("ses_start", g_sessionStart)); restored++; }
   if(CfgHas("ses_end"))     { g_sessionEnd   = WrapMinutes((int)CfgGet("ses_end", g_sessionEnd)); restored++; }
   if(CfgHas("flat_by"))     { g_flatBy       = WrapMinutes((int)CfgGet("flat_by", g_flatBy)); restored++; }
   if(CfgHas("be_r"))        { g_beAtR        = ClampD(CfgGet("be_r", g_beAtR), 0.0, 100.0); restored++; }
   if(CfgHas("trail_r"))     { g_trailAtR     = ClampD(CfgGet("trail_r", g_trailAtR), 0.0, 100.0); restored++; }
   if(CfgHas("trail_pts"))   { g_trailPoints  = ClampI((int)CfgGet("trail_pts", g_trailPoints), 1, 100000); restored++; }
   if(CfgHas("part_r"))      { g_partialAtR   = ClampD(CfgGet("part_r", g_partialAtR), 0.0, 100.0); restored++; }
   if(CfgHas("part_pct"))    { g_partialPct   = ClampD(CfgGet("part_pct", g_partialPct), 10.0, 90.0); restored++; }
   if(CfgHas("deviation"))   { g_deviation    = ClampI((int)CfgGet("deviation", g_deviation), 1, 10000); restored++; }
   if(CfgHas("stop_buffer")) { g_stopBuffer   = ClampI((int)CfgGet("stop_buffer", g_stopBuffer), 0, 100000); restored++; }
   if(CfgHas("alert_popup")) { g_alertPopup   = (CfgGet("alert_popup", 1.0) > 0.5); restored++; }
   if(CfgHas("alert_sound")) { g_alertSound   = (CfgGet("alert_sound", 0.0) > 0.5); restored++; }
   if(CfgHas("alert_push"))  { g_alertPush    = (CfgGet("alert_push", 0.0) > 0.5); restored++; }
   if(CfgHas("verbose"))     { g_verbose      = (CfgGet("verbose", 0.0) > 0.5); restored++; }
   if(CfgHas("heartbeat"))   { g_heartbeat    = ClampI((int)CfgGet("heartbeat", g_heartbeat), 0, 240); restored++; }
   if(restored > 0)
      Log("CONF", StringFormat("%d setting(s) restored from what you set on the chart last time", restored));
}

void ForgetSettings()
{
   string prefix = CFG_PREFIX;
   for(int i = GlobalVariablesTotal() - 1; i >= 0; i--)
   {
      string name = GlobalVariableName(i);
      if(StringFind(name, prefix) == 0)
         GlobalVariableDel(name);
   }
}

// the factory numbers are the inputs; the panel's saved table is thrown away
void ResetSettings(const string scope)
{
   ForgetSettings();
   ApplyInputDefaults();
   if(!ParseHHMM(InpSessionStart, g_sessionStart) ||
      !ParseHHMM(InpSessionEnd,   g_sessionEnd)   ||
      !ParseHHMM(InpFlatBy,       g_flatBy))
      Log("ERROR", "a time input is not HH:MM: the previous times stay in place");
   g_sessionStart = WrapMinutes(g_sessionStart);
   g_sessionEnd   = WrapMinutes(g_sessionEnd);
   g_flatBy       = WrapMinutes(g_flatBy);
   CreateHandles();
   g_confirmReset = false;
   Log("CTRL", "settings reset to the inputs (" + scope + ")");
   Notify("DayTraderMT5: settings reset (" + scope + ")");
}

// every click ends here: one id, one direction (-1 down, +1 up, 0 toggle,
// 2 next in a cycle, -2 previous)
bool AdjustSetting(const string id, const int dir)
{
   bool reshaped = false;
   string shown = "";

   if(id == "tf")
   {
      int order[5] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1};
      int at = 1;
      for(int i = 0; i < 5; i++)
         if(order[i] == (int)g_tf)
            at = i;
      at = (at + (dir > 0 ? 1 : 4)) % 5;
      g_tf = (ENUM_TIMEFRAMES)order[at];
      reshaped = true;
      shown = PeriodDescription(g_tf);
   }
   else if(id == "ema_fast")
   {
      g_emaFastPeriod = ClampI(g_emaFastPeriod + dir * 5, 2, 400);
      reshaped = true;
      shown = IntegerToString(g_emaFastPeriod);
   }
   else if(id == "ema_slow")
   {
      g_emaSlowPeriod = ClampI(g_emaSlowPeriod + dir * 10, 5, 800);
      reshaped = true;
      shown = IntegerToString(g_emaSlowPeriod);
   }
   else if(id == "atr_period")
   {
      g_atrPeriod = ClampI(g_atrPeriod + dir, 2, 50);
      reshaped = true;
      shown = IntegerToString(g_atrPeriod);
   }
   else if(id == "or_min")
   {
      g_orMinutes = ClampI(g_orMinutes + dir * 5, 5, 240);
      shown = IntegerToString(g_orMinutes) + " min";
   }
   else if(id == "atr_mult")
   {
      g_atrMult = ClampD(NormalizeDouble(g_atrMult + dir * 0.1, 2), 0.1, 3.0);
      shown = DoubleToString(g_atrMult, 1) + " ATR";
   }
   else if(id == "min_range")
   {
      g_minRangePoints = ClampD(g_minRangePoints + dir * 10.0, 0.0, 5000.0);
      shown = (g_minRangePoints <= 0.0 ? "off" : DoubleToString(g_minRangePoints, 0) + " points");
   }
   else if(id == "min_rr")
   {
      g_minRR = ClampD(NormalizeDouble(g_minRR + dir * 0.1, 2), 1.0, 5.0);
      shown = DoubleToString(g_minRR, 1) + "R";
   }
   else if(id == "risk_pct")
   {
      g_riskPct = ClampD(NormalizeDouble(g_riskPct + dir * 0.25, 2), 0.0, 10.0);
      shown = DoubleToString(g_riskPct, 2) + "%";
   }
   else if(id == "risk_money")
   {
      g_riskMoney = ClampD(g_riskMoney + dir * 10.0, 0.0, 1000000.0);
      shown = Money(g_riskMoney);
   }
   else if(id == "max_lots")
   {
      g_maxLots = ClampD(NormalizeDouble(g_maxLots + dir * 0.1, 2), 0.01, 500.0);
      shown = DoubleToString(g_maxLots, 2) + " lots";
   }
   else if(id == "margin_pct")
   {
      g_maxMarginPct = ClampD(g_maxMarginPct + dir * 5.0, 5.0, 100.0);
      shown = DoubleToString(g_maxMarginPct, 0) + "%";
   }
   else if(id == "spread_max")
   {
      g_spreadMax = ClampD(g_spreadMax + dir * 5.0, 0.0, 1000.0);
      shown = (g_spreadMax <= 0.0 ? "off" : DoubleToString(g_spreadMax, 0) + " points");
   }
   else if(id == "daily_loss")
   {
      g_maxDailyLoss = ClampD(g_maxDailyLoss + dir * 25.0, 0.0, 1000000.0);
      shown = (g_maxDailyLoss <= 0.0 ? "off" : Money(g_maxDailyLoss));
   }
   else if(id == "max_trades")
   {
      g_maxTrades = ClampI(g_maxTrades + dir, 1, 20);
      shown = IntegerToString(g_maxTrades) + " a day";
   }
   else if(id == "ses_start")
   {
      g_sessionStart = WrapMinutes(g_sessionStart + dir * 5);
      shown = HHMM(g_sessionStart);
   }
   else if(id == "ses_end")
   {
      g_sessionEnd = WrapMinutes(g_sessionEnd + dir * 5);
      shown = HHMM(g_sessionEnd);
   }
   else if(id == "flat_by")
   {
      g_flatBy = WrapMinutes(g_flatBy + dir * 5);
      shown = HHMM(g_flatBy);
   }
   else if(id == "be_r")
   {
      g_beAtR = ClampD(NormalizeDouble(g_beAtR + dir * 0.1, 2), 0.0, 5.0);
      shown = (g_beAtR <= 0.0 ? "off" : DoubleToString(g_beAtR, 1) + "R");
   }
   else if(id == "trail_r")
   {
      g_trailAtR = ClampD(NormalizeDouble(g_trailAtR + dir * 0.1, 2), 0.0, 5.0);
      shown = (g_trailAtR <= 0.0 ? "off" : DoubleToString(g_trailAtR, 1) + "R");
   }
   else if(id == "trail_pts")
   {
      g_trailPoints = ClampI(g_trailPoints + dir * 10, 10, 5000);
      shown = IntegerToString(g_trailPoints) + " points";
   }
   else if(id == "part_r")
   {
      g_partialAtR = ClampD(NormalizeDouble(g_partialAtR + dir * 0.1, 2), 0.0, 5.0);
      shown = (g_partialAtR <= 0.0 ? "off" : DoubleToString(g_partialAtR, 1) + "R");
   }
   else if(id == "part_pct")
   {
      g_partialPct = ClampD(g_partialPct + dir * 5.0, 10.0, 90.0);
      shown = DoubleToString(g_partialPct, 0) + "%";
   }
   else if(id == "deviation")
   {
      g_deviation = ClampI(g_deviation + dir * 5, 1, 500);
      g_trade.SetDeviationInPoints((ulong)g_deviation);
      shown = IntegerToString(g_deviation) + " points";
   }
   else if(id == "stop_buffer")
   {
      g_stopBuffer = ClampI(g_stopBuffer + dir * 5, 0, 500);
      shown = IntegerToString(g_stopBuffer) + " points";
   }
   else if(id == "trend")
   {
      g_useTrend = !g_useTrend;
      shown = (g_useTrend ? "on" : "off");
   }
   else if(id == "shorts")
   {
      g_shorts = !g_shorts;
      shown = (g_shorts ? "on" : "off");
   }
   else if(id == "ny")
   {
      g_newYork = !g_newYork;
      shown = (g_newYork ? "New York" : "server time");
   }
   else if(id == "weekdays")
   {
      g_weekdaysOnly = !g_weekdaysOnly;
      shown = (g_weekdaysOnly ? "on" : "off");
   }
   else if(id == "alert_popup")
   {
      g_alertPopup = !g_alertPopup;
      shown = (g_alertPopup ? "on" : "off");
   }
   else if(id == "alert_sound")
   {
      g_alertSound = !g_alertSound;
      shown = (g_alertSound ? "on" : "off");
   }
   else if(id == "alert_push")
   {
      g_alertPush = !g_alertPush;
      shown = (g_alertPush ? "on" : "off");
   }
   else if(id == "verbose")
   {
      g_verbose = !g_verbose;
      shown = (g_verbose ? "on" : "off");
   }
   else if(id == "heartbeat")
   {
      g_heartbeat = ClampI(g_heartbeat + dir * 5, 0, 240);
      shown = (g_heartbeat <= 0 ? "off" : IntegerToString(g_heartbeat) + " min");
   }
   else
      return false;

   // a session whose ends are the same minute can never trade
   if(id == "ses_start" || id == "ses_end")
   {
      if(g_sessionStart == g_sessionEnd)
      {
         if(id == "ses_start")
            g_sessionStart = WrapMinutes(g_sessionEnd - 60);
         else
            g_sessionEnd = WrapMinutes(g_sessionStart + 60);
         Log("CTRL", "the session ends cannot be the same minute: moved to " + HHMM(g_sessionStart) + "-" + HHMM(g_sessionEnd));
      }
   }

   if(reshaped && !CreateHandles())
      Log("ERROR", "could not rebuild the indicators: " + IntegerToString(GetLastError()));

   SaveSettings();
   Log("CTRL", "setting " + id + " is now " + shown);
   return true;
}

//+------------------------------------------------------------------+
//| Entry                                                            |
//+------------------------------------------------------------------+
void TryEntry()
{
   datetime nyNow = ToNewYork(TimeCurrent());
   int nowMinutes = MinutesOfDay(nyNow);
   int orEnd = g_sessionStart + g_orMinutes;

   // 1) the opening range: the high and the low of today's first bars
   double rangeHigh = 0.0, rangeLow = 0.0, rangeMid = 0.0;
   int orBars = 0;
   if(!OpeningRange(rangeHigh, rangeLow, rangeMid, orBars))
   {
      LogRule("norange", "no opening range yet: the session has not printed two bars inside " +
                         HHMM(g_sessionStart) + "-" + HHMM(orEnd) + " New York");
      return;
   }
   if(nowMinutes < orEnd)
   {
      LogRule("forming", StringFormat("opening range still forming: %d bar(s), %s - %s, done at %s",
                                      orBars, DoubleToString(rangeLow, _Digits),
                                      DoubleToString(rangeHigh, _Digits), HHMM(orEnd)));
      return;
   }
   LogRule("range", StringFormat("opening range %s - %s, mid %s, %d bars, %s points wide",
                                 DoubleToString(rangeLow, _Digits), DoubleToString(rangeHigh, _Digits),
                                 DoubleToString(rangeMid, _Digits), orBars,
                                 DoubleToString((rangeHigh - rangeLow) / _Point, 0)));
   if(g_minRangePoints > 0.0 && (rangeHigh - rangeLow) / _Point < g_minRangePoints)
   {
      LogRule("narrow", StringFormat("opening range is %s points, under the floor you set (%s): no entries today",
                                     DoubleToString((rangeHigh - rangeLow) / _Point, 0),
                                     DoubleToString(g_minRangePoints, 0)));
      return;
   }

   // 2) the break, measured on the last CLOSED bar and filtered by the EMAs
   MqlRates rates[];
   if(!LoadRates(10, rates))
   {
      LogRule("norates", "no bars from the terminal for " + _Symbol + " " + PeriodDescription(g_tf));
      return;
   }
   double lastClose = rates[1].close;                     // the last CLOSED bar
   double atr = AtrValue();
   if(atr <= 0.0)
   {
      LogRule("noatr", "the ATR is not ready yet");
      return;
   }

   bool buy  = (lastClose > rangeHigh && TrendUp());
   bool sell = (g_shorts && lastClose < rangeLow && TrendDown());

   if(!buy && !sell)
   {
      string where = "inside the range";
      if(lastClose > rangeHigh)
         where = "above the range, but the trend filter disagrees";
      else if(lastClose < rangeLow)
      {
         where = "below the range, but the trend filter disagrees";
         if(!g_shorts)
            where = "below the range, but short entries are off (InpAllowShort)";
      }
      LogRule("wait", StringFormat("waiting: %s %s closed %s, %s (range %s - %s, trend %s)",
                                   _Symbol, PeriodDescription(g_tf),
                                   DoubleToString(lastClose, _Digits), where,
                                   DoubleToString(rangeLow, _Digits), DoubleToString(rangeHigh, _Digits),
                                   TrendWord()));
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
   {
      Log("ERROR", "no tick from the terminal for " + _Symbol + ": nothing can be priced");
      return;
   }

   string side = (buy ? "BUY" : "SELL");
   string head = StringFormat("%s signal: %s closed %s, %s the range (%s - %s), trend %s",
                              side, PeriodDescription(g_tf), DoubleToString(lastClose, _Digits),
                              (buy ? "above" : "below"),
                              DoubleToString(rangeLow, _Digits), DoubleToString(rangeHigh, _Digits),
                              TrendWord());
   Log("SIGNAL", head);

   // 3) the gates, in the order that would change your mind
   string gate = "";
   if(g_weekdaysOnly && (WeekdayOf(nyNow) == 0 || WeekdayOf(nyNow) == 6))
      gate = "it is the weekend in New York";
   else if(!InWindow(nowMinutes, g_sessionStart, g_sessionEnd))
      gate = "outside the session " + HHMM(g_sessionStart) + "-" + HHMM(g_sessionEnd) +
             " New York (now " + HHMM(nowMinutes) + ")";
   else if(g_paused)
      gate = "entries are paused from the dashboard";
   else if(OurPositions() > 0)
      gate = "a position of ours is already open";
   else if(CountEntriesToday() >= g_maxTrades)
      gate = StringFormat("the daily entry limit is used (%d of %d)", CountEntriesToday(), g_maxTrades);
   else if(g_maxDailyLoss > 0.0 && RealisedToday() <= -g_maxDailyLoss)
      gate = "the daily loss stop: realised " + Money(RealisedToday()) +
             " against a limit of " + Money(g_maxDailyLoss);
   else if(g_spreadMax > 0.0 && SpreadPoints() > g_spreadMax)
      gate = "the spread is " + DoubleToString(SpreadPoints(), 0) + " points, over your ceiling of " +
             DoubleToString(g_spreadMax, 0);

   if(gate != "")
   {
      Log("BLOCK", StringFormat("%s -> skipped: %s", side, gate));
      return;
   }

   string readyWhy = "";
   if(!TerminalReady(readyWhy))
   {
      Log("BLOCK", StringFormat("%s -> skipped: %s", side, readyWhy));
      return;
   }

   // 4) the stop, the target, the size
   double minPoints = MinStopPoints();
   double minDistance = minPoints * _Point;

   double entry, stop, target;
   ENUM_ORDER_TYPE type;
   if(buy)
   {
      entry = NormalizeDouble(tick.ask, _Digits);
      // half an ATR behind the entry, never tighter than the range's midpoint
      stop = MathMin(entry - g_atrMult * atr, rangeMid);
      stop = NormalizeDouble(stop, _Digits);
      if(entry - stop < minDistance)
         stop = NormalizeDouble(entry - minDistance, _Digits);
      target = NormalizeDouble(entry + g_minRR * (entry - stop), _Digits);
      type = ORDER_TYPE_BUY;
   }
   else
   {
      entry = NormalizeDouble(tick.bid, _Digits);
      stop = MathMax(entry + g_atrMult * atr, rangeMid);
      stop = NormalizeDouble(stop, _Digits);
      if(stop - entry < minDistance)
         stop = NormalizeDouble(entry + minDistance, _Digits);
      target = NormalizeDouble(entry - g_minRR * (stop - entry), _Digits);
      type = ORDER_TYPE_SELL;
   }

   double distance = MathAbs(entry - stop);
   if(distance < minDistance)
   {
      Log("BLOCK", StringFormat("no order: the stop is %s points away and the broker needs %s",
                                DoubleToString(distance / _Point, 0), DoubleToString(minPoints, 0)));
      return;
   }
   double rr = MathAbs(target - entry) / distance;
   if(rr + 0.0001 < g_minRR)
   {
      Log("BLOCK", StringFormat("no order: the rounded target is %.2fR, under your %.2fR", rr, g_minRR));
      return;
   }

   string note = "";
   double lots = SizeLots(distance, note);
   string why = "";
   if(lots <= 0.0 || !VolumeFits(lots, why))
   {
      Log("BLOCK", "no order: " + (note == "" ? why : note) + (why == "" ? "" : " (" + why + ")"));
      return;
   }
   if(!MarginFits(type, lots, entry, why))
   {
      Log("BLOCK", "no order: " + why);
      return;
   }

   Log("SIZE", StringFormat("%s lots, stop %s (%s points, ATR %.2f x %s), target %s (%.2fR)",
                            DoubleToString(lots, 2), DoubleToString(stop, _Digits),
                            DoubleToString(distance / _Point, 0), g_atrMult,
                            DoubleToString(atr, _Digits), DoubleToString(target, _Digits), rr));
   Log("RISK", note + ", budget " + Money(RiskBudget()) + ", margin under " +
              DoubleToString(g_maxMarginPct, 0) + "% of free");

   string summary = StringFormat("%s %s %s lots at %s, stop %s, target %s (%.2fR)",
                                 side, _Symbol, DoubleToString(lots, 2), DoubleToString(entry, _Digits),
                                 DoubleToString(stop, _Digits), DoubleToString(target, _Digits), rr);

   if(g_dryRun)
   {
      Log("ORDER", "DRY RUN: would have sent " + summary);
      return;
   }

   Log("ORDER", "sending " + summary);
   bool sent = false;
   string comment = "dtcli orb " + TimeToString(nyNow, TIME_DATE);
   if(buy)
      sent = g_trade.Buy(lots, _Symbol, 0.0, stop, target, comment);
   else
      sent = g_trade.Sell(lots, _Symbol, 0.0, stop, target, comment);

   if(sent && g_trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      g_lastRetcode = "done";
      Log("ORDER", StringFormat("accepted: order #%d, deal #%d at %s, %s lots",
                                (int)g_trade.ResultOrder(), (int)g_trade.ResultDeal(),
                                DoubleToString(g_trade.ResultPrice(), _Digits), DoubleToString(lots, 2)));
      Notify(StringFormat("DayTraderMT5: %s %s %s lots at %s, stop %s, target %s",
                          side, _Symbol, DoubleToString(lots, 2),
                          DoubleToString(g_trade.ResultPrice(), _Digits),
                          DoubleToString(stop, _Digits), DoubleToString(target, _Digits)));
   }
   else
   {
      g_lastRetcode = IntegerToString(g_trade.ResultRetcode());
      Log("ERROR", StringFormat("refused: %d %s", (int)g_trade.ResultRetcode(),
                                g_trade.ResultRetcodeDescription()));
   }
}

//+------------------------------------------------------------------+
//| Managing what is open: breakeven, trailing, a partial            |
//+------------------------------------------------------------------+
void ManagePositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != g_magic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      long type = PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double current = (type == POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                  : SymbolInfoDouble(_Symbol, SYMBOL_ASK));
      if(current <= 0.0)
         continue;

      // R comes from the target we set: |TP - entry| / the RR it was built from.
      // It does not change when the stop moves, which is what makes breakeven
      // and trailing stable across restarts.
      double targetDistance = MathAbs(tp - open);
      if(targetDistance <= 0.0 || g_minRR <= 0.0)
         continue;
      double rDistance = targetDistance / g_minRR;
      if(rDistance <= 0.0)
         continue;
      double progress = (type == POSITION_TYPE_BUY ? (current - open) : (open - current)) / rDistance;

      double minDistance = MinStopPoints() * _Point;

      // 1) take part of it
      if(g_partialAtR > 0.0 && progress >= g_partialAtR && !Marked(ticket, "partial"))
      {
         double closeVolume = FloorToStep(volume * g_partialPct / 100.0);
         double left = NormalizeDouble(volume - closeVolume, 2);
         string why = "";
         if(closeVolume > 0.0 && LadderFits(closeVolume, why) && LadderFits(left, why))
         {
            if(g_dryRun)
               Log("MANAGE", StringFormat("DRY RUN: would have taken %s lots of #%d at %.2fR",
                                          DoubleToString(closeVolume, 2), (int)ticket, progress));
            else if(g_trade.PositionClosePartial(ticket, closeVolume))
            {
               Mark(ticket, "partial");
               Log("MANAGE", StringFormat("took %s lots of #%d at %.2fR, %s lots left",
                                          DoubleToString(closeVolume, 2), (int)ticket, progress,
                                          DoubleToString(left, 2)));
            }
            else
               Log("ERROR", StringFormat("the partial on #%d was refused: %d %s", (int)ticket,
                                         (int)g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()));
         }
      }

      // 2) breakeven
      if(g_beAtR > 0.0 && progress >= g_beAtR && !Marked(ticket, "breakeven"))
      {
         double be = NormalizeDouble(open, _Digits);
         bool better = (type == POSITION_TYPE_BUY ? (sl < be) : (sl > be || sl == 0.0));
         bool farEnough = (type == POSITION_TYPE_BUY ? (current - be >= minDistance) : (be - current >= minDistance));
         if(better && farEnough)
         {
            if(g_dryRun)
               Log("MANAGE", StringFormat("DRY RUN: would have moved #%d's stop to the entry %s",
                                          (int)ticket, DoubleToString(be, _Digits)));
            else if(g_trade.PositionModify(ticket, be, tp))
            {
               Mark(ticket, "breakeven");
               Log("MANAGE", StringFormat("#%d: stop to the entry %s at %.2fR",
                                          (int)ticket, DoubleToString(be, _Digits), progress));
            }
         }
      }

      // 3) trail it, after the R you asked for
      if(g_trailAtR > 0.0 && progress >= g_trailAtR)
      {
         double trailDistance = g_trailPoints * _Point;
         double wanted = (type == POSITION_TYPE_BUY ? current - trailDistance : current + trailDistance);
         wanted = NormalizeDouble(wanted, _Digits);
         // a fifth of the trail, and never less than the broker allows: a stop
         // that only creeps by a point is a request for a rejection
         double step = MathMax(minDistance, trailDistance * 0.2);
         bool better = (type == POSITION_TYPE_BUY
                        ? (wanted > sl + step && wanted < current - minDistance)
                        : ((wanted < sl - step || sl == 0.0) && wanted > current + minDistance));
         if(better)
         {
            if(g_dryRun)
               Log("MANAGE", StringFormat("DRY RUN: would have trailed #%d's stop to %s",
                                          (int)ticket, DoubleToString(wanted, _Digits)));
            else if(g_trade.PositionModify(ticket, wanted, tp))
               Log("MANAGE", StringFormat("#%d: stop trailed to %s at %.2fR",
                                          (int)ticket, DoubleToString(wanted, _Digits), progress));
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Flat by: nothing of ours survives the time you set                |
//+------------------------------------------------------------------+
void CloseAllOurs(const int reasonMinutes, const string why)
{
   int closed = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != g_magic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      double volume = PositionGetDouble(POSITION_VOLUME);
      if(g_dryRun)
      {
         Log("FLAT", StringFormat("DRY RUN: would have closed #%d (%s lots) at %s, %s",
                                  (int)ticket, DoubleToString(volume, 2), HHMM(reasonMinutes), why));
         continue;
      }
      if(g_trade.PositionClose(ticket))
      {
         closed++;
         Log("FLAT", StringFormat("closed #%d (%s lots) at %s, %s",
                                  (int)ticket, DoubleToString(volume, 2), HHMM(reasonMinutes), why));
      }
      else
         Log("ERROR", StringFormat("could not close #%d: %d %s", (int)ticket, (int)g_trade.ResultRetcode(),
                                   g_trade.ResultRetcodeDescription()));
   }
   if(closed > 0)
   {
      Log("FLAT", StringFormat("%d position(s) closed, %s", closed, why));
      Notify(StringFormat("DayTraderMT5: %d position(s) closed on %s, %s", closed, _Symbol, why));
   }
}

//+------------------------------------------------------------------+
//| The dashboard                                                     |
//+------------------------------------------------------------------+
//  Chart objects only: no DLL, no resources, no files. Eight pages,
//  every number clickable, and every click is written to the
//  terminal's global variables, so a chart change keeps your tuning.
//+------------------------------------------------------------------+
void DeletePanel()
{
   if(ObjectFind(0, PANEL_TAG + "bg") < 0)
      return;
   ObjectsDeleteAll(0, PANEL_TAG);
}

void UiRect(const string name, const int x, const int y, const int w, const int h,
            const color bg, const color border)
{
   if(ObjectFind(0, name) < 0)
   {
      if(!ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0))
         return;
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
   }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, (int)MathMax(1, w));
   ObjectSetInteger(0, name, OBJPROP_YSIZE, (int)MathMax(1, h));
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, name, OBJPROP_COLOR, border);
}

void UiText(const string name, const int x, const int y, const string text,
            const color clr, const int size, const string font, const ENUM_ANCHOR_POINT anchor)
{
   if(ObjectFind(0, name) < 0)
   {
      if(!ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
         return;
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
   }
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetString(0, name, OBJPROP_FONT, font);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void UiButton(const string name, const int x, const int y, const int w, const int h,
              const string text, const color bg, const color fg)
{
   if(ObjectFind(0, name) < 0)
   {
      if(!ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0))
         return;
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
      ObjectSetString(0, name, OBJPROP_FONT, "Segoe UI");
      ObjectSetInteger(0, name, OBJPROP_BORDER_COLOR, CLR_LINE);
   }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, name, OBJPROP_COLOR, fg);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

double Clamp01(const double value)
{
   if(value < 0.0)
      return 0.0;
   if(value > 1.0)
      return 1.0;
   return value;
}

void UiBar(const string key, const int x, const int y, const int w, const double fraction, const color clr)
{
   double f = Clamp01(fraction);
   UiRect(PANEL_TAG + key + "_bg", x, y, w, 4, CLR_LINE, CLR_LINE);
   UiRect(PANEL_TAG + key + "_fg", x, y, (int)MathMax(1, MathRound(w * f)), 4, clr, clr);
}

void UiSection(const string key, const string title)
{
   UiRect(PANEL_TAG + key + "_dot", g_uiX + PANEL_PAD, g_uiY + 4, 3, 9, CLR_SECT, CLR_SECT);
   UiText(PANEL_TAG + key + "_t", g_uiX + PANEL_PAD + 9, g_uiY, title, CLR_SECT, 8, "Segoe UI", ANCHOR_LEFT_UPPER);
   g_uiY += SECT_H;
}

void UiLine(const string key, const string text, const color clr, const int size)
{
   UiText(PANEL_TAG + "t_" + key, g_uiX + PANEL_PAD, g_uiY, Clip(text, 50), clr, size, "Consolas", ANCHOR_LEFT_UPPER);
   g_uiY += (size <= 7 ? 12 : 14);
}

// a full width button, for a page that owns an action
void UiWide(const string name, const string text, const color bg)
{
   UiButton(PANEL_TAG + name, g_uiX + PANEL_PAD, g_uiY, PANEL_W - 2 * PANEL_PAD, 20, text, bg, CLR_VALUE);
   g_uiY += 24;
}

// a line with a label and a value and nothing to click
void RowRead(const string key, const string label, const string value, const color clr)
{
   UiText(PANEL_TAG + "r_" + key + "_l", g_uiX + PANEL_PAD + 9, g_uiY, label, CLR_LABEL, 8,
          "Segoe UI", ANCHOR_LEFT_UPPER);
   UiText(PANEL_TAG + "r_" + key + "_v", g_uiX + 132, g_uiY, Clip(value, 31), clr, 8,
          "Consolas", ANCHOR_LEFT_UPPER);
   g_uiY += ROW_H;
}

// a line with [ - ] and [ + ] on the right
void RowEdit(const string key, const string label, const string value, const color clr)
{
   int yd = g_uiY + 1;
   UiText(PANEL_TAG + "e_" + key + "_l", g_uiX + PANEL_PAD + 9, yd + 1, label, CLR_LABEL, 8,
          "Segoe UI", ANCHOR_LEFT_UPPER);
   UiText(PANEL_TAG + "e_" + key + "_v", g_uiX + 132, yd + 1, Clip(value, 21), clr, 8,
          "Consolas", ANCHOR_LEFT_UPPER);
   UiButton(PANEL_TAG + "b_" + key + "_dn", g_uiX + 292, yd, 22, 15, "-", CLR_BTN, CLR_VALUE);
   UiButton(PANEL_TAG + "b_" + key + "_up", g_uiX + 316, yd, 22, 15, "+", CLR_BTN, CLR_VALUE);
   g_uiY += EROW_H;
}

// a line with [ < ] and [ > ]: a short list, like the bar size
void RowCycle(const string key, const string label, const string value, const color clr)
{
   int yd = g_uiY + 1;
   UiText(PANEL_TAG + "e_" + key + "_l", g_uiX + PANEL_PAD + 9, yd + 1, label, CLR_LABEL, 8,
          "Segoe UI", ANCHOR_LEFT_UPPER);
   UiText(PANEL_TAG + "e_" + key + "_v", g_uiX + 132, yd + 1, Clip(value, 21), clr, 8,
          "Consolas", ANCHOR_LEFT_UPPER);
   UiButton(PANEL_TAG + "b_" + key + "_pv", g_uiX + 292, yd, 22, 15, "<", CLR_BTN, CLR_VALUE);
   UiButton(PANEL_TAG + "b_" + key + "_nx", g_uiX + 316, yd, 22, 15, ">", CLR_BTN, CLR_VALUE);
   g_uiY += EROW_H;
}

// a line with one ON/OFF button
void RowToggle(const string key, const string label, const bool on, const string note)
{
   int yd = g_uiY + 1;
   UiText(PANEL_TAG + "e_" + key + "_l", g_uiX + PANEL_PAD + 9, yd + 1, label, CLR_LABEL, 8,
          "Segoe UI", ANCHOR_LEFT_UPPER);
   UiText(PANEL_TAG + "e_" + key + "_v", g_uiX + 132, yd + 1, Clip(note, 18), on ? CLR_GOOD : CLR_LABEL, 8,
          "Consolas", ANCHOR_LEFT_UPPER);
   UiButton(PANEL_TAG + "b_" + key + "_tg", g_uiX + 268, yd, 70, 15, (on ? "ON" : "OFF"),
            (on ? CLR_GOOD : CLR_BTN), (on ? CLR_BG : CLR_VALUE));
   g_uiY += EROW_H;
}

string NyWord()
{
   if(!g_newYork)
      return "server";
   return (g_nyOffset == -4 ? "EDT" : "EST");
}

double SessionFraction(const int minutes)
{
   if(!InWindow(minutes, g_sessionStart, g_sessionEnd))
      return 0.0;
   int span = (g_sessionEnd > g_sessionStart ? g_sessionEnd - g_sessionStart
                                             : g_sessionEnd + 1440 - g_sessionStart);
   if(span <= 0)
      return 0.0;
   int done = (minutes >= g_sessionStart ? minutes - g_sessionStart
                                         : minutes + 1440 - g_sessionStart);
   return Clamp01((double)done / (double)span);
}

// the one position this EA may have open, with everything the panel needs
bool OurPosition(ulong &ticket, long &type, double &lots, double &open, double &sl, double &tp, double &profit)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != g_magic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      ticket = t;
      type   = PositionGetInteger(POSITION_TYPE);
      lots   = PositionGetDouble(POSITION_VOLUME);
      open   = PositionGetDouble(POSITION_PRICE_OPEN);
      sl     = PositionGetDouble(POSITION_SL);
      tp     = PositionGetDouble(POSITION_TP);
      profit = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      return true;
   }
   return false;
}

// one word for where the rule is right now
string RuleStateWord()
{
   datetime nyNow = ToNewYork(TimeCurrent());
   int minutes = MinutesOfDay(nyNow);
   if(g_weekdaysOnly && (WeekdayOf(nyNow) == 0 || WeekdayOf(nyNow) == 6))
      return "weekend";
   if(PastTime(minutes, g_flatBy))
      return "past flat-by";
   if(!InWindow(minutes, g_sessionStart, g_sessionEnd))
      return "outside session";
   if(OurPositions() > 0)
      return "in a trade";
   if(g_maxDailyLoss > 0.0 && RealisedToday() <= -g_maxDailyLoss)
      return "daily loss stop";
   if(CountEntriesToday() >= g_maxTrades)
      return "done for the day";
   double high = 0.0, low = 0.0, mid = 0.0;
   int bars = 0;
   if(!OpeningRange(high, low, mid, bars))
      return "range forming";
   if(minutes < g_sessionStart + g_orMinutes)
      return "range forming";
   return "waiting for a break";
}

// a line every InpHeartbeatMinutes, so you can see it is awake and watching
// even on a quiet day; quiet, so it never replaces the last event on the panel
void Heartbeat()
{
   if(g_heartbeat <= 0)
      return;
   if(g_lastBeat != 0 && TimeCurrent() - g_lastBeat < g_heartbeat * 60)
      return;
   g_lastBeat = TimeCurrent();
   string firstFail = "";
   int open = GatesOpen(firstFail);
   string tail = (firstFail == "" ? "every gate is open" : "first closed gate: " + firstFail);
   Log("ALIVE", StringFormat("%s %s, %s, %d of 11 gates open (%s), %s",
                             _Symbol, PeriodDescription(g_tf), RuleStateWord(), open, tail,
                             (OurPositions() > 0 ? "a position is open" : "flat")), true);
}

// what the next order would be sized to, at the stop the rule would pick now
string LotsPreview()
{
   double atr = AtrValue();
   double distance = MathMax(atr * g_atrMult, MinStopPoints() * _Point);
   if(distance <= 0.0)
      return "no ATR yet";
   string note = "";
   double lots = SizeLots(distance, note);
   if(lots <= 0.0)
      return "too small for 1 lot";
   return DoubleToString(lots, 2) + " lots / " + DoubleToString(distance / _Point, 0) + " pts";
}

// today's closed deals of our own magic, for the log page
void JournalToday(int &deals, int &wins, int &losses, double &net, string &lastLine)
{
   deals = 0;
   wins = 0;
   losses = 0;
   net = 0.0;
   lastLine = "-";
   datetime nyNow = ToNewYork(TimeCurrent());
   datetime from = nyNow - 3 * 86400;
   if(!HistorySelect(from, TimeCurrent() + 60))
      return;
   int today = DayIndexOf(nyNow);
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != g_magic)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT)
         continue;
      datetime when = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      if(DayIndexOf(ToNewYork(when)) != today)
         continue;
      double result = HistoryDealGetDouble(ticket, DEAL_PROFIT) +
                      HistoryDealGetDouble(ticket, DEAL_SWAP) +
                      HistoryDealGetDouble(ticket, DEAL_COMMISSION) +
                      HistoryDealGetDouble(ticket, DEAL_FEE);
      deals++;
      net += result;
      if(result >= 0.0)
         wins++;
      else
         losses++;
      lastLine = TimeToString(when, TIME_MINUTES) + "  " + (result >= 0.0 ? "+" : "") + DoubleToString(result, 2);
   }
}

//+------------------------------------------------------------------+
//| The frame: header, tabs, actions, footer                          |
//+------------------------------------------------------------------+
void UiHeader(const string pageTitle)
{
   UiRect(PANEL_TAG + "bg", g_uiX, g_uiY, PANEL_W, 10, CLR_BG, CLR_LINE);
   UiRect(PANEL_TAG + "head", g_uiX + 1, g_uiY + 1, PANEL_W - 2, 26, CLR_HEAD, CLR_HEAD);
   UiText(PANEL_TAG + "head_t", g_uiX + PANEL_PAD, g_uiY + 7, "DayTraderMT5", CLR_VALUE, 10,
          "Segoe UI", ANCHOR_LEFT_UPPER);
   UiText(PANEL_TAG + "head_p", g_uiX + 120, g_uiY + 10, pageTitle, CLR_SECT, 7, "Consolas",
          ANCHOR_LEFT_UPPER);
   color modeClr = CLR_GOOD;
   if(!g_newYork)
      modeClr = CLR_WARN;
   if(IsLiveAccount())
      modeClr = CLR_BAD;
   UiText(PANEL_TAG + "head_m", g_uiX + PANEL_W - PANEL_PAD, g_uiY + 7, AccountModeWord(), modeClr,
          10, "Segoe UI", ANCHOR_RIGHT_UPPER);
   g_uiY += 30;
}

void UiTabs()
{
   string names[9] = {"DASH", "RULE", "RISK", "CLOCK", "MANAGE", "LOG", "TEST", "PACK", "HELP"};
   int w = (PANEL_W - 2 * PANEL_PAD - 24) / 5;
   for(int i = 0; i < 9; i++)
   {
      int row = i / 5;
      int col = i % 5;
      int x = g_uiX + PANEL_PAD + col * (w + 6);
      int y = g_uiY + row * 20;
      UiButton(PANEL_TAG + "tab" + IntegerToString(i), x, y, w, 18, names[i],
               (i == g_page ? CLR_SECT : CLR_BTN), (i == g_page ? CLR_BG : CLR_VALUE));
   }
   g_uiY += 44;
}

void UiActions()
{
   g_uiY += 3;
   int w = (PANEL_W - 2 * PANEL_PAD - 18) / 4;
   int x0 = g_uiX + PANEL_PAD;
   UiButton(PANEL_TAG + "btn_pause", x0, g_uiY, w, 18, (g_paused ? "RESUME" : "PAUSE"),
            (g_paused ? CLR_WARN : CLR_BTN), CLR_VALUE);
   UiButton(PANEL_TAG + "btn_dry", x0 + (w + 6), g_uiY, w, 18, (g_dryRun ? "DRY ON" : "DRY OFF"),
            (g_dryRun ? CLR_WARN : CLR_BTN), CLR_VALUE);
   UiButton(PANEL_TAG + "btn_close", x0 + 2 * (w + 6), g_uiY, w, 18,
            (g_confirmClose ? "SURE?" : "CLOSE OUR"), (g_confirmClose ? CLR_BAD : CLR_DANGER), CLR_VALUE);
   UiButton(PANEL_TAG + "btn_reset", x0 + 3 * (w + 6), g_uiY, w, 18,
            (g_confirmReset ? "SURE?" : "RESET"), (g_confirmReset ? CLR_BAD : CLR_BTN), CLR_VALUE);
   g_uiY += 22;
}

void UiFooter()
{
   string foot = "v1.22  magic " + IntegerToString(g_magic) + "  " + (g_verbose ? "verbose" : "quiet") + " log";
   UiText(PANEL_TAG + "foot", g_uiX + PANEL_PAD, g_uiY, foot, CLR_LABEL, 7, "Segoe UI",
          ANCHOR_LEFT_UPPER);
   g_uiY += 12;
}

//+------------------------------------------------------------------+
//| Page 1: the day at a glance                                       |
//+------------------------------------------------------------------+
void DrawDash()
{
   datetime nyNow   = ToNewYork(TimeCurrent());
   int minutes      = MinutesOfDay(nyNow);
   bool inSession   = InWindow(minutes, g_sessionStart, g_sessionEnd);
   double rangeHigh = 0.0, rangeLow = 0.0, rangeMid = 0.0;
   int orBars       = 0;
   bool haveRange   = OpeningRange(rangeHigh, rangeLow, rangeMid, orBars);
   double atr       = AtrValue();
   double fast      = IndicatorValue(g_emaFast);
   double slow      = IndicatorValue(g_emaSlow);
   double spread    = SpreadPoints();
   double realised  = RealisedToday();
   int entries      = CountEntriesToday();
   int open         = OurPositions();
   string readyWhy  = "";
   bool ready       = TerminalReady(readyWhy);

   UiSection("mkt", "MARKET");
   RowRead("mkt_sym", "Symbol / rule", _Symbol + "  " + PeriodDescription(g_tf), CLR_VALUE);
   RowRead("mkt_ny", "New York", TimeToString(nyNow, TIME_DATE | TIME_MINUTES) + "  " + NyWord(), CLR_VALUE);
   RowRead("mkt_ses", "Session", HHMM(g_sessionStart) + "-" + HHMM(g_sessionEnd) + "  " +
           (inSession ? "OPEN" : "closed"), inSession ? CLR_GOOD : CLR_LABEL);
   UiBar("ses", g_uiX + 132, g_uiY - 4, 200, SessionFraction(minutes), inSession ? CLR_SECT : CLR_LINE);

   UiSection("or", "OPENING RANGE");
   if(haveRange)
   {
      RowRead("or_hl", "High / low", DoubleToString(rangeHigh, _Digits) + "  " +
              DoubleToString(rangeLow, _Digits), CLR_VALUE);
      RowRead("or_md", "Mid", DoubleToString(rangeMid, _Digits), CLR_VALUE);
      RowRead("or_wd", "Width / bars", DoubleToString((rangeHigh - rangeLow) / _Point, 0) + " pts, " +
              IntegerToString(orBars) + " bars", CLR_VALUE);
   }
   else
   {
      RowRead("or_hl", "High / low", "-  still forming", CLR_WARN);
      RowRead("or_md", "Mid", "-", CLR_LABEL);
      RowRead("or_wd", "Width / bars", "-", CLR_LABEL);
   }

   UiSection("ind", "INDICATORS");
   RowRead("ind_ema", "EMA " + IntegerToString(g_emaFastPeriod) + "/" + IntegerToString(g_emaSlowPeriod),
           DoubleToString(fast, _Digits) + "  " + DoubleToString(slow, _Digits), CLR_VALUE);
   string trend = TrendWord();
   color trendClr = CLR_LABEL;
   if(trend == "up")
      trendClr = CLR_GOOD;
   if(trend == "down")
      trendClr = CLR_BAD;
   RowRead("ind_tr", "Trend", trend, trendClr);
   string spreadText = DoubleToString(atr, _Digits) + "  /  " + DoubleToString(spread, 0) + " pts";
   color spreadClr = CLR_VALUE;
   if(g_spreadMax > 0.0)
   {
      spreadText += "  (max " + DoubleToString(g_spreadMax, 0) + ")";
      if(spread > g_spreadMax)
         spreadClr = CLR_BAD;
   }
   RowRead("ind_atr", "ATR / spread", spreadText, spreadClr);

   UiSection("day", "TODAY");
   RowRead("day_en", "Entries", IntegerToString(entries) + " of " + IntegerToString(g_maxTrades),
           entries >= g_maxTrades ? CLR_WARN : CLR_VALUE);
   color plClr = CLR_VALUE;
   if(realised > 0.0)
      plClr = CLR_GOOD;
   if(realised < 0.0)
      plClr = CLR_BAD;
   RowRead("day_pl", "Realised", Money(realised), plClr);
   string roomText = "off";
   color roomClr = CLR_LABEL;
   if(g_maxDailyLoss > 0.0)
   {
      double lost = -realised;
      if(lost < 0.0)
         lost = 0.0;
      double room = g_maxDailyLoss - lost;
      roomClr = CLR_VALUE;
      if(room <= 0.0)
      {
         roomText = "STOPPED for the day";
         roomClr = CLR_BAD;
      }
      else
         roomText = Money(room) + " of " + Money(g_maxDailyLoss);
   }
   RowRead("day_lr", "Loss room", roomText, roomClr);

   UiSection("pos", "POSITION");
   ulong pticket = 0;
   long ptype    = 0;
   double plots = 0.0, popen = 0.0, psl = 0.0, ptp = 0.0, pprofit = 0.0;
   bool have = OurPosition(pticket, ptype, plots, popen, psl, ptp, pprofit);
   if(have)
   {
      double current = (ptype == POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                  : SymbolInfoDouble(_Symbol, SYMBOL_ASK));
      double rDistance = (g_minRR > 0.0 ? MathAbs(ptp - popen) / g_minRR : 0.0);
      double progress = 0.0;
      if(rDistance > 0.0)
         progress = (ptype == POSITION_TYPE_BUY ? current - popen : popen - current) / rDistance;
      bool isBuy = (ptype == POSITION_TYPE_BUY);
      RowRead("pos_t", "Ticket / side", "#" + IntegerToString((long)pticket) + "  " +
              (isBuy ? "BUY" : "SELL"), isBuy ? CLR_GOOD : CLR_BAD);
      RowRead("pos_l", "Lots / entry", DoubleToString(plots, 2) + "  @  " + DoubleToString(popen, _Digits), CLR_VALUE);
      RowRead("pos_s", "Stop / target", (psl > 0.0 ? DoubleToString(psl, _Digits) : "none") + "  " +
              (ptp > 0.0 ? DoubleToString(ptp, _Digits) : "none"), CLR_VALUE);
      RowRead("pos_r", "Progress", StringFormat("%.2fR, %s", progress, Money(pprofit)),
              progress >= 0.0 ? CLR_VALUE : CLR_BAD);
      UiBar("posr", g_uiX + 132, g_uiY - 4, 200, Clamp01(progress), CLR_GOOD);
   }
   else
   {
      RowRead("pos_t", "Ticket / side", "-  nothing open", CLR_LABEL);
      RowRead("pos_l", "Lots / entry", "-", CLR_LABEL);
      RowRead("pos_s", "Stop / target", "-", CLR_LABEL);
      RowRead("pos_r", "Progress", "-", CLR_LABEL);
      UiBar("posr", g_uiX + 132, g_uiY - 4, 200, 0.0, CLR_LINE);
   }

   UiSection("rsk", "RISK AND SIZE");
   RowRead("rsk_b", "Budget / trade", Money(RiskBudget()), CLR_VALUE);
   RowRead("rsk_c", "Caps", DoubleToString(g_maxLots, 2) + " lots, " +
           DoubleToString(g_maxMarginPct, 0) + "% margin, " + DoubleToString(g_minRR, 2) + "R", CLR_VALUE);

   UiSection("sts", "STATUS");
   string trading = "yes";
   color tradeClr = CLR_GOOD;
   if(g_paused)
   {
      trading = "paused from the panel";
      tradeClr = CLR_WARN;
   }
   else if(!ready)
   {
      trading = "no: " + readyWhy;
      tradeClr = CLR_BAD;
   }
   else if(g_dryRun)
   {
      trading = "dry run, nothing is sent";
      tradeClr = CLR_WARN;
   }
   RowRead("sts_tr", "Trading", trading, tradeClr);
   string modeText = AccountModeWord();
   if(g_liveBlocked)
      modeText += "  LIVE BLOCKED";
   if(g_dryRun)
      modeText += "  DRY";
   if(g_paused)
      modeText += "  PAUSED";
   modeText += "  " + IntegerToString(open) + " open";
   RowRead("sts_md", "Mode", modeText, g_liveBlocked ? CLR_BAD : CLR_VALUE);
   RowRead("sts_ev", "Last", g_lastEvent, CLR_LABEL);
}

//+------------------------------------------------------------------+
//| Page 2: the rule, every number clickable                          |
//+------------------------------------------------------------------+
void DrawRule()
{
   UiSection("rule", "THE RULE");
   RowCycle("tf", "Bar size", PeriodDescription(g_tf), CLR_VALUE);
   RowEdit("ema_fast", "Fast EMA", IntegerToString(g_emaFastPeriod), CLR_VALUE);
   RowEdit("ema_slow", "Slow EMA", IntegerToString(g_emaSlowPeriod), CLR_VALUE);
   RowToggle("trend", "Trend filter", g_useTrend, (g_useTrend ? "EMA fast > slow" : "break only"));
   RowEdit("atr_period", "ATR period", IntegerToString(g_atrPeriod), CLR_VALUE);

   UiSection("brk", "THE BREAK");
   RowEdit("or_min", "Opening range", IntegerToString(g_orMinutes) + " min", CLR_VALUE);
   RowEdit("atr_mult", "Stop distance", DoubleToString(g_atrMult, 1) + " ATR", CLR_VALUE);
   RowEdit("min_range", "Range floor", (g_minRangePoints <= 0.0 ? "off"
           : DoubleToString(g_minRangePoints, 0) + " pts"), CLR_VALUE);
   RowEdit("min_rr", "Reward:risk", DoubleToString(g_minRR, 1) + "R", CLR_VALUE);
   RowToggle("shorts", "Short side", g_shorts, (g_shorts ? "long and short" : "long only"));

   UiSection("now", "WHERE IT IS");
   RowRead("rule_state", "State", RuleStateWord(), CLR_WARN);
   RowRead("rule_size", "Next size", LotsPreview(), CLR_VALUE);
}

//+------------------------------------------------------------------+
//| Page 3: risk and size                                             |
//+------------------------------------------------------------------+
void DrawRisk()
{
   double realised = RealisedToday();
   UiSection("money", "MONEY");
   RowEdit("risk_pct", "Risk per trade", DoubleToString(g_riskPct, 2) + "%", CLR_VALUE);
   RowEdit("risk_money", "or a fixed", Money(g_riskMoney), CLR_VALUE);
   RowEdit("max_lots", "Lot cap", DoubleToString(g_maxLots, 2), CLR_VALUE);
   RowEdit("margin_pct", "Margin cap", DoubleToString(g_maxMarginPct, 0) + "%", CLR_VALUE);

   UiSection("lim", "LIMITS");
   RowEdit("spread_max", "Spread ceiling", (g_spreadMax <= 0.0 ? "off"
           : DoubleToString(g_spreadMax, 0) + " pts"), CLR_VALUE);
   RowEdit("daily_loss", "Daily loss stop", (g_maxDailyLoss <= 0.0 ? "off"
           : Money(g_maxDailyLoss)), CLR_VALUE);
   RowEdit("max_trades", "Entries a day", IntegerToString(g_maxTrades), CLR_VALUE);

   UiSection("live", "RIGHT NOW");
   RowRead("x_budget", "Budget per trade", Money(RiskBudget()), CLR_VALUE);
   RowRead("x_free", "Free margin", Money(AccountInfoDouble(ACCOUNT_MARGIN_FREE)), CLR_VALUE);
   RowRead("x_equity", "Equity", Money(AccountInfoDouble(ACCOUNT_EQUITY)), CLR_VALUE);
   RowRead("x_pl", "Realised today", Money(realised), realised < 0.0 ? CLR_BAD : CLR_VALUE);
   RowRead("x_spread", "Spread now", DoubleToString(SpreadPoints(), 0) + " pts",
           (g_spreadMax > 0.0 && SpreadPoints() > g_spreadMax) ? CLR_BAD : CLR_VALUE);
}

//+------------------------------------------------------------------+
//| Page 4: the clock                                                 |
//+------------------------------------------------------------------+
void DrawClock()
{
   datetime nyNow = ToNewYork(TimeCurrent());
   int minutes = MinutesOfDay(nyNow);
   bool inSession = InWindow(minutes, g_sessionStart, g_sessionEnd);
   int untilFlat = (g_flatBy - minutes + 1440) % 1440;

   UiSection("clk", "THE CLOCK");
   RowToggle("ny", "Time base", g_newYork, (g_newYork ? "New York, with DST" : "the server's clock"));
   RowEdit("ses_start", "No entries before", HHMM(g_sessionStart), CLR_VALUE);
   RowEdit("ses_end", "No entries after", HHMM(g_sessionEnd), CLR_VALUE);
   RowEdit("flat_by", "Close everything", HHMM(g_flatBy), CLR_VALUE);
   RowToggle("weekdays", "Weekdays only", g_weekdaysOnly, (g_weekdaysOnly ? "Mon to Fri" : "all days"));

   UiSection("now", "NOW");
   RowRead("c_ny", "New York", TimeToString(nyNow, TIME_DATE | TIME_MINUTES) + "  " + NyWord(), CLR_VALUE);
   RowRead("c_ses", "Session", (inSession ? "OPEN" : "closed"), inSession ? CLR_GOOD : CLR_LABEL);
   RowRead("c_flat", "Flat by in", (PastTime(minutes, g_flatBy) ? "already past"
           : IntegerToString(untilFlat) + " min"), PastTime(minutes, g_flatBy) ? CLR_BAD : CLR_VALUE);
   RowRead("c_cnt", "Entries today", IntegerToString(CountEntriesToday()) + " of " +
           IntegerToString(g_maxTrades), CLR_VALUE);
   RowRead("c_srv", "Server time", TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES), CLR_LABEL);
}

//+------------------------------------------------------------------+
//| Page 5: managing the trade, the broker, the alerts, the log       |
//+------------------------------------------------------------------+
void DrawManage()
{
   UiSection("mg", "MANAGE THE TRADE");
   RowEdit("be_r", "Stop to entry at", (g_beAtR <= 0.0 ? "off" : DoubleToString(g_beAtR, 1) + "R"), CLR_VALUE);
   RowEdit("trail_r", "Trail from", (g_trailAtR <= 0.0 ? "off" : DoubleToString(g_trailAtR, 1) + "R"), CLR_VALUE);
   RowEdit("trail_pts", "Trail distance", IntegerToString(g_trailPoints) + " pts", CLR_VALUE);
   RowEdit("part_r", "Take part at", (g_partialAtR <= 0.0 ? "off" : DoubleToString(g_partialAtR, 1) + "R"), CLR_VALUE);
   RowEdit("part_pct", "Part size", DoubleToString(g_partialPct, 0) + "%", CLR_VALUE);

   UiSection("brk", "THE BROKER");
   RowEdit("deviation", "Slippage allowed", IntegerToString(g_deviation) + " pts", CLR_VALUE);
   RowEdit("stop_buffer", "Stop buffer", IntegerToString(g_stopBuffer) + " pts", CLR_VALUE);
   RowRead("b_stops", "Stops level", DoubleToString((double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL), 0) +
           " + " + IntegerToString(g_stopBuffer) + " pts", CLR_VALUE);
   RowRead("b_last", "Last answer", g_lastRetcode, g_lastRetcode == "done" ? CLR_GOOD : CLR_LABEL);

   UiSection("al", "ALERTS");
   RowToggle("alert_popup", "Popup alert", g_alertPopup, (g_alertPopup ? "Alert() window" : "silent"));
   RowToggle("alert_sound", "Sound", g_alertSound, (g_alertSound ? "alert2.wav" : "silent"));
   RowToggle("alert_push", "Push to phone", g_alertPush, (g_alertPush ? "MetaQuotes ID" : "off"));

   UiSection("lg", "THE LOG");
   RowToggle("verbose", "Every bar", g_verbose, (g_verbose ? "bar by bar" : "changes only"));
   RowEdit("heartbeat", "Alive line", (g_heartbeat <= 0 ? "off" : IntegerToString(g_heartbeat) + " min"), CLR_VALUE);
}

//+------------------------------------------------------------------+
//| Page 6: the console on the chart, and today's journal            |
//+------------------------------------------------------------------+
void DrawLog()
{
   UiSection("con", "CONSOLE, NEWEST FIRST");
   int shown = (int)MathMin(g_logCount, 8);
   for(int i = 0; i < 8; i++)
   {
      string text = (i < shown ? g_logRing[i] : "");
      UiText(PANEL_TAG + "log" + IntegerToString(i), g_uiX + PANEL_PAD, g_uiY, Clip(text, 54),
             (i == 0 ? CLR_VALUE : CLR_LABEL), 7, "Consolas", ANCHOR_LEFT_UPPER);
      g_uiY += 12;
   }

   int deals = 0, wins = 0, losses = 0;
   double net = 0.0;
   string last = "-";
   JournalToday(deals, wins, losses, net, last);

   UiSection("jrn", "JOURNAL TODAY");
   RowRead("j_n", "Closed trades", IntegerToString(deals), CLR_VALUE);
   RowRead("j_wl", "Wins / losses", IntegerToString(wins) + " / " + IntegerToString(losses), CLR_VALUE);
   RowRead("j_net", "Net", Money(net), net < 0.0 ? CLR_BAD : (net > 0.0 ? CLR_GOOD : CLR_VALUE));
   RowRead("j_last", "Last one", last, CLR_LABEL);
   RowRead("j_open", "Open now", IntegerToString(OurPositions()), CLR_VALUE);
}

//+------------------------------------------------------------------+
//| Page 7: can it trade, and what exactly would it send              |
//+------------------------------------------------------------------+
void DrawTest()
{
   string detail = "";
   string labels[11] = {"Toolbar", "Algo setting", "Account", "Broker EA", "Live guard", "Weekday",
                        "Session", "Entries left", "Loss room", "Spread", "Market data"};
   UiSection("chk", "CAN IT TRADE RIGHT NOW?");
   for(int i = 0; i < 11; i++)
   {
      bool ok = GatePass(i, detail);
      RowRead("g" + IntegerToString(i), labels[i], (ok ? "PASS" : "NO: " + detail),
              ok ? CLR_GOOD : CLR_BAD);
   }

   string side = "", why = "";
   double lots = 0.0, entry = 0.0, stop = 0.0, target = 0.0, distance = 0.0, margin = 0.0;
   bool has = PreviewOrder(side, lots, entry, stop, target, distance, margin, why);

   bool stopsOk = (has && distance >= MinStopPoints() * _Point);
   RowRead("g11", "Stops distance", (stopsOk
           ? DoubleToString(distance / _Point, 0) + " pts, over the broker's " + DoubleToString(MinStopPoints(), 0)
           : "too tight: " + DoubleToString(distance / _Point, 0) + " pts"),
           stopsOk ? CLR_GOOD : CLR_BAD);

   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   bool marginOk = (has && margin > 0.0 && margin <= freeMargin * g_maxMarginPct / 100.0);
   RowRead("g12", "Margin", (has ? Money(margin) + " of " + Money(freeMargin) : "no price"),
           marginOk ? CLR_GOOD : CLR_BAD);

   UiSection("would", "WHAT IT WOULD SEND");
   RowRead("w_side", "Side / lots", (has ? side + "  " + DoubleToString(lots, 2) : "-"), CLR_VALUE);
   RowRead("w_entry", "Entry", (has ? DoubleToString(entry, _Digits) : "-"), CLR_VALUE);
   RowRead("w_stop", "Stop", (has ? DoubleToString(stop, _Digits) + "  (" +
           DoubleToString(distance / _Point, 0) + " pts)" : "-"), CLR_VALUE);
   RowRead("w_tp", "Target", (has ? DoubleToString(target, _Digits) + "  (" +
           DoubleToString(g_minRR * distance / _Point, 0) + " pts, " + DoubleToString(g_minRR, 1) + "R)" : "-"),
           CLR_VALUE);
   color chkClr = CLR_LABEL;
   if(StringFind(g_lastCheck, "ok") == 0)
      chkClr = CLR_GOOD;
   else if(StringFind(g_lastCheck, "no") == 0)
      chkClr = CLR_BAD;
   RowRead("w_chk", "Terminal check", g_lastCheck, chkClr);

   UiWide("btn_check", "RUN ORDER CHECK (sends nothing)", CLR_BTN);
   UiLine("chk_note", "OrderCheck validates and prices; it never sends", CLR_LABEL, 7);
}

//+------------------------------------------------------------------+
//| Page 8: the whole pack, and what the EA does with each skill      |
//+------------------------------------------------------------------+
void DrawPack()
{
   UiSection("ea", "INSIDE THIS EA");
   RowRead("p_scan", "scanner", "opening range on " + _Symbol, CLR_VALUE);
   RowRead("p_entry", "entry", "break of the range close", CLR_VALUE);
   RowRead("p_exit", "exit", "stop " + DoubleToString(g_atrMult, 1) + " ATR, target " +
           DoubleToString(g_minRR, 1) + "R", CLR_VALUE);
   RowRead("p_risk", "risk", RuleStateWord(), CLR_WARN);
   RowRead("p_budget", "budget", LotsPreview(), CLR_VALUE);
   RowRead("p_broker", "broker", "last answer " + g_lastRetcode, CLR_VALUE);
   RowRead("p_alert", "alerts", (g_alertPopup || g_alertSound || g_alertPush ? "on" : "off"),
           (g_alertPopup || g_alertSound || g_alertPush) ? CLR_GOOD : CLR_LABEL);
   RowRead("p_desk", "mt5 desk", "magic " + IntegerToString(g_magic) + ", " + AccountModeWord(), CLR_VALUE);

   UiSection("py", "IN THE PYTHON DESK (dtcli)");
   RowRead("p_news", "news", "dtcli news", CLR_LABEL);
   RowRead("p_analyst", "analyst", "dtcli analyst", CLR_LABEL);
   RowRead("p_pelosi", "pelosi", "dtcli pelosi", CLR_LABEL);
   RowRead("p_tm", "time machine", "dtcli timemachine", CLR_LABEL);
   UiLine("p_note", "those read the web; the EA stays offline", CLR_LABEL, 7);
}

//+------------------------------------------------------------------+
//| Page 9: how to use it                                             |
//+------------------------------------------------------------------+
void DrawHelp()
{
   UiSection("help", "HOW TO USE THIS PANEL");
   UiLine("h1", "tabs switch pages, nothing restarts", CLR_VALUE, 7);
   UiLine("h2", "[-] [+] move a number, ON/OFF flips it", CLR_VALUE, 7);
   UiLine("h3", "< > walk through the few that are lists", CLR_VALUE, 7);
   UiLine("h4", "every click is saved with the chart", CLR_VALUE, 7);
   UiLine("h5", "RESET puts the inputs back, twice", CLR_WARN, 7);

   UiSection("tst", "THE TEST PAGE");
   UiLine("t1", "11 gates, PASS or NO, one by one", CLR_VALUE, 7);
   UiLine("t2", "what it would send: side, lots, SL, TP", CLR_VALUE, 7);
   UiLine("t3", "RUN ORDER CHECK: priced, never sent", CLR_VALUE, 7);
   UiLine("t4", "ALIVE line in the log every heartbeat", CLR_LABEL, 7);

   UiSection("act", "THE FOUR BUTTONS");
   UiLine("a1", "PAUSE: no new entries, manage keeps", CLR_VALUE, 7);
   UiLine("a2", "DRY: signals logged, nothing sent", CLR_VALUE, 7);
   UiLine("a3", "CLOSE OUR: two clicks, 6 seconds", CLR_VALUE, 7);
   UiLine("a4", "RESET: the inputs, two clicks", CLR_VALUE, 7);

   UiSection("safe", "SAFETY");
   UiLine("s1", "REAL needs InpAllowLive = true", CLR_BAD, 7);
   UiLine("s2", "it only trades its own magic number", CLR_LABEL, 7);
   UiLine("s3", "a stop is a plan, not a guarantee", CLR_LABEL, 7);
   UiLine("s4", "demo first, always", CLR_LABEL, 7);
   UiLine("s5", "offline: no web, no sockets, no DLL", CLR_GOOD, 7);
}

//+------------------------------------------------------------------+
//| UpdatePanel: draw the page that is open                           |
//+------------------------------------------------------------------+
void UpdatePanel()
{
   if(!g_showPanel)
   {
      DeletePanel();
      return;
   }

   if(g_confirmClose && TimeCurrent() - g_confirmAt > 6)
      g_confirmClose = false;
   if(g_confirmReset && TimeCurrent() - g_confirmResetAt > 6)
      g_confirmReset = false;

   g_uiX = g_panelX;
   g_uiY = g_panelY;
   int top = g_uiY;
   if(g_page < 0 || g_page >= PAGE_COUNT)
      g_page = 0;

   string titles[9] = {"the day at a glance", "the rule", "risk and size", "the clock",
                       "managing the trade", "console and journal", "can it trade",
                       "the whole pack", "how to use this"};
   UiHeader(titles[g_page]);
   UiTabs();

   if(g_page == 0)
      DrawDash();
   else if(g_page == 1)
      DrawRule();
   else if(g_page == 2)
      DrawRisk();
   else if(g_page == 3)
      DrawClock();
   else if(g_page == 4)
      DrawManage();
   else if(g_page == 5)
      DrawLog();
   else if(g_page == 6)
      DrawTest();
   else if(g_page == 7)
      DrawPack();
   else
      DrawHelp();

   UiActions();
   UiFooter();

   // size the plate to what was actually drawn
   UiRect(PANEL_TAG + "bg", g_uiX, top, PANEL_W, g_uiY - top + 4, CLR_BG, CLR_LINE);
   ChartRedraw(0);
}

void SetPage(const int page)
{
   if(page == g_page || page < 0 || page >= PAGE_COUNT)
      return;
   g_page = page;
   ObjectsDeleteAll(0, PANEL_TAG);      // the other page's rows go with it
   UpdatePanel();
}

//+------------------------------------------------------------------+
//| A click: a tab, one of the four buttons, or a [-] [+] row         |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id != CHARTEVENT_OBJECT_CLICK)
      return;
   if(StringFind(sparam, PANEL_TAG) != 0)
      return;

   string prefix = PANEL_TAG;

   if(StringFind(sparam, prefix + "tab") == 0)
   {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      int page = (int)StringToInteger(StringSubstr(sparam, StringLen(prefix) + 3));
      SetPage(page);
      ChartRedraw(0);
      return;
   }

   if(sparam == prefix + "btn_pause")
   {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      g_paused = !g_paused;
      Log("CTRL", (g_paused ? "entries paused from the dashboard. Management and the flat-by close keep running"
                            : "entries resumed from the dashboard"));
   }
   else if(sparam == prefix + "btn_dry")
   {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      g_dryRun = !g_dryRun;
      Log("CTRL", (g_dryRun ? "dry run on: signals and orders are logged, nothing is sent"
                            : "dry run off: orders will be sent"));
   }
   else if(sparam == prefix + "btn_close")
   {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      if(!g_confirmClose)
      {
         g_confirmClose = true;
         g_confirmAt    = TimeCurrent();
         Log("CTRL", StringFormat("CLOSE OUR armed for 6 seconds: %d of our position(s) on %s will be closed on a second click",
                                  OurPositions(), _Symbol));
      }
      else
      {
         g_confirmClose = false;
         Log("CTRL", "CLOSE OUR confirmed by the second click");
         CloseAllOurs(MinutesOfDay(ToNewYork(TimeCurrent())), "closed from the dashboard");
      }
   }
   else if(sparam == prefix + "btn_check")
   {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      RunOrderCheck();
   }
   else if(sparam == prefix + "btn_reset")
   {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      if(!g_confirmReset)
      {
         g_confirmReset = true;
         g_confirmResetAt = TimeCurrent();
         Log("CTRL", "RESET armed for 6 seconds: click again to put every setting back to the inputs");
      }
      else
      {
         g_confirmReset = false;
         ResetSettings("from the dashboard");
      }
   }
   else if(StringFind(sparam, prefix + "b_") == 0)
   {
      string rest = StringSubstr(sparam, StringLen(prefix) + 2);
      int len = StringLen(rest);
      if(len < 5)
         return;
      string act = StringSubstr(rest, len - 3);
      string key = StringSubstr(rest, 0, len - 3);
      int dir = 0;
      if(act == "_up")
         dir = 1;
      else if(act == "_dn")
         dir = -1;
      else if(act == "_nx")
         dir = 2;
      else if(act == "_pv")
         dir = -2;
      else if(act == "_tg")
         dir = 0;
      else
         return;
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      if(!AdjustSetting(key, dir))
         return;
   }
   else
      return;

   UpdatePanel();
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| OnInit: read the inputs, load what you clicked last time, check   |
//| them, and say exactly what will happen                            |
//+------------------------------------------------------------------+
int OnInit()
{
   ApplyInputDefaults();

   if(!ParseHHMM(InpSessionStart, g_sessionStart) ||
      !ParseHHMM(InpSessionEnd,   g_sessionEnd)   ||
      !ParseHHMM(InpFlatBy,       g_flatBy))
   {
      Log("ERROR", "a time input is not HH:MM (session start, session end, flat by)");
      return INIT_PARAMETERS_INCORRECT;
   }

   LoadSettings();          // what you clicked last time wins over the inputs

   if(g_riskPct <= 0.0 && g_riskMoney <= 0.0)
   {
      Log("ERROR", "InpRiskPercent and InpRiskMoney are both zero: give it a risk budget. Nothing will trade.");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(g_sessionStart == g_sessionEnd)
   {
      Log("ERROR", "the session start and the session end are the same minute: there would never be an entry");
      return INIT_PARAMETERS_INCORRECT;
   }
   g_sessionStart = WrapMinutes(g_sessionStart);
   g_sessionEnd   = WrapMinutes(g_sessionEnd);
   g_flatBy       = WrapMinutes(g_flatBy);

   if(!SymbolSelect(_Symbol, true))
   {
      Log("ERROR", "the terminal does not list " + _Symbol + " in Market Watch");
      return INIT_FAILED;
   }

   if(!CreateHandles())
   {
      Log("ERROR", "could not create the indicator handles: " + IntegerToString(GetLastError()));
      return INIT_FAILED;
   }

   g_trade.SetExpertMagicNumber((ulong)g_magic);
   g_trade.SetDeviationInPoints((ulong)g_deviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   g_liveBlocked = (IsLiveAccount() && !g_allowLive);

   // a fresh plate, even if a previous run left objects behind
   DeletePanel();

   // the banner, then the whole configuration as a small table
   Log("INIT", "-------------------------------------------------------------");
   Log("INIT", "DayTraderMT5 v1.22 on " + _Symbol + " " + PeriodDescription(g_tf) +
              ", account " + AccountModeWord() + " #" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) +
              ", magic " + IntegerToString(g_magic));
   Log("INIT", "-------------------------------------------------------------");

   string shortWord = (g_shorts ? "long and short" : "long only");
   string trendWord = (g_useTrend ? "EMA " + IntegerToString(g_emaFastPeriod) + "/" + IntegerToString(g_emaSlowPeriod)
                                  : "no trend filter");
   Log("CONF", "rule      : " + PeriodDescription(g_tf) + " bars, " + trendWord +
               ", opening range " + IntegerToString(g_orMinutes) + " min, " + shortWord);
   Log("CONF", "stops     : " + DoubleToString(g_atrMult, 2) + " ATR (" + IntegerToString(g_atrPeriod) +
               ") behind the entry or the range mid, target " + DoubleToString(g_minRR, 2) + "R");
   string rangeWord = "off";
   if(g_minRangePoints > 0.0)
      rangeWord = DoubleToString(g_minRangePoints, 0) + " points";
   Log("CONF", "clock     : " + (g_newYork ? "New York" : "server") + " time, session " + HHMM(g_sessionStart) +
               "-" + HHMM(g_sessionEnd) + ", flat by " + HHMM(g_flatBy) +
               (g_weekdaysOnly ? ", weekdays only" : ""));
   Log("CONF", "risk      : " + RiskWords() + " per trade, cap " + DoubleToString(g_maxLots, 2) +
               " lots, " + DoubleToString(g_maxMarginPct, 0) + "% of free margin, range floor " + rangeWord);

   string lossWord = "off";
   if(g_maxDailyLoss > 0.0)
      lossWord = Money(g_maxDailyLoss);
   string spreadWord = "off";
   if(g_spreadMax > 0.0)
      spreadWord = DoubleToString(g_spreadMax, 0) + " points";
   Log("CONF", "limits    : " + IntegerToString(g_maxTrades) + " entr" +
               (g_maxTrades == 1 ? "y" : "ies") + " a day, daily loss stop " + lossWord +
               ", spread ceiling " + spreadWord);

   Log("CONF", "broker    : stops level " + DoubleToString((double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL), 0) +
               " points, freeze level " + DoubleToString((double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL), 0) +
               ", so no stop closer than " + DoubleToString(MinStopPoints(), 0) + " points");
   Log("CONF", "levels    : contract " + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), 0) +
               ", tick value " + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 2) +
               ", volume " + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) +
               " to " + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), 2) +
               " step " + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 2));

   string beWord = "off";
   if(g_beAtR > 0.0)
      beWord = DoubleToString(g_beAtR, 2) + "R";
   string trailWord = "off";
   if(g_trailAtR > 0.0)
      trailWord = DoubleToString(g_trailAtR, 2) + "R / " + IntegerToString(g_trailPoints) + " points";
   string partialWord = "off";
   if(g_partialAtR > 0.0)
      partialWord = DoubleToString(g_partialPct, 0) + "% at " + DoubleToString(g_partialAtR, 2) + "R";
   Log("CONF", "manage    : breakeven " + beWord + ", trail " + trailWord + ", partial " + partialWord);
   Log("CONF", "alerts    : popup " + (g_alertPopup ? "on" : "off") + ", sound " + (g_alertSound ? "on" : "off") +
               ", push " + (g_alertPush ? "on" : "off") + ", verbose log " + (g_verbose ? "on" : "off"));

   string readyWhy = "";
   if(TerminalReady(readyWhy))
      Log("GATE", "trading is allowed: the terminal, the account and the broker all agree");
   else
      Log("GATE", "trading is not allowed yet: " + readyWhy);

   if(g_liveBlocked)
      Log("GATE", "REAL account and InpAllowLive is false: this EA will read and log, and will not trade. "
                  "Switch to a demo account, or set InpAllowLive to true on purpose.");
   string firstFail = "";
   int openGates = GatesOpen(firstFail);
   if(firstFail == "")
      Log("GATE", "all 11 gates are open: an entry would be sent on the next break");
   else
      Log("GATE", StringFormat("%d of 11 gates open, the first closed one: %s", openGates, firstFail));

   Log("INIT", "this EA is offline: no WebRequest, no sockets, no DLL, no include beyond Trade.mqh. "
               "It only talks to your terminal, and your terminal only talks to your broker.");
   Log("INIT", "dashboard: " + (g_showPanel ? "9 pages, click a tab; every row with [-] [+] is live"
                                            : "off (InpShowPanel)") +
               ". TEST page proves it can trade and shows the exact SL and TP.");
   Log("INIT", "-------------------------------------------------------------");

   EventSetTimer(5);
   UpdatePanel();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_emaFast != INVALID_HANDLE)
      IndicatorRelease(g_emaFast);
   if(g_emaSlow != INVALID_HANDLE)
      IndicatorRelease(g_emaSlow);
   if(g_atr != INVALID_HANDLE)
      IndicatorRelease(g_atr);
   SaveSettings();
   DeletePanel();
   ChartRedraw(0);
   Log("STOP", "removed from the chart, reason " + IntegerToString(reason) +
               " (0 chart closed, 1 terminal closed, 2 recompile, 3 new inputs, 4 timeframe)");
}

void OnTimer()
{
   if(g_confirmClose && TimeCurrent() - g_confirmAt > 6)
   {
      g_confirmClose = false;
      Log("CTRL", "CLOSE OUR expired after 6 seconds: nothing was closed", true);
   }
   if(g_confirmReset && TimeCurrent() - g_confirmResetAt > 6)
   {
      g_confirmReset = false;
      Log("CTRL", "RESET expired after 6 seconds: nothing was reset", true);
   }
   Heartbeat();
   UpdatePanel();
}

//+------------------------------------------------------------------+
//| OnTick: flat-by, then management, then the rule on a new bar      |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime nyNow = ToNewYork(TimeCurrent());
   int minutes = MinutesOfDay(nyNow);

   // once a day: forget the marks of positions that are gone
   int day = DayIndexOf(nyNow);
   if(day != g_lastDay)
   {
      g_lastDay = day;
      PruneMarks();
      Log("DAY", "a new day in New York: " + TimeToString(nyNow, TIME_DATE) + ", session " +
                 HHMM(g_sessionStart) + "-" + HHMM(g_sessionEnd) + ", flat by " + HHMM(g_flatBy));
   }

   // flat by the time you set, whatever else is true
   if(PastTime(minutes, g_flatBy) && OurPositions() > 0 && TimeCurrent() - g_flatTry > 30)
   {
      g_flatTry = TimeCurrent();
      CloseAllOurs(minutes, "flat by " + HHMM(g_flatBy) + " New York");
   }

   // manage what is open, even when no new entry is allowed
   ManagePositions();

   // the rule looks at closed bars only
   datetime barTime = (datetime)SeriesInfoInteger(_Symbol, g_tf, SERIES_LASTBAR_DATE);
   if(barTime != 0 && barTime != g_lastBarTime)
   {
      g_lastBarTime = barTime;
      TryEntry();
      UpdatePanel();
   }
}
