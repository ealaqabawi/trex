import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { api, type TelegramActionResponse } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState, StatCard } from "../components/Card";
import { cls, fmtInt, fmtPct, fmtRelative } from "../lib/format";

export function TelegramMonitor() {
  const q = useApi(api.telegram);
  const d = q.data;

  const [sendBusy, setSendBusy] = useState<null | "verify" | "test" | "custom">(null);
  const [verifyFlash, setVerifyFlash] = useState<{ ok: boolean; text: string } | null>(null);
  const [sendFlash, setSendFlash] = useState<{ ok: boolean; text: string } | null>(null);
  const [custom, setCustom] = useState("");

  async function runVerify() {
    setSendBusy("verify");
    setVerifyFlash(null);
    const r = await api.telegramVerify();
    setSendBusy(null);
    if (r.ok && r.data.ok) {
      setVerifyFlash({ ok: true, text: `@${r.data.username ?? "?"} reachable` });
      q.reload();
    } else {
      const msg = r.ok ? (r.data.error ?? "verify failed") : r.error;
      setVerifyFlash({ ok: false, text: String(msg) });
    }
  }

  async function runTest() {
    setSendBusy("test");
    setSendFlash(null);
    const r = await api.telegramTest();
    setSendBusy(null);
    handleActionResult(r, "test");
  }

  async function runCustom() {
    if (!custom.trim()) return;
    setSendBusy("custom");
    setSendFlash(null);
    const r = await api.telegramSend(custom);
    setSendBusy(null);
    handleActionResult(r, "custom");
    if (r.ok && r.data.ok) setCustom("");
  }

  function handleActionResult(
    r: { ok: true; data: TelegramActionResponse } | { ok: false; error: string; status?: number },
    kind: "test" | "custom"
  ) {
    if (r.ok && r.data.ok) {
      setSendFlash({ ok: true, text: `${kind} sent · HTTP ${r.data.status_code}` });
      q.reload();
    } else if (r.ok) {
      setSendFlash({ ok: false, text: r.data.detail || r.data.error || "send failed" });
    } else if (r.status === 403) {
      setSendFlash({ ok: false, text: "writes disabled — set TRAX_ALLOW_SETTINGS_WRITE=true in .env" });
    } else {
      setSendFlash({ ok: false, text: r.error });
    }
  }

  const subtitle = d
    ? !d.configured
      ? "No TELEGRAM_BOT_TOKEN set in .env"
      : d.verify.ok
      ? `Bot @${d.verify.username} reachable via Bot API`
      : `Credentials set but Telegram rejected the token (${d.verify.error ?? "error"})`
    : "loading…";

  return (
    <>
      <PageHead title="Telegram Monitor" subtitle={subtitle} />

      <Panel
        title="Controls"
        action={
          !d?.writes_allowed ? (
            <span className="dim" style={{ fontSize: 11.5 }}>
              writes disabled · set <span className="mono">TRAX_ALLOW_SETTINGS_WRITE=true</span>
            </span>
          ) : null
        }
      >
        <div className="row-tight" style={{ gap: 12, flexWrap: "wrap" }}>
          <button onClick={runVerify} disabled={sendBusy !== null}>
            {sendBusy === "verify" ? "Verifying…" : "Verify bot"}
          </button>
          <button
            className="primary"
            onClick={runTest}
            disabled={sendBusy !== null || !d?.writes_allowed}
            title={!d?.writes_allowed ? "Enable writes in .env to send" : undefined}
          >
            {sendBusy === "test" ? "Sending…" : "Send test"}
          </button>
          {verifyFlash && (
            <span className={cls("badge", verifyFlash.ok ? "ok" : "failed")}>
              {verifyFlash.text}
            </span>
          )}
          {sendFlash && (
            <span className={cls("badge", sendFlash.ok ? "ok" : "failed")}>
              {sendFlash.text}
            </span>
          )}
        </div>

        <div className="row-tight" style={{ marginTop: 12, gap: 8 }}>
          <input
            placeholder="Send a custom message (Markdown)…"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runCustom()}
            style={{ flex: 1, minWidth: 260 }}
            disabled={!d?.writes_allowed}
          />
          <button
            onClick={runCustom}
            disabled={sendBusy !== null || !custom.trim() || !d?.writes_allowed}
          >
            {sendBusy === "custom" ? "Sending…" : "Send custom"}
          </button>
        </div>

        <div className="dim" style={{ fontSize: 11.5, marginTop: 10 }}>
          Autosend: {d?.autosend ? "ON" : "off"} · when on, trigger_server pushes every actionable signal to Telegram automatically (no n8n required).
        </div>
      </Panel>

      {d ? (
        <div className="grid grid-cols-4" style={{ marginTop: 14 }}>
          <StatCard title="Total sent" value={fmtInt(d.delivery_summary.total)} />
          <StatCard
            title="Delivered"
            value={fmtInt(d.delivery_summary.delivered)}
            tone="up"
          />
          <StatCard
            title="Failed"
            value={fmtInt(d.delivery_summary.failed)}
            tone={d.delivery_summary.failed > 0 ? "down" : undefined}
          />
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
              Click <strong>Send test</strong> above to produce a row and verify end-to-end delivery.
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Ticker</th>
                  <th>Direction</th>
                  <th>Status</th>
                  <th>Error</th>
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
                    <td className="dim" style={{ fontSize: 11.5 }}>
                      {h.error ?? ""}
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
