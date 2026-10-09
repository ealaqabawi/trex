import { useMemo, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState } from "../components/Card";
import { fmtPct, fmtPrice, fmtInt } from "../lib/format";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const PERIODS = ["1mo", "3mo", "6mo", "1y", "2y"];

export function StrategyLab() {
  const strategies = useApi(api.strategies);
  const [ticker, setTicker] = useState("SPY");
  const [strategy, setStrategy] = useState("momentum");
  const [period, setPeriod] = useState("1y");
  const [compareBaseline, setCompareBaseline] = useState(true);

  const result = useApi(
    () => api.backtest({ ticker, strategy, period }),
    [ticker, strategy, period]
  );

  const d = result.data;

  const chartData = useMemo(() => {
    if (!d || !d.ok) return [];
    const startEquity = d.starting_equity;
    const bars = d.trades.length;
    const curve = d.equity_curve;
    return curve.map((eq, i) => ({
      i, eq,
      baseline: startEquity * (1 + (d.buy_and_hold_return_pct / 100) * (i / Math.max(curve.length - 1, 1))),
    })).filter((_, i) => i % Math.max(1, Math.floor(curve.length / 400)) === 0 || i === curve.length - 1).slice(0, 1000);
    // No-op reference to bars so the lint keeps it visible: the UI shows trade count elsewhere.
    void bars;
  }, [d]);

  return (
    <>
      <PageHead
        title="Strategy Lab"
        subtitle="Reproducible historical backtests. Baseline is buy-and-hold over the same window."
      />

      <div className="row-tight" style={{ marginBottom: 14 }}>
        <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())}
               style={{ width: 110 }} />
        <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          {strategies.data?.ok ? strategies.data.strategies.map((s) => (
            <option key={s.name} value={s.name}>{s.name}</option>
          )) : <option>loading…</option>}
        </select>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <label className="row-tight">
          <input type="checkbox" checked={compareBaseline} onChange={(e) => setCompareBaseline(e.target.checked)} />
          <span>Compare buy-and-hold</span>
        </label>
        <button className="primary" onClick={result.reload}>Run</button>
      </div>

      {result.loading && !d ? (
        <Skeleton height={340} />
      ) : d && d.ok ? (
        <>
          <div className="grid grid-cols-4">
            <StatTile label="Total return" value={fmtPct(d.total_return_pct)}
                       tone={d.total_return_pct > 0 ? "up" : "down"} />
            <StatTile label="Buy & hold" value={fmtPct(d.buy_and_hold_return_pct)}
                       tone={d.buy_and_hold_return_pct > 0 ? "up" : "down"} />
            <StatTile label="Max drawdown" value={fmtPct(d.max_drawdown_pct)}
                       tone="down" />
            <StatTile label="Sharpe" value={d.sharpe_ratio.toFixed(2)} />
            <StatTile label="Win rate" value={fmtPct(d.win_rate_pct, 1)} />
            <StatTile label="Trades" value={fmtInt(d.trade_count)} />
            <StatTile label="Lookback" value={String(d.lookback)} />
            <StatTile label="Ending equity" value={`$${fmtPrice(d.ending_equity, 0)}`} />
          </div>

          <Panel title="Equity curve">
            <div style={{ height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={chartData}>
                  <CartesianGrid stroke="#171b22" />
                  <XAxis dataKey="i" tick={{ fill: "#6b7383", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#6b7383", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: "#0b0d10", border: "1px solid #22283340",
                                     fontSize: 11, color: "#e8ecf2" }}
                  />
                  <Line type="monotone" dataKey="eq" stroke="#4cc9f0" dot={false} strokeWidth={1.5} />
                  {compareBaseline && (
                    <Line type="monotone" dataKey="baseline" stroke="#7a8597" strokeDasharray="4 4" dot={false} />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel title={`Trades (${d.trade_count})`}>
            {d.trades.length === 0 ? (
              <EmptyState title="No trades in this window">The strategy never fired.</EmptyState>
            ) : (
              <div className="scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Entry</th>
                      <th>Entry price</th>
                      <th>Exit</th>
                      <th>Exit price</th>
                      <th>Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.trades.map((t, i) => {
                      const pct = t.exit_price !== null
                        ? ((t.exit_price - t.entry_price) / t.entry_price) * 100
                        : null;
                      return (
                        <tr key={i}>
                          <td className="dim">{t.entry_date}</td>
                          <td className="mono">{fmtPrice(t.entry_price)}</td>
                          <td className="dim">{t.exit_date ?? "–"}</td>
                          <td className="mono">{t.exit_price === null ? "–" : fmtPrice(t.exit_price)}</td>
                          <td className={"mono " + ((pct ?? 0) > 0 ? "up" : "down")}>
                            {pct === null ? "–" : fmtPct(pct)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <div className="dim" style={{ fontSize: 11.5, marginTop: 10 }}>
            Backtests exclude transaction costs and slippage by default; add explicit assumptions before using them to size paper trades.
          </div>
        </>
      ) : (
        <EmptyState title="Backtest failed">{d?.error ?? result.error ?? "–"}</EmptyState>
      )}
    </>
  );
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="card">
      <div className="card-title">{label}</div>
      <div className={"card-value-sm " + (tone ?? "")}>{value}</div>
    </div>
  );
}
