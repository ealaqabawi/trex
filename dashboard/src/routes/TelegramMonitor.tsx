import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState, StatCard } from "../components/Card";
import { fmtInt, fmtPct, fmtRelative } from "../lib/format";

export function TelegramMonitor() {
  const q = useApi(api.telegram);
  const d = q.data;

  return (
    <>
      <PageHead
        title="Telegram Monitor"
        subtitle={d ? (d.configured ? "Bot credentials configured" : "No TELEGRAM_BOT_TOKEN set") : "loading…"}
      />

      {d ? (
        <div className="grid grid-cols-4">
          <StatCard title="Total sent" value={fmtInt(d.delivery_summary.total)} />
          <StatCard title="Delivered" value={fmtInt(d.delivery_summary.delivered)}
                     tone="up" />
          <StatCard title="Failed" value={fmtInt(d.delivery_summary.failed)}
                     tone={d.delivery_summary.failed > 0 ? "down" : undefined} />
          <StatCard
            title="Delivery rate"
            value={
              d.delivery_summary.total === 0
                ? "n/a"
                : fmtPct((d.delivery_summary.delivered / d.delivery_summary.total) * 100, 1)
            }
          />
        </div>
      ) : (
        <Skeleton height={100} />
      )}

      <div className="grid grid-cols-2" style={{ marginTop: 14 }}>
        <Panel title="Delivery history">
          {!d ? (
            <Skeleton height={200} />
          ) : d.history.length === 0 ? (
            <EmptyState title="No Telegram deliveries recorded">
              Deliveries are logged to <span className="mono">memory.telegram_history</span> each time the signal publisher posts.
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Ticker</th>
                  <th>Direction</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {d.history.map((h, i) => (
                  <tr key={i}>
                    <td className="dim">{fmtRelative(h.sent_at)}</td>
                    <td>{h.ticker ?? "–"}</td>
                    <td>{h.direction ?? "–"}</td>
                    <td>
                      <span className={`badge ${h.delivered ? "ok" : "failed"}`}>
                        {h.delivered ? "delivered" : "failed"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Recent published signals">
          {!d ? (
            <Skeleton height={200} />
          ) : d.recent_signals.length === 0 ? (
            <EmptyState title="No published signals yet">
              The signal engine writes to <span className="mono">logs/signals.jsonl</span>, which this view aggregates.
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Ticker</th>
                  <th>Dir</th>
                  <th>Action</th>
                  <th>Confidence</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_signals.map((s, i) => (
                  <tr key={i}>
                    <td className="dim">{fmtRelative(s.generated_at)}</td>
                    <td><strong>{s.ticker}</strong></td>
                    <td>{s.direction}</td>
                    <td>{s.action}</td>
                    <td className="mono">{s.confidence}%</td>
                    <td>
                      <span className={`badge ${s.outcome === "win" ? "ok" : s.outcome === "loss" ? "failed" : "unavailable"}`}>
                        {s.outcome ?? "pending"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
    </>
  );
}
