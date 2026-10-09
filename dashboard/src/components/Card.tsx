import type { ReactNode } from "react";
import { cls } from "../lib/format";

export function StatCard({
  title,
  value,
  sub,
  tone,
  footnote,
}: {
  title: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "up" | "down" | "neutral";
  footnote?: ReactNode;
}) {
  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{title}</span>
      </div>
      <div className={cls("card-value", tone)}>{value}</div>
      {sub ? <div className="card-sub">{sub}</div> : null}
      {footnote ? <div className="card-sub" style={{ marginTop: 8 }}>{footnote}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{title}</span>
        {action}
      </div>
      {children}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Skeleton({ height = 100 }: { height?: number }) {
  return <div className="skeleton" style={{ height, width: "100%" }} />;
}

export function PageHead({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle ? <div className="page-subtitle">{subtitle}</div> : null}
      </div>
      {action}
    </div>
  );
}

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <>
      <div className="section-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </>
  );
}
