// The tutorial script — every step of the guided tour, in order.
//
// Each step: which page (route), what to highlight (a CSS selector, usually a
// [data-tour="…"] anchor placed in the page), and the explanation. Bodies use
// blank lines for paragraphs. Keep each step to one idea; the tour is the
// user's first real mental model of the system.

export interface TourStep {
  route: string;
  target?: string;        // CSS selector; omitted = centered welcome/summary card
  pageLabel: string;      // small label shown in the tooltip header
  title: string;
  body: string;
}

export const TOUR_STEPS: TourStep[] = [
  // ------------------------------------------------------------- welcome --
  {
    route: "/", pageLabel: "Welcome",
    title: "Welcome to Mark 👋",
    body: "Mark is your autonomous marketing engine: it decides what to post, writes it, "
      + "generates the images and videos, queues everything for your approval, posts across "
      + "platforms, measures what happened — and uses those results to get better every week."
      + "\n\nThis tour walks every page and explains what you can do there. Use Next / Back "
      + "(or ← → keys), and Esc to exit. You can restart it any time from Settings.",
  },
  {
    route: "/", target: ".sidebar", pageLabel: "Navigation",
    title: "The nine rooms of the house",
    body: "Dashboard (overview) → Campaigns (what you're marketing) → Studio (review what Mark "
      + "wrote) → Analytics (how posts performed) → Trends (what's hot right now) → Playbook "
      + "(the content strategies + characters) → Learn (what the system has learned) → "
      + "Autopilot (the on/off switch for full autonomy) → Settings."
      + "\n\nThe badge on Studio counts drafts waiting for your review.",
  },
  {
    route: "/", target: "[data-tour='providers']", pageLabel: "Topbar",
    title: "Offline mode vs live",
    body: "Right now every provider is mocked: Mark runs the entire machine — writing, images, "
      + "videos, posting, analytics — with fake providers that cost $0 and post nothing real. "
      + "Perfect for exploring."
      + "\n\nWhen you add API keys (OpenAI, fal.ai, upload-post) in your .env file, this pill "
      + "turns green and the same buttons start doing the real thing.",
  },
  {
    route: "/", target: "[data-tour='autopilot-toggle']", pageLabel: "Topbar",
    title: "The autopilot switch",
    body: "This toggle starts the autonomous scheduler: content generated every morning, posts "
      + "sent at optimal times, analytics collected every 6 hours, trends polled every 30 "
      + "minutes, and the learning loop running continuously — no clicking required."
      + "\n\nIt's also on the Autopilot page with the full schedule. The tour visits it later.",
  },

  // ----------------------------------------------------------- dashboard --
  {
    route: "/", target: "[data-tour='dash-stats']", pageLabel: "Dashboard",
    title: "Your at-a-glance numbers",
    body: "Campaigns running, drafts waiting for review, views over the last 7 days, and real "
      + "API spend over 30 days. In offline mode spend stays $0 forever.",
  },
  {
    route: "/", target: "[data-tour='dash-activity']", pageLabel: "Dashboard",
    title: "The activity feed",
    body: "Everything the system does is logged here — every draft, post, approval, learning "
      + "pass, trend reaction, and error. When Mark runs unattended, this is how you audit "
      + "what it did. Safety alerts (like an engagement collapse pausing a platform) show up "
      + "here in red.",
  },
  {
    route: "/", target: "[data-tour='dash-actions']", pageLabel: "Dashboard",
    title: "Run any part of the machine by hand",
    body: "These five buttons are the whole pipeline, manually: Generate (strategist picks a "
      + "strategy → writer drafts → humor engine punches up → media renders), Post approved, "
      + "Collect analytics (pulls views/likes/comments per post), Refresh trends, and Run "
      + "learning loop (turns results into updated preferences)."
      + "\n\nAutopilot runs exactly these on a schedule — try them by hand first to see each "
      + "stage work.",
  },

  // ----------------------------------------------------------- campaigns --
  {
    route: "/campaigns", target: "[data-tour='campaigns-new']", pageLabel: "Campaigns",
    title: "A campaign = one thing Mark markets",
    body: "Each campaign has its own audience model, brand voice, platforms, posting cadence — "
      + "and its own learning: what works for one campaign never bleeds into another."
      + "\n\nTwo kinds exist: PRODUCT campaigns market something real (a website, an app), and "
      + "ENTERTAINMENT campaigns are pure content accounts — the content itself is the "
      + "business, no product, no call-to-action, judged only on watchability and follows.",
  },
  {
    route: "/campaigns", target: "[data-tour='campaigns-list']", pageLabel: "Campaigns",
    title: "The campaign form, decoded",
    body: "Beyond name/audience/voice: CONTENT RATING sets how edgy humor may go (clean → "
      + "standard → edgy/PG-13; LinkedIn is always kept clean regardless). UPLOAD-POST "
      + "PROFILE lets each campaign post through its own social accounts — that's how you run "
      + "several test accounts at once. TREND SOURCES point the trend radar at this campaign's "
      + "niche (its own subreddits and search keywords)."
      + "\n\nPro tip: the CLI command `mark onboard \"<description>\"` researches and builds an "
      + "entire campaign automatically — audience, voice, strategy briefs, even a mascot concept.",
  },

  // -------------------------------------------------------------- studio --
  {
    route: "/studio", target: "[data-tour='studio-generate']", pageLabel: "Studio",
    title: "Where content gets made",
    body: "Generate kicks off the full pipeline for a campaign: the strategist picks a strategy "
      + "and angle (informed by trends, past winners, and learned preferences), the writer "
      + "drafts several candidates and a judge picks the best, the humor engine rewrites jokes "
      + "through a six-persona tournament, and media gets rendered — AI images, vertical video "
      + "with voiceover and word-synced captions, or pixel-perfect UI mockups.",
  },
  {
    route: "/studio", target: "[data-tour='studio-tabs']", pageLabel: "Studio",
    title: "The review queue",
    body: "Drafts land here for your approval. Each card shows its badges: which strategy made "
      + "it, the target emotion, the comedy persona/mechanism, a countdown if it's riding a "
      + "trend (trend content auto-expires rather than posting late), and a 🎲 holdout badge "
      + "on the ~10% of posts generated with a random policy — the control group that proves "
      + "the learning is real."
      + "\n\nClick any card to open it: edit every field, ask for an AI rewrite with an "
      + "instruction, regenerate media, approve, or reject. Rejection notes (\"too generic\") "
      + "become standing rules the writer must obey next time.",
  },
  {
    route: "/studio", target: "[data-tour='studio-tabs']", pageLabel: "Studio",
    title: "Autonomy is earned, not toggled",
    body: "By default Mark runs GRADUATED approval: a draft only approves itself when its "
      + "quality scores clear the bar AND that strategy has a proven track record on that "
      + "platform (5+ posts performing at or above baseline). Until then, everything waits "
      + "here for you."
      + "\n\nBecause evidence decays over time, a strategy that stops performing automatically "
      + "loses its self-approval privilege. You can switch to full-manual or full-auto in "
      + "Settings → Approval policy.",
  },

  // ----------------------------------------------------------- analytics --
  {
    route: "/analytics", target: "[data-tour='analytics-totals']", pageLabel: "Analytics",
    title: "What actually happened",
    body: "Views, likes, comments, shares, saves per post — collected every 6 hours. Engagement "
      + "rate weighs shares and saves 2x likes, because those are what actually predict "
      + "distribution on 2026 algorithms.",
  },
  {
    route: "/analytics", target: "[data-tour='analytics-top']", pageLabel: "Analytics",
    title: "Top content + the comment section",
    body: "Your best posts ranked by engagement. Below: every collected comment with sentiment "
      + "analysis, plus AI-drafted replies you can approve with one tap (fast author replies "
      + "are one of the strongest ranking signals). Comments touching sensitive topics — visa "
      + "status, mental health, desperation — are flagged for you personally; Mark never "
      + "drafts those."
      + "\n\nComments on character episodes also feed the lore: what the audience jokes about "
      + "becomes canon in the next episode.",
  },

  // -------------------------------------------------------------- trends --
  {
    route: "/trends", target: "[data-tour='trends-refresh']", pageLabel: "Trends",
    title: "The trend radar",
    body: "Every 30 minutes (on autopilot) Mark polls Reddit rising posts, Bluesky, and Google "
      + "Trends; TikTok's Creative Center a few times a day. Each sighting is stored, so the "
      + "system computes velocity — is this growing or dying? — and assigns a lifecycle stage: "
      + "new, rising, mature, or declining.",
  },
  {
    route: "/trends", target: "[data-tour='trends-table']", pageLabel: "Trends",
    title: "The discipline: skip 80-90% of trends",
    body: "Every topic is scored for relevance to YOUR campaign, checked for unsafe origins "
      + "(tragedy, community in-jokes — instant veto), and flagged if the joke depends on a "
      + "specific sound (posting APIs can't attach native audio, so those need 30 seconds of "
      + "manual help)."
      + "\n\nDeclining is an unconditional veto — a brand arriving late to a dying meme is the "
      + "worst outcome. The \"Ride this trend\" button drafts trend content immediately; those "
      + "drafts expire in 24-72h so it's mechanically impossible to post a dead meme.",
  },

  // ------------------------------------------------------------ playbook --
  {
    route: "/playbook", target: "[data-tour='playbook-strategies']", pageLabel: "Playbook",
    title: "The 12 strategies",
    body: "Every post is made under a named, research-backed playbook: pain-point POVs, "
      + "satirical UI mockups, educational hooks, demo videos, mascot episodes, self-aware AI "
      + "absurdism, meme carousels, trend-jacks, contrarian takes, social-proof receipts, "
      + "fake-text dramas, and founder build-logs."
      + "\n\nToggle any of them per campaign. Which strategy gets used when is LEARNED — each "
      + "strategy is a slot machine arm, and the system gradually favors the ones that earn "
      + "engagement on each platform while still exploring.",
  },
  {
    route: "/playbook", target: "[data-tour='playbook-characters']", pageLabel: "Playbook",
    title: "AI characters with a universe",
    body: "Persistent mascots front the character strategies — Poli the Apply Guy ships with the "
      + "SudoApply campaign. Each has a persona, a canonical look (every image is generated "
      + "from the same reference sheet so they stay visually consistent), running lore "
      + "counters that advance with every episode, and recurring NPCs."
      + "\n\nCallbacks are mandatory and explaining the lore is banned — insider knowledge is "
      + "what converts viewers into followers. Characters always disclose they're AI.",
  },

  // --------------------------------------------------------------- learn --
  {
    route: "/learn", target: "[data-tour='learn-stats']", pageLabel: "Learn",
    title: "The brain: proof it's learning",
    body: "Every posted piece is an experiment. When its metrics mature (~48h), every choice it "
      + "made — strategy, hook style, tone, comedy persona, emotion, posting time — gets "
      + "credited with a graded reward against that platform's own baseline."
      + "\n\nThe LIFT stat is the receipts: ~10% of posts are generated with a random policy "
      + "instead of the learned one, and this compares the two. Positive lift = the learning "
      + "is genuinely beating chance, measured on your own account.",
  },
  {
    route: "/learn", target: "[data-tour='learn-bandit']", pageLabel: "Learn",
    title: "The bandit leaderboard",
    body: "Each row is one learned preference: 'question hooks on TikTok', 'deadpan persona on "
      + "X'. Pulls = how much evidence, avg reward = how it performs (0.5 = platform average, "
      + "higher = better)."
      + "\n\nEvidence DECAYS with a 45-day half-life — so when your audience's taste or a "
      + "platform algorithm shifts, old convictions fade and the system re-explores instead of "
      + "being stuck on a dead preference. Winners also feed a retrieval index: future posts "
      + "are written with your own best past posts as examples.",
  },
  {
    route: "/learn", target: "[data-tour='learn-experiments']", pageLabel: "Learn",
    title: "The A/B test lab",
    body: "Experiments compare campaigns as variants: run two accounts with different themes, "
      + "ratings, or strategy mixes, and this table shows posts, engagement, and rewards per "
      + "variant with a leader. This is the summer plan — several test accounts per platform, "
      + "each an experiment, until the system has evolved on real data before you point it at "
      + "a real business.",
  },

  // ----------------------------------------------------------- autopilot --
  {
    route: "/autopilot", target: "[data-tour='autopilot-master']", pageLabel: "Autopilot",
    title: "Full autonomy, when you're ready",
    body: "One switch runs the whole loop unattended: generate every morning per campaign "
      + "cadence, post at optimal times with random jitter (bot patterns get suppressed), "
      + "collect analytics, poll trends, learn, and adapt."
      + "\n\nTwo safety systems watch it: if a platform's last five posts crater below "
      + "baseline, that platform pauses for 48h with a loud alert; and if real API spend "
      + "passes the daily cap, generation freezes until tomorrow.",
  },
  {
    route: "/autopilot", target: "[data-tour='autopilot-upcoming']", pageLabel: "Autopilot",
    title: "The schedule",
    body: "Exactly what will run and when — every posting slot per platform, the daily "
      + "generation run, analytics sweeps, the 30-minute trend pulse, the daily cross-platform "
      + "cascade (winners get re-expressed on lagging platforms), and the weekly deep learning "
      + "pass. All times respect your configured timezone.",
  },

  // ------------------------------------------------------------ settings --
  {
    route: "/settings", target: "[data-tour='settings-providers']", pageLabel: "Settings",
    title: "Going live",
    body: "Mark needs three keys to leave offline mode: OpenAI (writing, images, voices), "
      + "fal.ai (AI video), and upload-post.com (one API that posts to every platform — "
      + "connect your social accounts in their dashboard). Add them to the .env file in your "
      + "project folder and restart. ElevenLabs is optional for premium character voices.",
  },
  {
    route: "/settings", target: "[data-tour='settings-humor']", pageLabel: "Settings",
    title: "The humor engine knobs",
    body: "Jokes aren't one-shot: Mark searches for a 'benign violation' (something wrong "
      + "enough to be funny, safe enough to laugh at), writes ~6 candidates through distinct "
      + "comedy personas, runs a pairwise tournament judged with YOUR audience's own "
      + "preference history, and kills any joke whose punchline a model can guess in advance. "
      + "A joke that fails quality gates ships as a straight post instead — a dead joke is "
      + "worse than no joke."
      + "\n\nThe gates move with each campaign's content rating: an 'edgy' campaign is allowed "
      + "spikier material than a 'clean' one.",
  },
  {
    route: "/settings", target: "[data-tour='settings-learning']", pageLabel: "Settings",
    title: "Learning knobs",
    body: "Decay half-life controls how fast old evidence fades (adaptability vs stability). "
      + "Holdout % is the random control group size. Reward maturity is how long a post's "
      + "metrics settle before it teaches the system. Defaults are sensible — change them only "
      + "with a reason.",
  },
  {
    route: "/settings", target: "[data-tour='settings-tutorial']", pageLabel: "Done",
    title: "That's the whole machine 🎉",
    body: "Suggested first hour: create a campaign (or run `mark onboard`), hit Generate on the "
      + "Dashboard, review your drafts in Studio, approve a few, Post + Collect analytics, then "
      + "run the learning loop and watch the Learn page light up — all free, all offline."
      + "\n\nRestart this tour any time from right here. When you're ready for real accounts: "
      + "add the three API keys and flip Autopilot on.",
  },
];
