// Content Studio — the review/edit/approve queue. The most important page of Mark.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { ALL_PLATFORMS, Content, MediaItem, PLATFORM_COLORS, PLATFORM_LABELS, PostRecord } from "../types";
import { Empty, Modal, Pill, PlatformChip, Spinner, StatusPill, fmt, parseUtc, pct, timeAgo } from "../components/ui";

const STATUSES = ["draft", "approved", "posted", "failed", "rejected"] as const;
type Status = (typeof STATUSES)[number];
const STATUS_LABELS: Record<Status, string> = {
  draft: "Drafts", approved: "Approved", posted: "Posted", failed: "Failed", rejected: "Rejected",
};
const TYPE_GLYPHS: Record<string, string> = {
  text: "📝", thread: "🧵", video: "🎬", image: "🖼", carousel: "🎠",
};

export default function Studio() {
  const { status, campaigns, contentVersion, toast } = useGlobal();
  const [tab, setTab] = useState<Status>("draft");
  const [campaign, setCampaign] = useState("");
  const [platform, setPlatform] = useState("");
  const [items, setItems] = useState<Content[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState<{ id: number; reject?: boolean } | null>(null);
  const [genOpen, setGenOpen] = useState(false);

  const load = useCallback(() => {
    const qs = new URLSearchParams({ status: tab, limit: "100" });
    if (campaign) qs.set("campaign", campaign);
    if (platform) qs.set("platform", platform);
    api.get<Content[]>(`/api/content?${qs.toString()}`)
      .then((rows) => { setItems(rows); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tab, campaign, platform]);

  useEffect(() => { setLoading(true); load(); }, [load]);
  useEffect(() => { load(); }, [contentVersion, load]);

  const quickApprove = async (id: number) => {
    try {
      await api.post<Content>(`/api/content/${id}/approve`);
      toast(`#${id} approved`);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Approve failed", "error");
    }
  };

  return (
    <>
      <div className="row wrap between">
        <div className="tabs">
          {STATUSES.map((s) => (
            <button key={s} className={`tab ${tab === s ? "active" : ""}`} onClick={() => setTab(s)}>
              {STATUS_LABELS[s]}
              <span className="count">{status?.counts?.[s] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="row">
          <select className="input" style={{ width: 180 }} value={campaign}
            onChange={(e) => setCampaign(e.target.value)}>
            <option value="">All campaigns</option>
            {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="input" style={{ width: 150 }} value={platform}
            onChange={(e) => setPlatform(e.target.value)}>
            <option value="">All platforms</option>
            {ALL_PLATFORMS.map((p) => <option key={p} value={p}>{PLATFORM_LABELS[p] ?? p}</option>)}
          </select>
          <button className="btn primary" onClick={() => setGenOpen(true)}>✨ Generate</button>
        </div>
      </div>

      {loading ? (
        <div className="row" style={{ justifyContent: "center", padding: 40 }}><Spinner /></div>
      ) : items.length === 0 ? (
        <Empty icon={tab === "draft" ? "✍️" : "◎"} title={`No ${STATUS_LABELS[tab].toLowerCase()}`}
          hint={tab === "draft" ? "Generate content and it lands here for review." : undefined}
          action={tab === "draft"
            ? <button className="btn primary" onClick={() => setGenOpen(true)}>✨ Generate content</button>
            : undefined} />
      ) : (
        <div className="queue-grid">
          {items.map((c) => (
            <QueueCard key={c.id} content={c}
              onOpen={() => setDrawer({ id: c.id })}
              onApprove={() => quickApprove(c.id)}
              onReject={() => setDrawer({ id: c.id, reject: true })} />
          ))}
        </div>
      )}

      {drawer && (
        <Drawer id={drawer.id} initialReject={drawer.reject ?? false}
          onClose={() => setDrawer(null)} onChanged={load} />
      )}
      {genOpen && <GenerateModal onClose={() => setGenOpen(false)} />}
    </>
  );
}

/* ---------- queue card ---------- */

function QueueCard(props: {
  content: Content;
  onOpen: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  const c = props.content;
  const media = c.media?.[0];
  const ctx = c.strategy_context;
  return (
    <div className="content-card" onClick={props.onOpen}>
      <div className="content-thumb">
        <Thumb media={media} platform={c.platform} contentType={c.content_type} />
        <div className="thumb-badges">
          <StatusPill status={c.status} />
          <Pill>{c.content_type}</Pill>
        </div>
      </div>
      <div className="content-body">
        {c.hook && <div className="content-hook">{c.hook}</div>}
        {c.caption && <div className="content-caption">{c.caption}</div>}
        {(ctx?.strategy_name || ctx?.character || ctx?.forced_trend || ctx?.emotional_target || c.expires_at) && (
          <div className="row wrap" style={{ gap: 5 }}>
            {ctx?.strategy_name && (
              <Pill kind="accent">{ctx.strategy_name}{ctx.episode ? ` · ep ${ctx.episode}` : ""}</Pill>
            )}
            {ctx?.emotional_target && <Pill>{ctx.emotional_target.replace(/_/g, " ")}</Pill>}
            {ctx?.character && <Pill>🎭 {ctx.character}</Pill>}
            {ctx?.forced_trend && (
              <Pill><span title={`trend ride: ${ctx.forced_trend}`}>🏄 trend ride</span></Pill>
            )}
            <ExpiryChip expiresAt={c.expires_at} />
          </div>
        )}
        <div className="content-foot">
          <PlatformChip platform={c.platform} />
          <div className="row" style={{ gap: 6 }}>
            <span className="faint small">{timeAgo(c.created_at)}</span>
            {c.status === "draft" && (
              <>
                <button className="btn success sm" title="Approve"
                  onClick={(e) => { e.stopPropagation(); props.onApprove(); }}>✓</button>
                <button className="btn danger sm" title="Reject"
                  onClick={(e) => { e.stopPropagation(); props.onReject(); }}>✕</button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Thumb({ media, platform, contentType }: { media?: MediaItem; platform: string; contentType: string }) {
  if (media?.kind === "video") return <video src={media.url} muted preload="metadata" />;
  if (media?.kind === "image") return <img src={media.url} alt="" />;
  const color = PLATFORM_COLORS[platform] ?? "#666";
  return (
    <div style={{
      width: "100%", height: "100%", display: "grid", placeItems: "center",
      background: `linear-gradient(135deg, ${color}22, ${color}08)`,
    }}>
      <span style={{ fontSize: 34, opacity: 0.8 }}>{TYPE_GLYPHS[contentType] ?? "📝"}</span>
    </div>
  );
}

/** Trend-content TTL chip: countdown while the window is open, "expired" after. */
function ExpiryChip({ expiresAt }: { expiresAt?: string | null }) {
  if (!expiresAt) return null;
  const ms = parseUtc(expiresAt).getTime() - Date.now();
  if (ms <= 0) return <Pill kind="failed">trend window expired</Pill>;
  return <Pill kind="draft">⏳ trend window closes in {durationShort(ms)}</Pill>;
}

function durationShort(ms: number): string {
  const mins = Math.ceil(ms / 60_000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.round(ms / 3_600_000);
  if (hours < 48) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

/* ---------- detail drawer ---------- */

interface EditForm {
  hook: string;
  caption: string;
  hashtags: string;
  script: string;
  video_prompt: string;
  image_prompt: string;
  cta: string;
  alt_text: string;
  slide_texts: string[];
  image_prompts: string[];
}

function formFrom(c: Content): EditForm {
  return {
    hook: c.hook ?? c.draft?.hook ?? "",
    caption: c.caption ?? "",
    hashtags: (c.hashtags ?? []).join(" "),
    script: c.draft?.script ?? "",
    video_prompt: c.draft?.video_prompt ?? "",
    image_prompt: c.draft?.image_prompt ?? "",
    cta: c.draft?.cta ?? "",
    alt_text: c.draft?.alt_text ?? "",
    slide_texts: c.draft?.slide_texts ?? [],
    image_prompts: c.draft?.image_prompts ?? [],
  };
}

function Drawer(props: { id: number; initialReject: boolean; onClose: () => void; onChanged: () => void }) {
  const { contentVersion, runJob, toast } = useGlobal();
  const [detail, setDetail] = useState<Content | null>(null);
  const [form, setForm] = useState<EditForm | null>(null);
  const [baseline, setBaseline] = useState("");
  const [saving, setSaving] = useState(false);
  const [rewriteText, setRewriteText] = useState("");
  const [rejecting, setRejecting] = useState(props.initialReject);
  const [rejectText, setRejectText] = useState("");
  const [selectedImg, setSelectedImg] = useState(0);

  const dirty = form != null && JSON.stringify(form) !== baseline;

  const applyDetail = useCallback((c: Content, resetForm: boolean) => {
    setDetail(c);
    if (resetForm) {
      const f = formFrom(c);
      setForm(f);
      setBaseline(JSON.stringify(f));
    }
  }, []);

  const refetch = useCallback((resetForm: boolean) => {
    api.get<Content>(`/api/content/${props.id}`)
      .then((c) => applyDetail(c, resetForm))
      .catch((e) => toast(e instanceof Error ? e.message : "Failed to load content", "error"));
  }, [props.id, applyDetail, toast]);

  useEffect(() => { refetch(true); }, [props.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // Refresh detail when content changes server-side, but don't clobber in-progress edits.
  useEffect(() => { if (contentVersion > 0) refetch(!dirty); }, [contentVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof EditForm>(key: K, value: EditForm[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  const save = async () => {
    if (!detail || !form) return;
    setSaving(true);
    // Send raw strings — the backend treats null as "not provided", so a
    // cleared field must go over the wire as "" to actually clear. Hashtags
    // keep their '#' (posting joins them verbatim into the caption).
    const body: Record<string, unknown> = {
      hook: form.hook,
      caption: form.caption,
      hashtags: form.hashtags.split(/\s+/).filter(Boolean)
        .map((t) => (t.startsWith("#") ? t : `#${t}`)),
      cta: form.cta,
      alt_text: form.alt_text,
    };
    if (detail.content_type === "video") {
      body.script = form.script;
      body.video_prompt = form.video_prompt;
      body.image_prompt = form.image_prompt;
    } else if (detail.content_type === "carousel") {
      body.slide_texts = form.slide_texts;
      body.image_prompts = form.image_prompts;
    } else {
      body.image_prompt = form.image_prompt;
    }
    try {
      const updated = await api.patch<Content>(`/api/content/${detail.id}`, body);
      applyDetail(updated, true);
      toast("Saved");
      props.onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const approve = async () => {
    if (!detail) return;
    try {
      const updated = await api.post<Content>(`/api/content/${detail.id}/approve`);
      applyDetail(updated, true);
      toast("Approved");
      props.onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Approve failed", "error");
    }
  };

  const reject = async () => {
    if (!detail) return;
    try {
      const updated = await api.post<Content>(`/api/content/${detail.id}/reject`, { feedback: rejectText });
      applyDetail(updated, true);
      setRejecting(false);
      toast("Rejected — feedback saved for learning");
      props.onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Reject failed", "error");
    }
  };

  const postNow = () => runJob(() => api.post<{ job_id: string }>(`/api/content/${props.id}/post`));
  const rewrite = () => {
    runJob(() => api.post<{ job_id: string }>(`/api/content/${props.id}/rewrite`,
      rewriteText.trim() ? { instruction: rewriteText.trim() } : {}));
    toast("Rewriting — watch the job toast");
    setRewriteText("");
  };
  const regenMedia = () => {
    runJob(() => api.post<{ job_id: string }>(`/api/content/${props.id}/regenerate-media`));
    toast("Regenerating media — watch the job toast");
  };

  const ctx = detail?.strategy_context;
  const images = useMemo(() => (detail?.media ?? []).filter((m) => m.kind === "image"), [detail]);
  const video = (detail?.media ?? []).find((m) => m.kind === "video");
  const imgIdx = Math.min(selectedImg, Math.max(images.length - 1, 0));

  return (
    <>
      <div className="drawer-overlay" onMouseDown={props.onClose} />
      <div className="drawer">
        {!detail || !form ? (
          <div className="row" style={{ justifyContent: "center", padding: 40 }}><Spinner /></div>
        ) : (
          <div className="stack" style={{ gap: 16 }}>
            {/* header */}
            <div className="row between">
              <div className="row wrap">
                <StatusPill status={detail.status} />
                <PlatformChip platform={detail.platform} />
                <Pill>{detail.content_type}</Pill>
                <ExpiryChip expiresAt={detail.expires_at} />
                <span className="faint small">#{detail.id} · {timeAgo(detail.created_at)}</span>
              </div>
              <button className="btn ghost sm" onClick={props.onClose}>✕</button>
            </div>

            {detail.error && (
              <div style={{
                background: "var(--red-soft)", border: "1px solid rgba(248,113,113,.35)",
                borderRadius: "var(--radius-sm)", padding: "10px 12px", fontSize: 13, color: "var(--red)",
              }}>{detail.error}</div>
            )}
            {detail.status === "rejected" && detail.rejection_feedback && (
              <div className="small muted">Rejection feedback: “{detail.rejection_feedback}”</div>
            )}

            {/* media preview */}
            {video ? (
              <div className="media-frame"><video src={video.url} controls /></div>
            ) : images.length > 1 ? (
              <div className="stack">
                <div className="media-frame"><img src={images[imgIdx].url} alt={images[imgIdx].name} /></div>
                <div className="carousel-strip">
                  {images.map((m, i) => (
                    <img key={m.url} src={m.url} alt={m.name} onClick={() => setSelectedImg(i)}
                      style={i === imgIdx ? { borderColor: "var(--accent)" } : undefined} />
                  ))}
                </div>
              </div>
            ) : images.length === 1 ? (
              <div className="media-frame"><img src={images[0].url} alt={images[0].name} /></div>
            ) : null}

            {/* why this content */}
            {ctx && (ctx.topic || ctx.reasoning || ctx.strategy_name) && (
              <div style={{
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)", padding: "10px 12px",
              }}>
                <div className="field-label" style={{ marginBottom: 6 }}>Why this content</div>
                <div className="small muted stack" style={{ gap: 3 }}>
                  {ctx.strategy_name && (
                    <div>
                      <span className="faint">strategy</span> — {ctx.strategy_name}
                      {ctx.episode ? ` · episode ${ctx.episode}` : ""}
                    </div>
                  )}
                  {ctx.emotional_target && <div><span className="faint">emotional target</span> — {ctx.emotional_target.replace(/_/g, " ")}</div>}
                  {ctx.humor_mechanism && (
                    <div>
                      <span className="faint">humor</span> — {ctx.humor_mechanism}
                      {ctx.humor_persona ? ` · as ${ctx.humor_persona}` : ""}
                    </div>
                  )}
                  {ctx.character && <div><span className="faint">character</span> — 🎭 {ctx.character}</div>}
                  {ctx.forced_trend && <div><span className="faint">trend ride</span> — {ctx.forced_trend}</div>}
                  {ctx.topic && <div><span className="faint">topic</span> — {ctx.topic}</div>}
                  {ctx.angle && <div><span className="faint">angle</span> — {ctx.angle}</div>}
                  {ctx.hook_style && <div><span className="faint">hook style</span> — {ctx.hook_style}</div>}
                  {ctx.tone && <div><span className="faint">tone</span> — {ctx.tone}</div>}
                  {ctx.trend_tie_in && <div><span className="faint">trend tie-in</span> — {ctx.trend_tie_in}</div>}
                  {ctx.reasoning && <div className="faint" style={{ marginTop: 4 }}>{ctx.reasoning}</div>}
                </div>
              </div>
            )}

            {/* editing */}
            <EditableFields contentType={detail.content_type} form={form} set={set} />

            {dirty && (
              <div className="row">
                <button className="btn primary" disabled={saving} onClick={save}>
                  {saving ? <Spinner /> : "Save edits"}
                </button>
                <button className="btn ghost" onClick={() => { const f = formFrom(detail); setForm(f); setBaseline(JSON.stringify(f)); }}>
                  Discard
                </button>
              </div>
            )}

            {/* AI actions */}
            {detail.status !== "posted" && (
              <div className="row wrap" style={{ gap: 8 }}>
                <input className="input" style={{ flex: 1, minWidth: 180 }}
                  placeholder="Optional instruction, e.g. “punchier hook”"
                  value={rewriteText} onChange={(e) => setRewriteText(e.target.value)} />
                <button className="btn" onClick={rewrite}>↻ Rewrite with AI</button>
                <button className="btn" onClick={regenMedia}>🖼 Regenerate media</button>
              </div>
            )}

            {/* posted: performance */}
            {detail.status === "posted" && <PostedSection posts={detail.posts ?? []} />}

            {/* sticky actions */}
            <div style={{
              position: "sticky", bottom: -24, marginBottom: -24, marginTop: 4,
              background: "var(--bg-raised)", borderTop: "1px solid var(--border)",
              padding: "12px 0 20px",
            }}>
              {detail.status === "draft" && !rejecting && (
                <div className="row">
                  <button className="btn success" onClick={approve}>✓ Approve</button>
                  <button className="btn danger" onClick={() => setRejecting(true)}>✕ Reject</button>
                </div>
              )}
              {detail.status === "draft" && rejecting && (
                <div className="stack" style={{ gap: 8 }}>
                  <textarea className="input" rows={2} autoFocus
                    placeholder="What's wrong with it? Mark learns from this feedback."
                    value={rejectText} onChange={(e) => setRejectText(e.target.value)} />
                  <div className="row">
                    <button className="btn danger" onClick={reject}>Confirm reject</button>
                    <button className="btn ghost" onClick={() => setRejecting(false)}>Cancel</button>
                  </div>
                </div>
              )}
              {detail.status === "approved" && (
                <button className="btn primary" onClick={postNow}>📤 Post now</button>
              )}
              {detail.status === "failed" && (
                <button className="btn primary" onClick={postNow}>↻ Retry post</button>
              )}
              {(detail.status === "posted" || detail.status === "rejected") && (
                <button className="btn ghost" onClick={props.onClose}>Close</button>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/* ---------- editable fields ---------- */

function EditableFields(props: {
  contentType: string;
  form: EditForm;
  set: <K extends keyof EditForm>(key: K, value: EditForm[K]) => void;
}) {
  const { contentType, form, set } = props;
  const isVideo = contentType === "video";
  const isCarousel = contentType === "carousel";
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="field">
        <span className="field-label">Hook</span>
        <input className="input" value={form.hook} onChange={(e) => set("hook", e.target.value)} />
      </div>
      <div className="field">
        <span className="field-label">Caption</span>
        <textarea className="input" rows={4} value={form.caption}
          onChange={(e) => set("caption", e.target.value)} />
      </div>
      <div className="field">
        <span className="field-label">Hashtags <span className="faint">(space-separated)</span></span>
        <input className="input" value={form.hashtags} onChange={(e) => set("hashtags", e.target.value)} />
      </div>

      {isVideo && (
        <>
          <div className="field">
            <span className="field-label">Script <span className="faint">(spoken voiceover)</span></span>
            <textarea className="input" rows={5} value={form.script}
              onChange={(e) => set("script", e.target.value)} />
          </div>
          <div className="field">
            <span className="field-label">Video prompt</span>
            <textarea className="input" rows={2} value={form.video_prompt}
              onChange={(e) => set("video_prompt", e.target.value)} />
          </div>
        </>
      )}

      {(isVideo || contentType === "image") && (
        <div className="field">
          <span className="field-label">Image prompt</span>
          <textarea className="input" rows={2} value={form.image_prompt}
            onChange={(e) => set("image_prompt", e.target.value)} />
        </div>
      )}

      {isCarousel && (
        <div className="field">
          <span className="field-label">Slides</span>
          <div className="stack" style={{ gap: 10 }}>
            {form.slide_texts.map((text, i) => (
              <div key={i} className="stack" style={{
                gap: 6, border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 10,
              }}>
                <div className="row between">
                  <span className="small faint">Slide {i + 1}</span>
                  <button className="btn ghost sm" title="Remove slide" onClick={() => {
                    set("slide_texts", form.slide_texts.filter((_, j) => j !== i));
                    set("image_prompts", form.image_prompts.filter((_, j) => j !== i));
                  }}>✕</button>
                </div>
                <textarea className="input" rows={2} placeholder="Slide text" value={text}
                  onChange={(e) => set("slide_texts", form.slide_texts.map((t, j) => (j === i ? e.target.value : t)))} />
                <textarea className="input" rows={2} placeholder="Image prompt for this slide"
                  value={form.image_prompts[i] ?? ""}
                  onChange={(e) => {
                    const next = [...form.image_prompts];
                    while (next.length <= i) next.push("");
                    next[i] = e.target.value;
                    set("image_prompts", next);
                  }} />
              </div>
            ))}
            <button className="btn sm" style={{ width: "fit-content" }} onClick={() => {
              set("slide_texts", [...form.slide_texts, ""]);
              set("image_prompts", [...form.image_prompts, ""]);
            }}>+ Add slide</button>
          </div>
        </div>
      )}

      <div className="grid cols-2">
        <div className="field">
          <span className="field-label">CTA</span>
          <input className="input" value={form.cta} onChange={(e) => set("cta", e.target.value)} />
        </div>
        <div className="field">
          <span className="field-label">Alt text</span>
          <input className="input" value={form.alt_text} onChange={(e) => set("alt_text", e.target.value)} />
        </div>
      </div>
    </div>
  );
}

/* ---------- posted performance ---------- */

function PostedSection({ posts }: { posts: PostRecord[] }) {
  if (posts.length === 0) return <div className="small muted">No post records yet.</div>;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="field-label">Performance</div>
      {posts.map((p) => {
        const m = p.latest_metric;
        return (
          <div key={p.id} style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)", padding: "10px 12px",
          }}>
            <div className="row between">
              <PlatformChip platform={p.platform} />
              <span className="faint small">posted {timeAgo(p.posted_at)}</span>
            </div>
            {m ? (
              <div className="row wrap" style={{ gap: 16, marginTop: 8, fontSize: 13 }}>
                <span><span className="faint">views</span> <strong>{fmt(m.views)}</strong></span>
                <span><span className="faint">likes</span> <strong>{fmt(m.likes)}</strong></span>
                <span><span className="faint">comments</span> <strong>{fmt(m.comments)}</strong></span>
                <span><span className="faint">shares</span> <strong>{fmt(m.shares)}</strong></span>
                <span><span className="faint">engagement</span> <strong>{pct(m.engagement_rate)}</strong></span>
              </div>
            ) : (
              <div className="small faint" style={{ marginTop: 6 }}>No metrics collected yet.</div>
            )}
            {(p.comments ?? []).length > 0 && (
              <div className="stack" style={{ gap: 6, marginTop: 10 }}>
                {(p.comments ?? []).slice(0, 6).map((cm) => (
                  <div key={cm.id} className="row" style={{ alignItems: "flex-start" }}>
                    <div style={{ flex: 1, fontSize: 12.5 }}>
                      <span className="muted" style={{ fontWeight: 600 }}>{cm.author ?? "anon"}</span>{" "}
                      <span>{cm.comment_text}</span>
                    </div>
                    {cm.sentiment && (
                      <Pill kind={cm.sentiment === "positive" ? "posted" : cm.sentiment === "negative" ? "failed" : ""}>
                        {cm.sentiment}
                      </Pill>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ---------- generate modal ---------- */

function GenerateModal({ onClose }: { onClose: () => void }) {
  const { campaigns, runJob } = useGlobal();
  const [campaignId, setCampaignId] = useState("");
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [count, setCount] = useState(1);

  const selectedCampaign = campaigns.find((c) => c.id === campaignId);
  const options = selectedCampaign ? selectedCampaign.platforms : ALL_PLATFORMS;

  const togglePlatform = (p: string) =>
    setPlatforms((ps) => (ps.includes(p) ? ps.filter((x) => x !== p) : [...ps, p]));

  const submit = () => {
    runJob(() => api.post<{ job_id: string }>("/api/generate", {
      campaign_id: campaignId || undefined,
      platforms: platforms.length ? platforms : undefined,
      count,
    }));
    onClose();
  };

  return (
    <Modal title="Generate content" onClose={onClose}>
      <div className="stack" style={{ gap: 14 }}>
        <div className="field">
          <span className="field-label">Campaign</span>
          <select className="input" value={campaignId}
            onChange={(e) => { setCampaignId(e.target.value); setPlatforms([]); }}>
            <option value="">All running campaigns</option>
            {campaigns.filter((c) => c.active).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <span className="field-label">Platforms <span className="faint">(optional — default: campaign settings)</span></span>
          <div className="row wrap" style={{ gap: 8 }}>
            {options.map((p) => (
              <label key={p} className={`checkbox-row ${platforms.includes(p) ? "checked" : ""}`}>
                <input type="checkbox" checked={platforms.includes(p)} onChange={() => togglePlatform(p)} />
                <PlatformChip platform={p} />
              </label>
            ))}
          </div>
        </div>
        <div className="field" style={{ maxWidth: 140 }}>
          <span className="field-label">Posts per platform</span>
          <select className="input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
            {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={submit}>✨ Generate</button>
        </div>
      </div>
    </Modal>
  );
}
