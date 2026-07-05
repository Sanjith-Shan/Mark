// Settings: providers, connected accounts, quality/media/approval/schedule config, spend.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { ALL_PLATFORMS, PLATFORM_LABELS } from "../types";
import { Card, Empty, Pill, Spinner, Switch, fmt } from "../components/ui";

interface LlmSettings {
  text_model: string;
  judge_model: string;
  variants: number;
  self_critique: boolean;
  novelty_threshold: number;
}
interface MediaSettings {
  image_model: string;
  image_quality: string;
  video_model: string;
  video_fallback: string;
  video_duration: number;
  tts_voice: string;
}
interface SchedulingSettings {
  timezone: string;
  content_generation_cron: string;
  analytics_collection_cron: string;
  trend_monitoring_cron: string;
  feedback_loop_cron: string;
  posting_jitter_minutes: number;
}
interface ApprovalSettings {
  auto_approve: boolean;
  auto_approve_types: string[];
}
interface HumorSettings {
  enabled: boolean;
  candidates: number;
  candidates_light: number;
  min_violation: number;
  min_benignness: number;
  predictability_filter: boolean;
  model: string;
}
interface TrendsSettings {
  auto_react: boolean;
  react_threshold: number;
  min_velocity: number;
  max_reactions_per_day: number;
  react_platforms: string[];
  fast_poll_minutes: number;
  subreddits: string[];
}
interface LearningSettings {
  decay_half_life_days: number;
  holdout_pct: number;
  reward_maturity_hours: number;
  min_baseline_posts: number;
}
interface AllSettings {
  llm?: Partial<LlmSettings>;
  media?: Partial<MediaSettings>;
  scheduling?: Partial<SchedulingSettings>;
  approval?: Partial<ApprovalSettings>;
  humor?: Partial<HumorSettings>;
  trends?: Partial<TrendsSettings>;
  learning?: Partial<LearningSettings>;
  upload_post?: { profile_username?: string };
}
interface SettingsResp {
  settings: AllSettings;
  profile_username: string;
}
interface Connections {
  social_accounts?: Record<string, unknown>;
  mock?: boolean;
  error?: string;
}
interface CostRow {
  provider: string;
  operation: string;
  calls: number;
  usd: number;
  mocked_calls: number;
}
interface Costs {
  breakdown: CostRow[];
  by_day: { day: string; usd: number }[];
}

const PROVIDERS: { key: string; label: string; env: string; desc: string }[] = [
  { key: "openai", label: "OpenAI", env: "OPENAI_API_KEY", desc: "text, images, TTS, embeddings" },
  { key: "fal", label: "fal.ai", env: "FAL_KEY", desc: "AI video generation" },
  { key: "upload_post", label: "upload-post", env: "UPLOAD_POST_API_KEY", desc: "posting + analytics" },
  { key: "elevenlabs", label: "ElevenLabs", env: "ELEVENLABS_API_KEY", desc: "premium TTS (optional)" },
];

export default function Settings() {
  const [data, setData] = useState<SettingsResp | null>(null);
  const [connections, setConnections] = useState<Connections | null>(null);
  const [costs, setCosts] = useState<Costs | null>(null);

  const reload = useCallback(() => {
    api.get<SettingsResp>("/api/settings").then(setData).catch(() => {});
  }, []);

  useEffect(() => {
    reload();
    api.get<Connections>("/api/connections").then(setConnections).catch(() => {});
    api.get<Costs>("/api/costs?days=30").then(setCosts).catch(() => {});
  }, [reload]);

  if (!data) {
    return (
      <div className="row" style={{ justifyContent: "center", padding: 60 }}>
        <Spinner /> <span className="muted small">Loading settings…</span>
      </div>
    );
  }
  return <SettingsLoaded initial={data} connections={connections} costs={costs} reload={reload} />;
}

/** Per-section save helper: PATCH just that section, toast, re-GET. */
function useSectionSave(section: string, reload: () => void) {
  const { toast } = useGlobal();
  const [saving, setSaving] = useState(false);
  const save = async (payload: unknown) => {
    setSaving(true);
    try {
      await api.patch<SettingsResp>("/api/settings", { settings: { [section]: payload } });
      toast("Saved");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };
  return { saving, save };
}

function SaveBtn({ saving, onClick }: { saving: boolean; onClick: () => void }) {
  return (
    <button className="btn primary sm" disabled={saving} onClick={onClick}>
      {saving ? "Saving…" : "Save"}
    </button>
  );
}

function SettingsLoaded(props: {
  initial: SettingsResp;
  connections: Connections | null;
  costs: Costs | null;
  reload: () => void;
}) {
  const { initial, connections, costs, reload } = props;
  const { status } = useGlobal();
  const s = initial.settings;

  const [llm, setLlm] = useState<LlmSettings>({
    text_model: s.llm?.text_model ?? "",
    judge_model: s.llm?.judge_model ?? "",
    variants: s.llm?.variants ?? 1,
    self_critique: !!s.llm?.self_critique,
    novelty_threshold: s.llm?.novelty_threshold ?? 0.85,
  });
  const [media, setMedia] = useState<MediaSettings>({
    image_model: s.media?.image_model ?? "",
    image_quality: s.media?.image_quality ?? "medium",
    video_model: s.media?.video_model ?? "",
    video_fallback: s.media?.video_fallback ?? "",
    video_duration: s.media?.video_duration ?? 8,
    tts_voice: s.media?.tts_voice ?? "",
  });
  const [sched, setSched] = useState<SchedulingSettings>({
    timezone: s.scheduling?.timezone ?? "",
    content_generation_cron: s.scheduling?.content_generation_cron ?? "",
    analytics_collection_cron: s.scheduling?.analytics_collection_cron ?? "",
    trend_monitoring_cron: s.scheduling?.trend_monitoring_cron ?? "",
    feedback_loop_cron: s.scheduling?.feedback_loop_cron ?? "",
    posting_jitter_minutes: s.scheduling?.posting_jitter_minutes ?? 15,
  });
  const [approval, setApproval] = useState<ApprovalSettings>({
    auto_approve: !!s.approval?.auto_approve,
    auto_approve_types: s.approval?.auto_approve_types ?? [],
  });
  const [humor, setHumor] = useState<HumorSettings>({
    enabled: s.humor?.enabled ?? true,
    candidates: s.humor?.candidates ?? 6,
    candidates_light: s.humor?.candidates_light ?? 3,
    min_violation: s.humor?.min_violation ?? 0.5,
    min_benignness: s.humor?.min_benignness ?? 0.5,
    predictability_filter: s.humor?.predictability_filter ?? true,
    model: s.humor?.model ?? "",
  });
  const [trends, setTrends] = useState<TrendsSettings>({
    auto_react: !!s.trends?.auto_react,
    react_threshold: s.trends?.react_threshold ?? 0.55,
    min_velocity: s.trends?.min_velocity ?? 0,
    max_reactions_per_day: s.trends?.max_reactions_per_day ?? 2,
    react_platforms: s.trends?.react_platforms ?? [],
    fast_poll_minutes: s.trends?.fast_poll_minutes ?? 30,
    subreddits: s.trends?.subreddits ?? [],
  });
  const [learning, setLearning] = useState<LearningSettings>({
    decay_half_life_days: s.learning?.decay_half_life_days ?? 45,
    holdout_pct: s.learning?.holdout_pct ?? 0.1,
    reward_maturity_hours: s.learning?.reward_maturity_hours ?? 48,
    min_baseline_posts: s.learning?.min_baseline_posts ?? 3,
  });
  // Subreddits edit as a comma-separated string; parsed back on save.
  const [subredditsText, setSubredditsText] = useState(trends.subreddits.join(", "));
  const [profile, setProfile] = useState(
    s.upload_post?.profile_username ?? initial.profile_username ?? "",
  );

  const llmSave = useSectionSave("llm", reload);
  const mediaSave = useSectionSave("media", reload);
  const schedSave = useSectionSave("scheduling", reload);
  const approvalSave = useSectionSave("approval", reload);
  const humorSave = useSectionSave("humor", reload);
  const trendsSave = useSectionSave("trends", reload);
  const learningSave = useSectionSave("learning", reload);
  const profileSave = useSectionSave("upload_post", reload);

  const saveTrends = () => trendsSave.save({
    ...trends,
    subreddits: subredditsText.split(",").map((x) => x.trim().replace(/^r\//, "")).filter(Boolean),
  });

  return (
    <>
      <div className="grid cols-2" style={{ alignItems: "start" }}>
        {/* 1. Providers */}
        <Card title="Providers">
          <div className="stack" style={{ gap: 12 }}>
            {PROVIDERS.map((p) => {
              const mode = status?.providers?.[p.key] ?? "mock";
              return (
                <div className="row between" key={p.key}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{p.label}</div>
                    <div className="small faint">
                      {p.desc} · <span className="mono">{p.env}</span>
                    </div>
                  </div>
                  <Pill kind={mode}>{mode}</Pill>
                </div>
              );
            })}
            <p className="small faint" style={{ marginTop: 4 }}>
              Keys go in <code className="inline">.env</code>. Providers without a key run in mock
              mode — Mark still produces real local artifacts with zero spend.
            </p>
          </div>
        </Card>

        {/* 2. Connected accounts */}
        <Card title="Connected accounts">
          <div className="stack" style={{ gap: 12 }}>
            <ConnectedAccounts connections={connections} />
            <div className="field">
              <span className="field-label">upload-post profile username</span>
              <div className="row">
                <input className="input" value={profile} placeholder="my-profile"
                  onChange={(e) => setProfile(e.target.value)} />
                <SaveBtn saving={profileSave.saving}
                  onClick={() => profileSave.save({ profile_username: profile.trim() })} />
              </div>
              <span className="field-hint">Used in every upload-post.com API call.</span>
            </div>
          </div>
        </Card>

        {/* 3. Content quality */}
        <Card title="Content quality"
          action={<SaveBtn saving={llmSave.saving} onClick={() => llmSave.save(llm)} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Text model</span>
                <input className="input mono" value={llm.text_model}
                  onChange={(e) => setLlm({ ...llm, text_model: e.target.value })} />
              </div>
              <div className="field">
                <span className="field-label">Judge model</span>
                <input className="input mono" value={llm.judge_model}
                  onChange={(e) => setLlm({ ...llm, judge_model: e.target.value })} />
              </div>
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Variants per draft</span>
                <input className="input" type="number" min={1} max={4} value={llm.variants}
                  onChange={(e) => setLlm({
                    ...llm,
                    variants: Math.max(1, Math.min(4, Math.round(Number(e.target.value) || 1))),
                  })} />
                <span className="field-hint">Generate N candidates, keep the judge's pick.</span>
              </div>
              <div className="field">
                <span className="field-label">Novelty threshold</span>
                <input className="input" type="number" min={0.5} max={1} step={0.01}
                  value={llm.novelty_threshold}
                  onChange={(e) => setLlm({ ...llm, novelty_threshold: Number(e.target.value) })} />
                <span className="field-hint">Reject drafts too similar to recent posts (0.5–1).</span>
              </div>
            </div>
            <div className="row between">
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Self-critique pass</div>
                <div className="small faint">Writer reviews and revises its own draft before saving.</div>
              </div>
              <Switch checked={llm.self_critique}
                onChange={(v) => setLlm({ ...llm, self_critique: v })} />
            </div>
          </div>
        </Card>

        {/* 4. Media */}
        <Card title="Media"
          action={<SaveBtn saving={mediaSave.saving} onClick={() => mediaSave.save(media)} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Image model</span>
                <input className="input mono" value={media.image_model}
                  onChange={(e) => setMedia({ ...media, image_model: e.target.value })} />
              </div>
              <div className="field">
                <span className="field-label">Image quality</span>
                <select className="input" value={media.image_quality}
                  onChange={(e) => setMedia({ ...media, image_quality: e.target.value })}>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </div>
            </div>
            <div className="field">
              <span className="field-label">Video model</span>
              <input className="input mono" value={media.video_model}
                onChange={(e) => setMedia({ ...media, video_model: e.target.value })} />
            </div>
            <div className="field">
              <span className="field-label">Video fallback model</span>
              <input className="input mono" value={media.video_fallback}
                onChange={(e) => setMedia({ ...media, video_fallback: e.target.value })} />
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Video duration (s)</span>
                <input className="input" type="number" min={1} value={media.video_duration}
                  onChange={(e) => setMedia({ ...media, video_duration: Math.max(1, Math.round(Number(e.target.value) || 1)) })} />
              </div>
              <div className="field">
                <span className="field-label">TTS voice</span>
                <input className="input" value={media.tts_voice}
                  onChange={(e) => setMedia({ ...media, tts_voice: e.target.value })} />
              </div>
            </div>
          </div>
        </Card>

        {/* 5. Approval policy */}
        <Card title="Approval policy"
          action={<SaveBtn saving={approvalSave.saving} onClick={() => approvalSave.save(approval)} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="row between">
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Auto-approve everything</div>
                <div className="small" style={{ color: approval.auto_approve ? "var(--amber)" : "var(--text-faint)" }}>
                  {approval.auto_approve
                    ? "⚠ Content posts to your accounts without you reviewing it."
                    : "Off — every draft waits in the Studio for your review."}
                </div>
              </div>
              <Switch checked={approval.auto_approve}
                onChange={(v) => setApproval({ ...approval, auto_approve: v })} />
            </div>
            <div className="field">
              <span className="field-label">Auto-approve these types only</span>
              <div className="grid cols-4" style={{ gap: 8 }}>
                {["text", "image", "carousel", "video"].map((t) => {
                  const checked = approval.auto_approve_types.includes(t);
                  return (
                    <div key={t} className={`checkbox-row ${checked ? "checked" : ""}`}
                      onClick={() => setApproval({
                        ...approval,
                        auto_approve_types: checked
                          ? approval.auto_approve_types.filter((x) => x !== t)
                          : [...approval.auto_approve_types, t],
                      })}>
                      <input type="checkbox" checked={checked} readOnly style={{ pointerEvents: "none" }} />
                      <span style={{ fontSize: 13 }}>{t}</span>
                    </div>
                  );
                })}
              </div>
              <span className="field-hint">
                Applies when the master switch is off: only these content types skip review.
              </span>
            </div>
          </div>
        </Card>

        {/* 6. Schedule */}
        <Card title="Schedule"
          action={<SaveBtn saving={schedSave.saving} onClick={() => schedSave.save(sched)} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Timezone</span>
                <input className="input" value={sched.timezone} placeholder="America/Los_Angeles"
                  onChange={(e) => setSched({ ...sched, timezone: e.target.value })} />
              </div>
              <div className="field">
                <span className="field-label">Posting jitter (min)</span>
                <input className="input" type="number" min={0} value={sched.posting_jitter_minutes}
                  onChange={(e) => setSched({ ...sched, posting_jitter_minutes: Math.max(0, Math.round(Number(e.target.value) || 0)) })} />
              </div>
            </div>
            {([
              ["content_generation_cron", "Content generation"],
              ["analytics_collection_cron", "Analytics collection"],
              ["trend_monitoring_cron", "Trend monitoring"],
              ["feedback_loop_cron", "Learning loop"],
            ] as const).map(([key, label]) => (
              <div className="field" key={key}>
                <span className="field-label">{label}</span>
                <input className="input mono" value={sched[key]}
                  onChange={(e) => setSched({ ...sched, [key]: e.target.value })} />
              </div>
            ))}
            <p className="small faint">
              Cron format: <span className="mono">minute hour day month weekday</span> — e.g.{" "}
              <code className="inline">0 6 * * *</code> is daily at 6:00.
            </p>
          </div>
        </Card>

        {/* 7. Humor engine */}
        <Card title="Humor engine"
          action={<SaveBtn saving={humorSave.saving} onClick={() => humorSave.save(humor)} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="row between">
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Humor engine</div>
                <div className="small faint">Scaffold, gate, and pick jokes for humor-led strategies.</div>
              </div>
              <Switch checked={humor.enabled}
                onChange={(v) => setHumor({ ...humor, enabled: v })} />
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Joke candidates</span>
                <input className="input" type="number" min={1} max={12} value={humor.candidates}
                  onChange={(e) => setHumor({ ...humor, candidates: Math.max(1, Math.round(Number(e.target.value) || 1)) })} />
                <span className="field-hint">Candidates per piece for full-humor strategies.</span>
              </div>
              <div className="field">
                <span className="field-label">Candidates (light humor)</span>
                <input className="input" type="number" min={1} max={12} value={humor.candidates_light}
                  onChange={(e) => setHumor({ ...humor, candidates_light: Math.max(1, Math.round(Number(e.target.value) || 1)) })} />
              </div>
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Min violation</span>
                <input className="input" type="number" min={0} max={1} step={0.05} value={humor.min_violation}
                  onChange={(e) => setHumor({ ...humor, min_violation: Number(e.target.value) })} />
                <span className="field-hint">Below this the joke is bland corporate safety (0–1).</span>
              </div>
              <div className="field">
                <span className="field-label">Min benignness</span>
                <input className="input" type="number" min={0} max={1} step={0.05} value={humor.min_benignness}
                  onChange={(e) => setHumor({ ...humor, min_benignness: Number(e.target.value) })} />
                <span className="field-hint">Below this the joke punches wrong (0–1).</span>
              </div>
            </div>
            <div className="row between">
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Predictability filter</div>
                <div className="small faint">Kill jokes whose punchline can be guessed from the setup.</div>
              </div>
              <Switch checked={humor.predictability_filter}
                onChange={(v) => setHumor({ ...humor, predictability_filter: v })} />
            </div>
            <div className="field">
              <span className="field-label">Humor model</span>
              <input className="input mono" value={humor.model} placeholder="(empty = text model)"
                onChange={(e) => setHumor({ ...humor, model: e.target.value })} />
              <span className="field-hint">Override model for joke generation. Empty = the main text model.</span>
            </div>
          </div>
        </Card>

        {/* 8. Trend reaction */}
        <Card title="Trend reaction"
          action={<SaveBtn saving={trendsSave.saving} onClick={saveTrends} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="row between">
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Auto-react to hot trends</div>
                <div className="small" style={{ color: trends.auto_react ? "var(--amber)" : "var(--text-faint)" }}>
                  {trends.auto_react
                    ? "⚡ Mark drafts trend-riding content the moment a hot trend appears — drafts still wait for approval unless auto-approve is on."
                    : "Off — ride trends manually from the Trends page."}
                </div>
              </div>
              <Switch checked={trends.auto_react}
                onChange={(v) => setTrends({ ...trends, auto_react: v })} />
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">React threshold</span>
                <input className="input" type="number" min={0} max={1} step={0.05} value={trends.react_threshold}
                  onChange={(e) => setTrends({ ...trends, react_threshold: Number(e.target.value) })} />
                <span className="field-hint">Min trend score (relevance × popularity) to count as “hot”.</span>
              </div>
              <div className="field">
                <span className="field-label">Min velocity</span>
                <input className="input" type="number" step={0.01} value={trends.min_velocity}
                  onChange={(e) => setTrends({ ...trends, min_velocity: Number(e.target.value) })} />
                <span className="field-hint">Skip falling trends — a late meme is brand cringe.</span>
              </div>
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Max reactions / day</span>
                <input className="input" type="number" min={0} value={trends.max_reactions_per_day}
                  onChange={(e) => setTrends({ ...trends, max_reactions_per_day: Math.max(0, Math.round(Number(e.target.value) || 0)) })} />
                <span className="field-hint">Per campaign — don't trend-jack everything.</span>
              </div>
              <div className="field">
                <span className="field-label">Fast poll (min)</span>
                <input className="input" type="number" min={5} value={trends.fast_poll_minutes}
                  onChange={(e) => setTrends({ ...trends, fast_poll_minutes: Math.max(5, Math.round(Number(e.target.value) || 5)) })} />
                <span className="field-hint">Reddit rising / Bluesky / Google RSS poll interval.</span>
              </div>
            </div>
            <div className="field">
              <span className="field-label">React on these platforms</span>
              <div className="grid cols-3" style={{ gap: 8 }}>
                {ALL_PLATFORMS.map((p) => {
                  const checked = trends.react_platforms.includes(p);
                  return (
                    <div key={p} className={`checkbox-row ${checked ? "checked" : ""}`}
                      onClick={() => setTrends({
                        ...trends,
                        react_platforms: checked
                          ? trends.react_platforms.filter((x) => x !== p)
                          : [...trends.react_platforms, p],
                      })}>
                      <input type="checkbox" checked={checked} readOnly style={{ pointerEvents: "none" }} />
                      <span style={{ fontSize: 13 }}>{PLATFORM_LABELS[p] ?? p}</span>
                    </div>
                  );
                })}
              </div>
              <span className="field-hint">None selected = all enabled platforms.</span>
            </div>
            <div className="field">
              <span className="field-label">Subreddits <span className="faint">(comma-separated)</span></span>
              <input className="input" value={subredditsText} placeholder="recruitinghell, internships, jobs"
                onChange={(e) => setSubredditsText(e.target.value)} />
              <span className="field-hint">Niche subs watched for early trend signal and content material.</span>
            </div>
          </div>
        </Card>

        {/* 9. Learning */}
        <Card title="Learning"
          action={<SaveBtn saving={learningSave.saving} onClick={() => learningSave.save(learning)} />}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Evidence half-life (days)</span>
                <input className="input" type="number" min={0} value={learning.decay_half_life_days}
                  onChange={(e) => setLearning({ ...learning, decay_half_life_days: Math.max(0, Number(e.target.value) || 0) })} />
                <span className="field-hint">Old bandit evidence decays — 0 = never decay.</span>
              </div>
              <div className="field">
                <span className="field-label">Holdout share</span>
                <input className="input" type="number" min={0} max={0.5} step={0.01} value={learning.holdout_pct}
                  onChange={(e) => setLearning({ ...learning, holdout_pct: Number(e.target.value) })} />
                <span className="field-hint">Share of generations using a random policy — the control group that proves learning lifts (0–0.5).</span>
              </div>
            </div>
            <div className="grid cols-2">
              <div className="field">
                <span className="field-label">Reward maturity (hours)</span>
                <input className="input" type="number" min={0} value={learning.reward_maturity_hours}
                  onChange={(e) => setLearning({ ...learning, reward_maturity_hours: Math.max(0, Math.round(Number(e.target.value) || 0)) })} />
                <span className="field-hint">A post is rewarded exactly once, after this age.</span>
              </div>
              <div className="field">
                <span className="field-label">Min baseline posts</span>
                <input className="input" type="number" min={1} value={learning.min_baseline_posts}
                  onChange={(e) => setLearning({ ...learning, min_baseline_posts: Math.max(1, Math.round(Number(e.target.value) || 1)) })} />
                <span className="field-hint">Measured posts a platform needs before rewards flow.</span>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* 9. Spend */}
      <SpendCard costs={costs} />
    </>
  );
}

function ConnectedAccounts({ connections }: { connections: Connections | null }) {
  if (!connections) {
    return <div className="row"><Spinner /><span className="small muted">Checking accounts…</span></div>;
  }
  if (connections.error) {
    return <div className="small" style={{ color: "var(--red)" }}>{connections.error}</div>;
  }
  const entries = Object.entries(connections.social_accounts ?? {});
  if (connections.mock || entries.length === 0) {
    return (
      <p className="small faint">
        {connections.mock
          ? <>Running in mock mode — connected accounts appear here once <span className="mono">UPLOAD_POST_API_KEY</span> is set and your socials are linked on upload-post.com.</>
          : "No social accounts connected yet. Link them from your upload-post.com dashboard."}
      </p>
    );
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      {entries.map(([platform, v]) => {
        const username = accountName(v);
        const connected = v != null && v !== false && v !== "";
        return (
          <div className="row between" key={platform}>
            <div className="row">
              <span className={`dot ${connected ? "green" : "amber"}`} />
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                {PLATFORM_LABELS[platform] ?? platform}
              </span>
            </div>
            <span className="small muted mono">
              {username ?? (connected ? "connected" : "not connected")}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function accountName(v: unknown): string | null {
  if (typeof v === "string" && v) return v;
  if (v != null && typeof v === "object") {
    const o = v as Record<string, unknown>;
    for (const k of ["username", "display_name", "name", "handle"]) {
      const val = o[k];
      if (typeof val === "string" && val) return val;
    }
  }
  return null;
}

function SpendCard({ costs }: { costs: Costs | null }) {
  if (!costs) {
    return (
      <Card title="Spend · last 30 days">
        <div className="row"><Spinner /><span className="small muted">Loading costs…</span></div>
      </Card>
    );
  }

  const byProvider = new Map<string, { calls: number; usd: number; mocked: number }>();
  for (const row of costs.breakdown) {
    const cur = byProvider.get(row.provider) ?? { calls: 0, usd: 0, mocked: 0 };
    cur.calls += row.calls;
    cur.usd += row.usd;
    cur.mocked += row.mocked_calls;
    byProvider.set(row.provider, cur);
  }
  const rows = [...byProvider.entries()].sort(([, a], [, b]) => b.usd - a.usd);
  const totalUsd = rows.reduce((s, [, v]) => s + v.usd, 0);
  const totalMocked = rows.reduce((s, [, v]) => s + v.mocked, 0);

  return (
    <Card title="Spend · last 30 days"
      action={<span className="small muted">${totalUsd.toFixed(2)} total · {fmt(totalMocked)} mocked calls ($0)</span>}>
      {rows.length === 0 ? (
        <Empty icon="💸" title="No API usage yet"
          hint="Costs are tracked per provider and operation as Mark works." />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th className="num">Calls</th>
              <th className="num">Mocked</th>
              <th className="num">Spend</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([provider, v]) => (
              <tr key={provider}>
                <td style={{ fontWeight: 600 }}>{provider}</td>
                <td className="num">{fmt(v.calls)}</td>
                <td className="num">{fmt(v.mocked)}</td>
                <td className="num">${v.usd.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
