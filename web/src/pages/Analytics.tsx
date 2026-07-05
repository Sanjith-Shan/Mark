// Analytics — engagement charts, top content, and comment sentiment.
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api";
import { useGlobal } from "../store";
import { CommentRow, PLATFORM_COLORS, PLATFORM_LABELS, ReplyRow, SeriesPoint } from "../types";
import { Card, Empty, Pill, PlatformChip, Stat, fmt, pct, timeAgo } from "../components/ui";

interface TableRow {
  content_id: number;
  platform: string;
  content_type: string;
  hook: string | null;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  engagement_rate: number;
}

interface AnalyticsResp {
  table: TableRow[];
  series: SeriesPoint[];
  totals: { views: number; likes: number; comments: number; shares: number; avg_engagement: number };
}

interface CommentsResp {
  comments: CommentRow[];
  sentiment_summary: string;
}

export default function Analytics() {
  const { campaigns, jobsDoneVersion, runJob } = useGlobal();
  const [campaign, setCampaign] = useState("");
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AnalyticsResp | null>(null);
  const [comments, setComments] = useState<CommentsResp | null>(null);
  const [replies, setReplies] = useState<ReplyRow[]>([]);

  const load = () => {
    const q = `campaign=${encodeURIComponent(campaign)}`;
    api.get<AnalyticsResp>(`/api/analytics?${q}&days=${days}`).then(setData).catch(() => {});
    api.get<CommentsResp>(`/api/comments?${q}&limit=30`).then(setComments).catch(() => {});
    api.get<ReplyRow[]>(`/api/replies?${q}&status=draft&limit=50`).then(setReplies).catch(() => {});
  };
  useEffect(() => { load(); }, [campaign, days]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    // reload when a job (e.g. analytics collection) finishes
    if (jobsDoneVersion > 0) load();
  }, [jobsDoneVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const series = data?.series ?? [];
  const engagement = pivot(series, "engagement");
  const views = pivot(series, "views");
  const table = [...(data?.table ?? [])].sort((a, b) => b.engagement_rate - a.engagement_rate);
  const totals = data?.totals;

  return (
    <>
      <div className="row wrap">
        <select className="input" style={{ width: 220 }} value={campaign}
          onChange={(e) => setCampaign(e.target.value)}>
          <option value="">All campaigns</option>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input" style={{ width: 140 }} value={days}
          onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <div style={{ flex: 1 }} />
        <button className="btn"
          onClick={() => runJob(() => api.post(`/api/analytics/collect?campaign=${encodeURIComponent(campaign)}`))}>
          📊 Collect now
        </button>
      </div>

      <div className="grid cols-4">
        <Card><Stat value={fmt(totals?.views)} label="Views" /></Card>
        <Card><Stat value={fmt(totals?.likes)} label="Likes" /></Card>
        <Card><Stat value={fmt((totals?.comments ?? 0) + (totals?.shares ?? 0))} label="Comments + shares" /></Card>
        <Card><Stat value={pct(totals?.avg_engagement)} label="Avg engagement" /></Card>
      </div>

      <Card title="Engagement by day" action={<PlatformLegend platforms={engagement.platforms} />}>
        {engagement.rows.length === 0 ? (
          <Empty icon="📈" title="No engagement data yet"
            hint="Post content, then collect analytics to see engagement over time." />
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={engagement.rows} margin={{ top: 4, right: 4, bottom: 0, left: -14 }}>
              <CartesianGrid stroke="#222b38" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" stroke="#5f6c7d" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#5f6c7d" fontSize={11} tickLine={false} axisLine={false}
                tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
              <Tooltip content={<PctTip />} />
              {engagement.platforms.map((p) => (
                <Line key={p} type="monotone" dataKey={p} stroke={PLATFORM_COLORS[p] ?? "#8b5cf6"}
                  strokeWidth={2} dot={false} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      <Card title="Views per day" action={<PlatformLegend platforms={views.platforms} />}>
        {views.rows.length === 0 ? (
          <Empty icon="👁" title="No view data yet" hint="Views appear once analytics are collected." />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={views.rows} margin={{ top: 4, right: 4, bottom: 0, left: -14 }}>
              <CartesianGrid stroke="#222b38" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" stroke="#5f6c7d" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#5f6c7d" fontSize={11} tickLine={false} axisLine={false}
                tickFormatter={(v: number) => fmt(v)} />
              <Tooltip content={<ViewsTip />} cursor={{ fill: "rgba(139,92,246,0.06)" }} />
              {views.platforms.map((p) => (
                <Bar key={p} dataKey={p} stackId="views" fill={PLATFORM_COLORS[p] ?? "#8b5cf6"} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      <Card title="Top content">
        {table.length === 0 ? (
          <Empty icon="🏆" title="Nothing to rank yet"
            hint="Posted content shows up here ranked by engagement once metrics are in." />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Hook</th><th>Platform</th><th>Type</th>
                <th className="num">Views</th><th className="num">Likes</th>
                <th className="num">Comments</th><th className="num">Shares</th>
                <th className="num">Engagement</th>
              </tr>
            </thead>
            <tbody>
              {table.map((r) => (
                <tr key={`${r.content_id}-${r.platform}`}>
                  <td style={{ fontWeight: 600, maxWidth: 320 }}>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {r.hook || "—"}
                    </div>
                  </td>
                  <td><PlatformChip platform={r.platform} /></td>
                  <td className="muted">{r.content_type}</td>
                  <td className="num">{fmt(r.views)}</td>
                  <td className="num">{fmt(r.likes)}</td>
                  <td className="num">{fmt(r.comments)}</td>
                  <td className="num">{fmt(r.shares)}</td>
                  <td className="num" style={{ fontWeight: 600 }}>{pct(r.engagement_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <RepliesCard replies={replies} campaign={campaign} onChanged={load} />

      <Card title="Comments">
        {(comments?.comments ?? []).length === 0 ? (
          <Empty icon="💬" title="No comments collected"
            hint="Comments and their sentiment show up after analytics collection." />
        ) : (
          <>
            {comments?.sentiment_summary && (
              <div className="small muted" style={{ marginBottom: 12 }}>{comments.sentiment_summary}</div>
            )}
            <div className="stack">
              {(comments?.comments ?? []).map((c) => (
                <div key={c.id} className="row" style={{ alignItems: "flex-start" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ fontWeight: 600 }}>{c.author ?? "anonymous"}</span>
                    <span className="muted"> — {c.comment_text}</span>
                  </div>
                  <SentimentPill sentiment={c.sentiment} />
                </div>
              ))}
            </div>
          </>
        )}
      </Card>
    </>
  );
}

/* ---------- drafted comment replies ---------- */

function RepliesCard(props: { replies: ReplyRow[]; campaign: string; onChanged: () => void }) {
  const { runJob } = useGlobal();
  const { replies, campaign, onChanged } = props;
  // Label by platform: keep replies for the same platform together.
  const sorted = [...replies].sort((a, b) =>
    a.platform === b.platform ? b.id - a.id : a.platform.localeCompare(b.platform));

  return (
    <Card
      title={
        <span className="row" style={{ gap: 8 }}>
          Drafted replies
          {replies.length > 0 && <Pill kind="draft">{replies.length} pending</Pill>}
        </span>
      }
      action={
        <button className="btn sm"
          onClick={() => runJob(() => api.post<{ job_id: string }>(
            `/api/replies/draft?campaign=${encodeURIComponent(campaign)}`))}>
          💬 Draft replies now
        </button>
      }>
      {sorted.length === 0 ? (
        <Empty icon="↩️" title="No drafted replies"
          hint="Hit “Draft replies now” and Mark writes on-voice replies to fresh comments for you to review." />
      ) : (
        <div className="stack" style={{ gap: 0 }}>
          {sorted.map((r, i) => (
            <ReplyItem key={r.id} reply={r} onChanged={onChanged}
              last={i === sorted.length - 1} />
          ))}
        </div>
      )}
    </Card>
  );
}

function ReplyItem({ reply: r, onChanged, last }: { reply: ReplyRow; onChanged: () => void; last: boolean }) {
  const { toast } = useGlobal();
  const [text, setText] = useState(r.reply_text);
  const [busy, setBusy] = useState(false);
  const sensitive = !!r.sensitive;

  const patch = async (body: { reply_text?: string; status?: string }, msg: string) => {
    setBusy(true);
    try {
      await api.patch<ReplyRow>(`/api/replies/${r.id}`, body);
      toast(msg);
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Update failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack"
      style={{
        gap: 8, padding: "12px 0",
        borderBottom: last ? undefined : "1px solid var(--border)",
        ...(sensitive ? {
          borderLeft: "3px solid var(--amber)", paddingLeft: 12,
          background: "var(--amber-soft)", borderRadius: "var(--radius-sm)",
          marginBottom: last ? 0 : 8, borderBottom: undefined,
        } : {}),
      }}>
      <div className="row wrap" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          <div className="row wrap" style={{ gap: 8 }}>
            <PlatformChip platform={r.platform} />
            {sensitive && <Pill kind="draft">⚠ sensitive — handle personally</Pill>}
            <span className="faint small">{timeAgo(r.created_at)}</span>
          </div>
          <div style={{ fontSize: 13, marginTop: 4 }}>
            <span style={{ fontWeight: 600 }}>{r.author ?? "anonymous"}</span>
            <span className="muted"> — {r.comment_text}</span>
          </div>
          {r.post_hook && (
            <div className="small faint" style={{ marginTop: 2 }}>on “{r.post_hook}”</div>
          )}
        </div>
        <div className="row" style={{ gap: 6, flexShrink: 0 }}>
          <button className="btn success sm" disabled={busy}
            title="You post the reply yourself in the app — this just records it as done"
            onClick={() => patch({ status: "posted" }, "Marked posted")}>
            ✓ Mark posted
          </button>
          <button className="btn ghost sm" disabled={busy}
            onClick={() => patch({ status: "skipped" }, "Skipped")}>
            Skip
          </button>
        </div>
      </div>
      {sensitive ? (
        <div className="small" style={{ color: "var(--amber)" }}>
          Mark won't draft this one — reply personally, then mark it posted or skip it.
        </div>
      ) : (
        <textarea className="input" rows={2} value={text} placeholder="Drafted reply"
          onChange={(e) => setText(e.target.value)}
          onBlur={() => {
            if (text !== r.reply_text) patch({ reply_text: text }, "Reply saved");
          }} />
      )}
    </div>
  );
}

function SentimentPill({ sentiment }: { sentiment: string | null }) {
  if (sentiment === "positive") return <Pill kind="live">positive</Pill>;
  if (sentiment === "negative") return <Pill kind="failed">negative</Pill>;
  return <Pill>{sentiment ?? "neutral"}</Pill>;
}

function PlatformLegend({ platforms }: { platforms: string[] }) {
  if (platforms.length === 0) return null;
  return (
    <div className="row wrap" style={{ gap: 10 }}>
      {platforms.map((p) => <PlatformChip key={p} platform={p} />)}
    </div>
  );
}

/** Pivot the flat series into one row per day with a column per platform. */
function pivot(series: SeriesPoint[], key: "engagement" | "views") {
  const platforms = [...new Set(series.map((s) => s.platform))];
  const byDay = new Map<string, Record<string, number | string>>();
  for (const s of series) {
    const row = byDay.get(s.day) ?? { day: s.day.slice(5) };
    row[s.platform] = s[key] ?? 0;
    byDay.set(s.day, row);
  }
  const rows = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, r]) => r);
  return { platforms, rows };
}

function PctTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card" style={{ padding: "8px 12px", fontSize: 12 }}>
      <div style={{ fontWeight: 600 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.stroke ?? p.fill }}>
          {PLATFORM_LABELS[p.dataKey] ?? p.dataKey} · {(Number(p.value) * 100).toFixed(2)}%
        </div>
      ))}
    </div>
  );
}

function ViewsTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card" style={{ padding: "8px 12px", fontSize: 12 }}>
      <div style={{ fontWeight: 600 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.fill }}>
          {PLATFORM_LABELS[p.dataKey] ?? p.dataKey} · {fmt(Number(p.value))} views
        </div>
      ))}
    </div>
  );
}
