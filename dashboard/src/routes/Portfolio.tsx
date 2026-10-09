import { useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState, StatCard } from "../components/Card";
import { cls, fmtInt, fmtPrice, fmtRelative } from "../lib/format";

export function Portfolio() {
  const [source, setSource] = useState("sahm");
  const [accountLabel, setAccountLabel] = useState("");
  const [uploading, setUploading] = useState(false);
  const [lastImport, setLastImport] = useState<
    { positions_imported: number; warnings: string[]; import_id: number } | { error: string } | null
  >(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const summary = useApi(api.portfolioSummary);
  const imports = useApi(api.portfolioImports);

  async function handleFile(file: File) {
    setUploading(true);
    setLastImport(null);
    const res = await api.portfolioImport(file, { source, account_label: accountLabel });
    setUploading(false);
    if (res.ok) {
      setLastImport({
        positions_imported: res.data.positions_imported,
        warnings: res.data.warnings ?? [],
        import_id: res.data.import_id,
      });
      summary.reload();
      imports.reload();
    } else {
      setLastImport({ error: res.error });
    }
  }

  const d = summary.data;

  return (
    <>
      <PageHead
        title="Portfolio"
        subtitle={
          "CSV import from Sahm or any brokerage export. Credentials never leave your browser — no scraping, no auto-login, just the Export button you already have."
        }
      />

      <div className="grid grid-cols-4">
        <StatCard
          title="Positions"
          value={d ? fmtInt(d.position_count) : "–"}
          sub={d?.imported_at ? `imported ${fmtRelative(d.imported_at)}` : "no imports yet"}
        />
        <StatCard
          title="Gross market value"
          value={d ? "$" + fmtPrice(d.gross_market_value, 0) : "–"}
          sub="sum of |market_value| across positions"
        />
        <StatCard
          title="Net market value"
          value={d ? "$" + fmtPrice(d.net_market_value, 0) : "–"}
          tone={(d?.net_market_value ?? 0) >= 0 ? "up" : "down"}
          sub="signed; shorts subtract"
        />
        <StatCard
          title="Unrealized P&L"
          value={d ? "$" + fmtPrice(d.unrealized_pnl, 0) : "–"}
          tone={(d?.unrealized_pnl ?? 0) >= 0 ? "up" : "down"}
          sub="as reported in your export"
        />
      </div>

      <div className="grid grid-cols-2" style={{ marginTop: 14 }}>
        <Panel title="Import a portfolio CSV">
          <div className="row-tight" style={{ marginBottom: 10 }}>
            <label className="row-tight">
              <span className="dim">Source</span>
              <select value={source} onChange={(e) => setSource(e.target.value)}>
                <option value="sahm">Sahm Capital</option>
                <option value="alpaca">Alpaca</option>
                <option value="ibkr">IBKR</option>
                <option value="fidelity">Fidelity</option>
                <option value="schwab">Schwab</option>
                <option value="other">Other</option>
              </select>
            </label>
            <input
              placeholder="Account label (optional)"
              value={accountLabel}
              onChange={(e) => setAccountLabel(e.target.value)}
              style={{ width: 220 }}
            />
          </div>

          <div
            className={cls("drop-zone", dragOver && "drag-over", uploading && "busy")}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const file = e.dataTransfer.files?.[0];
              if (file) handleFile(file);
            }}
            onClick={() => inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
            {uploading ? (
              <>Uploading…</>
            ) : (
              <>
                <div className="muted" style={{ marginBottom: 4 }}>
                  Drop a <strong>.csv</strong> here or click to choose
                </div>
                <div className="dim" style={{ fontSize: 11.5 }}>
                  Export from <span className="mono">app.sahmcapital.com → Portfolios → Export</span> and drop it here.
                </div>
              </>
            )}
          </div>

          {lastImport && "positions_imported" in lastImport && (
            <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
              <span className="up">Imported {lastImport.positions_imported} position(s)</span>
              {lastImport.warnings.length > 0 && (
                <details style={{ marginTop: 6 }}>
                  <summary>{lastImport.warnings.length} warning(s)</summary>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {lastImport.warnings.map((w, i) => <li key={i} className="dim">{w}</li>)}
                  </ul>
                </details>
              )}
            </div>
          )}
          {lastImport && "error" in lastImport && (
            <div className="down" style={{ marginTop: 10, fontSize: 12 }}>
              Import failed: {lastImport.error}
            </div>
          )}

          <div className="dim" style={{ marginTop: 14, fontSize: 11.5 }}>
            Expected columns (any case, flexible order): <span className="mono">Symbol</span>, <span className="mono">Quantity</span>, optionally <span className="mono">Avg Cost</span>, <span className="mono">Market Price</span>, <span className="mono">Market Value</span>, <span className="mono">P&L</span>, <span className="mono">Currency</span>, <span className="mono">Type</span>.
          </div>
        </Panel>

        <Panel title="Import history">
          {imports.loading && !imports.data ? (
            <Skeleton height={200} />
          ) : imports.data?.ok && imports.data.imports.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Source</th>
                  <th>Rows</th>
                  <th>File</th>
                </tr>
              </thead>
              <tbody>
                {imports.data.imports.map((r) => (
                  <tr key={r.id}>
                    <td className="dim">{fmtRelative(r.imported_at)}</td>
                    <td>{r.source}</td>
                    <td className="mono">{fmtInt(r.row_count)}</td>
                    <td className="dim">{r.filename ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="No imports yet">Drop a CSV on the left to get started.</EmptyState>
          )}
        </Panel>
      </div>

      <Panel title={`Positions (${d?.position_count ?? 0})`}>
        {summary.loading && !d ? (
          <Skeleton height={200} />
        ) : d && d.positions.length ? (
          <div className="scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Qty</th>
                  <th>Avg cost</th>
                  <th>Price</th>
                  <th>Mkt value</th>
                  <th>Unrealized P&L</th>
                  <th>CCY</th>
                </tr>
              </thead>
              <tbody>
                {d.positions.map((p) => (
                  <tr key={p.id}>
                    <td><strong>{p.symbol}</strong></td>
                    <td className="dim">{p.instrument_type ?? "–"}</td>
                    <td className="mono">{fmtPrice(p.quantity, 4)}</td>
                    <td className="mono">{p.avg_cost === null ? "–" : fmtPrice(p.avg_cost)}</td>
                    <td className="mono">{p.market_price === null ? "–" : fmtPrice(p.market_price)}</td>
                    <td className="mono">{p.market_value === null ? "–" : "$" + fmtPrice(p.market_value, 0)}</td>
                    <td className={cls("mono", (p.unrealized_pnl ?? 0) > 0 ? "up" : (p.unrealized_pnl ?? 0) < 0 ? "down" : "")}>
                      {p.unrealized_pnl === null ? "–" : "$" + fmtPrice(p.unrealized_pnl, 0)}
                    </td>
                    <td className="dim">{p.currency ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No portfolio imported">
            {d?.note ?? "Drop a CSV above to see your positions."}
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
