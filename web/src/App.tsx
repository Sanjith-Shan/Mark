import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { GlobalProvider, useGlobal } from "./store";
import { TourProvider, useTour } from "./tour/Tour";
import Dashboard from "./pages/Dashboard";
import Campaigns from "./pages/Campaigns";
import Studio from "./pages/Studio";
import Analytics from "./pages/Analytics";
import Trends from "./pages/Trends";
import Playbook from "./pages/Playbook";
import Learn from "./pages/Learn";
import Autopilot from "./pages/Autopilot";
import Settings from "./pages/Settings";
import Editor from "./pages/Editor";
import { Pill } from "./components/ui";
import { api } from "./api";

// Inline icons (Lucide-style outlines, 17px).
function icon(paths: string) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: paths }} />
  );
}

const I = {
  home: icon('<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'),
  flag: icon('<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>'),
  sparkles: icon('<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>'),
  chart: icon('<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>'),
  fire: icon('<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>'),
  brain: icon('<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/>'),
  bolt: icon('<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>'),
  gear: icon('<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>'),
  book: icon('<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>'),
};

const NAV = [
  { to: "/", label: "Dashboard", icon: I.home },
  { to: "/campaigns", label: "Campaigns", icon: I.flag },
  { to: "/studio", label: "Studio", icon: I.sparkles },
  { to: "/analytics", label: "Analytics", icon: I.chart },
  { to: "/trends", label: "Trends", icon: I.fire },
  { to: "/playbook", label: "Playbook", icon: I.book },
  { to: "/learn", label: "Learn", icon: I.brain },
  { to: "/autopilot", label: "Autopilot", icon: I.bolt },
  { to: "/settings", label: "Settings", icon: I.gear },
];

const TITLES: Record<string, string> = {
  "/": "Dashboard", "/campaigns": "Campaigns", "/studio": "Content Studio",
  "/analytics": "Analytics", "/trends": "Trends", "/playbook": "Playbook",
  "/learn": "What's working",
  "/autopilot": "Autopilot", "/settings": "Settings",
  "/editor": "Clip Editor",
};

function titleFor(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname];
  if (pathname.startsWith("/editor")) return TITLES["/editor"];
  return "Mark";
}

export default function App() {
  return (
    <GlobalProvider>
      <TourProvider>
        <Shell />
      </TourProvider>
    </GlobalProvider>
  );
}

function Shell() {
  const { status } = useGlobal();
  const loc = useLocation();
  const drafts = status?.counts?.draft ?? 0;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-mark">M</div>
          Mark
        </div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            end={n.to === "/"}
          >
            {n.icon}
            <span style={{ flex: 1 }}>{n.label}</span>
            {n.to === "/studio" && drafts > 0 && (
              <span className="pill draft" style={{ fontSize: 10.5, padding: "1px 7px" }}>{drafts}</span>
            )}
          </NavLink>
        ))}
        <TutorialButton />
        <div className="sidebar-foot">
          Marketing on autopilot,
          <br />so you can keep building.
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>{titleFor(loc.pathname)}</h1>
          <div className="topbar-spacer" />
          <span data-tour="autopilot-toggle"><AutopilotIndicator /></span>
          <span data-tour="providers"><ProviderDots /></span>
        </header>
        <div className="content">
          <div className="content-inner">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/campaigns" element={<Campaigns />} />
              <Route path="/studio" element={<Studio />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/trends" element={<Trends />} />
              <Route path="/playbook" element={<Playbook />} />
              <Route path="/learn" element={<Learn />} />
              <Route path="/autopilot" element={<Autopilot />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/editor/:contentId" element={<Editor />} />
            </Routes>
          </div>
        </div>
      </div>
    </div>
  );
}

function TutorialButton() {
  const { start, seen, active } = useTour();
  if (active) return null;
  return (
    <button className="tour-nav-btn" onClick={start} data-tour-start
      title="A guided walkthrough of every page">
      <span className={`dot ${seen ? "" : "green pulse"}`}
        style={seen ? { background: "var(--text-faint)" } : undefined} />
      <span style={{ flex: 1, textAlign: "left" }}>Tutorial</span>
      {!seen && <span className="pill accent" style={{ fontSize: 10, padding: "1px 7px" }}>new</span>}
    </button>
  );
}

function AutopilotIndicator() {
  const { status, refreshStatus, toast } = useGlobal();
  const running = status?.autopilot.running ?? false;
  const toggle = async () => {
    try {
      await api.post(`/api/autopilot/${running ? "stop" : "start"}`);
      refreshStatus();
    } catch (e) {
      toast(e instanceof Error ? e.message : "failed", "error");
    }
  };
  return (
    <button className={`btn sm ${running ? "success" : ""}`} onClick={toggle} title="Toggle the autonomous scheduler">
      <span className={`dot ${running ? "green pulse" : "amber"}`} />
      Autopilot {running ? "on" : "off"}
    </button>
  );
}

function ProviderDots() {
  const { status } = useGlobal();
  if (!status) return null;
  const live = Object.values(status.providers).filter((v) => v === "live").length;
  const total = Object.keys(status.providers).length;
  const allLive = live >= 3; // openai + fal + upload_post
  return (
    <Pill kind={allLive ? "live" : "mock"}>
      <span className={`dot ${allLive ? "green" : "amber"}`} />
      {allLive ? "live" : `offline mode · ${live}/${total} keys`}
    </Pill>
  );
}
