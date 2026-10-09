import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { usePolling } from "../hooks/useApi";
import { api } from "../lib/api";
import { cls, fmtTime } from "../lib/format";

interface NavItem {
  to: string;
  label: string;
}

const NAV: NavItem[] = [
  { to: "/overview", label: "Overview" },
  { to: "/market", label: "Market Monitor" },
  { to: "/options", label: "Options Chain" },
  { to: "/scanner", label: "0DTE Scanner" },
  { to: "/intelligence", label: "Intelligence" },
  { to: "/strategy", label: "Strategy Lab" },
  { to: "/agents", label: "AI Agents" },
  { to: "/risk", label: "Risk Center" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/telegram", label: "Telegram" },
  { to: "/settings", label: "Settings" },
];

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="mark">TX</span>
          <span>TRAX</span>
        </div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) => cls("sidebar-link", isActive && "active")}
          >
            {n.label}
          </NavLink>
        ))}
        <div className="sidebar-footer">
          <div>Local-first</div>
          <div>Paper trading only</div>
          <div>Live execution disabled</div>
        </div>
      </aside>
      <main className="main">
        <TopBar />
        {children}
      </main>
    </div>
  );
}

function TopBar() {
  const health = usePolling(api.health, 20_000);
  const h = health.data;
  const session = h?.session;

  const modeBadge = h?.mode === "live-disabled" ? "disabled" : "ok";

  return (
    <div className="topbar">
      <div className="status-item">
        <span className="label">Mode</span>
        <span className={cls("badge", modeBadge)}>{h?.mode ?? "…"}</span>
      </div>
      <span className="divider" />
      <div className="status-item">
        <span className="label">Session</span>
        <span className={cls("badge", session?.session === "open" ? "ok" : "unavailable")}>
          {session?.session ?? "…"}
        </span>
      </div>
      <span className="divider" />
      <div className="status-item">
        <span className="label">ET</span>
        <span className="value mono">{fmtTime(session?.now_et, { date: false })}</span>
      </div>
      <span className="divider" />
      {h?.subsystems &&
        Object.entries(h.subsystems).map(([name, sys]) => (
          <div key={name} className="status-item">
            <span className="label">{name.replace(/_/g, " ")}</span>
            <span className={cls("badge", mapHealthStatus(sys.status))}>{sys.status}</span>
          </div>
        ))}
      {health.loading && !h ? <span className="dim">loading…</span> : null}
    </div>
  );
}

function mapHealthStatus(status: string): string {
  if (status === "ok") return "ok";
  if (status === "degraded") return "delayed";
  if (status === "unconfigured") return "unavailable";
  if (status === "unavailable") return "unavailable";
  return "unavailable";
}
