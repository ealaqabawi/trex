import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton } from "../components/Card";

export function Settings() {
  const q = useApi(api.settings);
  const d = q.data;

  if (!d) return <><PageHead title="Settings & Integrations" subtitle="loading…" /><Skeleton height={200} /></>;

  const c = d.config;

  return (
    <>
      <PageHead
        title="Settings & Integrations"
        subtitle="Read-only by default. Secrets are not sent to the browser."
      />

      <div className="grid grid-cols-2">
        <Panel title="Core">
          <table className="table">
            <tbody>
              <KV k="Mode" v={c.mode} />
              <KV k="Universe" v={c.universe.join(", ")} />
              <KV k="Allowed modes" v={c.allowed_modes.join(", ")} />
              <KV k="Live mode available" v={c.live_mode_available ? "yes (unlock token set)" : "no (disabled)"} />
              <KV k="Freshness warn" v={`${c.data_freshness_warning_minutes} min`} />
              <KV k="Freshness stale" v={`${c.data_freshness_stale_minutes} min`} />
            </tbody>
          </table>
        </Panel>

        <Panel title="Local model backend">
          <table className="table">
            <tbody>
              <KV k="Backend" v={c.local_model_backend} />
              <KV k="Model name" v={c.local_model_name} />
              <KV k="URL" v={c.local_model_url} />
            </tbody>
          </table>
          <div className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
            Configure in <span className="mono">.env</span>: <span className="mono">TRAX_LOCAL_MODEL_BACKEND</span>, <span className="mono">TRAX_LOCAL_MODEL_NAME</span>, <span className="mono">TRAX_LOCAL_MODEL_URL</span>.
          </div>
        </Panel>

        <Panel title="Risk envelope">
          <table className="table">
            <tbody>
              {Object.entries(c.risk).map(([k, v]) => (
                <KV key={k} k={k.replace(/_/g, " ")} v={String(v)} />
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Integrations">
          <table className="table">
            <tbody>
              <KV
                k="Telegram"
                v={c.telegram_configured
                   ? (c.telegram_autosend ? "configured · autosend ON" : "configured · autosend off")
                   : "not configured"}
              />
              <KV k="Overrides" v={d.overrides.mode ?? "none"} />
            </tbody>
          </table>
          <div className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
            Writing settings requires <span className="mono">TRAX_ALLOW_SETTINGS_WRITE=true</span>. Live execution never flips on from this surface. Verify your Telegram bot works end-to-end on the <a href="/telegram">Telegram screen</a>.
          </div>
        </Panel>
      </div>
    </>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <tr>
      <td className="dim">{k}</td>
      <td className="mono right">{v}</td>
    </tr>
  );
}
