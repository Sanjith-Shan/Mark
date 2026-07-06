// Trends — ranked trending topics scored for relevance to a campaign,
// plus the humor radar: copyworthy humor sighted in the wild.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { HumorFind, Trend } from "../types";
import { Card, Empty, Pill, pct, timeAgo } from "../components/ui";

export default function Trends() {
  const { campaigns, jobsDoneVersion, runJob } = useGlobal();
  const [campaign, setCampaign] = useState("");
  const [trends, setTrends] = useState<Trend[]>([]);
  const [hot, setHot] = useState<Trend[]>([]);
  const [humor, setHumor] = useState<HumorFind[]>([]);

  const load = () => {
    api.get<Trend[]>("/api/trends?limit=30").then(setTrends).catch(() => {});
    api.get<Trend[]>("/api/trends/hot?limit=5").then(setHot).catch(() => {});
    api.get<HumorFind[]>("/api/humor?limit=12").then(setHumor).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    // reload once a trends refresh/react job finishes (edge-triggered)
    if (jobsDoneVersion > 0) load();
  }, [jobsDoneVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const ride = (t: Trend) =>
    runJob(() => api.post<{ job_id: string }>("/api/trends/react", {
      topic: t.topic,
      campaign_id: campaign || undefined,
    }));

  return (
    <>
      <div className="row wrap">
        <select className="input" style={{ width: 220 }} value={campaign}
          onChange={(e) => setCampaign(e.target.value)}>
          <option value="">Active campaign</option>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <span className="small faint">relevance is scored against the selected campaign</span>
        <div style={{ flex: 1 }} />
        <button className="btn primary" data-tour="trends-refresh"
          onClick={() => runJob(() => api.post(`/api/trends/refresh?campaign=${encodeURIComponent(campaign)}`))}>
          🔥 Refresh trends
        </button>
      </div>

      {hot.length > 0 && (
        <Card title="Hot right now"
          action={<span className="small faint">fresh + rising + relevant — the window to ride these is short</span>}>
          <div className="stack" style={{ gap: 0 }}>
            {hot.map((t, i) => (
              <div key={`${t.source}-${t.topic}-${i}`} className="row wrap"
                style={{ padding: "11px 0", borderBottom: i < hot.length - 1 ? "1px solid var(--border)" : undefined }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className="row wrap" style={{ gap: 8 }}>
                    <span style={{ fontWeight: 600 }}>{t.topic}</span>
                    <StageBadge stage={t.stage} />
                    <VelocityArrow velocity={t.velocity} />
                    {t.metadata?.safe === false && <UnsafeMark />}
                  </div>
                  {t.metadata?.sound_dependent === true && (
                    <div className="small faint" style={{ marginTop: 3 }}>
                      🔇 needs native sound — manual post
                    </div>
                  )}
                  {t.style_notes && (
                    <div className="small muted" style={{ fontStyle: "italic", marginTop: 3 }}>
                      {t.style_notes}
                    </div>
                  )}
                </div>
                <button className="btn primary sm" onClick={() => ride(t)}
                  title="Draft trend-riding content for this topic right now">
                  🏄 Ride this trend
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <HumorRadar finds={humor} />

      <Card title="Trending now" dataTour="trends-table">
        {trends.length === 0 ? (
          <Empty icon="🔥" title="No trend data yet"
            hint="Hit “Refresh trends” to pull trending topics from TikTok and Google, scored for relevance to your campaign." />
        ) : (
          <div className="stack" style={{ gap: 0 }}>
            {trends.map((t, i) => (
              <div key={`${t.source}-${t.topic}-${i}`} className="row"
                style={{ padding: "11px 0", borderBottom: i < trends.length - 1 ? "1px solid var(--border)" : undefined, alignItems: "flex-start" }}>
                <span className="mono faint" style={{ width: 28, fontSize: 13, paddingTop: 2 }}>{i + 1}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row wrap" style={{ gap: 8 }}>
                    <span style={{ fontWeight: 600 }}>{t.topic}</span>
                    {t.source === "tiktok"
                      ? <Pill kind="accent">tiktok</Pill>
                      : <Pill>{t.source}</Pill>}
                    <StageBadge stage={t.stage} />
                    <VelocityArrow velocity={t.velocity} />
                    {t.metadata?.safe === false && <UnsafeMark />}
                    {t.metadata?.fallback === true && (
                      <span className="pill faint" style={{ fontSize: 10.5, padding: "1px 7px" }}>evergreen</span>
                    )}
                  </div>
                  {t.metadata?.sound_dependent === true && (
                    <div className="small faint" style={{ marginTop: 3 }}>
                      🔇 needs native sound — manual post
                    </div>
                  )}
                  {t.style_notes && (
                    <div className="small muted" style={{ fontStyle: "italic", marginTop: 3 }}>
                      How it's executed: {t.style_notes}
                    </div>
                  )}
                </div>
                <div style={{ width: 200, flexShrink: 0 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <div className="progress-track" style={{ flex: 1, marginTop: 0 }}>
                      <div className="progress-fill"
                        style={{ width: `${Math.min(Math.max(t.trend_score, 0), 1) * 100}%` }} />
                    </div>
                    <span className="small muted" style={{ width: 58, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {relevance(t) != null ? `${pct(relevance(t))} rel` : "—"}
                    </span>
                  </div>
                  <div className="small faint" style={{ textAlign: "right", marginTop: 2 }}>
                    {timeAgo(t.collected_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

function HumorRadar({ finds }: { finds: HumorFind[] }) {
  const { campaigns, toast, runJob } = useGlobal();
  const entertainment = campaigns.filter((c) => c.kind === "entertainment" && c.active);
  const [target, setTarget] = useState("");
  const targetId = target || entertainment[0]?.id || "";

  const draft = async (f: HumorFind) => {
    if (!targetId) return;
    try {
      await api.post(`/api/humor/${f.id}/draft`, { campaign_id: targetId });
      toast(`repost drafted for ${targetId} — review it in the Studio`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "draft failed", "error");
    }
  };

  return (
    <Card title="Humor radar · copyworthy right now" dataTour="humor-radar"
      action={
        <div className="row" style={{ gap: 8 }}>
          {entertainment.length > 1 && (
            <select className="input" style={{ width: 170, padding: "4px 8px", fontSize: 12 }}
              value={targetId} onChange={(e) => setTarget(e.target.value)}>
              {entertainment.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          <button className="btn sm"
            onClick={() => runJob(() => api.post("/api/humor/refresh"))}>
            😂 Refresh
          </button>
        </div>
      }>
      {finds.length === 0 ? (
        <Empty icon="😂" title="Radar is empty"
          hint="Hit Refresh — it polls meme subreddits, Tenor trending, and live meme-template rankings, then scores every find for funniness and freshness." />
      ) : (
        <>
          {entertainment.length === 0 && (
            <div className="small faint" style={{ marginBottom: 10 }}>
              ⚠ Reposts are for <b>entertainment campaigns only</b> (a brand account
              reposting memes is a copyright exposure and an algorithm-killer).
              Create a campaign with kind = entertainment to draft from here.
            </div>
          )}
          <div className="stack" style={{ gap: 0 }}>
            {finds.map((f, i) => (
              <div key={f.id} className="row wrap"
                style={{ padding: "10px 0", borderBottom: i < finds.length - 1 ? "1px solid var(--border)" : undefined }}>
                {f.media_url ? (
                  <a href={f.permalink ?? f.media_url} target="_blank" rel="noreferrer">
                    <img src={f.media_url} alt="" loading="lazy"
                      style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 8, background: "var(--bg-raised)" }} />
                  </a>
                ) : (
                  <div style={{ width: 56, height: 56, borderRadius: 8, background: "var(--bg-raised)",
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>🧩</div>
                )}
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className="row wrap" style={{ gap: 8 }}>
                    {f.post_now && <Pill kind="live">post now</Pill>}
                    <span style={{ fontWeight: 600 }}>{f.title}</span>
                  </div>
                  <div className="row wrap small faint" style={{ gap: 10, marginTop: 3 }}>
                    <span>{f.source}{f.community ? ` · ${f.community}` : ""}</span>
                    <StageBadge stage={f.stage as Trend["stage"]} />
                    <span title="judge: how funny">😂 {((f.funny ?? 0) * 100).toFixed(0)}%</span>
                    <span title="blended radar score">◎ {(f.radar_score * 100).toFixed(0)}</span>
                    {f.author && <span>{f.author}</span>}
                  </div>
                </div>
                {f.media_url && (
                  <button className="btn primary sm" disabled={!targetId}
                    title={targetId ? "Create a credited repost draft (review in Studio)"
                      : "Needs an active entertainment campaign"}
                    onClick={() => draft(f)}>
                    📋 Draft repost
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function relevance(t: Trend): number | null {
  const r = t.metadata?.relevance;
  return typeof r === "number" ? r : null;
}

function StageBadge({ stage }: { stage?: Trend["stage"] }) {
  if (!stage) return null;
  return <Pill kind={`stage-${stage}`}>{stage}</Pill>;
}

function VelocityArrow({ velocity }: { velocity?: number | null }) {
  if (velocity == null) return null;
  const up = velocity > 0.01;
  const down = velocity < -0.01;
  return (
    <span className="small" title={`velocity ${velocity.toFixed(3)}/hr`}
      style={{
        fontWeight: 700,
        color: up ? "var(--green)" : down ? "var(--red)" : "var(--text-faint)",
      }}>
      {up ? "↑" : down ? "↓" : "→"}
    </span>
  );
}

function UnsafeMark() {
  return (
    <span className="small faint" title="Flagged as not brand-safe — Mark won't auto-react to this one"
      style={{ cursor: "help" }}>⚠</span>
  );
}
