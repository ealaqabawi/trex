import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState } from "../components/Card";
import { fmtRelative, fmtTime } from "../lib/format";

export function AgentsPage() {
  const catalog = useApi(api.agentCatalog);
  const runs = useApi(api.agents);

  return (
    <>
      <PageHead
        title="AI Agent Activity"
        subtitle="Agent roles, recent runs, tool executions. No private chain-of-thought is exposed."
      />

      <div className="grid grid-cols-2">
        <Panel title="Agent catalog">
          {catalog.loading && !catalog.data ? (
            <Skeleton height={200} />
          ) : catalog.data?.ok ? (
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {catalog.data.agents.map((a) => (
                <li key={a.id} style={{
                  padding: "10px 0",
                  borderBottom: "1px solid var(--hairline)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <strong>{a.label}</strong>
                    <span className="dim mono" style={{ fontSize: 11.5 }}>{a.id}</span>
                  </div>
                  <div className="dim" style={{ fontSize: 12 }}>{a.role}</div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Catalog unavailable">{catalog.error}</EmptyState>
          )}
        </Panel>

        <Panel title="Recent agent runs">
          {runs.loading && !runs.data ? (
            <Skeleton height={200} />
          ) : runs.data?.ok && runs.data.runs.length > 0 ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Task</th>
                  <th>Status</th>
                  <th>Model</th>
                  <th>Tokens</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.runs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.agent}</td>
                    <td className="dim">{r.task}</td>
                    <td className={r.status === "ok" ? "up" : r.status === "running" ? "" : "down"}>
                      {r.status}
                    </td>
                    <td className="mono dim">{r.model ?? "–"}</td>
                    <td className="mono dim">{r.tokens ?? "–"}</td>
                    <td className="dim" title={fmtTime(r.started_at, { date: true })}>
                      {fmtRelative(r.started_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="No recorded runs">
              The pipeline is instrumented through <span className="mono">memory.repository.start_agent_run / finish_agent_run</span>; nothing has fired yet.
            </EmptyState>
          )}
        </Panel>
      </div>
    </>
  );
}
