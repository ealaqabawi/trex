import { useEffect, useMemo, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api, type OptionRow } from "../lib/api";
import { PageHead, Panel, Skeleton, EmptyState } from "../components/Card";
import { cls, fmtInt, fmtPct, fmtPrice } from "../lib/format";

const DEFAULTS = ["SPX", "SPY", "QQQ", "NVDA"];

export function OptionsChain() {
  const [ticker, setTicker] = useState("SPY");
  const [expiration, setExpiration] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<keyof OptionRow>("strike");
  const [sortDesc, setSortDesc] = useState(false);

  const exps = useApi(() => api.expirations(ticker), [ticker]);
  useEffect(() => {
    if (exps.data?.ok && exps.data.expirations.length) {
      setExpiration(exps.data.expirations[0].expiration);
    }
  }, [exps.data, ticker]);

  const chain = useApi(
    () => (expiration ? api.chain(ticker, expiration) : Promise.resolve({ ok: true, data: null } as never)),
    [ticker, expiration]
  );

  const sortedRows = useMemo(() => {
    const rows = chain.data?.rows ?? [];
    const filtered = search
      ? rows.filter((r) =>
          r.contract_symbol.toLowerCase().includes(search.toLowerCase()) ||
          String(r.strike).includes(search)
        )
      : rows;
    return [...filtered].sort((a, b) => {
      const av = (a[sortKey] as number) ?? 0;
      const bv = (b[sortKey] as number) ?? 0;
      return sortDesc ? bv - av : av - bv;
    });
  }, [chain.data, search, sortKey, sortDesc]);

  const atm = chain.data?.underlying_price ?? null;

  function toggleSort(key: keyof OptionRow) {
    if (sortKey === key) {
      setSortDesc((d) => !d);
    } else {
      setSortKey(key);
      setSortDesc(false);
    }
  }

  function sortArrow(key: keyof OptionRow) {
    if (sortKey !== key) return null;
    return <span className="dim"> {sortDesc ? "↓" : "↑"}</span>;
  }

  return (
    <>
      <PageHead
        title="Options Intelligence"
        subtitle={`${ticker} · underlying ${fmtPrice(atm)} · ${
          exps.data?.ok ? `${exps.data.expirations.length} expirations` : "…"
        }`}
      />

      <div className="row-tight" style={{ marginBottom: 14 }}>
        {DEFAULTS.map((t) => (
          <button
            key={t}
            className={cls(ticker === t && "primary")}
            onClick={() => { setTicker(t); setExpiration(null); }}
          >
            {t}
          </button>
        ))}
        <input
          placeholder="Custom symbol"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const v = (e.target as HTMLInputElement).value.trim().toUpperCase();
              if (v) { setTicker(v); setExpiration(null); }
            }
          }}
          style={{ width: 140 }}
        />
        <select
          value={expiration ?? ""}
          onChange={(e) => setExpiration(e.target.value)}
          style={{ minWidth: 220 }}
        >
          {exps.data?.ok ? (
            exps.data.expirations.map((e) => (
              <option key={e.expiration} value={e.expiration}>
                {e.expiration} · {e.dte}DTE · {e.bucket}
              </option>
            ))
          ) : (
            <option>loading…</option>
          )}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by strike or symbol"
          style={{ width: 220 }}
        />
      </div>

      <Panel
        title={
          <>
            Chain
            {chain.data ? (
              <span className="dim" style={{ marginLeft: 10 }}>
                freshness <span className={`badge ${chain.data.freshness}`}>{chain.data.freshness}</span>
              </span>
            ) : null}
          </>
        }
      >
        {chain.loading && !chain.data ? (
          <Skeleton height={420} />
        ) : chain.data?.ok ? (
          <div className="scroll">
            <table className="table">
              <thead>
                <tr>
                  <th onClick={() => toggleSort("contract_type")}>Type{sortArrow("contract_type")}</th>
                  <th onClick={() => toggleSort("strike")}>Strike{sortArrow("strike")}</th>
                  <th onClick={() => toggleSort("bid")}>Bid{sortArrow("bid")}</th>
                  <th onClick={() => toggleSort("ask")}>Ask{sortArrow("ask")}</th>
                  <th onClick={() => toggleSort("mid")}>Mid{sortArrow("mid")}</th>
                  <th onClick={() => toggleSort("spread_pct")}>Spread{sortArrow("spread_pct")}</th>
                  <th onClick={() => toggleSort("delta")}>Δ{sortArrow("delta")}</th>
                  <th onClick={() => toggleSort("implied_vol")}>IV{sortArrow("implied_vol")}</th>
                  <th onClick={() => toggleSort("volume")}>Vol{sortArrow("volume")}</th>
                  <th onClick={() => toggleSort("open_interest")}>OI{sortArrow("open_interest")}</th>
                  <th>Quality</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((r) => (
                  <tr key={r.contract_symbol}>
                    <td>
                      <span className={cls("pill", r.contract_type === "CALL" ? "long" : "short")}>
                        {r.contract_type[0]}
                      </span>
                    </td>
                    <td className="mono"><strong>{fmtPrice(r.strike)}</strong></td>
                    <td className="mono">{fmtPrice(r.bid)}</td>
                    <td className="mono">{fmtPrice(r.ask)}</td>
                    <td className="mono">{r.mid === null ? "–" : fmtPrice(r.mid)}</td>
                    <td className="mono">{r.spread_pct === null ? "–" : fmtPct(r.spread_pct * 100, 1)}</td>
                    <td className="mono">{r.delta === null ? "–" : r.delta.toFixed(2)}</td>
                    <td className="mono">{fmtPct(r.implied_vol * 100, 1)}</td>
                    <td className="mono">{fmtInt(r.volume)}</td>
                    <td className="mono">{fmtInt(r.open_interest)}</td>
                    <td>
                      <span className={`badge ${r.data_quality}`}>{r.data_quality}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No chain data">
            {chain.data?.error ?? "Select an expiration above."}
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
