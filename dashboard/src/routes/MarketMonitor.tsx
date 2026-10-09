import { useState } from "react";
import { usePolling, useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState } from "../components/Card";
import { PriceChart } from "../components/PriceChart";
import { cls, fmtPct, fmtPrice, fmtInt } from "../lib/format";

export function MarketMonitor() {
  const snap = usePolling(api.marketSnapshot, 20_000);
  const [selected, setSelected] = useState<string | null>(null);
  const [interval, setInterval] = useState("5m");

  const first = snap.data?.rows[0]?.ticker ?? null;
  const activeTicker = selected ?? first;

  const quote = useApi(() => api.quote(activeTicker ?? "SPY", interval, "1d"), [activeTicker, interval]);

  return (
    <>
      <PageHead
        title="Live Market Monitor"
        subtitle={`session: ${snap.data?.session.session ?? "…"} · freshness thresholds are shown on each row`}
      />

      {snap.data ? (
        <table className="table" style={{ background: "var(--bg-1)", borderRadius: 6 }}>
          <thead>
            <tr>
              <th>Instrument</th>
              <th>Last</th>
              <th>Change</th>
              <th>Change %</th>
              <th>Prev close</th>
              <th>Freshness</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {snap.data.rows.map((r) => (
              <tr
                key={r.ticker}
                style={{ cursor: "pointer" }}
                onClick={() => setSelected(r.ticker)}
                className={cls(activeTicker === r.ticker && "active-row")}
              >
                <td>
                  <strong>{r.ticker}</strong>
                </td>
                <td className="mono">{fmtPrice(r.last_price)}</td>
                <td className={cls("mono", (r.change ?? 0) > 0 ? "up" : (r.change ?? 0) < 0 ? "down" : "dim")}>
                  {r.change === null ? "–" : (r.change >= 0 ? "+" : "") + fmtPrice(r.change)}
                </td>
                <td className={cls("mono", (r.change_pct ?? 0) > 0 ? "up" : (r.change_pct ?? 0) < 0 ? "down" : "dim")}>
                  {fmtPct(r.change_pct)}
                </td>
                <td className="mono dim">{fmtPrice(r.previous_close)}</td>
                <td><span className={`badge ${r.freshness}`}>{r.freshness}</span></td>
                <td className="dim">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <Skeleton height={200} />
      )}

      <Panel
        title={activeTicker ? `${activeTicker} intraday` : "Select an instrument"}
        action={
          <div className="row-tight">
            {["1m", "5m", "15m", "30m", "1h"].map((i) => (
              <button
                key={i}
                className={interval === i ? "primary" : undefined}
                onClick={() => setInterval(i)}
              >
                {i}
              </button>
            ))}
          </div>
        }
      >
        {quote.loading && !quote.data ? (
          <Skeleton height={320} />
        ) : quote.data?.ok && quote.data.bars.length > 0 ? (
          <>
            <div className="row-tight dim" style={{ marginBottom: 8 }}>
              <span>Last: <strong className="mono">{fmtPrice(quote.data.last_price)}</strong></span>
              <span>Bars: <strong className="mono">{fmtInt(quote.data.bars.length)}</strong></span>
              <span>
                Freshness: <span className={`badge ${quote.data.freshness}`}>{quote.data.freshness}</span>
              </span>
              <span>Source: {quote.data.source}</span>
            </div>
            <PriceChart bars={quote.data.bars} height={340} />
          </>
        ) : (
          <EmptyState title="No intraday bars">
            {quote.data?.error ?? "The data source returned no bars for this interval."}
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
