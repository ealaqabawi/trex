/**
 * Thin wrapper over the TRAX FastAPI backend. Every public function is
 * typed, and every call returns a discriminated union: either the parsed
 * body or an error envelope. Components never throw on fetch failure.
 */

const BASE = "/api/v1";

export type ApiOk<T> = { ok: true; data: T };
export type ApiErr = { ok: false; error: string; status?: number };
export type ApiResult<T> = ApiOk<T> | ApiErr;

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, init);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail || body.error || detail;
      } catch {
        /* body not json */
      }
      return { ok: false, error: detail, status: res.status };
    }
    const data = (await res.json()) as T;
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

// --- types mirroring the backend --------------------------------------

export interface SessionStatus {
  now_utc: string;
  now_et: string;
  is_trading_day: boolean;
  session: "premarket" | "open" | "after" | "closed";
  minutes_to_open: number | null;
  minutes_to_close: number | null;
}

export interface HealthResponse {
  ok: boolean;
  now_utc: string;
  version: string;
  mode: string;
  subsystems: Record<string, { status: string; detail?: string; source?: string; error?: string | null }>;
  session: SessionStatus;
}

export interface OverviewResponse {
  ok: boolean;
  now_utc: string;
  mode: string;
  session: SessionStatus;
  qualified_setups: number;
  scanner_candidate_count: number;
  paper_trading: {
    total_orders: number;
    real_fills: number;
    dry_run_orders: number;
    buy_count: number;
    sell_count: number;
    note: string | null;
  };
  signal_history: {
    total_published: number;
    actionable: number;
    unresolved: number;
    hit_rate: number | null;
    hit_rate_note: string;
  };
  recent_alerts: Array<{ created_at: string; severity: string; event_type: string; ticker?: string; detail: string }>;
  recent_agent_activity: Array<{ started_at: string; finished_at: string | null; agent: string; task: string; status: string }>;
  universe: string[];
  portfolio: {
    position_count: number;
    gross_market_value: number;
    net_market_value: number;
    unrealized_pnl: number;
    imported_at: string | null;
  };
}

export interface MarketSnapshotRow {
  ticker: string;
  ok: boolean;
  last_price: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  freshness: string;
  source: string;
  error: string | null;
}

export interface QuoteBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface QuoteResponse {
  ok: boolean;
  ticker: string;
  last_price: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  freshness: string;
  source: string;
  bars: QuoteBar[];
  error: string | null;
}

export interface ExpirationRow {
  expiration: string;
  dte: number;
  bucket: string;
}

export interface OptionRow {
  contract_type: "CALL" | "PUT";
  strike: number;
  contract_symbol: string;
  bid: number;
  ask: number;
  mid: number | null;
  last: number;
  spread_pct: number | null;
  volume: number;
  open_interest: number;
  implied_vol: number;
  delta: number | null;
  data_quality: string;
  notes: string[];
}

export interface ChainResponse {
  ok: boolean;
  ticker: string;
  expiration: string | null;
  underlying_price: number | null;
  freshness: string;
  source: string;
  dte: number;
  rows: OptionRow[];
  error?: string;
}

export interface Candidate {
  ticker: string;
  direction: "LONG" | "SHORT";
  contract_type: "CALL" | "PUT";
  expiration: string;
  dte: number;
  dte_bucket: string;
  strike: number;
  bid: number;
  ask: number;
  mid: number;
  spread_pct: number;
  last: number;
  delta: number;
  implied_vol: number;
  volume: number;
  open_interest: number;
  volume_oi_ratio: number;
  underlying_price: number;
  distance_from_atm_pct: number;
  contract_symbol: string;
  confidence: number;
  rationale: string[];
  data_source: string;
  data_quality: string;
  data_freshness: string;
  created_at: string;
}

export interface IntelligenceFlowRow {
  ticker: string;
  ok: boolean;
  direction: string;
  net_premium: number | null;
  net_premium_display: string;
  call_premium: number | null;
  put_premium: number | null;
  whale_count: number;
  whales: Array<{ contract: string; type: string; strike: number; premium: number; volume: number; open_interest: number }>;
  source: string | null;
  error: string | null;
}

export interface IntelligenceSource {
  id: string;
  label: string;
  status: string;
  detail: string;
}

export interface BacktestResponse {
  ok: boolean;
  ticker: string;
  strategy: string;
  lookback: number;
  period: string;
  starting_equity: number;
  ending_equity: number;
  total_return_pct: number;
  buy_and_hold_return_pct: number;
  win_rate_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  trade_count: number;
  trades: Array<{ entry_date: string; entry_price: number; exit_date: string | null; exit_price: number | null }>;
  equity_curve: number[];
  error?: string;
}

export interface AgentRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  agent: string;
  task: string;
  status: string;
  detail: string | null;
  tokens: number | null;
  model: string | null;
}

export interface RiskResponse {
  ok: boolean;
  mode: string;
  envelope: Record<string, number>;
  legacy_portfolio_limits: Record<string, number>;
  utilization: {
    open_signals: number;
    concurrent_position_utilization: number;
    real_fills: number;
    dry_run_orders: number;
  };
  live_execution: {
    enabled: boolean;
    reason: string;
    unlock_token_present: boolean;
  };
  emergency_stop: { active: boolean; detail: string };
  recent_events: Array<{ created_at: string; event_type: string; severity: string; ticker?: string; detail: string }>;
}

export interface TelegramResponse {
  ok: boolean;
  configured: boolean;
  verify: { ok: boolean; username: string | null; bot_id: number | null; error: string | null };
  writes_allowed: boolean;
  autosend: boolean;
  history: Array<{ sent_at: string; chat_id: string | null; ticker: string | null; direction: string | null; body: string; delivered: number; error: string | null; signal_ref: string | null }>;
  recent_signals: Array<{ generated_at: string; ticker: string; direction: string; confidence: number; action: string; outcome: string | null }>;
  delivery_summary: { total: number; delivered: number; failed: number };
}

export interface TelegramVerifyResponse {
  ok: boolean;
  username: string | null;
  bot_id: number | null;
  error: string | null;
  detail: string | null;
}

export interface TelegramActionResponse {
  ok: boolean;
  status_code: number | null;
  error: string | null;
  detail: string | null;
}

export interface SettingsResponse {
  ok: boolean;
  config: {
    universe: string[];
    mode: string;
    data_freshness_warning_minutes: number;
    data_freshness_stale_minutes: number;
    local_model_backend: string;
    local_model_name: string;
    local_model_url: string;
    telegram_configured: boolean;
    telegram_autosend: boolean;
    risk: Record<string, number>;
    live_mode_available: boolean;
    allowed_modes: string[];
  };
  overrides: { mode: string | null };
}

// --- public API --------------------------------------------------------

export interface PortfolioPosition {
  id: number;
  imported_at: string;
  source: string;
  account_label: string | null;
  symbol: string;
  instrument_type: string | null;
  quantity: number;
  avg_cost: number | null;
  market_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  currency: string | null;
}

export interface PortfolioSummary {
  ok: boolean;
  positions: PortfolioPosition[];
  position_count: number;
  gross_market_value: number;
  net_market_value: number;
  unrealized_pnl: number;
  imported_at: string | null;
  note?: string;
}

export interface PortfolioImportRow {
  id: number;
  imported_at: string;
  source: string;
  filename: string | null;
  row_count: number;
  account_label: string | null;
  note: string | null;
}

export const api = {
  health: () => request<HealthResponse>("/health/"),
  overview: () => request<OverviewResponse>("/overview/"),
  marketSnapshot: () =>
    request<{ ok: boolean; session: SessionStatus; rows: MarketSnapshotRow[] }>(
      "/market/snapshot"
    ),
  quote: (ticker: string, interval = "5m", period = "1d") =>
    request<QuoteResponse>(`/market/${ticker}?interval=${interval}&period=${period}`),
  expirations: (ticker: string) =>
    request<{ ok: boolean; ticker: string; expirations: ExpirationRow[]; source: string; error?: string }>(
      `/options/${ticker}/expirations`
    ),
  chain: (ticker: string, expiration?: string) =>
    request<ChainResponse>(
      `/options/${ticker}/chain${expiration ? `?expiration=${expiration}` : ""}`
    ),
  scanner: (opts: { only_0dte?: boolean; max_dte?: number; tickers?: string }) => {
    const params = new URLSearchParams();
    if (opts.only_0dte) params.set("only_0dte", "true");
    if (opts.max_dte !== undefined) params.set("max_dte", String(opts.max_dte));
    if (opts.tickers) params.set("tickers", opts.tickers);
    return request<{ ok: boolean; universe: string[]; only_0dte: boolean; max_dte: number; count: number; candidates: Candidate[] }>(
      `/scanner/?${params}`
    );
  },
  intelligenceFlow: () =>
    request<{ ok: boolean; rows: IntelligenceFlowRow[] }>("/intelligence/flow"),
  intelligenceSources: () =>
    request<{ ok: boolean; sources: IntelligenceSource[] }>("/intelligence/sources"),
  strategies: () =>
    request<{ ok: boolean; strategies: Array<{ name: string; default_lookback: number }> }>(
      "/strategy/strategies"
    ),
  backtest: (opts: { ticker: string; strategy: string; period?: string; lookback?: number }) => {
    const params = new URLSearchParams({ ticker: opts.ticker, strategy: opts.strategy });
    if (opts.period) params.set("period", opts.period);
    if (opts.lookback !== undefined) params.set("lookback", String(opts.lookback));
    return request<BacktestResponse>(`/strategy/backtest?${params}`);
  },
  agents: () =>
    request<{ ok: boolean; runs: AgentRun[]; by_agent: Record<string, number> }>(
      "/agents/"
    ),
  agentCatalog: () =>
    request<{ ok: boolean; agents: Array<{ id: string; label: string; role: string }> }>(
      "/agents/catalog"
    ),
  risk: () => request<RiskResponse>("/risk/"),
  telegram: () => request<TelegramResponse>("/telegram/"),
  telegramVerify: () => request<TelegramVerifyResponse>("/telegram/verify"),
  telegramTest: (text?: string) =>
    request<TelegramActionResponse>("/telegram/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  telegramSend: (text: string, parseMode: string = "Markdown") =>
    request<TelegramActionResponse>("/telegram/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, parse_mode: parseMode }),
    }),
  settings: () => request<SettingsResponse>("/settings/"),
  portfolioSummary: (account_label?: string) =>
    request<PortfolioSummary>(`/portfolio/${account_label ? `?account_label=${encodeURIComponent(account_label)}` : ""}`),
  portfolioImports: () =>
    request<{ ok: boolean; imports: PortfolioImportRow[] }>("/portfolio/imports"),
  portfolioImport: async (
    file: File,
    opts: { source?: string; account_label?: string; note?: string } = {}
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("source", opts.source ?? "sahm");
    if (opts.account_label) body.append("account_label", opts.account_label);
    if (opts.note) body.append("note", opts.note);
    try {
      const res = await fetch("/api/v1/portfolio/import", { method: "POST", body });
      const data = await res.json();
      if (!res.ok) return { ok: false as const, error: data.detail?.error || data.detail || `HTTP ${res.status}`, status: res.status };
      return { ok: true as const, data };
    } catch (e) {
      return { ok: false as const, error: e instanceof Error ? e.message : String(e) };
    }
  },
};
