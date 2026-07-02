// Autopilot — control the autonomous scheduler, see upcoming + recent runs.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useGlobal } from "../store";
import { Card, Empty, Pill, PlatformChip, Spinner, timeAgo } from "../components/ui";

interface UpcomingRun {
  id: string;
  name: string;
  next: string; // "YYYY-MM-DD HH:MM" or "—"
}

interface AutopilotState {
  running: boolean;
  started_at: string | null;
  upcoming: UpcomingRun[];
}

const STEPS: { icon: string; title: string; detail: string }[] = [
  {
    icon: "🔥",
    title: "Trends, twice daily",
    detail: "Pulls TikTok Creative Center + Google Trends and ranks topics by relevance to your campaigns.",
  },
  {
    icon: "✍️",
    title: "Content, every morning",
    detail: "The strategist picks topics and formats, the writer drafts platform-native copy, media gets generated.",
  },
  {
    icon: "📤",
    title: "Posting at optimal times",
    detail: "Approved content goes out at each platform's best hours, with random jitter so it never looks botted.",
  },
  {
    icon: "📊",
    title: "Analytics, every 6 hours",
    detail: "Views, likes, comments, shares and sentiment are collected for every live post.",
  },
  {
    icon: "🧠",
    title: "Learning, weekly",
    detail: "Top posts feed the winners index and bandit, so next week's content leans into what actually worked.",
  },
];

/** "post-instagram-08:00" -> "instagram"; other ids are their own kind. */
function jobKind(id: string): { kind: string; platform: string | null } {
  if (id.startsWith("post-")) {
    const platform = id.split("-")[1] ?? "post";
    return { kind: "post", platform };
  }
  const kind = id.split("-")[0];
  return { kind, platform: null };
}

export default function Autopilot() {
  const { status, jobs, refreshStatus, runJob } = useGlobal();
  const [ap, setAp] = useState<AutopilotState | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<AutopilotState>("/api/autopilot").then(setAp).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 30_000);
    return () => window.clearInterval(t);
  }, [load]);

  const running = ap?.running ?? status?.autopilot.running ?? false;
  const startedAt = ap?.started_at ?? status?.autopilot.started_at ?? null;

  const toggle = async () => {
    setBusy(true);
    try {
      await api.post(`/api/autopilot/${running ? "stop" : "start"}`);
    } catch {
      /* surfaced via refetch */
    } finally {
      setBusy(false);
      load();
      refreshStatus();
    }
  };

  return (
    <>
      {/* ---- hero ---- */}
      <Card>
        <div className="row between wrap" style={{ gap: 18 }}>
          <div className="row" style={{ gap: 16 }}>
            <span
              className={`dot ${running ? "green pulse" : "amber"}`}
              style={{ width: 14, height: 14 }}
            />
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>
                Autopilot is {running ? "on" : "off"}
              </div>
              <div className="small muted">
                {running
                  ? startedAt
                    ? `Running since ${startedAt} · ${status?.timezone ?? ""}`
                    : "Running"
                  : "Mark is idle — nothing is generated or posted until you start it."}
              </div>
            </div>
          </div>
          <div className="row wrap">
            <button
              className={`btn ${running ? "danger" : "primary"}`}
              disabled={busy}
              onClick={toggle}
            >
              {running ? "⏹ Stop autopilot" : "▶ Start autopilot"}
            </button>
            <button
              className="btn"
              onClick={() => runJob(() => api.post<{ job_id: string }>("/api/autopilot/run-once"))}
            >
              ⚡ Run one cycle now
            </button>
          </div>
        </div>
        <div className="small faint" style={{ marginTop: 12 }}>
          One cycle = trends → generate content → (post, if auto-approve is on) → collect
          analytics. Drafts land in the Studio for review either way.
        </div>
      </Card>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1.4fr" }}>
        {/* ---- how it works ---- */}
        <Card title="How autopilot works">
          <div className="stack" style={{ gap: 14 }}>
            {STEPS.map((s, i) => (
              <div className="row" key={i} style={{ alignItems: "flex-start" }}>
                <div className="feed-icon">{s.icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{s.title}</div>
                  <div className="small muted">{s.detail}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="small faint" style={{ marginTop: 14 }}>
            The schedule (crons, posting times, jitter) is editable in{" "}
            <Link to="/settings">Settings</Link>.
          </div>
        </Card>

        {/* ---- upcoming runs ---- */}
        <Card title="Upcoming runs">
          {ap == null ? (
            <div className="row" style={{ justifyContent: "center", padding: 24 }}>
              <Spinner />
            </div>
          ) : ap.upcoming.length === 0 ? (
            <Empty
              icon="🗓"
              title="Nothing scheduled"
              hint="Enable platforms and set posting times in Settings."
            />
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Kind</th>
                  <th className="num">Next run</th>
                </tr>
              </thead>
              <tbody>
                {ap.upcoming.map((u) => {
                  const { kind, platform } = jobKind(u.id);
                  return (
                    <tr key={u.id}>
                      <td style={{ fontWeight: 600 }}>{u.name}</td>
                      <td>
                        {platform ? (
                          <PlatformChip platform={platform} />
                        ) : (
                          <Pill kind="accent">{kind}</Pill>
                        )}
                      </td>
                      <td className="num mono small">{u.next}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      {/* ---- recent jobs ---- */}
      <Card title="Recent jobs">
        {jobs.length === 0 ? (
          <Empty
            icon="🕰"
            title="No jobs yet"
            hint="Start autopilot or run a cycle — every job shows up here live."
          />
        ) : (
          <div className="stack" style={{ gap: 14 }}>
            {jobs.map((j) => (
              <div key={j.id}>
                <div className="row between wrap" style={{ gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{j.label}</span>
                  {j.status === "running" || j.status === "queued" ? (
                    <Pill kind="accent">
                      <Spinner /> {j.status}
                    </Pill>
                  ) : j.status === "done" ? (
                    <Pill kind="posted">done</Pill>
                  ) : (
                    <Pill kind="failed">failed</Pill>
                  )}
                </div>
                <div className="small muted" style={{ marginTop: 2 }}>
                  {j.message || j.status} · {timeAgo(j.created_at)}
                </div>
                {j.status === "failed" && j.error != null && (
                  <div className="small" style={{ color: "var(--red)", marginTop: 2 }}>
                    {j.error}
                  </div>
                )}
                <div className="progress-track">
                  <div
                    className={`progress-fill ${
                      j.status === "done" ? "done" : j.status === "failed" ? "failed" : ""
                    }`}
                    style={{
                      width: `${Math.max(j.progress * 100, j.status === "done" ? 100 : 4)}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <p className="small faint">
        Safety: daily per-platform caps and the approval gate protect your accounts — nothing is
        posted without your sign-off unless you turn on auto-approve (off by default).
      </p>
    </>
  );
}
