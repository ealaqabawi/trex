import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState, StatCard } from "../components/Card";
import { fmtPct, fmtInt } from "../lib/format";

export function RiskCenter() {
  const q = useApi(api.risk);
  const d = q.data;

  if (!d) return <><PageHead title="Risk Center" subtitle="loading…" /><Skeleton height={200} /></>;

  return (
    <>
      <PageHead
        title="Risk Center"
        subtitle="The risk engine runs independently of the LLM and the dashboard. Live execution is a hard disabled default."
      />

      <div className="grid grid-cols-4">
        <StatCard
          title="Operating mode"
          value={d.mode}
          sub={d.emergency_stop.detail}
          tone={d.emergency_stop.active ? "down" : undefined}
        />
        <StatCard
          title="Position utilization"
          value={fmtPct(d.utilization.concurrent_position_utilization * 100, 0)}
          sub={`${fmtInt(d.utilization.open_signals)} open / ${d.envelope.max_concurrent_positions} max`}
        />
        <StatCard
          title="Real fills"
          value={fmtInt(d.utilization.real_fills)}
          sub={`${fmtInt(d.utilization.dry_run_orders)} dry-run attempts`}
        />
        <StatCard
          title="Live execution"
          value={d.live_execution.enabled ? "ENABLED" : "disabled"}
          sub={d.live_execution.reason}
          tone={d.live_execution.enabled ? "down" : undefined}
        />
      </div>

      <div className="grid grid-cols-2" style={{ marginTop: 14 }}>
        <Panel title="Risk envelope">
          <table className="table">
            <tbody>
              {Object.entries(d.envelope).map(([k, v]) => (
                <tr key={k}>
                  <td>{k.replace(/_/g, " ")}</td>
                  <td className="mono right">{formatEnvelopeValue(k, v)}</td>
                </tr>
              ))}
              <tr>
                <td colSpan={2} className="dim" style={{ paddingTop: 10 }}>
                  Portfolio-level legacy limits (from <span className="mono">risk/rules.py</span>):
                </td>
              </tr>
              {Object.entries(d.legacy_portfolio_limits).map(([k, v]) => (
                <tr key={"legacy-" + k}>
                  <td className="dim">{k.replace(/_/g, " ")}</td>
                  <td className="mono right dim">{formatEnvelopeValue(k, v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Recent risk events">
          {d.recent_events.length === 0 ? (
            <EmptyState title="No risk events">
              The risk engine logs rejections, limit breaches, and emergency-stop toggles. Nothing is logged yet.
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Severity</th>
                  <th>Ticker</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_events.map((e: any, i: number) => (
                  <tr key={i}>
                    <td>{e.event_type}</td>
                    <td>
                      <span className={`badge ${e.severity === "critical" ? "danger" : "delayed"}`}>
                        {e.severity}
                      </span>
                    </td>
                    <td>{e.ticker ?? "–"}</td>
                    <td className="dim">{e.detail}</td>
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

function formatEnvelopeValue(key: string, v: number): string {
  if (key.endsWith("_pct")) return fmtPct(v * 100);
  if (key.endsWith("_loss") || key.endsWith("_position") || key.endsWith("_size"))
    return "$" + v.toLocaleString();
  if (key.startsWith("min_") || key.startsWith("max_") && !key.endsWith("_pct"))
    return v.toLocaleString();
  return String(v);
}
