// Playbook — the strategy catalog and character ambassadors, scoped per campaign.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useGlobal } from "../store";
import { Character, Strategy } from "../types";
import { Card, Empty, Pill, PlatformChip, Spinner, Switch } from "../components/ui";

const HUMOR_LABELS: Record<string, string> = {
  none: "no humor", light: "light humor", full: "full humor",
};

export default function Playbook() {
  const { campaigns, jobsDoneVersion, runJob, toast } = useGlobal();
  const [campaign, setCampaign] = useState("");
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [syncing, setSyncing] = useState(false);

  // Strategy enablement is per-campaign, so a campaign must be selected.
  useEffect(() => {
    if (!campaign && campaigns.length > 0) {
      setCampaign((campaigns.find((c) => c.active) ?? campaigns[0]).id);
    }
  }, [campaigns, campaign]);

  const loadStrategies = useCallback(() => {
    if (!campaign) return;
    api.get<Strategy[]>(`/api/strategies?campaign=${encodeURIComponent(campaign)}`)
      .then(setStrategies).catch(() => {});
  }, [campaign]);
  const loadCharacters = useCallback(() => {
    if (!campaign) return;
    api.get<Character[]>(`/api/characters?campaign=${encodeURIComponent(campaign)}`)
      .then(setCharacters).catch(() => {});
  }, [campaign]);

  useEffect(() => { setStrategies(null); loadStrategies(); loadCharacters(); },
    [loadStrategies, loadCharacters]);
  useEffect(() => {
    // reference-sheet / generation jobs may change usage counts and images
    if (jobsDoneVersion > 0) { loadStrategies(); loadCharacters(); }
  }, [jobsDoneVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleStrategy = async (id: string, on: boolean) => {
    if (!campaign || !strategies) return;
    const next = strategies.map((s) => (s.id === id ? { ...s, enabled: on } : s));
    const enabledIds = next.filter((s) => s.enabled).map((s) => s.id);
    if (enabledIds.length === 0) {
      toast("At least one strategy must stay enabled", "error");
      return;
    }
    setStrategies(next); // optimistic
    try {
      // Full allowlist of enabled ids — or null when everything is enabled.
      await api.patch(`/api/campaigns/${campaign}/strategies`,
        { strategies: enabledIds.length === next.length ? null : enabledIds });
    } catch (e) {
      toast(e instanceof Error ? e.message : "Update failed", "error");
      loadStrategies();
    }
  };

  const syncCharacters = async () => {
    setSyncing(true);
    try {
      await api.post<Character[]>("/api/characters/sync");
      toast("Characters synced from config");
      loadCharacters();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Sync failed", "error");
    } finally {
      setSyncing(false);
    }
  };

  if (campaigns.length === 0) {
    return (
      <Card>
        <Empty icon="📖" title="No campaigns yet"
          hint="Strategies and characters are configured per campaign — create one first." />
      </Card>
    );
  }

  return (
    <>
      <div className="row wrap">
        <select className="input" style={{ width: 220 }} value={campaign}
          onChange={(e) => setCampaign(e.target.value)}>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <span className="small faint">
          toggle which strategies Mark may use for this campaign — the bandit learns within the enabled set
        </span>
      </div>

      {strategies == null ? (
        <div className="row" style={{ justifyContent: "center", padding: 40 }}><Spinner /></div>
      ) : strategies.length === 0 ? (
        <Card><Empty icon="📖" title="No strategies in the catalog" /></Card>
      ) : (
        <div className="grid" data-tour="playbook-strategies"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
          {strategies.map((s) => (
            <StrategyCard key={s.id} strategy={s}
              onToggle={(on) => toggleStrategy(s.id, on)} />
          ))}
        </div>
      )}

      {/* ---------- characters ---------- */}
      <Card title="Characters" dataTour="playbook-characters"
        action={
          <button className="btn sm" disabled={syncing} onClick={syncCharacters}>
            {syncing ? "Syncing…" : "⟳ Sync from config"}
          </button>
        }>
        {characters.length === 0 ? (
          <Empty icon="🎭" title="No characters for this campaign"
            hint={<>Define AI ambassadors in <code className="inline">config/characters/*.yaml</code>, then hit “Sync from config”.</>} />
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
            {characters.map((c) => (
              <CharacterCard key={c.id} character={c} onChanged={loadCharacters}
                onGenerateSheet={() =>
                  runJob(() => api.post<{ job_id: string }>(`/api/characters/${c.id}/sheet`))} />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

/* ---------- strategy card ---------- */

function StrategyCard({ strategy: s, onToggle }: { strategy: Strategy; onToggle: (on: boolean) => void }) {
  const [expanded, setExpanded] = useState(false);
  const long = s.description.length > 150;
  return (
    <Card>
      <div className="stack" style={{ gap: 11, opacity: s.enabled ? 1 : 0.55 }}>
        <div className="row between">
          <span style={{ fontWeight: 700, fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {s.name}
          </span>
          <Switch checked={s.enabled} onChange={onToggle} />
        </div>

        <div>
          <p className="small muted" style={expanded ? undefined : {
            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>
            {s.description}
          </p>
          {long && (
            <button className="btn ghost sm" style={{ padding: "2px 0", fontSize: 11.5 }}
              onClick={() => setExpanded(!expanded)}>
              {expanded ? "less ▴" : "more ▾"}
            </button>
          )}
          {expanded && s.example_sketches.length > 0 && (
            <div className="stack" style={{ gap: 5, marginTop: 6 }}>
              {s.example_sketches.map((ex, i) => (
                <div key={i} className="small faint" style={{ fontStyle: "italic" }}>{ex}</div>
              ))}
            </div>
          )}
        </div>

        <div className="row wrap" style={{ gap: 6 }}>
          <Pill kind="accent">{s.emotional_target.replace(/_/g, " ")}</Pill>
          <Pill>{HUMOR_LABELS[s.humor_level] ?? s.humor_level}</Pill>
          {s.uses_character && <Pill>🎭 character</Pill>}
          {s.series_format != null && (
            <Pill kind="approved"><span title={s.series_format}>📺 series{s.episode ? ` · next ep ${s.episode}` : ""}</span></Pill>
          )}
          {s.never_auto_approve && <Pill kind="draft">manual approve</Pill>}
        </div>

        <div className="row wrap" style={{ gap: 9 }}>
          {Object.entries(s.platforms).map(([p, note]) => (
            <span key={p} title={note || "native fit"}><PlatformChip platform={p} /></span>
          ))}
        </div>

        <div className="row between">
          <span className="small faint">
            {s.usage ?? 0} post{(s.usage ?? 0) === 1 ? "" : "s"} generated
          </span>
          <span className="small faint">mix weight {s.mix_weight}</span>
        </div>
      </div>
    </Card>
  );
}

/* ---------- character card ---------- */

function CharacterCard(props: {
  character: Character;
  onChanged: () => void;
  onGenerateSheet: () => void;
}) {
  const { toast } = useGlobal();
  const c = props.character;
  const [persona, setPersona] = useState(c.persona);
  const [phrases, setPhrases] = useState(c.catchphrases.join(", "));
  const [saving, setSaving] = useState(false);

  // Re-sync the form when the character reloads from the server.
  useEffect(() => {
    setPersona(c.persona);
    setPhrases(c.catchphrases.join(", "));
  }, [c.id, c.persona, c.catchphrases]);

  const dirty = persona !== c.persona || phrases !== c.catchphrases.join(", ");
  const active = !!c.active;

  const patch = async (body: Record<string, unknown>, msg: string) => {
    setSaving(true);
    try {
      await api.patch<Character>(`/api/characters/${c.id}`, body);
      toast(msg);
      props.onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Update failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const lore = Object.entries(c.lore_state);

  return (
    <div style={{
      background: "var(--bg-raised)", border: "1px solid var(--border)",
      borderRadius: "var(--radius)", padding: 14,
    }}>
      <div className="stack" style={{ gap: 11, opacity: active ? 1 : 0.65 }}>
        <div className="row between">
          <div className="row" style={{ minWidth: 0 }}>
            <span style={{ fontWeight: 700, fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {c.name}
            </span>
            <Pill>{c.role}</Pill>
          </div>
          <Switch checked={active}
            onChange={(on) => patch({ active: on }, on ? `${c.name} activated` : `${c.name} deactivated`)} />
        </div>

        <div className="media-frame" style={{ height: 190 }}>
          {c.reference_url ? (
            <img src={c.reference_url} alt={`${c.name} reference sheet`} />
          ) : (
            <div className="stack" style={{ alignItems: "center", gap: 4, padding: 16 }}>
              <span style={{ fontSize: 32, opacity: 0.7 }}>🎭</span>
              <span className="small faint">No reference sheet yet</span>
            </div>
          )}
        </div>

        <div className="field">
          <span className="field-label">Persona</span>
          <textarea className="input" rows={3} value={persona}
            onChange={(e) => setPersona(e.target.value)} />
        </div>

        <div className="field">
          <span className="field-label">Catchphrases <span className="faint">(comma-separated)</span></span>
          <input className="input" value={phrases}
            onChange={(e) => setPhrases(e.target.value)} />
        </div>

        {lore.length > 0 && (
          <div className="field">
            <span className="field-label">Lore</span>
            <div className="row wrap" style={{ gap: 6 }}>
              {lore.map(([k, v]) => {
                const full = typeof v === "object" ? JSON.stringify(v) : String(v);
                const short = full.length > 36 ? `${full.slice(0, 36)}…` : full;
                return (
                  <Pill key={k}>
                    <span title={full.length > 36 ? full : undefined}>
                      <span className="faint">{k}</span> {short}
                    </span>
                  </Pill>
                );
              })}
            </div>
          </div>
        )}

        <div className="row wrap" style={{ gap: 8 }}>
          {dirty && (
            <button className="btn primary sm" disabled={saving}
              onClick={() => patch({
                persona,
                catchphrases: phrases.split(",").map((s) => s.trim()).filter(Boolean),
              }, "Character saved")}>
              {saving ? "Saving…" : "Save"}
            </button>
          )}
          <button className="btn sm" onClick={props.onGenerateSheet}
            title="Generates the canonical reference image used to keep the character consistent across posts">
            🖼 Generate reference sheet
          </button>
        </div>
      </div>
    </div>
  );
}
