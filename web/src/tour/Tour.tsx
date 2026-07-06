// Guided tour — a dependency-free spotlight walkthrough across every page.
//
// How it works: steps (steps.ts) declare a route, a CSS target and copy. The
// engine navigates to the step's route, waits for the target to render,
// scrolls it into view, and draws a "spotlight" over it (one absolutely
// positioned box whose giant box-shadow dims everything else) plus a tooltip
// card with the explanation and Back/Next controls. A full-screen backdrop
// blocks page interaction while the tour is running. Steps whose target is
// missing (e.g. empty states) fall back to a centered card so the tour never
// dead-ends. Keyboard: ← → advance, Esc exits.
import {
  ReactNode, createContext, useCallback, useContext, useEffect,
  useMemo, useRef, useState,
} from "react";
import { useNavigate } from "react-router-dom";
import { TOUR_STEPS, TourStep } from "./steps";

const DONE_KEY = "mark.tour.done";

interface TourCtx {
  active: boolean;
  start: () => void;
  seen: boolean; // has the user ever finished/skipped the tour?
}

const Ctx = createContext<TourCtx>({ active: false, start: () => {}, seen: true });

export function useTour() {
  return useContext(Ctx);
}

export function TourProvider({ children }: { children: ReactNode }) {
  const [idx, setIdx] = useState<number | null>(null);
  const [seen, setSeen] = useState<boolean>(() => localStorage.getItem(DONE_KEY) === "1");

  const start = useCallback(() => setIdx(0), []);
  const stop = useCallback(() => {
    setIdx(null);
    localStorage.setItem(DONE_KEY, "1");
    setSeen(true);
  }, []);

  const value = useMemo(() => ({ active: idx !== null, start, seen }), [idx, start, seen]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {idx !== null && <TourOverlay idx={idx} setIdx={setIdx} stop={stop} />}
    </Ctx.Provider>
  );
}

// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------
interface Rect { top: number; left: number; width: number; height: number }

function TourOverlay({ idx, setIdx, stop }: {
  idx: number; setIdx: (i: number) => void; stop: () => void;
}) {
  const navigate = useNavigate();
  const step: TourStep = TOUR_STEPS[idx];
  const [rect, setRect] = useState<Rect | null>(null);
  const [settled, setSettled] = useState(false); // target found (or given up)
  const targetEl = useRef<Element | null>(null);

  const next = useCallback(() => {
    if (idx + 1 >= TOUR_STEPS.length) stop();
    else setIdx(idx + 1);
  }, [idx, setIdx, stop]);
  const back = useCallback(() => { if (idx > 0) setIdx(idx - 1); }, [idx, setIdx]);

  // Navigate + locate the target each time the step changes.
  useEffect(() => {
    let cancelled = false;
    setSettled(false);
    setRect(null);
    targetEl.current = null;
    if (window.location.pathname !== step.route) navigate(step.route);

    const deadline = Date.now() + 3500;
    const find = () => {
      if (cancelled) return;
      const el = step.target ? document.querySelector(step.target) : null;
      if (el) {
        targetEl.current = el;
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        // Give the smooth scroll a beat before measuring.
        setTimeout(() => { if (!cancelled) { measure(); setSettled(true); } }, 350);
      } else if (Date.now() < deadline) {
        setTimeout(find, 120);
      } else {
        setSettled(true); // no target — centered fallback
      }
    };
    // Small delay so the destination page mounts after navigate().
    const t = setTimeout(find, 60);
    return () => { cancelled = true; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  const measure = useCallback(() => {
    const el = targetEl.current;
    if (!el) { setRect(null); return; }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, []);

  // Track layout shifts while the spotlight is up.
  useEffect(() => {
    const on = () => measure();
    window.addEventListener("resize", on);
    window.addEventListener("scroll", on, true);
    return () => {
      window.removeEventListener("resize", on);
      window.removeEventListener("scroll", on, true);
    };
  }, [measure]);

  // Keyboard controls.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key === "Escape") stop();
      else if (e.key === "ArrowRight" || e.key === "Enter") next();
      else if (e.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [next, back, stop]);

  const pad = 6;
  const spot = rect && {
    top: rect.top - pad, left: rect.left - pad,
    width: rect.width + pad * 2, height: rect.height + pad * 2,
  };

  return (
    <div className="tour-root" data-tour-active>
      {/* Click-catcher: the page is read-only while the tour runs. */}
      <div className="tour-backdrop" style={spot ? undefined : { background: "rgba(5, 8, 13, 0.7)" }}
        onClick={next} />
      {spot && (
        <div className="tour-spotlight" style={{
          top: spot.top, left: spot.left, width: spot.width, height: spot.height,
        }} />
      )}
      {settled && <Tooltip step={step} idx={idx} total={TOUR_STEPS.length} rect={spot}
        onNext={next} onBack={back} onSkip={stop} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tooltip card
// ---------------------------------------------------------------------------
const TIP_W = 380;

function Tooltip({ step, idx, total, rect, onNext, onBack, onSkip }: {
  step: TourStep; idx: number; total: number; rect: Rect | null;
  onNext: () => void; onBack: () => void; onSkip: () => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [tipH, setTipH] = useState(220);
  // Measure the real rendered height so positioning never pushes the buttons
  // off-screen (step bodies vary a lot in length).
  useEffect(() => {
    if (ref.current) setTipH(ref.current.offsetHeight);
  }, [step, rect]);

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let style: React.CSSProperties;
  if (!rect) {
    style = { top: vh / 2, left: vw / 2, transform: "translate(-50%, -50%)" };
  } else {
    // Prefer below the target; flip above when there's no room; always clamp
    // into the viewport so the controls stay clickable.
    const below = rect.top + rect.height + 14;
    let top = below + tipH <= vh - 12 ? below : rect.top - tipH - 14;
    top = Math.min(Math.max(12, top), Math.max(12, vh - tipH - 12));
    const left = Math.min(Math.max(12, rect.left + rect.width / 2 - TIP_W / 2), vw - TIP_W - 12);
    style = { top, left };
  }
  const last = idx === total - 1;
  return (
    <div className="tour-tip" ref={ref} style={style} onClick={(e) => e.stopPropagation()}>
      <div className="tour-progress">
        <div className="tour-progress-fill" style={{ width: `${((idx + 1) / total) * 100}%` }} />
      </div>
      <div className="tour-tip-head">
        <span className="tour-count">{idx + 1} / {total}</span>
        <span className="tour-page">{step.pageLabel}</span>
      </div>
      <div className="tour-tip-title">{step.title}</div>
      <div className="tour-tip-body">
        {step.body.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}
      </div>
      <div className="tour-tip-actions">
        <button className="btn ghost sm" onClick={onSkip}>Exit tour</button>
        <div style={{ flex: 1 }} />
        {idx > 0 && <button className="btn sm" onClick={onBack}>← Back</button>}
        <button className="btn primary sm" onClick={onNext} data-tour-next>
          {last ? "Finish ✓" : "Next →"}
        </button>
      </div>
    </div>
  );
}
