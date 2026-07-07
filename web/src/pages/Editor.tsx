// Clip / caption editor (Contract 6) — human touch-up of an auto-assembled clip
// video before posting. The browser NEVER burns captions: it plays a captionless
// proxy/master <video> and draws a karaoke caption overlay synced via rAF against
// video.currentTime. A wavesurfer waveform carries draggable regions for caption
// timing; a plain-div clip lane trims/reorders clips. Every control mutates an
// in-memory EDL; Save / Re-cut proxy / Render final are explicit.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { type Region } from "wavesurfer.js/dist/plugins/regions.esm.js";
import { editor } from "../api";
import { useGlobal } from "../store";
import {
  CaptionStyle, Edl, EdlAudioTrack, EdlCaptionWord, EdlClip, EditData,
  FontRef, SfxItem,
} from "../types";
import { Empty, PlatformChip, Spinner } from "../components/ui";

/* ----------------------------- helpers ----------------------------- */

/** ASS &HAABBGGRR (BGR, inverted alpha) → CSS color. Falls back for #hex. */
function assToCss(ass: string | undefined, fallback: string): string {
  if (!ass) return fallback;
  const s = ass.trim();
  if (s.startsWith("#")) return s;
  const m = /^&H?([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})$/.exec(s);
  if (!m) return fallback;
  const a = parseInt(m[1], 16), b = parseInt(m[2], 16), g = parseInt(m[3], 16), r = parseInt(m[4], 16);
  return `rgba(${r},${g},${b},${((255 - a) / 255).toFixed(3)})`;
}

function clipDur(c: EdlClip): number {
  return Math.max(0, (c.out - c.in) / (c.speed || 1));
}

/** Largest word index whose t0 <= t (binary search; words are t0-sorted). */
function activeWordIndex(words: EdlCaptionWord[], t: number): number {
  let lo = 0, hi = words.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].t0 <= t) { ans = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  // Past its own end with a gap before the next word → nothing active.
  if (ans >= 0 && t > words[ans].t1 && (ans + 1 >= words.length || t < words[ans + 1].t0)) {
    return -1;
  }
  return ans;
}

const num = (v: string, fallback = 0) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : fallback;
};

/* ----------------------------- page ----------------------------- */

export default function Editor() {
  const { contentId } = useParams<{ contentId: string }>();
  const { toast } = useGlobal();
  const [data, setData] = useState<EditData | null>(null);
  const [edl, setEdl] = useState<Edl | null>(null);
  const [baseline, setBaseline] = useState("");
  const [sfx, setSfx] = useState<SfxItem[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [captionless, setCaptionless] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [selClip, setSelClip] = useState(0);
  const [selWord, setSelWord] = useState(-1);

  const dirty = edl != null && JSON.stringify(edl) !== baseline;

  useEffect(() => {
    if (!contentId) return;
    editor.load(contentId)
      .then((d) => {
        setData(d);
        setEdl(d.edl);
        setBaseline(JSON.stringify(d.edl));
        const cl = d.media_urls.proxy || d.media_urls.master;
        setCaptionless(!!cl);
        setVideoSrc(cl || d.media_urls.video || null);
      })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : "Failed to load editor"));
    editor.sfx().then(setSfx).catch(() => setSfx([]));
  }, [contentId]);

  // Inject @font-face for the caption fonts so the preview matches the burn.
  useEffect(() => {
    if (!data?.fonts?.length) return;
    const id = "mark-editor-fonts";
    let el = document.getElementById(id) as HTMLStyleElement | null;
    if (!el) { el = document.createElement("style"); el.id = id; document.head.appendChild(el); }
    el.textContent = data.fonts.map((f: FontRef) =>
      `@font-face{font-family:"${f.family}";src:url("${f.url}") format("truetype");font-display:swap;}`,
    ).join("\n");
  }, [data?.fonts]);

  const patch = useCallback((fn: (e: Edl) => Edl) => {
    setEdl((prev) => (prev ? fn(structuredClone(prev)) : prev));
  }, []);

  const style: CaptionStyle | undefined = useMemo(() => {
    if (!data || !edl) return undefined;
    return data.styles.find((s) => s.id === edl.captions.style) || data.styles[0];
  }, [data, edl]);

  const runJob = useCallback(async (
    kind: string, start: () => Promise<{ job_id: string }>,
  ): Promise<Record<string, unknown> | null> => {
    setBusy(kind);
    try {
      const { job_id } = await start();
      for (;;) {
        await new Promise((r) => setTimeout(r, 500));
        const j = await editor.job(job_id);
        if (j.status === "done") return (j.result as Record<string, unknown>) || {};
        if (j.status === "failed") throw new Error(j.error || "job failed");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "job failed", "error");
      return null;
    } finally {
      setBusy(null);
    }
  }, [toast]);

  const save = useCallback(async () => {
    if (!edl || !contentId) return;
    setBusy("save");
    try {
      await editor.save(contentId, edl);
      setBaseline(JSON.stringify(edl));
      toast("EDL saved");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "error");
    } finally { setBusy(null); }
  }, [edl, contentId, toast]);

  const recutProxy = useCallback(async () => {
    if (!contentId || !edl) return;
    // Structural edits must be persisted before the server re-cuts from disk.
    if (dirty) { await editor.save(contentId, edl).catch(() => {}); setBaseline(JSON.stringify(edl)); }
    const res = await runJob("proxy", () => editor.proxy(contentId));
    if (res?.proxy_url) {
      setCaptionless(true);
      setVideoSrc(`${res.proxy_url}?t=${Date.now()}`);
      toast("Preview re-cut");
    }
  }, [contentId, edl, dirty, runJob, toast]);

  const renderFinal = useCallback(async () => {
    if (!contentId || !edl) return;
    if (dirty) { await editor.save(contentId, edl).catch(() => {}); setBaseline(JSON.stringify(edl)); }
    const res = await runJob("render", () => editor.render(contentId));
    if (res) toast("Final rendered — back in the Studio queue");
  }, [contentId, edl, dirty, runJob, toast]);

  if (loadErr) {
    return (
      <Empty icon="✂️" title="This content isn't editable"
        hint={loadErr}
        action={<Link className="btn" to="/studio">← Back to Studio</Link>} />
    );
  }
  if (!data || !edl) {
    return <div className="row" style={{ justifyContent: "center", padding: 60 }}><Spinner /></div>;
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      {/* header */}
      <div className="row wrap between">
        <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
          <Link className="btn ghost sm" to="/studio">← Studio</Link>
          <PlatformChip platform={data.platform} />
          <span className="faint small">#{data.content_id} · {data.content_type} · {data.status}</span>
          {dirty && <span className="pill draft">unsaved</span>}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" disabled={busy != null || !dirty} onClick={save}>
            {busy === "save" ? <Spinner /> : "💾 Save EDL"}
          </button>
          <button className="btn" disabled={busy != null} onClick={recutProxy}
            title="Fast 480p preview reflecting clip cuts">
            {busy === "proxy" ? <Spinner /> : "⚡ Re-cut proxy"}
          </button>
          <button className="btn primary" disabled={busy != null} onClick={renderFinal}
            title="Render the final 1080×1920 and send it back to the queue">
            {busy === "render" ? <Spinner /> : "🎬 Render final"}
          </button>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(240px, 320px) 1fr", gap: 16, alignItems: "start" }}>
        <Preview videoSrc={videoSrc} captionless={captionless} edl={edl}
          style={style} onRecut={recutProxy} busy={busy != null} />
        <div className="stack" style={{ gap: 14 }}>
          <CaptionPanel data={data} edl={edl} patch={patch}
            selWord={selWord} setSelWord={setSelWord} />
          <AudioPanel edl={edl} patch={patch} sfx={sfx} sfxAvailable={data.sfx_available} />
        </div>
      </div>

      <Waveform audioUrl={data.audio_url} edl={edl} patch={patch}
        selWord={selWord} setSelWord={setSelWord} />

      <ClipLane edl={edl} patch={patch} selClip={selClip} setSelClip={setSelClip} />
    </div>
  );
}

/* ----------------------------- preview ----------------------------- */

function Preview(props: {
  videoSrc: string | null; captionless: boolean; edl: Edl;
  style?: CaptionStyle; onRecut: () => void; busy: boolean;
}) {
  const { videoSrc, captionless, edl, style } = props;
  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(-1);
  const [wrapH, setWrapH] = useState(480);

  const words = edl.captions.words;
  const wordsRef = useRef(words);
  wordsRef.current = words;

  // rAF caption sync — binary search current word; setState only on change.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    let raf = 0;
    let last = -2;
    const tick = () => {
      const idx = edl.captions.mode === "none" ? -1 : activeWordIndex(wordsRef.current, v.currentTime);
      if (idx !== last) { last = idx; setActive(idx); }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [edl.captions.mode]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWrapH(el.clientHeight));
    ro.observe(el);
    setWrapH(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  const chunkSize = Math.max(1, style?.chunk_size ?? 3);
  const yFrac = style?.y_frac ?? 0.64;
  const canvasH = edl.canvas.height || 1920;
  const fontPx = (style?.font_size ?? 84) * (wrapH / canvasH);
  const primary = assToCss(style?.primary_color, "#ffffff");
  const highlight = assToCss(style?.highlight_color, "#ffd400");
  const family = style?.font ? `"${style.font}", system-ui, sans-serif` : "system-ui, sans-serif";

  let chunk: EdlCaptionWord[] = [];
  let activeInChunk = -1;
  if (active >= 0) {
    const start = Math.floor(active / chunkSize) * chunkSize;
    chunk = words.slice(start, start + chunkSize);
    activeInChunk = active - start;
  }

  return (
    <div className="stack" style={{ gap: 8, position: "sticky", top: 8 }}>
      <div ref={wrapRef} style={{
        position: "relative", width: "100%", aspectRatio: "9 / 16",
        background: "#000", borderRadius: "var(--radius-sm)", overflow: "hidden",
        border: "1px solid var(--border)",
      }}>
        {videoSrc ? (
          <video ref={videoRef} src={videoSrc} controls playsInline
            style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }} />
        ) : (
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: 16, textAlign: "center" }}>
            <div className="small muted">No preview yet.<br />Re-cut a proxy to preview.</div>
          </div>
        )}
        {/* caption overlay — never burned, drawn live */}
        {chunk.length > 0 && (
          <div style={{
            position: "absolute", left: 0, right: 0, top: `${yFrac * 100}%`,
            transform: "translateY(-50%)", textAlign: "center", pointerEvents: "none",
            padding: "0 6%", lineHeight: 1.1,
          }}>
            {chunk.map((w, i) => (
              <span key={i} style={{
                fontFamily: family, fontWeight: 800,
                fontSize: `${fontPx}px`,
                color: i === activeInChunk ? highlight : primary,
                textTransform: style?.uppercase ? "uppercase" : "none",
                WebkitTextStroke: `${Math.max(1, (style?.outline ?? 4) * (wrapH / canvasH))}px #000`,
                paintOrder: "stroke fill", marginRight: "0.3em",
                display: "inline-block",
              }}>{w.w}</span>
            ))}
          </div>
        )}
        {edl.ai_generated && (
          <div style={{
            position: "absolute", top: 6, left: 0, right: 0, textAlign: "center",
            fontSize: 11, color: "rgba(255,255,255,.6)", pointerEvents: "none",
          }}>AI-generated</div>
        )}
      </div>
      {!captionless && videoSrc && (
        <div className="small" style={{ color: "var(--amber, #f59e0b)" }}>
          Preview shows the burned-in final. Re-cut a proxy for a captionless live preview.
        </div>
      )}
    </div>
  );
}

/* ----------------------------- captions ----------------------------- */

function CaptionPanel(props: {
  data: EditData; edl: Edl; patch: (fn: (e: Edl) => Edl) => void;
  selWord: number; setSelWord: (i: number) => void;
}) {
  const { data, edl, patch, selWord, setSelWord } = props;
  const cap = edl.captions;

  const setMode = (mode: Edl["captions"]["mode"]) =>
    patch((e) => { e.captions.mode = mode; return e; });
  const setStyle = (s: string) =>
    patch((e) => { e.captions.style = s; return e; });

  const setWord = (i: number, field: keyof EdlCaptionWord, value: string | number | boolean) =>
    patch((e) => { (e.captions.words[i] as unknown as Record<string, unknown>)[field] = value; return e; });
  const delWord = (i: number) =>
    patch((e) => { e.captions.words.splice(i, 1); return e; });
  const addWord = () =>
    patch((e) => {
      const last = e.captions.words[e.captions.words.length - 1];
      const t0 = last ? last.t1 : 0;
      e.captions.words.push({ w: "word", t0, t1: t0 + 0.4, emphasize: false });
      return e;
    });

  return (
    <div className="card">
      <div className="card-title"><span>Captions</span></div>
      <div className="stack" style={{ gap: 12 }}>
        <div className="grid cols-2" style={{ gap: 10 }}>
          <div className="field">
            <span className="field-label">Mode</span>
            <select className="input" value={cap.mode} onChange={(e) => setMode(e.target.value as Edl["captions"]["mode"])}>
              {["karaoke", "static_scene", "seam_band", "none"].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="field">
            <span className="field-label">Style preset</span>
            <select className="input" value={cap.style} onChange={(e) => setStyle(e.target.value)}>
              {data.styles.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
              {!data.styles.some((s) => s.id === cap.style) && <option value={cap.style}>{cap.style}</option>}
            </select>
          </div>
        </div>

        {cap.mode !== "none" && cap.mode !== "static_scene" && (
          <div className="stack" style={{ gap: 6, maxHeight: 260, overflowY: "auto" }}>
            {cap.words.length === 0 && <div className="small muted">No words. Add one to start captioning.</div>}
            {cap.words.map((w, i) => (
              <div key={i} className={`row ${selWord === i ? "" : ""}`} style={{
                gap: 6, alignItems: "center",
                background: selWord === i ? "var(--bg-card)" : undefined,
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 6,
              }} onMouseDown={() => setSelWord(i)}>
                <input className="input" style={{ flex: 1, minWidth: 60 }} value={w.w}
                  onChange={(e) => setWord(i, "w", e.target.value)} />
                <input className="input" type="number" step="0.05" style={{ width: 72 }} value={w.t0}
                  title="start (s)" onChange={(e) => setWord(i, "t0", num(e.target.value))} />
                <input className="input" type="number" step="0.05" style={{ width: 72 }} value={w.t1}
                  title="end (s)" onChange={(e) => setWord(i, "t1", num(e.target.value))} />
                <label className="small" title="emphasize (bigger pop)" style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <input type="checkbox" checked={!!w.emphasize} onChange={(e) => setWord(i, "emphasize", e.target.checked)} />★
                </label>
                <button className="btn ghost sm" title="Delete word" onClick={() => delWord(i)}>✕</button>
              </div>
            ))}
            <button className="btn sm" style={{ width: "fit-content" }} onClick={addWord}>+ Add word</button>
          </div>
        )}

        {cap.mode === "static_scene" && (
          <StaticEvents edl={edl} patch={patch} />
        )}
      </div>
    </div>
  );
}

function StaticEvents(props: { edl: Edl; patch: (fn: (e: Edl) => Edl) => void }) {
  const { edl, patch } = props;
  const events = edl.captions.events;
  const set = (i: number, field: "text" | "t0" | "t1", value: string | number) =>
    patch((e) => { (e.captions.events[i] as unknown as Record<string, unknown>)[field] = value; return e; });
  const del = (i: number) => patch((e) => { e.captions.events.splice(i, 1); return e; });
  const add = () => patch((e) => {
    const last = e.captions.events[e.captions.events.length - 1];
    const t0 = last ? last.t1 : 0;
    e.captions.events.push({ text: "scene text", t0, t1: t0 + 2 });
    return e;
  });
  return (
    <div className="stack" style={{ gap: 6, maxHeight: 260, overflowY: "auto" }}>
      {events.map((ev, i) => (
        <div key={i} className="stack" style={{ gap: 4, border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 6 }}>
          <textarea className="input" rows={2} value={ev.text} onChange={(e) => set(i, "text", e.target.value)} />
          <div className="row" style={{ gap: 6 }}>
            <input className="input" type="number" step="0.1" style={{ width: 80 }} value={ev.t0} onChange={(e) => set(i, "t0", num(e.target.value))} />
            <input className="input" type="number" step="0.1" style={{ width: 80 }} value={ev.t1} onChange={(e) => set(i, "t1", num(e.target.value))} />
            <button className="btn ghost sm" onClick={() => del(i)}>✕</button>
          </div>
        </div>
      ))}
      <button className="btn sm" style={{ width: "fit-content" }} onClick={add}>+ Add scene</button>
    </div>
  );
}

/* ----------------------------- audio ----------------------------- */

function AudioPanel(props: {
  edl: Edl; patch: (fn: (e: Edl) => Edl) => void; sfx: SfxItem[]; sfxAvailable: boolean;
}) {
  const { edl, patch, sfx, sfxAvailable } = props;
  const [pick, setPick] = useState("");

  const setTrack = (i: number, field: keyof EdlAudioTrack, value: number | null) =>
    patch((e) => { (e.audio[i] as unknown as Record<string, unknown>)[field] = value; return e; });
  const delTrack = (i: number) => patch((e) => { e.audio.splice(i, 1); return e; });
  const addSfx = () => {
    const item = sfx.find((s) => s.slug === pick);
    if (!item || !item.src) return;
    patch((e) => {
      e.audio.push({ src: item.src!, kind: "sfx", gain_db: item.gain_db ?? 0, t0: 0, label: item.name });
      return e;
    });
  };

  const kindGlyph: Record<string, string> = {
    voiceover: "🎙", music: "🎵", original: "🎞", sfx: "💥",
  };

  return (
    <div className="card">
      <div className="card-title"><span>Audio</span></div>
      <div className="stack" style={{ gap: 8 }}>
        {edl.audio.length === 0 && <div className="small muted">No audio tracks.</div>}
        {edl.audio.map((tr, i) => (
          <div key={i} className="stack" style={{ gap: 6, border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 8 }}>
            <div className="row between">
              <span className="small" style={{ fontWeight: 600 }}>
                {kindGlyph[tr.kind] ?? "🔊"} {tr.kind}{tr.label ? ` · ${tr.label}` : ""}
              </span>
              {(tr.kind === "sfx" || tr.kind === "music") && (
                <button className="btn ghost sm" title="Remove track" onClick={() => delTrack(i)}>✕</button>
              )}
            </div>
            <label className="small muted row" style={{ gap: 8, alignItems: "center" }}>
              <span style={{ width: 78 }}>gain {tr.gain_db.toFixed(0)} dB</span>
              <input type="range" min={-30} max={12} step={1} value={tr.gain_db} style={{ flex: 1 }}
                onChange={(e) => setTrack(i, "gain_db", num(e.target.value))} />
            </label>
            {tr.kind === "music" && (
              <label className="small muted row" style={{ gap: 8, alignItems: "center" }}>
                <span style={{ width: 78 }}>duck {(tr.duck_db ?? 0).toFixed(0)} dB</span>
                <input type="range" min={-24} max={0} step={1} value={tr.duck_db ?? 0} style={{ flex: 1 }}
                  onChange={(e) => setTrack(i, "duck_db", num(e.target.value))} />
              </label>
            )}
            {tr.kind === "sfx" && (
              <label className="small muted row" style={{ gap: 8, alignItems: "center" }}>
                <span style={{ width: 78 }}>at {tr.t0.toFixed(2)} s</span>
                <input className="input" type="number" step="0.1" style={{ width: 90 }} value={tr.t0}
                  onChange={(e) => setTrack(i, "t0", num(e.target.value))} />
              </label>
            )}
          </div>
        ))}

        {/* SFX library — degrades gracefully when the engine hasn't shipped one. */}
        {sfx.length > 0 ? (
          <div className="row" style={{ gap: 6 }}>
            <select className="input" style={{ flex: 1 }} value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Add a sound effect…</option>
              {sfx.map((s) => <option key={s.slug} value={s.slug}>{s.name}{s.category ? ` (${s.category})` : ""}</option>)}
            </select>
            <button className="btn sm" disabled={!pick} onClick={addSfx}>+ Add</button>
          </div>
        ) : (
          <div className="small faint">
            {sfxAvailable ? "SFX library is empty." : "SFX library not available yet — existing SFX cues stay editable above."}
          </div>
        )}
      </div>
    </div>
  );
}

/* ----------------------------- waveform ----------------------------- */

function Waveform(props: {
  audioUrl: string | null; edl: Edl; patch: (fn: (e: Edl) => Edl) => void;
  selWord: number; setSelWord: (i: number) => void;
}) {
  const { audioUrl, edl, patch, setSelWord } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<RegionsPlugin | null>(null);
  const regionByIdx = useRef<Region[]>([]);
  const [ready, setReady] = useState(false);

  // Keep the latest patch fn reachable from region callbacks without re-init.
  const patchRef = useRef(props.patch);
  patchRef.current = props.patch;
  const selRef = useRef(props.setSelWord);
  selRef.current = props.setSelWord;

  const words = edl.captions.words;
  const mode = edl.captions.mode;

  useEffect(() => {
    if (!audioUrl || !containerRef.current) return;
    const ws = WaveSurfer.create({
      container: containerRef.current,
      url: audioUrl,
      height: 72,
      waveColor: "#5b6472",
      progressColor: "#8b93a7",
      cursorColor: "#e5e7eb",
      normalize: true,
    });
    const regions = ws.registerPlugin(RegionsPlugin.create());
    wsRef.current = ws;
    regionsRef.current = regions;
    ws.on("ready", () => setReady(true));
    ws.on("interaction", () => ws.play());
    return () => { ws.destroy(); wsRef.current = null; regionsRef.current = null; setReady(false); };
  }, [audioUrl]);

  // (Re)build one region per caption word when the timeline is ready / words change count.
  useEffect(() => {
    const regions = regionsRef.current;
    if (!regions || !ready || mode === "none") return;
    regions.clearRegions();
    regionByIdx.current = [];
    words.forEach((w, i) => {
      const region = regions.addRegion({
        id: `w${i}`,
        start: w.t0,
        end: Math.max(w.t1, w.t0 + 0.05),
        content: w.w,
        color: "rgba(96,165,250,0.22)",
        drag: true,
        resize: true,
      });
      region.on("update-end", () => {
        patchRef.current((e) => {
          if (e.captions.words[i]) {
            e.captions.words[i].t0 = Math.round(region.start * 1000) / 1000;
            e.captions.words[i].t1 = Math.round(region.end * 1000) / 1000;
          }
          return e;
        });
      });
      region.on("click", () => selRef.current(i));
      regionByIdx.current[i] = region;
    });
    // Rebuild only when the number of words changes (drag handles live updates).
  }, [ready, words.length, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Push table edits (t0/t1) back onto existing regions without a full rebuild.
  useEffect(() => {
    if (!ready || mode === "none") return;
    words.forEach((w, i) => {
      const region = regionByIdx.current[i];
      if (region && (Math.abs(region.start - w.t0) > 1e-3 || Math.abs(region.end - w.t1) > 1e-3)) {
        region.setOptions({ start: w.t0, end: Math.max(w.t1, w.t0 + 0.05) });
      }
    });
  }, [words, ready, mode]);

  if (!audioUrl) {
    return (
      <div className="card">
        <div className="card-title"><span>Caption timing</span></div>
        <div className="small faint">No voiceover track — waveform timing unavailable. Edit word times in the Captions panel.</div>
      </div>
    );
  }
  return (
    <div className="card">
      <div className="card-title">
        <span>Caption timing</span>
        <span className="small faint">drag / resize a word region to nudge its timing</span>
      </div>
      <div ref={containerRef} style={{ width: "100%" }} />
      {!ready && <div className="small muted" style={{ marginTop: 6 }}>Loading waveform…</div>}
    </div>
  );
}

/* ----------------------------- clip lane ----------------------------- */

function ClipLane(props: {
  edl: Edl; patch: (fn: (e: Edl) => Edl) => void; selClip: number; setSelClip: (i: number) => void;
}) {
  const { edl, patch, selClip, setSelClip } = props;
  const laneRef = useRef<HTMLDivElement>(null);
  const dragFrom = useRef<number | null>(null);

  const clips = edl.clips; // already order-sorted server-side / on save
  const total = clips.reduce((a, c) => a + clipDur(c), 0) || 1;

  const reorder = (from: number, to: number) => {
    if (from === to) return;
    patch((e) => {
      const arr = e.clips;
      const [moved] = arr.splice(from, 1);
      arr.splice(to, 0, moved);
      arr.forEach((c, i) => { c.order = i; });
      return e;
    });
  };

  const setClip = (i: number, field: keyof EdlClip, value: number | boolean | string) =>
    patch((e) => { (e.clips[i] as unknown as Record<string, unknown>)[field] = value; return e; });

  // Pointer-drag a trim handle: convert px delta → seconds via the block's scale.
  const startTrim = (i: number, side: "in" | "out", ev: React.PointerEvent) => {
    ev.preventDefault(); ev.stopPropagation();
    const lane = laneRef.current;
    if (!lane) return;
    const pxPerSec = lane.clientWidth / total;
    const startX = ev.clientX;
    const clip = clips[i];
    const startVal = side === "in" ? clip.in : clip.out;
    const onMove = (e: PointerEvent) => {
      const deltaSec = (e.clientX - startX) / (pxPerSec * (clip.speed || 1));
      patch((prev) => {
        const c = prev.clips[i];
        if (!c) return prev;
        if (side === "in") c.in = Math.max(0, Math.min(startVal + deltaSec, c.out - 0.05));
        else c.out = Math.max(c.in + 0.05, startVal + deltaSec);
        return prev;
      });
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const sel = clips[selClip];

  return (
    <div className="card">
      <div className="card-title">
        <span>Clips</span>
        <span className="small faint">drag to reorder · drag edges to trim</span>
      </div>
      <div ref={laneRef} className="row" style={{ gap: 4, alignItems: "stretch", minHeight: 56, width: "100%" }}>
        {clips.map((c, i) => (
          <div key={c.id} draggable
            onDragStart={() => { dragFrom.current = i; }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => { if (dragFrom.current != null) reorder(dragFrom.current, i); dragFrom.current = null; }}
            onMouseDown={() => setSelClip(i)}
            style={{
              flexGrow: clipDur(c), flexBasis: 0, minWidth: 64, position: "relative",
              background: selClip === i ? "var(--accent-soft, rgba(96,165,250,.18))" : "var(--bg-card)",
              border: `1px solid ${selClip === i ? "var(--accent)" : "var(--border)"}`,
              borderRadius: "var(--radius-sm)", padding: "8px 10px", cursor: "grab",
              display: "flex", flexDirection: "column", justifyContent: "center", overflow: "hidden",
            }}>
            <div className="small" style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.src.split("/").pop()}
            </div>
            <div className="small faint">{clipDur(c).toFixed(1)}s{c.speed !== 1 ? ` · ${c.speed}×` : ""}{c.mute ? " · muted" : ""}</div>
            <div onPointerDown={(e) => startTrim(i, "in", e)} title="trim in"
              style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 7, cursor: "ew-resize", background: "rgba(96,165,250,.5)" }} />
            <div onPointerDown={(e) => startTrim(i, "out", e)} title="trim out"
              style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 7, cursor: "ew-resize", background: "rgba(96,165,250,.5)" }} />
          </div>
        ))}
      </div>

      {sel && (
        <div className="stack" style={{ gap: 10, marginTop: 12 }}>
          <div className="field-label">Clip {selClip + 1} — {sel.src.split("/").pop()}</div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 10 }}>
            <div className="field">
              <span className="field-label">In (s)</span>
              <input className="input" type="number" step="0.05" value={sel.in}
                onChange={(e) => setClip(selClip, "in", Math.max(0, num(e.target.value)))} />
            </div>
            <div className="field">
              <span className="field-label">Out (s)</span>
              <input className="input" type="number" step="0.05" value={sel.out}
                onChange={(e) => setClip(selClip, "out", num(e.target.value))} />
            </div>
            <div className="field">
              <span className="field-label">Speed</span>
              <input className="input" type="number" step="0.05" min={0.5} max={2} value={sel.speed}
                onChange={(e) => setClip(selClip, "speed", num(e.target.value, 1))} />
            </div>
            <div className="field">
              <span className="field-label">Fit</span>
              <select className="input" value={sel.fit} onChange={(e) => setClip(selClip, "fit", e.target.value)}>
                {["cover", "contain", "window"].map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div className="field">
              <span className="field-label">Audio</span>
              <label className="checkbox-row" style={{ marginTop: 4 }}>
                <input type="checkbox" checked={!sel.mute} onChange={(e) => setClip(selClip, "mute", !e.target.checked)} />
                <span className="small">use clip sound</span>
              </label>
            </div>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn ghost sm" disabled={selClip === 0}
              onClick={() => { reorder(selClip, selClip - 1); setSelClip(Math.max(0, selClip - 1)); }}>◀ move left</button>
            <button className="btn ghost sm" disabled={selClip >= clips.length - 1}
              onClick={() => { reorder(selClip, selClip + 1); setSelClip(Math.min(clips.length - 1, selClip + 1)); }}>move right ▶</button>
            {clips.length > 1 && (
              <button className="btn danger sm"
                onClick={() => { patch((e) => { e.clips.splice(selClip, 1); e.clips.forEach((c, i) => { c.order = i; }); return e; }); setSelClip(0); }}>
                ✕ delete clip
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
