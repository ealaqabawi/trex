import { usePolling } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, StatCard, Panel, EmptyState, Skeleton, Section } from "../components/Card";
import { fmtInt, fmtPct, fmtRelative } from "../lib/format";

export function Overview() {
  const q = usePolling(api.overview, 15_000);
  const d = q.data;

  if (!d) return (
    <>
      <PageHead title="Executive Overview" subtitle="loading backend…" />
      <div className="grid grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={100} />)}
      </div>
    </>
  );

  return (
    <>
      <PageHead
        title="Executive Overview"
        subtitle={`universe: ${d.universe.join(" · ")} · mode: ${d.mode} · ${d.session.session}`}
      />

      <div className="grid grid-cols-4">
        <StatCard
          title="Qualified setups"
          value={fmtInt(d.qualified_setups)}
          sub={`of ${fmtInt(d.scanner_candidate_count)} scanned candidates (confidence ≥ 60)`}
        />
        <StatCard
          title="Portfolio"
          value={d.portfolio.position_count > 0 ? fmtInt(d.portfolio.position_count) + " pos" : "—"}
          sub={d.portfolio.imported_at
            ? `net $${d.portfolio.net_market_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
            : "no CSV imported yet — see Portfolio screen"}
          tone={d.portfolio.unrealized_pnl > 0 ? "up" : d.portfolio.unrealized_pnl < 0 ? "down" : undefined}
          footnote={d.portfolio.imported_at ? `Unrealized $${d.portfolio.unrealized_pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : null}
        />
        <StatCard
          title="Signal hit rate"
          value={d.signal_history.hit_rate === null ? "n/a" : fmtPct(d.signal_history.hit_rate * 100)}
          sub={`${fmtInt(d.signal_history.total_published)} published, ${fmtInt(d.signal_history.unresolved)} unresolved`}
          footnote={d.signal_history.hit_rate_note}
        />
        <StatCard
          title="Market session"
          value={d.session.session.toUpperCase()}
          sub={
            d.session.minutes_to_close !== null
              ? `${d.session.minutes_to_close}m to close`
              : d.session.minutes_to_open !== null
              ? `${d.session.minutes_to_open}m to open`
              : "closed"
          }
        />
      </div>

      <div className="grid grid-cols-2" style={{ marginTop: 14 }}>
        <Panel title="Recent agent activity">
          {d.recent_agent_activity.length === 0 ? (
            <EmptyState title="No agent runs recorded yet">
              Agent runs are logged to the memory DB. Trigger the Phase 9 supervisor pipeline or the signal engine to populate this.
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Task</th>
                  <th>Status</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_agent_activity.map((r, i) => (
                  <tr key={i}>
                    <td>{r.agent}</td>
                    <td className="dim">{r.task}</td>
                    <td className={r.status === "ok" ? "up" : r.status === "running" ? "dim" : "down"}>
                      {r.status}
                    </td>
                    <td className="dim">{fmtRelative(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Risk & alert events">
          {d.recent_alerts.length === 0 ? (
            <EmptyState title="No risk events recorded">
              The risk engine logs every rejection, limit breach, and emergency-stop toggle here.
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Ticker</th>
                  <th>Severity</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_alerts.map((e, i) => (
                  <tr key={i}>
                    <td className="dim">{e.detail}</td>
                    <td>{e.ticker ?? "–"}</td>
                    <td>
                      <span className={`badge ${e.severity === "critical" ? "danger" : "delayed"}`}>
                        {e.severity}
                      </span>
                    </td>
                    <td className="dim">{fmtRelative(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Section title="Universe">
        <div className="grid grid-cols-4">
          {d.universe.map((t) => (
            <div key={t} className="card">
              <div className="card-head">
                <span className="card-title">{t}</span>
              </div>
              <div className="card-value-sm mono">tracked</div>
              <div className="card-sub">quotes, chains, scanner inputs</div>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
