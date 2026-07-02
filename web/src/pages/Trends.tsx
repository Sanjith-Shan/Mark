// Trends — ranked trending topics scored for relevance to a campaign.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { Trend } from "../types";
import { Card, Empty, Pill, pct, timeAgo } from "../components/ui";

export default function Trends() {
  const { campaigns, jobsDoneVersion, runJob } = useGlobal();
  const [campaign, setCampaign] = useState("");
  const [trends, setTrends] = useState<Trend[]>([]);

  const load = () => api.get<Trend[]>("/api/trends?limit=30").then(setTrends).catch(() => {});
  useEffect(() => { load(); }, []);
  useEffect(() => {
    // reload once a trends refresh job finishes (edge-triggered)
    if (jobsDoneVersion > 0) load();
  }, [jobsDoneVersion]); // eslint-disable-line react-hooks/exhaustive-deps

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
        <button className="btn primary"
          onClick={() => runJob(() => api.post(`/api/trends/refresh?campaign=${encodeURIComponent(campaign)}`))}>
          🔥 Refresh trends
        </button>
      </div>

      <Card title="Trending now">
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
                    {t.metadata?.fallback === true && (
                      <span className="pill faint" style={{ fontSize: 10.5, padding: "1px 7px" }}>evergreen</span>
                    )}
                  </div>
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

function relevance(t: Trend): number | null {
  const r = t.metadata?.relevance;
  return typeof r === "number" ? r : null;
}
