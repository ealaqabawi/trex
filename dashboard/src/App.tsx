import { Routes, Route, Navigate } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Overview } from "./routes/Overview";
import { MarketMonitor } from "./routes/MarketMonitor";
import { OptionsChain } from "./routes/OptionsChain";
import { Scanner } from "./routes/Scanner";
import { Intelligence } from "./routes/Intelligence";
import { StrategyLab } from "./routes/StrategyLab";
import { AgentsPage } from "./routes/Agents";
import { RiskCenter } from "./routes/RiskCenter";
import { TelegramMonitor } from "./routes/TelegramMonitor";
import { Settings } from "./routes/Settings";
import { Portfolio } from "./routes/Portfolio";

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/market" element={<MarketMonitor />} />
        <Route path="/options" element={<OptionsChain />} />
        <Route path="/options/:ticker" element={<OptionsChain />} />
        <Route path="/scanner" element={<Scanner />} />
        <Route path="/intelligence" element={<Intelligence />} />
        <Route path="/strategy" element={<StrategyLab />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/risk" element={<RiskCenter />} />
        <Route path="/telegram" element={<TelegramMonitor />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Shell>
  );
}
