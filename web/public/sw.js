// Minimal service worker: exists so the app is installable (Add to Home
// Screen). Everything is network-first — the review feed is live data and the
// backend runs on the same host, so offline caching would only show stale
// queues. The install prompt is the feature, not offline mode.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => { /* network passthrough */ });
