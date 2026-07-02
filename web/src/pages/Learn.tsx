// Learn — insights, bandit leaderboard, and the self-improvement loop.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { Insights } from "../types";
import { Card, Empty, Pill, PlatformChip, Stat, pct, timeAgo } from "../components/ui";

export default function Learn() {
  const { campaigns, jobsDoneVersion, runJob } = useGlobal();
  const [campaign, setCampaign] = useState("");
  const [data, setData] = useState<Insights | null>(null);

  // default to the active campaign once campaigns load
  useEffect(() => {
    if (!campaign && campaigns.length > 0) {
      const first = campaigns.find((c) => c.active) ?? campaigns[0];
      setCampaign(first.id);
    }
  }, [campaigns]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = () => {
    api.get<Insights>(`/api/insights?campaign=${encodeURIComponent(campaign)}`)
      .then(setData).catch(() => {});
  };
  useEffect(() => { load(); }, [campaign]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    // reload once a learning job finishes
    if (jobsDoneVersion > 0) load();
  }, [jobsDoneVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const payload = data?.insights?.payload;
  const bandit = [...(data?.bandit ?? [])].sort((a, b) => b.avg_reward - a.avg_reward);
  const hasAnything = (data?.winners ?? 0) > 0 || bandit.length > 0 || payload != null;

  return (
    <>
      <div className="row wrap">
        <select className="input" style={{ width: 220 }} value={campaign}
          onChange={(e) => setCampaign(e.target.value)}>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button className="btn primary"
          onClick={() => runJob(() => api.post("/api/learn", { campaign_id: campaign || undefined, days: 30 }))}>
          🧠 Run learning loop now
        </button>
      </div>

      <div className="grid cols-3">
        <Card><Stat value={data?.winners ?? 0} label="Winners indexed"
          sub="top posts reused as examples" /></Card>
        <Card><Stat value={bandit.length} label="Bandit arms tried"
          sub="choices Mark is optimizing" /></Card>
        <Card><Stat
          value={data?.insights?.created_at ? timeAgo(data.insights.created_at) : "never"}
          label="Last analysis" /></Card>
      </div>

      {!hasAnything ? (
        <Card>
          <Empty icon="🧠" title="No learnings yet"
            hint="Post content and collect analytics first — then run the learning loop and Mark starts learning what works." />
        </Card>
      ) : (
        <>
          <div className="grid cols-2">
            <Card title="What's working">
              {payload == null ? (
                <Empty icon="✨" title="No analysis yet"
                  hint="Run the learning loop to generate insights from your engagement data." />
              ) : (
                <div className="stack" style={{ gap: 14 }}>
                  {(payload.best_hook_styles ?? []).length > 0 && (
                    <div>
                      <div className="small faint" style={{ marginBottom: 6 }}>Best hook styles</div>
                      <div className="row wrap" style={{ gap: 6 }}>
                        {(payload.best_hook_styles ?? []).map((h) => <Pill key={h} kind="accent">{h}</Pill>)}
                      </div>
                    </div>
                  )}
                  {Object.keys(payload.best_content_types ?? {}).length > 0 && (
                    <div>
                      <div className="small faint" style={{ marginBottom: 4 }}>Best content type per platform</div>
                      <table className="table">
                        <tbody>
                          {Object.entries(payload.best_content_types ?? {}).map(([p, t]) => (
                            <tr key={p}>
                              <td><PlatformChip platform={p} /></td>
                              <td className="num muted">{t}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {Object.keys(payload.best_posting_times ?? {}).length > 0 && (
                    <div>
                      <div className="small faint" style={{ marginBottom: 4 }}>Best posting time per platform</div>
                      <table className="table">
                        <tbody>
                          {Object.entries(payload.best_posting_times ?? {}).map(([p, t]) => (
                            <tr key={p}>
                              <td><PlatformChip platform={p} /></td>
                              <td className="num muted mono">{t}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {((payload.top_performing_topics ?? []).length > 0 ||
                    (payload.worst_performing_topics ?? []).length > 0) && (
                    <div>
                      <div className="small faint" style={{ marginBottom: 6 }}>Topics</div>
                      <div className="stack" style={{ gap: 4 }}>
                        {(payload.top_performing_topics ?? []).map((t) => (
                          <div key={`up-${t}`} className="small">
                            <span style={{ color: "var(--green)" }}>↑</span> {t}
                          </div>
                        ))}
                        {(payload.worst_performing_topics ?? []).map((t) => (
                          <div key={`down-${t}`} className="small">
                            <span style={{ color: "var(--red)" }}>↓</span> {t}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Card>

            <Card title="Recommended adjustments">
              {payload == null || (payload.recommended_adjustments ?? []).length === 0 ? (
                <Empty icon="🛠" title="Nothing to adjust yet"
                  hint="Recommendations appear after the weekly analysis has data to chew on." />
              ) : (
                <>
                  <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8 }}>
                    {(payload.recommended_adjustments ?? []).map((r, i) => (
                      <li key={i} style={{ fontSize: 13 }}>{r}</li>
                    ))}
                  </ol>
                  {payload.audience_sentiment_summary && (
                    <div className="muted small"
                      style={{ marginTop: 14, paddingLeft: 12, borderLeft: "3px solid var(--border-strong)", fontStyle: "italic" }}>
                      {payload.audience_sentiment_summary}
                    </div>
                  )}
                </>
              )}
            </Card>
          </div>

          <Card title="Bandit leaderboard">
            {bandit.length === 0 ? (
              <Empty icon="🎰" title="No arms pulled yet"
                hint="Each content choice (hook style, tone, timing…) becomes an arm the bandit learns to favor." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Type</th><th>Choice</th><th>Platform</th>
                    <th className="num">Pulls</th><th>Avg reward</th>
                  </tr>
                </thead>
                <tbody>
                  {bandit.map((a) => (
                    <tr key={`${a.arm_type}-${a.arm_value}-${a.platform}`}>
                      <td><span className="pill mono">{a.arm_type}</span></td>
                      <td style={{ fontWeight: 600 }}>{a.arm_value}</td>
                      <td><PlatformChip platform={a.platform} /></td>
                      <td className="num">{a.pulls}</td>
                      <td style={{ width: 180 }}>
                        <div className="row" style={{ gap: 8 }}>
                          <div className="progress-track" style={{ flex: 1, marginTop: 0 }}>
                            <div className="progress-fill"
                              style={{ width: `${Math.min(Math.max(a.avg_reward, 0), 1) * 100}%` }} />
                          </div>
                          <span className="small muted" style={{ width: 44, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                            {pct(a.avg_reward)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}

      <div className="faint small">
        Mark rewards choices that earn engagement (Thompson sampling) and feeds your best posts back
        into generation as examples.
      </div>
    </>
  );
}
