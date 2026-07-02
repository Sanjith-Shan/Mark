// Global app state: status, campaigns, live job/event stream, toasts.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  ReactNode,
} from "react";
import { api, subscribeEvents, MarkEvent } from "./api";
import { Campaign, Job, Status } from "./types";

interface GlobalState {
  status: Status | null;
  campaigns: Campaign[];
  jobs: Job[];
  refreshStatus: () => void;
  refreshCampaigns: () => void;
  /** bumps whenever a content event arrives — pages listen to reload lists */
  contentVersion: number;
  /** bumps once each time a job finishes (done or failed) — edge-triggered */
  jobsDoneVersion: number;
  runJob: (start: () => Promise<{ job_id: string }>) => Promise<void>;
  toast: (msg: string, level?: "info" | "error") => void;
}

const Ctx = createContext<GlobalState>(null as unknown as GlobalState);
export const useGlobal = () => useContext(Ctx);

interface Toast { id: number; msg: string; level: "info" | "error" }

export function GlobalProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [contentVersion, setContentVersion] = useState(0);
  const [jobsDoneVersion, setJobsDoneVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const jobStatusRef = useRef<Map<string, string>>(new Map());

  const refreshStatus = useCallback(() => {
    api.get<Status>("/api/status").then(setStatus).catch(() => {});
  }, []);
  const refreshCampaigns = useCallback(() => {
    api.get<Campaign[]>("/api/campaigns").then(setCampaigns).catch(() => {});
  }, []);

  const toast = useCallback((msg: string, level: "info" | "error" = "info") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, msg, level }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshCampaigns();
    api.get<Job[]>("/api/jobs").then(setJobs).catch(() => {});
    const off = subscribeEvents((e: MarkEvent) => {
      if (e.kind === "job" && e.job) {
        const job = e.job as Job;
        const prevStatus = jobStatusRef.current.get(job.id);
        jobStatusRef.current.set(job.id, job.status);
        setJobs((prev) => {
          const rest = prev.filter((j) => j.id !== job.id);
          return [job, ...rest].slice(0, 30);
        });
        // Edge-trigger: fire once per job completion, not on every progress tick.
        if ((job.status === "done" || job.status === "failed") && prevStatus !== job.status) {
          setJobsDoneVersion((v) => v + 1);
          refreshStatus();
        }
      } else if (e.kind === "content") {
        setContentVersion((v) => v + 1);
        refreshStatus();
      } else if (e.kind === "autopilot") {
        refreshStatus();
      }
    });
    return off;
  }, [refreshStatus, refreshCampaigns]);

  const runJob = useCallback(async (start: () => Promise<{ job_id: string }>) => {
    try {
      await start();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Request failed", "error");
    }
  }, [toast]);

  const value = useMemo(
    () => ({ status, campaigns, jobs, refreshStatus, refreshCampaigns,
             contentVersion, jobsDoneVersion, runJob, toast }),
    [status, campaigns, jobs, refreshStatus, refreshCampaigns,
     contentVersion, jobsDoneVersion, runJob, toast],
  );

  return (
    <Ctx.Provider value={value}>
      {children}
      <JobToasts jobs={jobs} toasts={toasts} />
    </Ctx.Provider>
  );
}

function JobToasts({ jobs, toasts }: { jobs: Job[]; toasts: Toast[] }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  // Show active jobs + recently finished (within their finish, until dismissed).
  const visible = jobs.filter(
    (j) => !dismissed.has(j.id) &&
      (j.status === "running" || j.status === "queued" ||
        (j.finished_at != null && recentlyFinished(j.finished_at))),
  ).slice(0, 4);

  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className="toast" style={t.level === "error" ? { borderColor: "rgba(248,113,113,.5)" } : undefined}>
          <div className="row between">
            <span style={{ fontWeight: 600, fontSize: 13, color: t.level === "error" ? "var(--red)" : undefined }}>
              {t.msg}
            </span>
          </div>
        </div>
      ))}
      {visible.map((j) => (
        <div key={j.id} className="toast">
          <div className="row between">
            <span style={{ fontWeight: 600, fontSize: 13 }}>{j.label}</span>
            <button
              className="btn ghost sm"
              onClick={() => setDismissed((d) => new Set(d).add(j.id))}
            >✕</button>
          </div>
          <div className="small muted" style={{ marginTop: 2 }}>
            {j.status === "failed" ? (j.error ?? "failed") : (j.message || j.status)}
          </div>
          <div className="progress-track">
            <div
              className={`progress-fill ${j.status === "done" ? "done" : j.status === "failed" ? "failed" : ""}`}
              style={{ width: `${Math.max(j.progress * 100, j.status === "done" ? 100 : 4)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function recentlyFinished(finishedAt: string): boolean {
  const t = new Date(finishedAt.replace(" ", "T")).getTime();
  return Date.now() - t < 6000;
}
