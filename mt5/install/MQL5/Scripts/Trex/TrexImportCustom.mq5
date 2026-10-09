//+------------------------------------------------------------------+
//| TrexImportCustom.mq5                                              |
//| Builds custom symbols (e.g. GOLD.cap) from Capital.com 1-minute   |
//| history so the Strategy Tester can run on the prices Emad trades. |
//| Input: MQL5\Files\trex_import\specs.csv  (name,digits,file)       |
//|        MQL5\Files\trex_import\<file>.bin  raw MqlRates records    |
//| Market data only - no trading functions.                          |
//+------------------------------------------------------------------+
#property script_show_inputs
#property version "1.00"

input string SpecFile       = "trex_import\\specs.csv";
input bool   CloseWhenDone  = true;

bool BuildSymbol(const string name, const int digits, const string currency)
  {
   if(!SymbolInfoInteger(name, SYMBOL_CUSTOM))
     {
      ResetLastError();
      if(!CustomSymbolCreate(name, "Trex\\Capital.com"))
        {
         Print(name, ": CustomSymbolCreate failed, error ", GetLastError());
         return false;
        }
     }
   double point = MathPow(10.0, -digits);
   CustomSymbolSetInteger(name, SYMBOL_DIGITS, digits);
   CustomSymbolSetDouble(name, SYMBOL_POINT, point);
   CustomSymbolSetDouble(name, SYMBOL_TRADE_TICK_SIZE, point);
   CustomSymbolSetDouble(name, SYMBOL_TRADE_TICK_VALUE, point);
   CustomSymbolSetDouble(name, SYMBOL_TRADE_CONTRACT_SIZE, 1.0);
   CustomSymbolSetDouble(name, SYMBOL_VOLUME_MIN, 0.01);
   CustomSymbolSetDouble(name, SYMBOL_VOLUME_MAX, 1000.0);
   CustomSymbolSetDouble(name, SYMBOL_VOLUME_STEP, 0.01);
   CustomSymbolSetInteger(name, SYMBOL_SPREAD_FLOAT, true);
   CustomSymbolSetInteger(name, SYMBOL_TRADE_CALC_MODE, SYMBOL_CALC_MODE_CFD);
   CustomSymbolSetInteger(name, SYMBOL_TRADE_MODE, SYMBOL_TRADE_MODE_FULL);
   CustomSymbolSetInteger(name, SYMBOL_CHART_MODE, SYMBOL_CHART_MODE_BID);
   CustomSymbolSetString(name, SYMBOL_CURRENCY_BASE, currency);
   CustomSymbolSetString(name, SYMBOL_CURRENCY_PROFIT, currency);
   CustomSymbolSetString(name, SYMBOL_CURRENCY_MARGIN, currency);
   CustomSymbolSetString(name, SYMBOL_DESCRIPTION, name + " - Capital.com 1-minute bid history with real spread");
   // trade and quote all week
   for(int d = 0; d < 7; d++)
     {
      CustomSymbolSetSessionQuote(name, (ENUM_DAY_OF_WEEK)d, 0, 0, 86400);
      CustomSymbolSetSessionTrade(name, (ENUM_DAY_OF_WEEK)d, 0, 0, 86400);
     }
   return true;
  }

int ImportRates(const string name, const string file)
  {
   int fh = FileOpen(file, FILE_READ | FILE_BIN);
   if(fh == INVALID_HANDLE)
     {
      Print(name, ": cannot open ", file, " error ", GetLastError());
      return -1;
     }
   MqlRates rates[];
   uint n = FileReadArray(fh, rates);
   FileClose(fh);
   if(n == 0)
     {
      Print(name, ": no records in ", file);
      return -1;
     }
   CustomRatesDelete(name, 0, LONG_MAX);
   int total = 0;
   const int CHUNK = 50000;
   for(int start = 0; start < (int)n; start += CHUNK)
     {
      int cnt = MathMin(CHUNK, (int)n - start);
      MqlRates part[];
      ArrayCopy(part, rates, 0, start, cnt);
      int done = CustomRatesUpdate(name, part);
      if(done < 0)
        {
         Print(name, ": CustomRatesUpdate failed at ", start, " error ", GetLastError());
         return -1;
        }
      total += done;
     }
   PrintFormat("%s: imported %d M1 bars %s .. %s", name, total,
               TimeToString(rates[0].time), TimeToString(rates[n - 1].time));
   return total;
  }

void OnStart()
  {
   Print("TrexImportCustom: sizeof(MqlRates)=", sizeof(MqlRates));
   int fh = FileOpen(SpecFile, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE)
     {
      Print("Cannot open ", SpecFile, " error ", GetLastError());
      if(CloseWhenDone) TerminalClose(1);
      return;
     }
   int ok = 0, bad = 0;
   while(!FileIsEnding(fh))
     {
      string name = FileReadString(fh);
      if(name == "" || StringFind(name, "#") == 0)
        {
         while(!FileIsLineEnding(fh) && !FileIsEnding(fh)) FileReadString(fh);
         continue;
        }
      int digits = (int)StringToInteger(FileReadString(fh));
      string file = FileReadString(fh);
      string currency = FileReadString(fh);
      if(currency == "") currency = "USD";
      if(BuildSymbol(name, digits, currency) && ImportRates(name, file) > 0)
         ok++;
      else
         bad++;
     }
   FileClose(fh);
   PrintFormat("TrexImportCustom finished: %d symbols ok, %d failed", ok, bad);
   if(CloseWhenDone)
      TerminalClose(0);
  }
//+------------------------------------------------------------------+
