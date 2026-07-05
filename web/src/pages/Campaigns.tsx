// Multi-campaign manager: create, edit, pause, archive, and kick off generation.
import { useState } from "react";
import { api, ApiError } from "../api";
import { useGlobal } from "../store";
import { ALL_PLATFORMS, Campaign, PLATFORM_LABELS } from "../types";
import { Card, Empty, Modal, Pill, PlatformChip, Switch } from "../components/ui";

interface CampaignForm {
  name: string;
  description: string;
  target_audience: string;
  brand_voice: string;
  website_url: string;
  platforms: string[];
  cadence: Record<string, number>;
  subreddit: string;
  board_id: string;
  kind: string;
  content_rating: string;
  upload_profile: string;
  trend_subreddits: string;
  trend_keywords: string;
}

const blankForm = (): CampaignForm => ({
  name: "", description: "", target_audience: "", brand_voice: "",
  website_url: "", platforms: [], cadence: {}, subreddit: "", board_id: "",
  kind: "product", content_rating: "standard", upload_profile: "",
  trend_subreddits: "", trend_keywords: "",
});

const formFrom = (c: Campaign): CampaignForm => ({
  name: c.name,
  description: c.description,
  target_audience: c.target_audience,
  brand_voice: c.brand_voice,
  website_url: c.website_url ?? "",
  platforms: [...c.platforms],
  cadence: { ...c.posting_cadence },
  subreddit: c.platform_options?.reddit?.subreddit ?? "",
  board_id: c.platform_options?.pinterest?.pinterest_board_id ?? "",
  kind: c.kind ?? "product",
  content_rating: c.content_rating ?? "standard",
  upload_profile: c.upload_profile ?? "",
  trend_subreddits: (c.trend_sources?.subreddits ?? []).join(", "),
  trend_keywords: (c.trend_sources?.keywords ?? []).join(", "),
});

const parseCsv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Campaigns() {
  const { campaigns, refreshCampaigns, runJob, toast } = useGlobal();
  const [modal, setModal] = useState<{ open: boolean; campaign: Campaign | null }>({ open: false, campaign: null });

  const toggleActive = async (c: Campaign, on: boolean) => {
    try {
      await api.patch<Campaign>(`/api/campaigns/${c.id}`, { active: on });
      refreshCampaigns();
      toast(on ? `${c.name} resumed` : `${c.name} paused`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Update failed", "error");
    }
  };

  const archive = async (c: Campaign) => {
    if (!window.confirm(`Archive "${c.name}"? It stops posting and is hidden from this list.`)) return;
    try {
      await api.del<unknown>(`/api/campaigns/${c.id}`);
      refreshCampaigns();
      toast(`${c.name} archived`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Archive failed", "error");
    }
  };

  return (
    <>
      <div className="row between">
        <span className="muted small">
          {campaigns.length} campaign{campaigns.length === 1 ? "" : "s"} · Mark markets every active one autonomously
        </span>
        <button className="btn primary" onClick={() => setModal({ open: true, campaign: null })}>
          + New campaign
        </button>
      </div>

      {campaigns.length === 0 ? (
        <Card>
          <Empty
            icon="🚩"
            title="No campaigns yet"
            hint="Tell Mark what you're building and it starts creating and posting content for it."
            action={
              <button className="btn primary" onClick={() => setModal({ open: true, campaign: null })}>
                Create your first campaign
              </button>
            }
          />
        </Card>
      ) : (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
          {campaigns.map((c) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              onToggle={(on) => toggleActive(c, on)}
              onEdit={() => setModal({ open: true, campaign: c })}
              onArchive={() => archive(c)}
              onGenerate={() => runJob(() => api.post<{ job_id: string }>("/api/generate", { campaign_id: c.id }))}
            />
          ))}
        </div>
      )}

      {modal.open && (
        <CampaignModal campaign={modal.campaign} onClose={() => setModal({ open: false, campaign: null })} />
      )}
    </>
  );
}

function CampaignCard(props: {
  campaign: Campaign;
  onToggle: (on: boolean) => void;
  onEdit: () => void;
  onArchive: () => void;
  onGenerate: () => void;
}) {
  const c = props.campaign;
  const active = !!c.active;
  const totalPerDay = c.platforms.reduce((s, p) => s + (c.posting_cadence[p] ?? 0), 0);

  return (
    <Card>
      <div className="stack" style={{ gap: 11, opacity: active ? 1 : 0.65 }}>
        <div className="row between">
          <div className="row" style={{ minWidth: 0 }}>
            <span style={{ fontWeight: 700, fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {c.name}
            </span>
            {!active && <Pill kind="mock">paused</Pill>}
          </div>
          <Switch checked={active} onChange={props.onToggle} />
        </div>

        <p className="small muted" style={{
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
          overflow: "hidden", minHeight: 36,
        }}>
          {c.description}
        </p>

        <div className="row wrap" style={{ gap: 9 }}>
          {c.platforms.map((p) => <PlatformChip key={p} platform={p} />)}
        </div>

        <span className="small faint">
          {totalPerDay} post{totalPerDay === 1 ? "" : "s"}/day across {c.platforms.length} platform{c.platforms.length === 1 ? "" : "s"}
        </span>

        <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn primary sm" disabled={!active} onClick={props.onGenerate}>✨ Generate now</button>
          <button className="btn sm" onClick={props.onEdit}>Edit</button>
          <button className="btn danger sm" onClick={props.onArchive}>Archive</button>
        </div>
      </div>
    </Card>
  );
}

function CampaignModal({ campaign, onClose }: { campaign: Campaign | null; onClose: () => void }) {
  const { refreshCampaigns, toast } = useGlobal();
  const [form, setForm] = useState<CampaignForm>(campaign ? formFrom(campaign) : blankForm());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof CampaignForm>(k: K, v: CampaignForm[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const togglePlatform = (p: string) => {
    setForm((f) => {
      const on = f.platforms.includes(p);
      return {
        ...f,
        platforms: on ? f.platforms.filter((x) => x !== p) : [...f.platforms, p],
        cadence: on ? f.cadence : { ...f.cadence, [p]: f.cadence[p] ?? 1 },
      };
    });
  };

  const canSave =
    form.name.trim() !== "" &&
    form.description.trim() !== "" &&
    form.target_audience.trim() !== "" &&
    form.brand_voice.trim() !== "" &&
    form.platforms.length > 0;

  const save = async () => {
    setError(null);
    setSaving(true);
    const posting_cadence: Record<string, number> = {};
    for (const p of form.platforms) posting_cadence[p] = form.cadence[p] ?? 1;
    const platform_options: Record<string, Record<string, string>> = {};
    if (form.platforms.includes("reddit") && form.subreddit.trim()) {
      platform_options.reddit = { subreddit: form.subreddit.trim().replace(/^r\//, "") };
    }
    if (form.platforms.includes("pinterest") && form.board_id.trim()) {
      platform_options.pinterest = { pinterest_board_id: form.board_id.trim() };
    }
    const body = {
      name: form.name.trim(),
      description: form.description.trim(),
      target_audience: form.target_audience.trim(),
      brand_voice: form.brand_voice.trim(),
      website_url: form.kind === "entertainment" ? null : form.website_url.trim() || null,
      platforms: form.platforms,
      posting_cadence,
      platform_options,
      kind: form.kind,
      content_rating: form.content_rating,
      upload_profile: form.upload_profile.trim() || null,
      trend_sources: {
        subreddits: parseCsv(form.trend_subreddits).map((s) => s.replace(/^r\//, "")),
        keywords: parseCsv(form.trend_keywords),
      },
    };
    try {
      if (campaign) {
        await api.patch<Campaign>(`/api/campaigns/${campaign.id}`, body);
      } else {
        await api.post<Campaign>("/api/campaigns", { ...body, active: true });
      }
      refreshCampaigns();
      toast(campaign ? "Campaign updated" : "Campaign created");
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={campaign ? `Edit ${campaign.name}` : "New campaign"} onClose={onClose} wide>
      <div className="stack" style={{ gap: 16 }}>
        <div className="grid cols-2">
          <div className="field">
            <span className="field-label">Name</span>
            <input className="input" value={form.name} placeholder="SudoApply"
              onChange={(e) => set("name", e.target.value)} autoFocus />
          </div>
          <div className="field">
            <span className="field-label">Kind</span>
            <select className="input" value={form.kind}
              onChange={(e) => set("kind", e.target.value)}>
              <option value="product">product — marketing something</option>
              <option value="entertainment">entertainment — content is the product</option>
            </select>
          </div>
        </div>

        <div className="grid cols-2">
          {form.kind !== "entertainment" && (
            <div className="field">
              <span className="field-label">Website URL <span className="faint">(optional)</span></span>
              <input className="input" value={form.website_url} placeholder="https://…"
                onChange={(e) => set("website_url", e.target.value)} />
            </div>
          )}
          <div className="field">
            <span className="field-label">Content rating</span>
            <select className="input" value={form.content_rating}
              onChange={(e) => set("content_rating", e.target.value)}>
              <option value="clean">clean</option>
              <option value="standard">standard</option>
              <option value="edgy">edgy</option>
            </select>
            <span className="field-hint">How spicy the content is allowed to get — platform caps still apply.</span>
          </div>
        </div>

        <div className="field">
          <span className="field-label">What is it?</span>
          <textarea className="input" rows={3} value={form.description}
            placeholder="What the product does, key features, why it exists…"
            onChange={(e) => set("description", e.target.value)} />
        </div>

        <div className="grid cols-2">
          <div className="field">
            <span className="field-label">Target audience</span>
            <textarea className="input" rows={3} value={form.target_audience}
              placeholder="Who you're trying to reach, their pain points, where they hang out…"
              onChange={(e) => set("target_audience", e.target.value)} />
          </div>
          <div className="field">
            <span className="field-label">Brand voice</span>
            <textarea className="input" rows={3} value={form.brand_voice}
              placeholder="Tone and style: casual? irreverent? educational? First or second person?"
              onChange={(e) => set("brand_voice", e.target.value)} />
          </div>
        </div>

        <div className="field">
          <span className="field-label">Platforms</span>
          <span className="field-hint">Pick where Mark should post and how many posts per day (0–5) on each.</span>
          <div className="grid cols-3" style={{ gap: 8 }}>
            {ALL_PLATFORMS.map((p) => {
              const checked = form.platforms.includes(p);
              return (
                <div key={p} className={`checkbox-row ${checked ? "checked" : ""}`}
                  onClick={() => togglePlatform(p)}>
                  <input type="checkbox" checked={checked} readOnly style={{ pointerEvents: "none" }} />
                  <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{PLATFORM_LABELS[p] ?? p}</span>
                  {checked && (
                    <input className="input" type="number" min={0} max={5} title="posts per day"
                      value={form.cadence[p] ?? 1}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        const n = Math.max(0, Math.min(5, Math.round(Number(e.target.value) || 0)));
                        set("cadence", { ...form.cadence, [p]: n });
                      }}
                      style={{ width: 54, padding: "3px 8px", fontSize: 12.5 }} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {(form.platforms.includes("reddit") || form.platforms.includes("pinterest")) && (
          <div className="grid cols-2">
            {form.platforms.includes("reddit") && (
              <div className="field">
                <span className="field-label">Subreddit</span>
                <input className="input" value={form.subreddit} placeholder="e.g. cscareerquestions"
                  onChange={(e) => set("subreddit", e.target.value)} />
                <span className="field-hint">Reddit posts go to this subreddit.</span>
              </div>
            )}
            {form.platforms.includes("pinterest") && (
              <div className="field">
                <span className="field-label">Board ID</span>
                <input className="input" value={form.board_id} placeholder="Pinterest board ID"
                  onChange={(e) => set("board_id", e.target.value)} />
                <span className="field-hint">Pins are added to this board.</span>
              </div>
            )}
          </div>
        )}

        <div className="field">
          <span className="field-label">upload-post profile <span className="faint">(optional)</span></span>
          <input className="input" value={form.upload_profile} placeholder="defaults to the global profile"
            onChange={(e) => set("upload_profile", e.target.value)} />
          <span className="field-hint">Post this campaign through its own upload-post.com profile (separate accounts).</span>
        </div>

        <div className="grid cols-2">
          <div className="field">
            <span className="field-label">Trend subreddits <span className="faint">(comma-separated)</span></span>
            <input className="input" value={form.trend_subreddits} placeholder="e.g. cscareerquestions, internships"
              onChange={(e) => set("trend_subreddits", e.target.value)} />
            <span className="field-hint">Subreddits watched for this campaign's trend radar.</span>
          </div>
          <div className="field">
            <span className="field-label">Trend keywords <span className="faint">(comma-separated)</span></span>
            <input className="input" value={form.trend_keywords} placeholder="e.g. job search, resume"
              onChange={(e) => set("trend_keywords", e.target.value)} />
            <span className="field-hint">Search terms scanned across trend sources.</span>
          </div>
        </div>

        {error != null && (
          <div className="small" style={{ color: "var(--red)" }}>{error}</div>
        )}

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!canSave || saving} onClick={save}>
            {saving ? "Saving…" : campaign ? "Save changes" : "Create campaign"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
