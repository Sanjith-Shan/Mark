import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useGlobal } from "../store";
import { Activity, Campaign, Job, SeriesPoint } from "../types";
import { Card, Empty, Pill, PlatformChip, Stat, fmt, pct, timeAgo } from "../components/ui";

interface Overview {
  campaigns: Campaign[];
  series: SeriesPoint[];
  activity: Activity[];
  jobs: Job[];
}

const FEED_ICONS: Record<string, string> = {
  generate: "✍️", post: "📤", approve: "✓", reject: "✕", learn: "🧠",
  trends: "🔥", analytics: "📊", campaign: "🚩", autopilot: "⚡",
  edit: "✎", media: "🖼", rewrite: "↻", settings: "⚙", error: "!",
};

export default function Dashboard() {
  const { status, contentVersion, jobsDoneVersion, runJob } = useGlobal();
  const [ov, setOv] = useState<Overview | null>(null);

  const load = () => api.get<Overview>("/api/overview").then(setOv).catch(() => {});
  useEffect(() => { load(); }, [contentVersion]);
  useEffect(() => {
    // refresh once each time a job finishes (edge-triggered)
    if (jobsDoneVersion > 0) load();
  }, [jobsDoneVersion]);

  const running = ov?.campaigns.filter((c) => c.active) ?? [];
  const totalViews = ov?.campaigns.reduce((s, c) => s + (c.views_7d ?? 0), 0) ?? 0;
  const avgEng = running.length
    ? running.reduce((s, c) => s + (c.avg_engagement_7d ?? 0), 0) / running.length
    : 0;

  const chartData = buildChart(ov?.series ?? []);

  return (
    <>
      <div className="grid cols-4">
        <Card><Stat value={running.length} label="Campaigns running"
          sub={<Link to="/campaigns">manage →</Link>} /></Card>
        <Card><Stat value={status?.counts?.draft ?? 0} label="Drafts awaiting review"
          sub={<Link to="/studio">review →</Link>} /></Card>
        <Card><Stat value={fmt(totalViews)} label="Views · last 7 days" sub={`avg engagement ${pct(avgEng)}`} /></Card>
        <Card><Stat value={`$${(status?.spend_30d_usd ?? 0).toFixed(2)}`} label="Spend · last 30 days"
          sub={status && Object.values(status.providers).every((p) => p === "mock") ? "offline mode — $0 real spend" : "real API spend"} /></Card>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1.7fr 1fr" }}>
        <Card title="Engagement · last 14 days">
          {chartData.length === 0 ? (
            <Empty icon="📈" title="No posted content yet"
              hint="Once posts go live and analytics are collected, engagement shows up here." />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <defs>
                  <linearGradient id="eng" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#222b38" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" stroke="#5f6c7d" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#5f6c7d" fontSize={11} tickLine={false} axisLine={false}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                <Tooltip content={<ChartTip />} />
                <Area type="monotone" dataKey="engagement" stroke="#8b5cf6" strokeWidth={2}
                  fill="url(#eng)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Activity">
          <div className="feed" style={{ maxHeight: 246, overflowY: "auto" }}>
            {(ov?.activity ?? []).length === 0 && (
              <Empty icon="🕰" title="Nothing yet" hint="System actions appear here as they happen." />
            )}
            {(ov?.activity ?? []).slice(0, 20).map((a) => (
              <div className="feed-item" key={a.id}>
                <div className="feed-icon">{FEED_ICONS[a.kind] ?? "·"}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    color: a.level === "error" ? "var(--red)" : undefined,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>{a.message}</div>
                  <div className="feed-time">
                    {a.product_id && <span className="mono">{a.product_id} · </span>}
                    {timeAgo(a.created_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Campaigns" action={<Link to="/campaigns" className="small">all campaigns →</Link>}>
        {(ov?.campaigns ?? []).filter((c) => c.active).length === 0 ? (
          <Empty icon="🚩" title="No campaigns running"
            hint="Create a campaign and Mark starts marketing it."
            action={<Link to="/campaigns" className="btn primary">New campaign</Link>} />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Campaign</th><th>Platforms</th><th className="num">Drafts</th>
                <th className="num">Posted (7d)</th><th className="num">Views (7d)</th>
                <th className="num">Engagement</th><th className="num">Spend</th>
              </tr>
            </thead>
            <tbody>
              {(ov?.campaigns ?? []).filter((c) => c.active).map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.name}</td>
                  <td><div className="row wrap" style={{ gap: 8 }}>
                    {c.platforms.slice(0, 5).map((p) => <PlatformChip key={p} platform={p} />)}
                    {c.platforms.length > 5 && <span className="faint small">+{c.platforms.length - 5}</span>}
                  </div></td>
                  <td className="num">{c.counts?.draft ?? 0}</td>
                  <td className="num">{c.posts_7d ?? 0}</td>
                  <td className="num">{fmt(c.views_7d)}</td>
                  <td className="num">{pct(c.avg_engagement_7d)}</td>
                  <td className="num">${(c.spend_usd ?? 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <QuickActions onDone={load} />
    </>
  );
}

function QuickActions({ onDone }: { onDone: () => void }) {
  const { runJob } = useGlobal();
  return (
    <Card title="Quick actions">
      <div className="row wrap">
        <button className="btn primary" onClick={() => runJob(() => api.post("/api/generate", {}))}>
          ✨ Generate today's content
        </button>
        <button className="btn" onClick={() => runJob(() => api.post("/api/post-approved"))}>
          📤 Post all approved
        </button>
        <button className="btn" onClick={() => runJob(() => api.post("/api/analytics/collect"))}>
          📊 Collect analytics
        </button>
        <button className="btn" onClick={() => runJob(() => api.post("/api/trends/refresh"))}>
          🔥 Refresh trends
        </button>
        <button className="btn" onClick={() => runJob(() => api.post("/api/learn", {}))}>
          🧠 Run learning loop
        </button>
      </div>
    </Card>
  );
}

function buildChart(series: SeriesPoint[]) {
  const byDay = new Map<string, { total: number; n: number; views: number }>();
  for (const s of series) {
    const cur = byDay.get(s.day) ?? { total: 0, n: 0, views: 0 };
    cur.total += s.engagement ?? 0;
    cur.n += 1;
    cur.views += s.views ?? 0;
    byDay.set(s.day, cur);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, v]) => ({
      day: day.slice(5),
      engagement: v.n ? v.total / v.n : 0,
      views: v.views,
    }));
}

function ChartTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card" style={{ padding: "8px 12px", fontSize: 12 }}>
      <div style={{ fontWeight: 600 }}>{label}</div>
      <div className="muted">engagement {(payload[0].value * 100).toFixed(2)}%</div>
      <div className="faint">{fmt(payload[0].payload.views)} views</div>
    </div>
  );
}
