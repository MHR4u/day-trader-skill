//+------------------------------------------------------------------+
//| GoldProfessionalEA.mq5                                           |
//| Research EA generated alongside the trader-gold multi-agent tool |
//| New entries are OFF by default. Not financial advice.            |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Closed-bar XAUUSD breakout EA with ATR risk management"
#property description "Validate on broker real ticks and demo before any live use"

#include <Trade/Trade.mqh>

CTrade trade;

input group "Execution and safety"
input bool     InpEnableNewEntries=false;       // Live entries; tester always evaluates entries
input ulong    InpMagic=260119;
input bool     InpRequireGoldSymbol=false;      // If true, require XAU in the broker symbol name
input double   InpMaxSpreadPoints=50.0;
input ulong    InpDeviationPoints=20;
input double   InpCommissionPerLotSide=7.0;     // Sizing estimate only; use your broker value
input bool     InpAllowLong=true;
input bool     InpAllowShort=true;
input bool     InpOnePositionPerSymbol=true;

input group "Strategy: closed candles only"
input ENUM_TIMEFRAMES InpSignalTimeframe=PERIOD_CURRENT;
input ENUM_TIMEFRAMES InpTrendTimeframe=PERIOD_CURRENT; // CURRENT means automatic higher timeframe
input int      InpFastEMA=50;
input int      InpSlowEMA=200;
input int      InpBreakoutBars=20;
input int      InpATRPeriod=14;
input double   InpStopATR=2.0;
input double   InpTargetR=3.0;
input double   InpMinATRPercent=0.0;
input double   InpMaxATRPercent=5.0;
input int      InpMinStopDistancePoints=30;

input group "Position risk and account protection"
input double   InpRiskPerTradePct=0.25;
input double   InpMaxDailyLossPct=2.0;
input double   InpMaxWeeklyLossPct=4.0;
input double   InpMaxTotalDrawdownPct=12.0;
input int      InpMaxTradesPerDay=3;
input int      InpCooldownBars=3;
input int      InpMaxHoldingBars=96;
input bool     InpResetProtectionLocks=false;   // Reset the persistent total lock once, then set false

input group "Automatic profit management"
input bool     InpUsePartial=true;
input double   InpPartialPercent=50.0;
input double   InpPartialAtR=1.0;
input bool     InpUseBreakEven=true;
input double   InpBreakEvenAtR=1.0;
input int      InpBreakEvenOffsetPoints=5;
input bool     InpUseTrailing=true;
input double   InpTrailStartR=1.5;
input double   InpTrailATR=2.0;

input group "Server-time sessions"
input bool     InpUseSessionFilter=false;
input int      InpSessionStartHour=0;
input int      InpSessionEndHour=24;
input bool     InpCloseAtDayEnd=false;
input int      InpDayEndHour=23;
input bool     InpFridayClose=true;
input int      InpFridayCloseHour=20;

input group "USD economic-calendar blackout"
input bool     InpUseNewsFilter=false;          // CSV backtests do not reproduce this filter
input string   InpNewsCurrency="USD";
input int      InpNewsMinutesBefore=30;
input int      InpNewsMinutesAfter=30;
input ENUM_CALENDAR_EVENT_IMPORTANCE InpNewsImportance=CALENDAR_IMPORTANCE_HIGH;
input bool     InpNewsFailClosed=true;
input bool     InpAllowTesterWithoutNews=false; // Prevents silent news-free tester claims

input group "Logging"
input bool     InpChartStatus=true;
input bool     InpVerboseLog=false;

ENUM_TIMEFRAMES signalTF=PERIOD_H1;
ENUM_TIMEFRAMES trendTF=PERIOD_H4;
int fastHandle=INVALID_HANDLE;
int slowHandle=INVALID_HANDLE;
int atrHandle=INVALID_HANDLE;
datetime lastSignalBar=0;
datetime lastEntryTime=0;
datetime lastNewsCheck=0;
bool cachedNewsClear=true;

ulong managedTicket=0;
ulong managedId=0;
double initialRisk=0.0;
double initialVolume=0.0;
bool partialDone=false;

int currentDayKey=-1;
int currentWeekKey=-1;
double dayStartEquity=0.0;
double weekStartEquity=0.0;
double peakEquity=0.0;
bool dailyLocked=false;
bool weeklyLocked=false;
bool totalLocked=false;

//+------------------------------------------------------------------+
//| General helpers                                                  |
//+------------------------------------------------------------------+
bool TradeRetcodeOK()
  {
   uint code=trade.ResultRetcode();
   return(code==TRADE_RETCODE_DONE || code==TRADE_RETCODE_DONE_PARTIAL || code==TRADE_RETCODE_PLACED);
  }

void LogTradeError(const string action)
  {
   PrintFormat("GPF %s failed: %u %s",action,trade.ResultRetcode(),trade.ResultRetcodeDescription());
  }

string StatePrefix()
  {
   return(StringFormat("GPF.%I64d.%s.%I64u",AccountInfoInteger(ACCOUNT_LOGIN),_Symbol,InpMagic));
  }

string PositionKey(const string suffix)
  {
   return(StringFormat("%s.%I64u.%s",StatePrefix(),managedId,suffix));
  }

int DateKey(const datetime value)
  {
   MqlDateTime part;
   TimeToStruct(value,part);
   return(part.year*10000+part.mon*100+part.day);
  }

int WeekKey(const datetime value)
  {
   MqlDateTime part;
   TimeToStruct(value,part);
   datetime monday=value-((part.day_of_week+6)%7)*86400;
   TimeToStruct(monday,part);
   return(part.year*10000+part.mon*100+part.day);
  }

datetime StartOfDay(const datetime value)
  {
   MqlDateTime part;
   TimeToStruct(value,part);
   part.hour=0;
   part.min=0;
   part.sec=0;
   return(StructToTime(part));
  }

datetime StartOfWeek(const datetime value)
  {
   MqlDateTime part;
   TimeToStruct(value,part);
   return(StartOfDay(value-((part.day_of_week+6)%7)*86400));
  }

ENUM_TIMEFRAMES AutoTrend(const ENUM_TIMEFRAMES value)
  {
   switch(value)
     {
      case PERIOD_M1:  return PERIOD_M15;
      case PERIOD_M2:  return PERIOD_M15;
      case PERIOD_M3:  return PERIOD_M15;
      case PERIOD_M4:  return PERIOD_M20;
      case PERIOD_M5:  return PERIOD_M30;
      case PERIOD_M6:  return PERIOD_M30;
      case PERIOD_M10: return PERIOD_H1;
      case PERIOD_M12: return PERIOD_H1;
      case PERIOD_M15: return PERIOD_H1;
      case PERIOD_M20: return PERIOD_H2;
      case PERIOD_M30: return PERIOD_H4;
      case PERIOD_H1:  return PERIOD_H4;
      case PERIOD_H2:  return PERIOD_H8;
      case PERIOD_H3:  return PERIOD_H12;
      case PERIOD_H4:  return PERIOD_D1;
      case PERIOD_H6:  return PERIOD_D1;
      case PERIOD_H8:  return PERIOD_D1;
      case PERIOD_H12: return PERIOD_D1;
      case PERIOD_D1:  return PERIOD_W1;
      case PERIOD_W1:  return PERIOD_MN1;
      default:         return PERIOD_MN1;
     }
  }

double VolumeDown(const double requested)
  {
   double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(step<=0.0 || requested<minimum)
      return(0.0);
   double volume=MathMin(requested,maximum);
   volume=MathFloor((volume+1e-12)/step)*step;
   volume=NormalizeDouble(volume,8);
   if(volume<minimum-1e-12)
      return(0.0);
   return(volume);
  }

bool SelectMyPosition()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0)
         continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      managedTicket=ticket;
      return(true);
     }
   managedTicket=0;
   return(false);
  }

bool ForeignPositionOnSymbol()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         return(true);
     }
   return(false);
  }

bool TradingPermissions()
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
      return(false);
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return(false);
   return(true);
  }

//+------------------------------------------------------------------+
//| Deal history and account guards                                  |
//+------------------------------------------------------------------+
double ClosedTradePnlSince(const datetime from)
  {
   double result=0.0;
   if(!HistorySelect(from,TimeCurrent()+1))
      return(0.0);
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0)
         continue;
      ENUM_DEAL_TYPE kind=(ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket,DEAL_TYPE);
      if(kind!=DEAL_TYPE_BUY && kind!=DEAL_TYPE_SELL)
         continue;
      result+=HistoryDealGetDouble(ticket,DEAL_PROFIT);
      result+=HistoryDealGetDouble(ticket,DEAL_SWAP);
      result+=HistoryDealGetDouble(ticket,DEAL_COMMISSION);
      result+=HistoryDealGetDouble(ticket,DEAL_FEE);
     }
   return(result);
  }

int EntriesToday()
  {
   datetime from=StartOfDay(TimeCurrent());
   if(!HistorySelect(from,TimeCurrent()+1))
      return(0);
   int count=0;
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0 || HistoryDealGetString(ticket,DEAL_SYMBOL)!=_Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=InpMagic)
         continue;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
         count++;
     }
   return(count);
  }

void RecoverLastEntryTime()
  {
   datetime to=TimeCurrent()+1;
   if(!HistorySelect(to-90*86400,to))
      return;
   for(int i=HistoryDealsTotal()-1;i>=0;i--)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0 || HistoryDealGetString(ticket,DEAL_SYMBOL)!=_Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=InpMagic)
         continue;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
        {
         lastEntryTime=(datetime)HistoryDealGetInteger(ticket,DEAL_TIME);
         return;
        }
     }
  }

void UpdateProtection()
  {
   datetime now=TimeCurrent();
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   int dayKey=DateKey(now);
   int weekKey=WeekKey(now);
   if(dayKey!=currentDayKey)
     {
      currentDayKey=dayKey;
      dayStartEquity=equity-ClosedTradePnlSince(StartOfDay(now));
      dailyLocked=false;
     }
   if(weekKey!=currentWeekKey)
     {
      currentWeekKey=weekKey;
      weekStartEquity=equity-ClosedTradePnlSince(StartOfWeek(now));
      weeklyLocked=false;
     }
   if(peakEquity<=0.0)
     {
      string key=StatePrefix()+".peak";
      peakEquity=(GlobalVariableCheck(key) ? GlobalVariableGet(key) : equity);
      if(peakEquity<=0.0)
         peakEquity=equity;
     }
   if(equity>peakEquity)
     {
      peakEquity=equity;
      GlobalVariableSet(StatePrefix()+".peak",peakEquity);
     }
   if(InpMaxDailyLossPct>0.0 && dayStartEquity>0.0 &&
      equity<=dayStartEquity*(1.0-InpMaxDailyLossPct/100.0))
     {
      if(!dailyLocked)
         Print("GPF daily equity-loss lock activated");
      dailyLocked=true;
     }
   if(InpMaxWeeklyLossPct>0.0 && weekStartEquity>0.0 &&
      equity<=weekStartEquity*(1.0-InpMaxWeeklyLossPct/100.0))
     {
      if(!weeklyLocked)
         Print("GPF weekly equity-loss lock activated");
      weeklyLocked=true;
     }
   if(InpMaxTotalDrawdownPct>0.0 && peakEquity>0.0 &&
      equity<=peakEquity*(1.0-InpMaxTotalDrawdownPct/100.0))
     {
      if(!totalLocked)
         Print("GPF persistent total-drawdown lock activated");
      totalLocked=true;
      GlobalVariableSet(StatePrefix()+".totalLock",1.0);
     }
  }

bool CloseManaged(const string reason)
  {
   if(!SelectMyPosition())
      return(true);
   ulong ticket=managedTicket;
   if(InpVerboseLog)
      PrintFormat("GPF closing %I64u: %s",ticket,reason);
   if(!trade.PositionClose(ticket,InpDeviationPoints) || !TradeRetcodeOK())
     {
      LogTradeError("close "+reason);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Recoverable per-position R state                                 |
//+------------------------------------------------------------------+
double OpenedVolumeFromHistory(const ulong identifier)
  {
   if(!HistorySelectByPosition(identifier))
      return(0.0);
   double result=0.0;
   for(int i=0;i<HistoryDealsTotal();i++)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0)
         continue;
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=InpMagic)
         continue;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
         result+=HistoryDealGetDouble(ticket,DEAL_VOLUME);
     }
   return(result);
  }

void SavePositionState()
  {
   if(managedId==0)
      return;
   GlobalVariableSet(PositionKey("risk"),initialRisk);
   GlobalVariableSet(PositionKey("volume"),initialVolume);
   GlobalVariableSet(PositionKey("partial"),(partialDone ? 1.0 : 0.0));
  }

void LoadPositionState()
  {
   if(!SelectMyPosition())
      return;
   ulong identifier=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
   if(identifier==managedId && initialVolume>0.0)
      return;
   managedId=identifier;
   string riskKey=PositionKey("risk");
   string volumeKey=PositionKey("volume");
   string partialKey=PositionKey("partial");
   if(GlobalVariableCheck(riskKey) && GlobalVariableCheck(volumeKey))
     {
      initialRisk=GlobalVariableGet(riskKey);
      initialVolume=GlobalVariableGet(volumeKey);
      partialDone=(GlobalVariableCheck(partialKey) && GlobalVariableGet(partialKey)>0.5);
     }
   else
     {
      initialVolume=OpenedVolumeFromHistory(identifier);
      if(initialVolume<=0.0)
         initialVolume=PositionGetDouble(POSITION_VOLUME);
      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double stop=PositionGetDouble(POSITION_SL);
      ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      initialRisk=MathAbs(open-stop);
      bool originalSide=(stop>0.0 && ((kind==POSITION_TYPE_BUY && stop<open) ||
                                     (kind==POSITION_TYPE_SELL && stop>open)));
      if(!originalSide)
         initialRisk=0.0; // Do not invent R targets after a restart with a moved stop
      double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
      partialDone=(PositionGetDouble(POSITION_VOLUME)<initialVolume-step/2.0);
      if(initialRisk<=0.0)
         partialDone=true;
      Print("GPF recovered an existing position; unavailable original R state disables R-based management");
     }
   SavePositionState();
  }

void ClearPositionState()
  {
   if(managedId!=0)
     {
      GlobalVariableDel(PositionKey("risk"));
      GlobalVariableDel(PositionKey("volume"));
      GlobalVariableDel(PositionKey("partial"));
     }
   managedId=0;
   managedTicket=0;
   initialRisk=0.0;
   initialVolume=0.0;
   partialDone=false;
  }

double ProfitR()
  {
   if(initialRisk<=0.0 || !SelectMyPosition())
      return(-1000.0);
   double open=PositionGetDouble(POSITION_PRICE_OPEN);
   ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
      return(-1000.0);
   double close=(kind==POSITION_TYPE_BUY ? tick.bid : tick.ask);
   double direction=(kind==POSITION_TYPE_BUY ? 1.0 : -1.0);
   return(direction*(close-open)/initialRisk);
  }

bool ModifyManagedStop(double proposed)
  {
   if(!SelectMyPosition())
      return(false);
   ulong ticket=managedTicket;
   double oldStop=PositionGetDouble(POSITION_SL);
   double target=PositionGetDouble(POSITION_TP);
   ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double direction=(kind==POSITION_TYPE_BUY ? 1.0 : -1.0);
   if(oldStop>0.0 && direction*(proposed-oldStop)<=_Point)
      return(false);
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
      return(false);
   double market=(kind==POSITION_TYPE_BUY ? tick.bid : tick.ask);
   double stops=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   double freeze=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL)*_Point;
   if((kind==POSITION_TYPE_BUY && proposed>=market-stops) ||
      (kind==POSITION_TYPE_SELL && proposed<=market+stops))
      return(false);
   if(freeze>0.0)
     {
      if(oldStop>0.0 && MathAbs(market-oldStop)<=freeze)
         return(false);
      if(target>0.0 && MathAbs(market-target)<=freeze)
         return(false);
     }
   proposed=NormalizeDouble(proposed,_Digits);
   if(!trade.PositionModify(ticket,proposed,target) || !TradeRetcodeOK())
     {
      LogTradeError("stop modification");
      return(false);
     }
   return(true);
  }

bool PartialCloseVolume(const double volume)
  {
   if(!SelectMyPosition())
      return(false);
   ulong ticket=managedTicket;
   ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   bool sent=false;
   ENUM_ACCOUNT_MARGIN_MODE mode=(ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(mode==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      sent=trade.PositionClosePartial(ticket,volume,InpDeviationPoints);
     }
   else
     {
      // CTrade::PositionClosePartial is hedging-only. An opposite, smaller
      // market deal reduces a netting position without reversing it.
      if(kind==POSITION_TYPE_BUY)
         sent=trade.Sell(volume,_Symbol,0.0,0.0,0.0,"GPF partial");
      else
         sent=trade.Buy(volume,_Symbol,0.0,0.0,0.0,"GPF partial");
     }
   if(!sent || !TradeRetcodeOK())
     {
      LogTradeError("partial close");
      return(false);
     }
   return(true);
  }

void ManagePartial()
  {
   if(!InpUsePartial || partialDone || initialRisk<=0.0 || ProfitR()<InpPartialAtR)
      return;
   if(!SelectMyPosition())
      return;
   double current=PositionGetDouble(POSITION_VOLUME);
   double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double volume=VolumeDown(initialVolume*InpPartialPercent/100.0);
   if(volume<minimum || current-volume<minimum)
     {
      partialDone=true; // Too small to split safely; leave the full bracket intact
      SavePositionState();
      return;
     }
   if(PartialCloseVolume(volume))
     {
      partialDone=true;
      SavePositionState();
      if(InpUseBreakEven)
        {
         double open=PositionGetDouble(POSITION_PRICE_OPEN);
         ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         double direction=(kind==POSITION_TYPE_BUY ? 1.0 : -1.0);
         ModifyManagedStop(open+direction*InpBreakEvenOffsetPoints*_Point);
        }
     }
  }

void ManageBreakEven()
  {
   if(!InpUseBreakEven || initialRisk<=0.0 || ProfitR()<InpBreakEvenAtR)
      return;
   if(!SelectMyPosition())
      return;
   double open=PositionGetDouble(POSITION_PRICE_OPEN);
   ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double direction=(kind==POSITION_TYPE_BUY ? 1.0 : -1.0);
   ModifyManagedStop(open+direction*InpBreakEvenOffsetPoints*_Point);
  }

void ManageTrailing()
  {
   if(!InpUseTrailing || initialRisk<=0.0 || ProfitR()<InpTrailStartR)
      return;
   double atrValue[];
   if(CopyBuffer(atrHandle,0,1,1,atrValue)!=1 || atrValue[0]<=0.0)
      return;
   if(!SelectMyPosition())
      return;
   ENUM_POSITION_TYPE kind=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
      return;
   double proposed=(kind==POSITION_TYPE_BUY ? tick.bid-InpTrailATR*atrValue[0]
                                             : tick.ask+InpTrailATR*atrValue[0]);
   ModifyManagedStop(proposed);
  }

void ManageTimeExits()
  {
   if(!SelectMyPosition())
      return;
   MqlDateTime part;
   TimeToStruct(TimeCurrent(),part);
   if(InpFridayClose && part.day_of_week==5 && part.hour>=InpFridayCloseHour)
     {
      CloseManaged("Friday exit");
      return;
     }
   if(InpCloseAtDayEnd && part.hour>=InpDayEndHour)
     {
      CloseManaged("day-end exit");
      return;
     }
   if(InpMaxHoldingBars>0)
     {
      datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
      int shift=iBarShift(_Symbol,signalTF,opened,false);
      if(shift>=InpMaxHoldingBars)
         CloseManaged("maximum holding time");
     }
  }

//+------------------------------------------------------------------+
//| Entry filters, sizing and signal                                 |
//+------------------------------------------------------------------+
bool EntryWindow()
  {
   MqlDateTime part;
   TimeToStruct(TimeCurrent(),part);
   if(part.day_of_week==0 || part.day_of_week==6)
      return(false);
   if(InpFridayClose && part.day_of_week==5 && part.hour>=InpFridayCloseHour)
      return(false);
   if(!InpUseSessionFilter)
      return(true);
   if(InpSessionStartHour<=InpSessionEndHour)
      return(part.hour>=InpSessionStartHour && part.hour<InpSessionEndHour);
   return(part.hour>=InpSessionStartHour || part.hour<InpSessionEndHour);
  }

bool SpreadClear()
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick) || _Point<=0.0)
      return(false);
   return((tick.ask-tick.bid)/_Point<=InpMaxSpreadPoints);
  }

bool NewsClear()
  {
   if(!InpUseNewsFilter)
      return(true);
   if(MQLInfoInteger(MQL_TESTER))
      return(InpAllowTesterWithoutNews);
   datetime now=TimeCurrent();
   if(lastNewsCheck>0 && now-lastNewsCheck<60)
      return(cachedNewsClear);
   lastNewsCheck=now;
   cachedNewsClear=false;
   MqlCalendarValue values[];
   ResetLastError();
   int count=CalendarValueHistory(values,now-InpNewsMinutesAfter*60,
                                  now+InpNewsMinutesBefore*60,NULL,InpNewsCurrency);
   if(count<0)
     {
      PrintFormat("GPF calendar error %d; fail-closed=%s",GetLastError(),(InpNewsFailClosed ? "true" : "false"));
      cachedNewsClear=!InpNewsFailClosed;
      return(cachedNewsClear);
     }
   for(int i=0;i<count;i++)
     {
      MqlCalendarEvent event;
      if(!CalendarEventById(values[i].event_id,event))
         continue;
      if(event.importance>=InpNewsImportance)
        {
         if(InpVerboseLog)
            PrintFormat("GPF news blackout: %s at %s",event.name,TimeToString(values[i].time));
         return(false);
        }
     }
   cachedNewsClear=true;
   return(true);
  }

bool CooldownClear()
  {
   if(lastEntryTime==0 || InpCooldownBars<=0)
      return(true);
   return(TimeCurrent()-lastEntryTime>=InpCooldownBars*PeriodSeconds(signalTF));
  }

double RiskVolume(const ENUM_ORDER_TYPE kind,const double entry,const double stop)
  {
   double oneLotLoss=0.0;
   if(!OrderCalcProfit(kind,_Symbol,1.0,entry,stop,oneLotLoss))
     {
      PrintFormat("GPF OrderCalcProfit failed: %d",GetLastError());
      return(0.0);
     }
   double riskPerLot=MathAbs(oneLotLoss)+2.0*InpCommissionPerLotSide+
                     InpDeviationPoints*_Point*SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE)/
                     MathMax(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),_Point);
   if(riskPerLot<=0.0)
      return(0.0);
   double cash=AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPerTradePct/100.0;
   double volume=VolumeDown(cash/riskPerLot);
   if(volume<=0.0)
      return(0.0);
   double margin=0.0;
   if(OrderCalcMargin(kind,_Symbol,volume,entry,margin))
     {
      double available=AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.95;
      if(margin>available && margin>0.0)
         volume=VolumeDown(volume*available/margin);
     }
   return(volume);
  }

void EvaluateEntry()
  {
   if(EntriesToday()>=InpMaxTradesPerDay || !CooldownClear())
      return;
   if(InpOnePositionPerSymbol && ForeignPositionOnSymbol())
      return;
   int requiredBars=(InpSlowEMA>InpATRPeriod ? InpSlowEMA : InpATRPeriod)+InpBreakoutBars+5;
   if(BarsCalculated(fastHandle)<requiredBars || BarsCalculated(slowHandle)<requiredBars ||
      BarsCalculated(atrHandle)<requiredBars)
      return;
   MqlRates rates[];
   ArraySetAsSeries(rates,true);
   int needed=InpBreakoutBars+1;
   if(CopyRates(_Symbol,signalTF,1,needed,rates)!=needed)
      return;
   double fast[],slow[],atrValue[];
   MqlRates trendBar[];
   if(CopyBuffer(fastHandle,0,1,1,fast)!=1 || CopyBuffer(slowHandle,0,1,1,slow)!=1 ||
      CopyBuffer(atrHandle,0,1,1,atrValue)!=1 || CopyRates(_Symbol,trendTF,1,1,trendBar)!=1)
      return;
   if(atrValue[0]<=0.0 || rates[0].close<=0.0)
      return;
   double atrPercent=100.0*atrValue[0]/rates[0].close;
   if(atrPercent<InpMinATRPercent || atrPercent>InpMaxATRPercent)
      return;
   double highest=rates[1].high;
   double lowest=rates[1].low;
   for(int i=2;i<=InpBreakoutBars;i++)
     {
      highest=MathMax(highest,rates[i].high);
      lowest=MathMin(lowest,rates[i].low);
     }
   bool longTrend=fast[0]>slow[0] && trendBar[0].close>slow[0];
   bool shortTrend=fast[0]<slow[0] && trendBar[0].close<slow[0];
   int direction=0;
   if(InpAllowLong && longTrend && rates[0].close>highest)
      direction=1;
   else if(InpAllowShort && shortTrend && rates[0].close<lowest)
      direction=-1;
   if(direction==0)
      return;
   ENUM_SYMBOL_TRADE_MODE mode=(ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if(mode==SYMBOL_TRADE_MODE_DISABLED || mode==SYMBOL_TRADE_MODE_CLOSEONLY)
      return;
   if((direction==1 && mode==SYMBOL_TRADE_MODE_SHORTONLY) ||
      (direction==-1 && mode==SYMBOL_TRADE_MODE_LONGONLY))
      return;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
      return;
   double entry=(direction==1 ? tick.ask : tick.bid);
   double spread=tick.ask-tick.bid;
   double brokerMinimum=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   double minimum=MathMax(InpMinStopDistancePoints*_Point,brokerMinimum)+spread;
   double distance=MathMax(InpStopATR*atrValue[0],minimum);
   if(distance<=0.0)
      return;
   double stop=entry-direction*distance;
   double target=entry+direction*distance*InpTargetR;
   if(stop<=0.0 || target<=0.0)
      return;
   stop=NormalizeDouble(stop,_Digits);
   target=NormalizeDouble(target,_Digits);
   ENUM_ORDER_TYPE kind=(direction==1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double volume=RiskVolume(kind,entry,stop);
   if(volume<=0.0)
     {
      if(InpVerboseLog)
         Print("GPF signal skipped: volume below broker minimum or insufficient free margin");
      return;
     }
   bool sent=(direction==1 ? trade.Buy(volume,_Symbol,0.0,stop,target,"GPF breakout")
                           : trade.Sell(volume,_Symbol,0.0,stop,target,"GPF breakout"));
   if(!sent || !TradeRetcodeOK())
     {
      LogTradeError("entry");
      return;
     }
   lastEntryTime=TimeCurrent();
   if(SelectMyPosition())
     {
      managedId=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      initialRisk=distance;
      initialVolume=volume;
      partialDone=false;
      SavePositionState();
     }
   if(InpVerboseLog)
      PrintFormat("GPF entry %s %.2f lots, SL %.*f TP %.*f",(direction==1 ? "BUY" : "SELL"),
                  volume,_Digits,stop,_Digits,target);
  }

void UpdateChartStatus()
  {
   if(!InpChartStatus)
      return;
   string state="ACTIVE";
   if(!InpEnableNewEntries && !MQLInfoInteger(MQL_TESTER))
      state="ENTRIES OFF";
   if(dailyLocked)
      state="DAILY LOCK";
   if(weeklyLocked)
      state="WEEKLY LOCK";
   if(totalLocked)
      state="TOTAL DD LOCK";
   MqlTick tick;
   double spread=0.0;
   if(SymbolInfoTick(_Symbol,tick) && _Point>0.0)
      spread=(tick.ask-tick.bid)/_Point;
   Comment(StringFormat("Gold Professional EA | %s\nSignal %s | Trend %s | Spread %.1f points\nDaily %.2f%% | Weekly %.2f%% | Peak equity %.2f\nResearch software, not financial advice",
           state,EnumToString(signalTF),EnumToString(trendTF),spread,
           (dayStartEquity>0.0 ? 100.0*(AccountInfoDouble(ACCOUNT_EQUITY)/dayStartEquity-1.0) : 0.0),
           (weekStartEquity>0.0 ? 100.0*(AccountInfoDouble(ACCOUNT_EQUITY)/weekStartEquity-1.0) : 0.0),
           peakEquity));
  }

//+------------------------------------------------------------------+
//| MT5 events                                                       |
//+------------------------------------------------------------------+
int OnInit()
  {
   signalTF=(InpSignalTimeframe==PERIOD_CURRENT ? (ENUM_TIMEFRAMES)_Period : InpSignalTimeframe);
   trendTF=(InpTrendTimeframe==PERIOD_CURRENT ? AutoTrend(signalTF) : InpTrendTimeframe);
   if(InpFastEMA<1 || InpSlowEMA<=InpFastEMA || InpBreakoutBars<2 || InpATRPeriod<2 ||
      InpStopATR<=0.0 || InpTargetR<=0.0 || InpRiskPerTradePct<=0.0 || InpRiskPerTradePct>5.0 ||
      InpMaxTradesPerDay<1 || InpMaxHoldingBars<1 || InpPartialPercent<=0.0 || InpPartialPercent>=100.0 ||
      InpSessionStartHour<0 || InpSessionStartHour>23 || InpSessionEndHour<1 || InpSessionEndHour>24 ||
      InpNewsMinutesBefore<0 || InpNewsMinutesAfter<0)
     {
      Print("GPF invalid input parameters");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(PeriodSeconds(trendTF)<PeriodSeconds(signalTF) || InpMagic==0 ||
      InpMaxSpreadPoints<=0.0 || InpMinStopDistancePoints<0 || InpCommissionPerLotSide<0.0 ||
      InpMinATRPercent<0.0 || InpMaxATRPercent<=InpMinATRPercent ||
      InpMaxDailyLossPct<0.0 || InpMaxDailyLossPct>=100.0 ||
      InpMaxWeeklyLossPct<0.0 || InpMaxWeeklyLossPct>=100.0 ||
      InpMaxTotalDrawdownPct<0.0 || InpMaxTotalDrawdownPct>=100.0 ||
      InpFridayCloseHour<0 || InpFridayCloseHour>23 || InpDayEndHour<0 || InpDayEndHour>23 ||
      (InpUseNewsFilter && StringLen(InpNewsCurrency)==0))
     {
      Print("GPF invalid safety, timeframe or risk parameters");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpRequireGoldSymbol && StringFind(_Symbol,"XAU")<0)
     {
      Print("GPF this chart is not an XAU symbol");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpUseNewsFilter && MQLInfoInteger(MQL_TESTER) && !InpAllowTesterWithoutNews)
     {
      Print("GPF refusing a tester run that would silently omit the enabled news filter. Provide calendar data externally or explicitly allow a news-free test.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);
   fastHandle=iMA(_Symbol,trendTF,InpFastEMA,0,MODE_EMA,PRICE_CLOSE);
   slowHandle=iMA(_Symbol,trendTF,InpSlowEMA,0,MODE_EMA,PRICE_CLOSE);
   atrHandle=iATR(_Symbol,signalTF,InpATRPeriod);
   if(fastHandle==INVALID_HANDLE || slowHandle==INVALID_HANDLE || atrHandle==INVALID_HANDLE)
     {
      PrintFormat("GPF indicator initialization failed: %d",GetLastError());
      return(INIT_FAILED);
     }
   lastSignalBar=iTime(_Symbol,signalTF,0); // Never enter from a stale signal on attachment
   RecoverLastEntryTime();
   if(InpResetProtectionLocks)
     {
      GlobalVariableDel(StatePrefix()+".totalLock");
      GlobalVariableDel(StatePrefix()+".peak");
      Print("GPF protection lock reset requested; set InpResetProtectionLocks=false now");
     }
   totalLocked=(GlobalVariableCheck(StatePrefix()+".totalLock") &&
                GlobalVariableGet(StatePrefix()+".totalLock")>0.5);
   UpdateProtection();
   if(SelectMyPosition())
      LoadPositionState();
   EventSetTimer(30);
   UpdateChartStatus();
   PrintFormat("GPF initialized on %s, signal=%s trend=%s; live new entries=%s",
               _Symbol,EnumToString(signalTF),EnumToString(trendTF),(InpEnableNewEntries ? "true" : "false"));
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(fastHandle!=INVALID_HANDLE)
      IndicatorRelease(fastHandle);
   if(slowHandle!=INVALID_HANDLE)
      IndicatorRelease(slowHandle);
   if(atrHandle!=INVALID_HANDLE)
      IndicatorRelease(atrHandle);
   Comment("");
  }

void OnTick()
  {
   UpdateProtection();
   if(dailyLocked || weeklyLocked || totalLocked)
     {
      CloseManaged("account protection");
      UpdateChartStatus();
      return;
     }
   if(SelectMyPosition())
     {
      LoadPositionState();
      ManageTimeExits();
      if(SelectMyPosition())
        {
         ManagePartial();
         if(SelectMyPosition())
           {
            ManageBreakEven();
            ManageTrailing();
           }
        }
     }
   else
      ClearPositionState();

   datetime currentBar=iTime(_Symbol,signalTF,0);
   if(currentBar<=0 || currentBar==lastSignalBar)
     {
      UpdateChartStatus();
      return;
     }
   lastSignalBar=currentBar;
   bool tester=MQLInfoInteger(MQL_TESTER);
   if((InpEnableNewEntries || tester) && TradingPermissions() && !SelectMyPosition() &&
      EntryWindow() && SpreadClear() && NewsClear())
      EvaluateEntry();
   UpdateChartStatus();
  }

void OnTimer()
  {
   UpdateProtection();
   if(dailyLocked || weeklyLocked || totalLocked)
      CloseManaged("timer account protection");
   UpdateChartStatus();
  }

// Optimization score only. It does not replace walk-forward or forward tests.
double OnTester()
  {
   double trades=TesterStatistics(STAT_TRADES);
   double profit=TesterStatistics(STAT_PROFIT);
   double factor=TesterStatistics(STAT_PROFIT_FACTOR);
   double drawdown=TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   if(trades<30 || profit<=0.0 || factor<=1.0)
      return(-1000000.0+trades);
   double score=MathLog(1.0+MathMax(0.0,factor))*MathSqrt(trades);
   score*=MathMax(0.0,1.0-drawdown/100.0);
   return(score);
  }
//+------------------------------------------------------------------+
