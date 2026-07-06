// Learn — insights, bandit leaderboard, experiments, and the self-improvement loop.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { Experiment, ExperimentReport, Insights } from "../types";
import { Card, Empty, Pill, PlatformChip, Stat, StatusPill, pct, timeAgo } from "../components/ui";

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

      <div className="grid cols-3" data-tour="learn-stats">
        <Card><Stat value={data?.winners ?? 0} label="Winners indexed"
          sub="top posts reused as examples" /></Card>
        <Card><Stat value={bandit.length} label="Bandit arms tried"
          sub="choices Mark is optimizing" /></Card>
        <Card><Stat
          value={data?.insights?.created_at ? timeAgo(data.insights.created_at) : "never"}
          label="Last analysis" /></Card>
        {data?.holdout_lift != null && (
          <Card><Stat
            value={
              <span style={{ color: data.holdout_lift.lift_pct >= 0 ? "var(--green)" : "var(--red)" }}>
                {data.holdout_lift.lift_pct >= 0 ? "+" : ""}{data.holdout_lift.lift_pct}%
              </span>
            }
            label="Learning lift vs random"
            sub={`${data.holdout_lift.bandit_posts} bandit / ${data.holdout_lift.holdout_posts} holdout posts`} /></Card>
        )}
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

          <Card title="Bandit leaderboard" dataTour="learn-bandit">
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

      <ExperimentsSection />

      <div className="faint small">
        Mark rewards choices that earn engagement (Thompson sampling) and feeds your best posts back
        into generation as examples.
      </div>
    </>
  );
}

/* ---------- experiments (campaigns as A/B variants) ---------- */

function ExperimentsSection() {
  const { campaigns, toast } = useGlobal();
  const [reports, setReports] = useState<ExperimentReport[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [variantIds, setVariantIds] = useState<string[]>([]);

  const load = useCallback(() => {
    api.get<Experiment[]>("/api/experiments")
      .then((exps) =>
        Promise.all(exps.map((e) => api.get<ExperimentReport>(`/api/experiments/${e.id}/report`))))
      .then(setReports)
      .catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleVariant = (id: string) =>
    setVariantIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));

  const create = async () => {
    try {
      await api.post<Experiment>("/api/experiments", {
        name: name.trim(), hypothesis: hypothesis.trim(), campaign_ids: variantIds,
      });
      toast("Experiment started");
      setCreating(false);
      setName(""); setHypothesis(""); setVariantIds([]);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Create failed", "error");
    }
  };

  const conclude = async (r: ExperimentReport) => {
    const leaderName = r.variants.find((v) => v.campaign_id === r.leader)?.campaign_name;
    const conclusion = window.prompt(
      "Conclusion — what did this experiment prove?",
      leaderName ? `${leaderName} wins on ${r.metric}` : "");
    if (conclusion == null) return;
    try {
      await api.post<Experiment>(`/api/experiments/${r.id}/conclude`, { conclusion });
      toast("Experiment concluded");
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Conclude failed", "error");
    }
  };

  return (
    <Card title="Experiments · A/B test lab" dataTour="learn-experiments"
      action={
        <button className="btn sm" onClick={() => setCreating((v) => !v)}>
          {creating ? "Cancel" : "+ New experiment"}
        </button>
      }>
      <div className="stack" style={{ gap: 14 }}>
        {creating && (
          <div className="stack" style={{
            gap: 10, border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 12,
          }}>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Name</span>
                <input className="input" value={name} placeholder="Summer hook test"
                  onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="field">
                <span className="field-label">Hypothesis</span>
                <input className="input" value={hypothesis}
                  placeholder="e.g. edgy voice out-engages clean voice"
                  onChange={(e) => setHypothesis(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <span className="field-label">Variant campaigns <span className="faint">(pick 2+)</span></span>
              <div className="grid cols-3" style={{ gap: 8 }}>
                {campaigns.map((c) => {
                  const checked = variantIds.includes(c.id);
                  return (
                    <div key={c.id} className={`checkbox-row ${checked ? "checked" : ""}`}
                      onClick={() => toggleVariant(c.id)}>
                      <input type="checkbox" checked={checked} readOnly style={{ pointerEvents: "none" }} />
                      <span style={{ fontSize: 13 }}>{c.name}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button className="btn primary sm" disabled={!name.trim() || variantIds.length < 2}
                onClick={create}>Start experiment</button>
            </div>
          </div>
        )}

        {reports.length === 0 && !creating ? (
          <Empty icon="🧪" title="No experiments yet"
            hint="Run two campaign variants side by side and let the numbers pick the winner." />
        ) : (
          reports.map((r) => (
            <div key={r.id} className="stack" style={{
              gap: 8, border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 12,
            }}>
              <div className="row between">
                <div className="row wrap">
                  <span style={{ fontWeight: 700, fontSize: 13.5 }}>{r.name}</span>
                  <StatusPill status={r.status} />
                  <Pill>{r.metric}</Pill>
                </div>
                {r.status === "running" && (
                  <button className="btn sm" onClick={() => conclude(r)}>Conclude</button>
                )}
              </div>
              {r.hypothesis && <div className="small muted">Hypothesis: {r.hypothesis}</div>}
              <table className="table">
                <thead>
                  <tr>
                    <th>Variant</th><th className="num">Posts</th>
                    <th className="num">Avg engagement</th><th className="num">Avg reward</th>
                    <th className="num">Views</th><th className="num">Likes</th>
                  </tr>
                </thead>
                <tbody>
                  {r.variants.map((v) => (
                    <tr key={v.campaign_id}>
                      <td style={{ fontWeight: 600 }}>
                        {v.campaign_name}
                        {r.leader === v.campaign_id && <Pill kind="accent"> 🏆 leader</Pill>}
                      </td>
                      <td className="num">{v.posts}</td>
                      <td className="num">{pct(v.avg_engagement)}</td>
                      <td className="num">{v.avg_reward != null ? pct(v.avg_reward) : "—"}</td>
                      <td className="num">{v.views}</td>
                      <td className="num">{v.likes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {r.conclusion && (
                <div className="small muted" style={{
                  paddingLeft: 12, borderLeft: "3px solid var(--border-strong)", fontStyle: "italic",
                }}>
                  {r.conclusion}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
