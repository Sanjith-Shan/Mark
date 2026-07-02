// Small shared UI primitives.
import { ReactNode } from "react";
import { PLATFORM_COLORS, PLATFORM_LABELS } from "../types";

export function Card(props: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`card ${props.className ?? ""}`}>
      {props.title != null && (
        <div className="card-title">
          <span>{props.title}</span>
          {props.action}
        </div>
      )}
      {props.children}
    </div>
  );
}

export function Pill(props: { kind?: string; children: ReactNode }) {
  return <span className={`pill ${props.kind ?? ""}`}>{props.children}</span>;
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill ${status}`}>{status}</span>;
}

export function PlatformChip({ platform }: { platform: string }) {
  return (
    <span className="platform-chip">
      <span className="platform-swatch" style={{ background: PLATFORM_COLORS[platform] ?? "#666" }} />
      {PLATFORM_LABELS[platform] ?? platform}
    </span>
  );
}

export function Stat(props: { value: ReactNode; label: string; sub?: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-value">{props.value}</span>
      <span className="stat-label">{props.label}</span>
      {props.sub != null && <span className="stat-sub">{props.sub}</span>}
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" />;
}

export function Empty(props: { icon?: string; title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{props.icon ?? "◎"}</div>
      <div style={{ fontWeight: 600, color: "var(--text-dim)" }}>{props.title}</div>
      {props.hint != null && <div className="small">{props.hint}</div>}
      {props.action}
    </div>
  );
}

export function Modal(props: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <div className={`modal ${props.wide ? "wide" : ""}`}>
        <div className="row between" style={{ marginBottom: 4 }}>
          <div className="modal-title" style={{ marginBottom: 0 }}>{props.title}</div>
          <button className="btn ghost sm" onClick={props.onClose}>✕</button>
        </div>
        <div style={{ marginTop: 16 }}>{props.children}</div>
      </div>
    </div>
  );
}

export function Switch(props: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="switch" style={props.disabled ? { opacity: 0.5, pointerEvents: "none" } : undefined}>
      <input type="checkbox" checked={props.checked} onChange={(e) => props.onChange(e.target.checked)} />
      <span className="track" />
      <span className="thumb" />
    </label>
  );
}

export function timeAgo(ts: string): string {
  // Server timestamps are UTC ("YYYY-MM-DD HH:MM:SS") — parse them as such.
  let iso = ts.includes("T") ? ts : ts.replace(" ", "T");
  if (!/Z|[+-]\d{2}:?\d{2}$/.test(iso)) iso += "Z";
  const t = new Date(iso);
  const secs = Math.max(0, (Date.now() - t.getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n * 100) / 100);
}

export function pct(x: number | null | undefined): string {
  if (x == null) return "—";
  return `${(x * 100).toFixed(1)}%`;
}
