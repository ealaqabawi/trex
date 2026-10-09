import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { api, type Candidate } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState } from "../components/Card";
import { cls, fmtInt, fmtPct, fmtPrice } from "../lib/format";

export function Scanner() {
  const [only0DTE, setOnly0DTE] = useState(false);
  const [maxDTE, setMaxDTE] = useState(7);
  const [tickers, setTickers] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const q = useApi(
    () => api.scanner({ only_0dte: only0DTE, max_dte: maxDTE, tickers: tickers || undefined }),
    [only0DTE, maxDTE, tickers]
  );

  const d = q.data;

  return (
    <>
      <PageHead
        title="0DTE Opportunity Scanner"
        subtitle="Research candidates ranked by liquidity-weighted composite score. These are observations, not trade signals."
        action={<button className="primary" onClick={q.reload}>Rescan</button>}
      />

      <div className="row-tight" style={{ marginBottom: 14 }}>
        <label className="row-tight">
          <input
            type="checkbox"
            checked={only0DTE}
            onChange={(e) => setOnly0DTE(e.target.checked)}
          />
          <span>0DTE only</span>
        </label>
        <label className="row-tight">
          <span className="dim">Max DTE</span>
          <select value={maxDTE} onChange={(e) => setMaxDTE(Number(e.target.value))}>
            {[0, 1, 2, 3, 7, 14, 30, 60].map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <input
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
          placeholder="Tickers (comma, default universe)"
          style={{ width: 300 }}
        />
      </div>

      <Panel
        title={
          d ? `${d.count} candidate${d.count === 1 ? "" : "s"} across ${d.universe.join(", ")}`
             : "scanning…"
        }
      >
        {q.loading && !d ? (
          <Skeleton height={420} />
        ) : d && d.candidates.length > 0 ? (
          <div className="scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Score</th>
                  <th>Underlying</th>
                  <th>Dir</th>
                  <th>Contract</th>
                  <th>DTE</th>
                  <th>Strike</th>
                  <th>Mid</th>
                  <th>Spread</th>
                  <th>Δ</th>
                  <th>IV</th>
                  <th>Vol</th>
                  <th>OI</th>
                  <th>Quality</th>
                  <th>Freshness</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {d.candidates.map((c) => (
                  <ScannerRow
                    key={c.contract_symbol + c.created_at}
                    c={c}
                    isOpen={expanded === c.contract_symbol}
                    onToggle={() =>
                      setExpanded((cur) => (cur === c.contract_symbol ? null : c.contract_symbol))
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No candidates matched">
            Try widening the DTE filter, adding tickers, or lowering the data-quality floor. The scanner never fabricates candidates when the source feed returns nothing.
          </EmptyState>
        )}
      </Panel>
    </>
  );
}

function ScannerRow({ c, isOpen, onToggle }: { c: Candidate; isOpen: boolean; onToggle: () => void }) {
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: "pointer" }}>
        <td className="mono">
          <strong className={c.confidence >= 60 ? "up" : c.confidence >= 40 ? "" : "dim"}>
            {c.confidence}
          </strong>
        </td>
        <td><strong>{c.ticker}</strong></td>
        <td>
          <span className={cls("pill", c.direction === "LONG" ? "long" : "short")}>
            {c.direction}
          </span>
        </td>
        <td className="mono">{c.contract_type[0]} {fmtPrice(c.strike)}</td>
        <td className="mono">
          <span className={`badge ${c.dte_bucket === "0DTE" ? "accent" : ""}`}>
            {c.dte_bucket}
          </span>
        </td>
        <td className="mono">{fmtPrice(c.strike)}</td>
        <td className="mono">{fmtPrice(c.mid)}</td>
        <td className="mono">{fmtPct(c.spread_pct * 100, 1)}</td>
        <td className="mono">{c.delta.toFixed(2)}</td>
        <td className="mono">{fmtPct(c.implied_vol * 100, 1)}</td>
        <td className="mono">{fmtInt(c.volume)}</td>
        <td className="mono">{fmtInt(c.open_interest)}</td>
        <td><span className={`badge ${c.data_quality}`}>{c.data_quality}</span></td>
        <td><span className={`badge ${c.data_freshness}`}>{c.data_freshness}</span></td>
        <td className="dim">{isOpen ? "▲" : "▼"}</td>
      </tr>
      {isOpen && (
        <tr>
          <td colSpan={15} style={{ background: "var(--bg-2)" }}>
            <div style={{ padding: "6px 4px 10px" }}>
              <div className="muted" style={{ marginBottom: 8 }}>
                Rationale
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {c.rationale.map((r, i) => (
                  <li key={i} className="dim" style={{ fontSize: 12.5 }}>{r}</li>
                ))}
              </ul>
              <div className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
                Contract: <span className="mono">{c.contract_symbol}</span> ·
                Underlying {fmtPrice(c.underlying_price)} · {fmtPct(c.distance_from_atm_pct)} from ATM ·
                vol/OI {c.volume_oi_ratio.toFixed(2)} · source {c.data_source}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
