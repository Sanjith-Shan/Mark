// Taste — what the owner told Mark, and what Mark did with it.
// The rating trend (is the content getting better?), every reviewed video with
// the AI's takeaway, the learned taste profile, the experiment lab, and the
// scientist's notebook.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { review, subscribeEvents } from "../api";
import { Card, Empty, Pill, Spinner, Stat } from "../components/ui";
import { useGlobal } from "../store";
import {
  CreativeExperiment, ReviewInsights, ReviewedRow, TasteLesson,
} from "../types";

export default function Taste() {
  const { campaigns } = useGlobal();
  const [campaign, setCampaign] = useState<string>("");
  const [data, setData] = useState<ReviewInsights | null>(null);

  const load = useCallback(() => {
    review.insights(campaign || undefined).then(setData).catch(() => {});
  }, [campaign]);
  useEffect(load, [load]);
  useEffect(() => subscribeEvents((e) => {
    if (e.kind === "review" || (e.kind === "job" &&
        (e.job as { kind?: string; status?: string })?.kind === "learn" &&
        (e.job as { status?: string })?.status === "done")) load();
  }), [load]);

  const reviewUrl = `${window.location.origin}/review`;
  const running = useMemo(
    () => data?.experiments.filter((e) => e.status === "running") ?? [],
    [data]);

  if (!data) return <div className="row" style={{ gap: 8 }}><Spinner /> Loading…</div>;

  const rated = data.totals.rated ?? 0;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {/* header row */}
      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <select value={campaign} onChange={(e) => setCampaign(e.target.value)}>
          <option value="">All campaigns</option>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <span className="small muted">
          Rate on your phone → <a href={reviewUrl}>{reviewUrl}</a>
        </span>
      </div>

      <div className="grid cols-4">
        <Stat value={rated} label="videos rated" />
        <Stat value={data.totals.avg_rating ? data.totals.avg_rating.toFixed(1) : "—"}
              label="avg rating (all time)" />
        <Stat value={data.totals.avg_rating_14d ? data.totals.avg_rating_14d.toFixed(1) : "—"}
              label="avg rating (14 days)"
              sub={trendDelta(data.totals.avg_rating, data.totals.avg_rating_14d)} />
        <Stat value={running.length} label="experiments running" />
      </div>

      {/* trend */}
      <Card title="Your rating trend — the number Mark is optimizing" dataTour="taste-trend">
        {data.trend.length >= 2 ? (
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={data.trend} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="week_start" tick={{ fontSize: 11, fill: "var(--text-faint)" }} />
              <YAxis domain={[1, 10]} tick={{ fontSize: 11, fill: "var(--text-faint)" }} />
              <Tooltip
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)",
                                borderRadius: 8, fontSize: 12 }}
                formatter={(v: number, name: string) =>
                  name === "avg_rating" ? [`${v} / 10`, "avg rating"] : [v, name]}
              />
              <Line type="monotone" dataKey="avg_rating" stroke="var(--accent-strong)"
                    strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <Empty icon="📈" title="Not enough ratings yet"
                 hint="Rate a few videos in the phone feed and the trend appears here." />
        )}
      </Card>

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        {/* left: reviewed feed */}
        <Card title={`Reviewed videos (${data.reviews.length})`} dataTour="taste-reviews">
          {data.reviews.length === 0 ? (
            <Empty icon="🎬" title="Nothing reviewed yet"
                   hint={<>Open <a href={reviewUrl}>{reviewUrl}</a> on your phone and start swiping.</>} />
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {data.reviews.map((r) => <ReviewRow key={r.id} r={r} />)}
            </div>
          )}
        </Card>

        {/* right: profile + lab */}
        <div className="stack" style={{ gap: 16 }}>
          <Card title="Taste profile — standing directives Mark now follows"
                dataTour="taste-lessons">
            <LessonList lessons={data.lessons} />
          </Card>
          <Card title="Experiment lab — what Mark is testing on you"
                dataTour="taste-experiments">
            {data.experiments.length === 0 ? (
              <Empty icon="🧪" title="No experiments yet"
                     hint="Once ratings accumulate, the scientist opens A/B tests to isolate what you like." />
            ) : (
              <div className="stack" style={{ gap: 10 }}>
                {data.experiments.map((e) => <ExperimentCard key={e.id} e={e} />)}
              </div>
            )}
          </Card>
          <Card title="Lab notebook — the scientist's running memory">
            {data.notebook.length === 0 ? (
              <Empty icon="📓" title="Empty notebook"
                     hint="Every scientist run leaves an entry: what it saw, what it decided, why." />
            ) : (
              <div className="stack" style={{ gap: 8 }}>
                {data.notebook.map((n) => (
                  <div key={n.id} className="taste-note">
                    <div className="small muted">{n.created_at} UTC</div>
                    <div style={{ fontSize: 13 }}>{n.entry}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function trendDelta(all: number | null, recent: number | null) {
  if (!all || !recent) return null;
  const d = recent - all;
  if (Math.abs(d) < 0.05) return "steady";
  return (
    <span style={{ color: d > 0 ? "var(--green)" : "var(--red)" }}>
      {d > 0 ? "▲" : "▼"} {Math.abs(d).toFixed(1)} vs all-time
    </span>
  );
}

/* ------------------------------------------------------------------ */
function ReviewRow({ r }: { r: ReviewedRow }) {
  const [open, setOpen] = useState(false);
  const media = r.media[0];
  const watchPct = r.video_duration
    ? Math.min(100, Math.round((r.watch_seconds / r.video_duration) * 100)) : null;
  return (
    <div className="taste-review" onClick={() => setOpen((o) => !o)}>
      <div className="taste-review-thumb">
        {media?.kind === "video"
          ? <video src={media.url} muted preload="metadata" playsInline />
          : media ? <img src={media.url} alt="" /> : <div className="rv-grid-empty" />}
        {r.rating != null && <span className="rv-grid-rating">★ {r.rating}</span>}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          <b style={{ fontSize: 13 }}>{r.hook || r.caption?.slice(0, 60) || `#${r.content_id}`}</b>
        </div>
        <div className="row small muted" style={{ gap: 8, flexWrap: "wrap" }}>
          <span>{r.campaign_name}</span>
          <span>{r.platform}</span>
          <Pill kind={r.status}>{r.status}</Pill>
          {watchPct != null && <span>watched {watchPct}%{r.replays ? ` ·  ${r.replays}↻` : ""}</span>}
          {r.experiment && <span>🧪 {r.experiment.aspect}:{r.experiment.variant}</span>}
        </div>
        {r.feedback && (
          <div className="taste-quote">“{r.feedback}”</div>
        )}
        {r.learning?.summary && (
          <div className="taste-learned">🧠 {r.learning.summary}</div>
        )}
        {open && r.learning?.signals && r.learning.signals.length > 0 && (
          <div className="stack" style={{ gap: 4, marginTop: 6 }}>
            {r.learning.signals.map((s, i) => (
              <div key={i} className="small">
                <Pill kind={s.polarity === "prefer" ? "posted" : "rejected"}>
                  {s.polarity} · {s.aspect}
                </Pill>{" "}
                {s.directive}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function LessonList({ lessons }: { lessons: TasteLesson[] }) {
  const active = lessons.filter((l) => l.status === "active");
  const retired = lessons.filter((l) => l.status === "retired");
  if (lessons.length === 0) {
    return <Empty icon="🎯" title="No lessons yet"
                  hint="Leave a note on any video — Mark distills notes into durable directives." />;
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      {active.map((l) => (
        <div key={l.id} className="taste-lesson">
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            <Pill kind={l.polarity === "prefer" ? "posted" : "rejected"}>
              {l.polarity} · {l.aspect}
            </Pill>
            {l.scope_platform && <Pill>{l.scope_platform}</Pill>}
            {l.scope_strategy && <Pill>{l.scope_strategy}</Pill>}
            <span className="small muted" style={{ marginLeft: "auto" }}>
              ×{l.support}{l.contradictions ? ` / ✗${l.contradictions}` : ""}
            </span>
          </div>
          <div style={{ fontSize: 13, margin: "4px 0" }}>{l.directive}</div>
          <div className="progress-track" title={`confidence ${(l.confidence * 100).toFixed(0)}%`}>
            <div className="progress-fill" style={{ width: `${l.confidence * 100}%` }} />
          </div>
        </div>
      ))}
      {retired.length > 0 && (
        <details>
          <summary className="small muted" style={{ cursor: "pointer" }}>
            {retired.length} retired lesson{retired.length > 1 ? "s" : ""}
          </summary>
          <div className="stack" style={{ gap: 6, marginTop: 6, opacity: 0.6 }}>
            {retired.map((l) => (
              <div key={l.id} className="small">
                <s>{l.directive}</s>
                <span className="muted"> — {l.retired_reason}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function ExperimentCard({ e }: { e: CreativeExperiment }) {
  const total = Object.values(e.stats ?? {}).reduce((a, s) => a + s.n, 0);
  return (
    <div className="taste-exp">
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        <Pill kind={e.status === "running" ? "approved" : e.status === "concluded" ? "posted" : "rejected"}>
          {e.status}
        </Pill>
        {e.aspect && <Pill kind="accent">{e.aspect}</Pill>}
        {e.scope_platform && <Pill>{e.scope_platform}</Pill>}
        <span className="small muted" style={{ marginLeft: "auto" }}>#{e.id}</span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, margin: "5px 0 2px" }}>{e.hypothesis}</div>
      {e.rationale && <div className="small muted">why: {e.rationale}</div>}
      <div className="stack" style={{ gap: 4, marginTop: 6 }}>
        {e.variants.map((v) => {
          const s = e.stats?.[v.key];
          const isWinner = e.winner === v.key;
          return (
            <div key={v.key} className={`taste-variant ${isWinner ? "winner" : ""}`}>
              <div className="row" style={{ gap: 6 }}>
                <b style={{ fontSize: 12 }}>{isWinner ? "🏆 " : ""}{v.key}</b>
                <span className="small muted" style={{ marginLeft: "auto" }}>
                  {s ? `${s.n}/${e.min_samples} rated · ${s.mean_rating != null ? `avg ★${s.mean_rating}` : "—"}` : "—"}
                </span>
              </div>
              <div className="small muted" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                {v.directive}
              </div>
            </div>
          );
        })}
      </div>
      {e.status === "running" && (
        <div className="small muted" style={{ marginTop: 5 }}>
          {total} rated so far — concludes at {e.min_samples} per variant.
        </div>
      )}
      {e.conclusion && <div className="taste-learned" style={{ marginTop: 6 }}>📌 {e.conclusion}</div>}
    </div>
  );
}
