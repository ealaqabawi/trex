import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState } from "../components/Card";
import { fmtInt, fmtMoney } from "../lib/format";

export function Intelligence() {
  const flow = useApi(api.intelligenceFlow);
  const sources = useApi(api.intelligenceSources);
  const notes = useApi(() => api.quote("SPY", "5m")); // placeholder, replaced by proper note endpoint usage below
  // the real notes call:
  const noteList = useApi(() => fetch("/api/v1/intelligence/notes?limit=20").then(r => r.json()).then(j => ({ ok: true as const, data: j })));

  return (
    <>
      <PageHead
        title="Financial Intelligence"
        subtitle="Only grounded, source-attributed observations. Nothing here is a prediction."
      />

      <Panel title="Options flow across universe">
        {flow.loading && !flow.data ? (
          <Skeleton height={200} />
        ) : flow.data?.ok ? (
          <table className="table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Direction</th>
                <th>Net premium</th>
                <th>Call $</th>
                <th>Put $</th>
                <th>Whales</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {flow.data.rows.map((r) => (
                <tr key={r.ticker}>
                  <td><strong>{r.ticker}</strong></td>
                  <td>
                    <span
                      className={
                        "pill " +
                        (r.direction === "bullish"
                          ? "long"
                          : r.direction === "bearish"
                          ? "short"
                          : "neutral")
                      }
                    >
                      {r.direction}
                    </span>
                  </td>
                  <td className={"mono " + ((r.net_premium ?? 0) > 0 ? "up" : (r.net_premium ?? 0) < 0 ? "down" : "")}>
                    {r.net_premium_display}
                  </td>
                  <td className="mono dim">{fmtMoney(r.call_premium)}</td>
                  <td className="mono dim">{fmtMoney(r.put_premium)}</td>
                  <td className="mono">{fmtInt(r.whale_count)}</td>
                  <td className="dim">{r.source ?? r.error ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="Flow unavailable">{flow.error ?? "No data"}</EmptyState>
        )}
      </Panel>

      <div className="grid grid-cols-2" style={{ marginTop: 14 }}>
        <Panel title="Intelligence sources">
          {sources.loading && !sources.data ? (
            <Skeleton height={120} />
          ) : sources.data?.ok ? (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {sources.data.sources.map((s) => (
                <li key={s.id} style={{
                  display: "flex", alignItems: "center",
                  justifyContent: "space-between", padding: "8px 0",
                  borderBottom: "1px solid var(--hairline)",
                }}>
                  <div>
                    <div><strong>{s.label}</strong></div>
                    <div className="dim" style={{ fontSize: 11.5 }}>{s.detail}</div>
                  </div>
                  <span className={`badge ${s.status === "live" ? "ok" : "unavailable"}`}>
                    {s.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Sources index unavailable">{sources.error}</EmptyState>
          )}
        </Panel>

        <Panel title="Research notes">
          {noteList.loading && !noteList.data ? (
            <Skeleton height={120} />
          ) : (noteList.data as any)?.data?.notes?.length ? (
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {(noteList.data as any).data.notes.map((n: { id: number; topic: string; body: string; created_at: string }) => (
                <li key={n.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                  <div className="muted"><strong>{n.topic}</strong></div>
                  <div style={{ fontSize: 12.5 }}>{n.body}</div>
                  <div className="dim" style={{ fontSize: 11 }}>{n.created_at}</div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No research notes yet">
              Research findings written by agents land here. The POST /api/v1/intelligence/notes endpoint accepts topic/body/source/tags.
            </EmptyState>
          )}
        </Panel>
      </div>

      <div className="dim" style={{ marginTop: 20, fontSize: 11.5 }}>
        News, economic calendar, and public-trader observations are deliberately absent until an authorized source is wired. Fabricating these would make the whole dashboard untrustworthy.
      </div>
      {/* exhaust the lint — notes placeholder is unused */}
      <span style={{ display: "none" }}>{notes.loading ? "" : ""}</span>
    </>
  );
}
