// The phone review feed — a TikTok-style vertical audit of everything queued
// to post. Full-screen (rendered outside the sidebar shell), installable as a
// PWA. Interactions: tap = sound, hold the rate button and slide = 1-10 rating
// (saves on release), ✓/✕ = approve/reject, note sheet = free-text feedback.
// Watch time / replays are measured passively and sent when you scroll away —
// all of it feeds the taste learner on the backend.
import {
  useCallback, useEffect, useMemo, useRef, useState,
} from "react";
import { Link } from "react-router-dom";
import { review, subscribeEvents, ReviewSubmit } from "../api";
import { ReviewFeedItem, ReviewAccount, PLATFORM_LABELS } from "../types";
import { useGlobal } from "../store";

interface WatchState {
  seconds: number;
  duration: number;
  replays: number;
  completed: boolean;
  lastTime: number;
  dirty: boolean;
}

export default function Review() {
  const { toast } = useGlobal();
  const [items, setItems] = useState<ReviewFeedItem[] | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [muted, setMuted] = useState(true);
  const [account, setAccount] = useState<ReviewAccount | null>(null);
  const [noteFor, setNoteFor] = useState<{ id: number; reject: boolean } | null>(null);
  const [learned, setLearned] = useState<string[] | null>(null);
  const watchRef = useRef<Map<number, WatchState>>(new Map());
  const feedRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    review.feed().then(setItems).catch((e) => toast(e.message ?? "load failed", "error"));
  }, [toast]);
  useEffect(load, [load]);

  // "AI learned:" cards streamed back after the learn job finishes.
  useEffect(() => subscribeEvents((e) => {
    if (e.kind === "review" && Array.isArray(e.learned) && e.learned.length) {
      setLearned(e.learned as string[]);
      setTimeout(() => setLearned(null), 9000);
    }
  }), []);

  const flushWatch = useCallback((contentId: number) => {
    const w = watchRef.current.get(contentId);
    if (!w || !w.dirty || w.seconds < 0.5) return;
    w.dirty = false;
    review.submit(contentId, {
      watch_seconds: Math.round(w.seconds * 10) / 10,
      video_duration: Math.round(w.duration * 10) / 10,
      replays: w.replays,
      completed: w.completed,
    }, { keepalive: true }).catch(() => { w.dirty = true; });
  }, []);

  // Flush telemetry when the app is backgrounded / closed.
  useEffect(() => {
    const flushAll = () => watchRef.current.forEach((_, id) => flushWatch(id));
    window.addEventListener("pagehide", flushAll);
    document.addEventListener("visibilitychange", flushAll);
    return () => {
      window.removeEventListener("pagehide", flushAll);
      document.removeEventListener("visibilitychange", flushAll);
      flushAll();
    };
  }, [flushWatch]);

  // Flush the PREVIOUS video's telemetry whenever the active card changes.
  // Done here (as an effect on activeId) rather than inside the onActive
  // callback — a callback captured by each card's IntersectionObserver would
  // close over a stale activeId and never flush anything.
  const onActive = useCallback((id: number) => setActiveId(id), []);
  const prevActiveRef = useRef<number | null>(null);
  useEffect(() => {
    const prev = prevActiveRef.current;
    if (prev !== null && prev !== activeId) flushWatch(prev);
    prevActiveRef.current = activeId;
  }, [activeId, flushWatch]);

  const patchItem = useCallback((id: number, patch: Partial<ReviewFeedItem>) => {
    setItems((prev) => prev?.map((x) => (x.id === id ? { ...x, ...patch } : x)) ?? prev);
  }, []);

  const submit = useCallback(async (item: ReviewFeedItem, body: ReviewSubmit) => {
    const w = watchRef.current.get(item.id);
    if (w) {
      body.watch_seconds = Math.round(w.seconds * 10) / 10;
      body.video_duration = Math.round(w.duration * 10) / 10;
      body.replays = w.replays;
      body.completed = w.completed;
      w.dirty = false;
    }
    try {
      const out = await review.submit(item.id, body);
      patchItem(item.id, { review: out.review, status: out.status });
      return out;
    } catch (e) {
      toast(e instanceof Error ? e.message : "save failed", "error");
      return null;
    }
  }, [patchItem, toast]);

  const scrollNext = useCallback((fromId: number) => {
    const idx = items?.findIndex((x) => x.id === fromId) ?? -1;
    const next = feedRef.current?.children[idx + 1] as HTMLElement | undefined;
    next?.scrollIntoView({ behavior: "smooth" });
  }, [items]);

  if (items === null) {
    return <div className="rv-root rv-center"><span className="spinner" /> Loading queue…</div>;
  }
  if (items.length === 0) {
    return (
      <div className="rv-root rv-center" style={{ flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 40 }}>🎬</div>
        <div style={{ fontWeight: 700 }}>Queue is clear</div>
        <div className="small muted" style={{ textAlign: "center", maxWidth: 260 }}>
          Nothing waiting for review. New drafts appear here the moment Mark generates them.
        </div>
        <button className="btn" onClick={load}>Refresh</button>
        <Link className="btn ghost sm" to="/">Open dashboard</Link>
      </div>
    );
  }

  return (
    <div className="rv-root">
      <div className="rv-feed" ref={feedRef}>
        {items.map((item) => (
          <FeedCard
            key={item.id}
            item={item}
            muted={muted}
            active={activeId === item.id}
            onActive={onActive}
            onToggleMute={() => setMuted((m) => !m)}
            watchRef={watchRef}
            onApprove={async () => {
              const out = await submit(item, { action: "approve" });
              if (out) { toast(`#${item.id} approved ✓`); scrollNext(item.id); }
            }}
            onReject={() => setNoteFor({ id: item.id, reject: true })}
            onNote={() => setNoteFor({ id: item.id, reject: false })}
            onRate={async (rating) => {
              const out = await submit(item, { rating });
              if (out) toast(`Rated ${rating}/10 — learning from it…`);
            }}
            onAccount={() => review.account(item.campaign.id).then(setAccount)
              .catch(() => toast("couldn't load account", "error"))}
          />
        ))}
      </div>

      <div className="rv-topbar">
        <Link to="/" className="rv-chip" style={{ textDecoration: "none" }}>← Mark</Link>
        <span className="rv-chip">{items.length} in queue</span>
        <button className="rv-chip" onClick={load}>↻</button>
      </div>

      {learned && (
        <div className="rv-learned" onClick={() => setLearned(null)}>
          <div className="rv-learned-title">🧠 What Mark took away</div>
          {learned.slice(0, 4).map((l, i) => <div key={i} className="rv-learned-line">{l}</div>)}
        </div>
      )}

      {noteFor && (
        <NoteSheet
          reject={noteFor.reject}
          onClose={() => setNoteFor(null)}
          onSend={async (text) => {
            const item = items.find((x) => x.id === noteFor.id);
            if (!item) return;
            const out = await submit(item, {
              feedback: text || undefined,
              action: noteFor.reject ? "reject" : undefined,
            });
            if (out) {
              toast(noteFor.reject ? `#${item.id} rejected` : "Feedback sent — learning…");
              if (noteFor.reject) scrollNext(item.id);
            }
            setNoteFor(null);
          }}
        />
      )}

      {account && <AccountSheet account={account} onClose={() => setAccount(null)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function FeedCard(props: {
  item: ReviewFeedItem;
  muted: boolean;
  active: boolean;
  onActive: (id: number) => void;
  onToggleMute: () => void;
  watchRef: React.MutableRefObject<Map<number, WatchState>>;
  onApprove: () => void;
  onReject: () => void;
  onNote: () => void;
  onRate: (rating: number) => void;
  onAccount: () => void;
}) {
  const { item, muted, active } = props;
  const videoRef = useRef<HTMLVideoElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const video = item.media.find((m) => m.kind === "video");
  const image = item.media.find((m) => m.kind === "image");

  // Visibility → play/pause + mark active.
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((en) => {
        if (en.intersectionRatio >= 0.6) props.onActive(item.id);
      }),
      { threshold: [0.6] },
    );
    obs.observe(el);
    return () => obs.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (active) { v.play().catch(() => {}); } else { v.pause(); }
  }, [active]);

  // Watch telemetry: accumulate real played seconds, detect loops.
  const onTimeUpdate = () => {
    const v = videoRef.current;
    if (!v) return;
    const map = props.watchRef.current;
    let w = map.get(item.id);
    if (!w) {
      w = { seconds: 0, duration: v.duration || 0, replays: 0, completed: false,
            lastTime: v.currentTime, dirty: false };
      map.set(item.id, w);
    }
    w.duration = v.duration || w.duration;
    const dt = v.currentTime - w.lastTime;
    if (dt > 0 && dt < 2) { w.seconds += dt; w.dirty = true; }
    if (dt < -1) { // looped back to the start
      w.replays += 1;
      w.completed = true;
      w.dirty = true;
    }
    if (w.duration && v.currentTime >= w.duration - 0.3) w.completed = true;
    w.lastTime = v.currentTime;
  };

  const rating = item.review?.rating ?? null;
  const when = item.scheduled_at
    ? `scheduled ${fmtWhen(item.scheduled_at)}`
    : item.status === "approved" ? "next optimal slot" : "awaiting approval";

  return (
    <div className="rv-card" ref={cardRef}>
      {video ? (
        <video
          ref={videoRef}
          className="rv-video"
          src={video.url}
          playsInline
          loop
          muted={muted}
          preload="metadata"
          onTimeUpdate={onTimeUpdate}
          onClick={props.onToggleMute}
        />
      ) : image ? (
        <img className="rv-video" src={image.url} alt="" onClick={props.onToggleMute} />
      ) : (
        <div className="rv-video rv-center muted">no media</div>
      )}

      {muted && video && <div className="rv-mute-hint">tap for sound 🔇</div>}

      {/* top meta */}
      <div className="rv-meta-top">
        <button className="rv-account" onClick={props.onAccount}>
          {item.character?.image
            ? <img src={item.character.image} alt="" />
            : <span className="rv-avatar-fallback">{item.campaign.name.slice(0, 1)}</span>}
          <span>
            <b>{item.campaign.name}</b>
            <small>
              {PLATFORM_LABELS[item.platform] ?? item.platform}
              {item.campaign.upload_profile ? ` · @${item.campaign.upload_profile}` : ""}
              {item.character ? ` · ${item.character.name}` : ""}
            </small>
          </span>
        </button>
        <div className="rv-when">
          <span className={`pill ${item.status}`}>{item.status}</span>
          <small>{when}</small>
          {item.experiment && (
            <small className="rv-exp">🧪 {item.experiment.aspect}: {item.experiment.variant}</small>
          )}
        </div>
      </div>

      {/* caption */}
      <div className={`rv-caption ${expanded ? "expanded" : ""}`}
           onClick={() => setExpanded((e) => !e)}>
        {item.hook && <div className="rv-hook">{item.hook}</div>}
        {item.caption && <div className="rv-caption-text">{item.caption}</div>}
        {item.hashtags?.length > 0 && (
          <div className="rv-tags">{item.hashtags.slice(0, 6).join(" ")}</div>
        )}
      </div>

      {/* action rail */}
      <div className="rv-rail">
        <RateButton current={rating} onRate={props.onRate} />
        <button className="rv-rail-btn approve" onClick={props.onApprove}
                disabled={item.status === "approved"}
                title="Approve for posting">
          ✓<small>{item.status === "approved" ? "approved" : "approve"}</small>
        </button>
        <button className="rv-rail-btn reject" onClick={props.onReject} title="Reject">
          ✕<small>reject</small>
        </button>
        <button className="rv-rail-btn" onClick={props.onNote} title="Leave feedback">
          💬<small>note</small>
        </button>
      </div>
    </div>
  );
}

/* Hold → vertical slider appears → slide to 1-10 → release saves.
   A bare tap is a no-op: saving only arms after the finger MOVES or the hold
   lasts ≥250ms — otherwise a mis-tap on the ★ would silently submit a bogus
   rating (and bogus ratings train the taste learner). */
const HOLD_ARM_MS = 250;

function RateButton({ current, onRate }: {
  current: number | null;
  onRate: (r: number) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [value, setValue] = useState(current ?? 7);
  const trackEl = useRef<HTMLDivElement>(null);
  const downAt = useRef(0);
  const moved = useRef(false);
  const lastValue = useRef(current ?? 7);

  const ratingFromY = (clientY: number) => {
    // Measure the REAL rendered track — hardcoded viewport fractions drift
    // from the flex-centered layout and make the ticks lag the finger.
    const rect = trackEl.current?.getBoundingClientRect();
    const top = rect ? rect.top : window.innerHeight * 0.2;
    const height = rect ? rect.height : window.innerHeight * 0.6;
    const frac = 1 - Math.min(Math.max((clientY - top) / height, 0), 1);
    return Math.max(1, Math.min(10, Math.round(frac * 9 + 1)));
  };

  const setBoth = (r: number) => {
    if (r !== lastValue.current) {
      lastValue.current = r;
      navigator.vibrate?.(4); // side effect OUTSIDE the state updater
      setValue(r);
    }
  };

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    downAt.current = Date.now();
    moved.current = false;
    lastValue.current = current ?? 7;
    setValue(current ?? 7);
    setDragging(true);
    navigator.vibrate?.(8);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return;
    moved.current = true;
    setBoth(ratingFromY(e.clientY));
  };
  const onPointerUp = () => {
    if (!dragging) return;
    setDragging(false);
    const held = Date.now() - downAt.current >= HOLD_ARM_MS;
    if (moved.current || held) onRate(lastValue.current);
  };

  return (
    <>
      <button
        className={`rv-rail-btn rate ${current != null ? "rated" : ""}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => setDragging(false)}
        onContextMenu={(e) => e.preventDefault()}
        title="Hold and slide to rate"
      >
        {current != null ? current : "★"}
        <small>{current != null ? "rated" : "hold to rate"}</small>
      </button>
      {dragging && (
        <div className="rv-slider">
          <div className="rv-slider-value">{value}</div>
          <div className="rv-slider-track" ref={trackEl}>
            <div className="rv-slider-fill" style={{ height: `${((value - 1) / 9) * 100}%` }} />
            {Array.from({ length: 10 }, (_, i) => 10 - i).map((n) => (
              <span key={n} className={`rv-slider-tick ${n <= value ? "on" : ""}`}>{n}</span>
            ))}
          </div>
          <div className="rv-slider-hint">slide, release to save</div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
function NoteSheet({ reject, onClose, onSend }: {
  reject: boolean;
  onClose: () => void;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  return (
    <div className="rv-sheet-backdrop" onClick={onClose}>
      <div className="rv-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="rv-sheet-title">
          {reject ? "Reject — tell Mark why" : "Feedback for Mark"}
        </div>
        <textarea
          autoFocus
          rows={4}
          placeholder={reject
            ? "e.g. hook takes too long, voiceover sounds robotic…"
            : "What's working, what isn't — Mark learns from every note."}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className={`btn ${reject ? "danger" : "primary"}`}
                  onClick={() => onSend(text.trim())}
                  disabled={!reject && !text.trim()}>
            {reject ? "Reject" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function AccountSheet({ account, onClose }: {
  account: ReviewAccount;
  onClose: () => void;
}) {
  const c = account.campaign;
  return (
    <div className="rv-sheet-backdrop" onClick={onClose}>
      <div className="rv-sheet rv-account-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="rv-account-head">
          <div className="rv-avatar-fallback big">{c.name.slice(0, 1)}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 17 }}>{c.name}</div>
            <div className="small muted">
              {c.kind === "entertainment" ? "entertainment page" : "product campaign"}
              {c.upload_profile ? ` · @${c.upload_profile}` : ""}
            </div>
          </div>
          <button className="btn ghost sm" onClick={onClose}>✕</button>
        </div>
        <div className="rv-account-stats">
          <span><b>{account.stats.posts ?? 0}</b> posts</span>
          <span><b>{account.stats.rated ?? 0}</b> rated</span>
          <span><b>{account.stats.avg_rating ? account.stats.avg_rating.toFixed(1) : "—"}</b> avg ★</span>
        </div>
        {account.characters.length > 0 && (
          <div className="rv-account-chars">
            {account.characters.map((ch) => (
              <span key={ch.id} className="rv-chip">
                {ch.image && <img src={ch.image} alt="" />}
                {ch.name}
              </span>
            ))}
          </div>
        )}
        <div className="small muted" style={{ margin: "6px 0 10px" }}>
          {c.description?.slice(0, 180)}
        </div>
        <div className="rv-grid">
          {account.items.map((it) => {
            const v = it.media.find((m) => m.kind === "video");
            const img = it.media.find((m) => m.kind === "image");
            return (
              <div key={it.id} className="rv-grid-item">
                {v ? <video src={v.url} muted preload="metadata" playsInline />
                   : img ? <img src={img.url} alt="" /> : <div className="rv-grid-empty" />}
                <span className={`rv-grid-status ${it.status}`}>{it.status}</span>
                {it.review?.rating != null && (
                  <span className="rv-grid-rating">★ {it.review.rating}</span>
                )}
                {it.latest_metric && (
                  <span className="rv-grid-views">{fmtNum(it.latest_metric.views)} views</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function fmtWhen(ts: string): string {
  try {
    const d = new Date(ts.includes("T") ? ts : ts.replace(" ", "T") + "Z");
    return d.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}
