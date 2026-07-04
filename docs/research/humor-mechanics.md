# The Mechanics of Humor for Automated Short-Form Content

*Research report for Mark's content pipeline — July 2026*

This report distills what actually makes short-form content funny: the theories that predict laughs, the joke formats that encode them, why LLM humor usually fails, the documented techniques that fix it, the 2024–2026 research literature, and how professional comedy writers iterate. It ends with concrete rules an automated pipeline can encode.

---

## 1. Theories that actually predict laughs

### 1.1 Benign Violation Theory (BVT) — the best single predictor

McGraw & Warren's [Benign Violation Theory](https://leeds-faculty.colorado.edu/mcgrawp/pdf/mcgraw.warren.2010.pdf) is the most empirically validated modern theory: humor occurs **when and only when** (1) something violates how the world "ought" to be, (2) the violation is simultaneously perceived as benign/safe, and (3) both perceptions happen at once. In their experiments, subjects who rated a scenario as simultaneously "wrong" AND "not wrong" were **~3x more likely to laugh** than those who saw it as purely fine or purely unacceptable ([HuRL summary](https://humorresearchlab.com/benign-violation-theory/)).

Three documented mechanisms make a violation benign:
1. **Alternative norms** — one reading is wrong, another is fine (this is how puns work)
2. **Weak commitment to the violated norm** — audiences laugh harder at violations of norms they don't hold sacred
3. **Psychological distance** — "comedy is tragedy plus time" (or plus fiction, or plus it-happened-to-someone-else)

**Prediction it makes, both directions:** too benign → boring ("mildly amusing at best"); too much violation → offensive/upsetting. Funny lives on the ridge between. This is why corporate content dies: brands sand off every violation until nothing is wrong, and nothing wrong = nothing funny.

**Mapping to short-form:** the violation for a product account is usually a *register violation* — a brand behaving in a way brands ought not to (Duolingo's owl threatening users, Nutter Butter's horror-filter cookie lore, Ryanair's pettiness). It's benign because the stakes are zero: it's a cookie account, nobody is harmed. For SudoApply, the natural violation space is the *shared suffering of job hunting* said too honestly ("we automated lying about being passionate about supply chain logistics") — a truth violation kept benign by self-deprecation and audience membership (we're students too, punching at the system, not at applicants).

### 1.2 Incongruity-Resolution — the engine inside every joke format

The dominant cognitive account ([Suls 1972; Ritchie's formalization](https://homepages.abdn.ac.uk/g.ritchie/pages/papers/aisb99.pdf)): a setup builds a mental model; the punchline initially doesn't fit; the laugh fires at the moment the audience **resolves** the incongruity by discovering the hidden second interpretation that was available all along ([detailed linguistic account](https://personal.ua.es/francisco.yus/site/cases.pdf)). Key mechanical requirements:

- The setup must be **ambiguous enough to support two readings** but strongly bias toward the wrong one (misdirection).
- The punchline must force **inferential backtracking** — the audience re-reads the setup and finds the second meaning themselves. **The audience does the last step.** Jokes that explain themselves remove this step and die.
- fMRI work distinguishes incongruity-*resolution* humor from pure absurd (nonsense) humor as separate processing paths ([dual-path model](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2017.00498/full)) — meaning absurdism is a legitimately different product, not a failed joke.

**Information-theoretic version (very usable by a pipeline):** humor correlates with *surprisal* — the punchline should be low-probability given the setup, yet high-coherence in retrospect. Empirically, [humorous headlines have higher perplexity, and swapping high-surprisal tokens for predictable ones removes the humor](https://arxiv.org/pdf/2012.12007); humor concentrates in the **late** part of satirical headlines (late-stage expectation violation). This gives a measurable proxy: *a funny line is one a language model would NOT have predicted, that a language model can nonetheless explain afterward.*

### 1.3 Superiority theory — why roasts, fails, and "POV: you" work

The oldest theory (Hobbes/Plato): laughter as sudden glory at someone else's expense ([overview of the big three](https://comedyphilosopher.com/the-big-three-incongruity-vs-superiority-vs-relief/)). Weak as a total theory, but it explains the direction-of-punch rule that dominates social media:

- **Punching up or sideways** (at institutions, at the absurd job market, at yourself) is safe and bonding.
- **Punching down** (at the audience's in-group) is the fastest way to get ratio'd.
- **Self-deprecation from a brand is superiority the audience gets to enjoy** — the brand lowers itself, the viewer feels above it, engagement follows. This is the mechanic behind self-aware "our AI wrote this" humor.

For SudoApply the targets are: the job application process, ATS systems, ghost jobs, "entry level, 5 years experience required", LinkedIn cringe culture, recruiters who ghost. Never the students.

### 1.4 Timing, misdirection, and the prediction-error account

The 2026 paper [Timing is Everything: Temporal Scaffolding of Semantic Surprise in Humor](https://arxiv.org/html/2605.00143v1) analyzed real stand-up and found:

- **Peak semantic violation matters more than average incongruity** — the funniest line is the single sentence most semantically distant from its predecessor, not a uniformly weird script.
- Pros extend the pause before high-surprise content: pauses before surprising transitions were **35.6% longer** on average, and **expert comedians showed 41.2% pause increases vs 27.4% for weaker ones**. The pause creates a prediction window; the audience commits to a guess; the violation then lands harder.
- **Temporal features outperformed semantic features in predicting audience laughter.** Timing is not delivery polish — it's half the mechanism.

**Short-form mapping:** the "pause" translates to a beat of silence before the punch word in video, a line break / page-break before the last line of a caption, the final slide of a carousel, or the cut in an edit. The punchline word should be the **last** word (Greg Dean's rule; also observed as late-position humor in the headline-corpus studies).

### 1.5 Relief theory (brief)

Freud's tension-release account survives mainly as a practical note: humor about a *shared anxiety* (job-hunting dread, rejection emails) releases real tension and produces disproportionate engagement — this is documented as the psychological function of Gen Z absurdism ("absurd humour acts as a coping tool… Gen Z uses absurdity to soften collective anxieties" — [Zeitgust on brainrot humor](https://thezeitgust.substack.com/p/6-brainrot-humour-gen-zs-dadaism)). Anxiety topics are humor fuel, not humor risk, *if* the account is clearly inside the anxiety with the audience.

---

## 2. Anatomy of online joke formats

### 2.1 Setup–subversion (the atomic unit)

[Greg Dean's joke structure](https://stand-upcomedy.com/glossary/joke-structure/) is the cleanest mechanical decomposition and is directly encodable as a generation scaffold:

1. **Setup** creates a **1st Story** in the audience's head.
2. It contains a **Connector** — one thing with two possible interpretations.
3. The audience adopts the **Target Assumption** — the expected interpretation the setup deliberately implies.
4. The **Punchline** reveals the **Reinterpretation** — the unexpected but valid second reading — which **shatters the target assumption** and creates a **2nd Story**.

Corollaries: if the audience guesses the twist, the joke is dead ("surprise is non-negotiable"); the reveal word goes last; everything in the setup that doesn't serve misdirection or the second reading is cut.

### 2.2 Escalation / "the game" (the sketch unit)

UCB's core doctrine ([Game of the Scene](https://www.hooplaimpro.com/quick-guide-game-of-scene), [UCB sketch notes](https://drewtarvin.com/comedy/ucb-sketch-101-class-notes/)): a sketch is not a series of jokes — it's **one unusual thing** (the "first unusual thing"), plus a pattern of exploring and heightening it:

- Find the **first unusual thing** — the single break from normal reality.
- Ask **"if this is true, what else is true?"** — heightening must stay *logically consistent with the premise* while getting more absurd.
- Alternate **heighten → explore** (raise absurdity, then make sense of it) — escalation without exploration reads as random; exploration without escalation goes flat.

This is the structure of every good recurring-character TikTok (the corporate recruiter character, the "day in the life" parody): one game, three-to-five heightens, out at the peak. It's also the structure of a good *account*: Nutter Butter's entire channel is one game ("what if a cookie brand was a cursed liminal entity") heightened for months.

### 2.3 Rule of three

Establish, reinforce, surprise ([Rule of three](https://en.wikipedia.org/wiki/Rule_of_three_(writing)); [why it works](https://buddyonstage.com/blogs/rule-of-3-in-comedy)). Two is the minimum to establish a pattern, three is the first chance to break it; four is a list. Craft details: items 1 and 2 roughly equal length; item 3 slightly longer because it carries the twist; item 3 must be the funniest. Directly usable for captions, carousel slides, and thread structure ("3 things recruiters say: … , … , [violation]").

### 2.4 Callback

Bringing back an earlier element in a new context ([callback mechanics](https://www.chrishead.com/post/2018/04/27/lesson-17-comic-analogies)). The laugh is partly recognition, partly the reward of being an insider. **On social, callbacks operate at account level, not post level**: recurring bits, running lore, in-jokes only followers get. This is Nutter Butter's engine (surreal recurring characters and lore; followers grew **3,000 → 700,000 with 4.1M likes in months** — [Digiday](https://digiday.com/marketing/should-brands-be-so-online-nutter-butters-extreme-social-persona-speaks-to-changing-brand-dynamics/), [Pulsar analysis](https://www.pulsarplatform.com/blog/2025/does-unhinged-marketing-work-and-can-anyone-do-it-from-utter-nutter-butter-chaos-to-duolingo-death)). Callbacks convert casual viewers into followers because the *next* joke pays more if you followed.

### 2.5 Anti-humor

The [anti-joke](https://en.wikipedia.org/wiki/Anti-humor) removes the expected punchline and plays the situation literal/flat; the laugh comes from subverting the expectation *of a joke itself*. Anti-memes (normal meme image + deliberately literal, flat text) work because meme formats are so over-learned that the audience already knows the punchline — the absence is the only remaining surprise. 2020s TikTok anti-humor delivers "abrupt, literal payoffs in under 15 seconds… discomforting non-sequiturs that parody viral comedy trends." **Requirement:** anti-humor only works against a format the audience has fully internalized — it's a second-order joke. A pipeline should only deploy it on formats currently saturated on the platform.

### 2.6 Absurdism / brainrot (the self-aware AI-slop lane)

Italian brainrot (Tralalero Tralala, Ballerina Cappuccina, etc.) dominated spring 2025 precisely because it was AI-generated nonsense: "the joke, as one animator put it, is that there is no joke" ([Wikipedia](https://en.wikipedia.org/wiki/Italian_brainrot), [Milleworld](https://www.milleworld.com/so-are-we-just-gonna-ignore-the-racism-in-italian-brain-rot/)). Mechanics that matter for a pipeline:

- Absurdism is **pattern-less on the surface but format-rigid underneath** (brainrot had a strict template: AI image of animal-object hybrid + pseudo-Italian TTS narration + lore). The template IS the game; each new entity is a heighten.
- Uncanny/intentionally-bad AI output "blurs sense and nonsense" and grabs attention faster than long setups — it front-loads the violation into frame 1 ([Medium analysis](https://medium.com/scripting-horizons/gen-z-humour-explained-why-absurd-memes-dominate-online-culture-47f4d7c5821d)).
- It functions as Dada-style anxiety coping, which is why it resonates with 18–24s specifically.
- Crucially for Mark: the CHI 2026 study ["Not Human, Funnier"](https://arxiv.org/pdf/2602.12763) found audiences rate AI comedy **more positively when the AI acknowledges its own artificial nature** — self-referential machine identity aligns expectations and resolves the authenticity tension. An AI marketing account that openly says "our marketing department is an unsupervised script" is playing a documented winning hand.

### 2.7 Observational specificity

The craft axiom "the more specific, the more universal" ([discussion](https://figmentsandfables.com/2025/04/01/the-power-of-specificity-how-adding-small-details-creates-universal-results/)): audiences relate to concrete, hyper-specific details ("the Workday account you made for one application in 2023") far more than to categories ("job applications are annoying"). Mechanically, specificity does double duty: it raises surprisal (specific tokens are lower-probability) AND it signals insider membership (only someone who has suffered this would know this detail). Observational comedy for a niche = enumerate the audience's most specific shared experiences and say the quiet part.

### 2.8 Misdirection formats native to short-form

- **Hook-as-setup:** the scroll-stopping first line doubles as the joke's setup; the video's payoff is the reinterpretation. Platform data: viewers decide in ~1.5–2 seconds; the hook must land by second 3 ([short-form structure guides](https://www.socialync.io/blog/short-form-video-structure-guide-2026)).
- **The loop:** ending a video so it flows back into its opening drives 2–4x rewatch rates and 15–30% higher completion ([loop strategy](https://smmnut.com/blog/tiktok-loop-content-strategy-2025/)) — a callback to the video's own start, executed structurally.
- **Visual/format misdirection:** the caption promises one register ("serious career advice") while the video delivers another (absurd escalation) — a register-level connector with two readings.

---

## 3. Why LLM humor fails, and what fixes it

### 3.1 Documented failure modes

1. **The objective is anti-comedy.** Training that minimizes perplexity optimizes for the *most predictable* continuation; a punchline is by definition a low-probability continuation. Surprise and next-token likelihood pull in opposite directions ([HumorGen](https://arxiv.org/html/2604.09629v2) frames comedy as living in "low-probability semantic regions"; the surprisal literature confirms swapping surprising tokens for likely ones deletes the humor).
2. **The alignment tax.** RLHF-style safety/helpfulness tuning produces hedging, both-sides-ing, and violation-avoidance — and per BVT, no violation means no joke. Google DeepMind's comedian study ([A Robot Walks into a Bar](https://arxiv.org/pdf/2405.20956), FAccT 2024) had 20 professional comedians use LLMs: they described the output as **"cruise ship comedy material from the 1950s, but a bit less racist"** — bland, stereotype-laden, and stripped of any point of view; safety filtering also erased minority perspectives and neutered satire/punching-up.
3. **Over-explaining.** LLMs append the explanation to the joke, removing the audience's resolution step. HumorGen explicitly documented an **"explainer trap"**: training students on reasoning traces *reduced* judged funniness by encouraging over-explanation.
4. **Mode collapse into memorized jokes.** Studies find models "rely on a limited repertoire of pre-learned jokes" and formulaic phrasing; minor rewording of a known joke breaks their apparent understanding ([Oogiri study](https://arxiv.org/html/2511.09133v1); [Creativity & Cognition 2025](https://dl.acm.org/doi/10.1145/3698061.3734388)).
5. **No point of view / punching at nothing.** Comedy needs a target assumption and a stance. Default LLM output has neither — it gestures at "humor-shaped" text (wacky adjectives, exclamation marks) without an actual violation of anything.
6. **Empathy gap.** The [Oogiri benchmark](https://arxiv.org/html/2511.09133v1) (GPT-4.1, Gemini 2.5 Pro, Claude Sonnet 4) scored LLMs "between low- and mid-tier humans"; the **largest gap was Empathy/relatability** — humans weight relatability highest, LLMs optimize novelty. Generic references are the symptom: the model doesn't know what THIS audience has lived through.
7. **LLMs are bad judges of funny by default.** Same study: LLM-human correlation on funniness was only **ρ = 0.17–0.27**, with positivity bias and self-preference bias. Naive "rate this joke 1–10" self-evaluation is close to noise.

### 3.2 Documented techniques that work

1. **Generate-many, rank-hard (the single most validated technique).**
   - [HumorGen](https://arxiv.org/html/2604.09629v2): teacher generates 24 candidates per prompt via 6 comedic personas, an LLM judge Elo-ranks them; a 7B model trained on the survivors beat models 4–18x larger. Their conclusion: "cognitively driven data curation is more critical than alignment algorithms or model scale."
   - [SemEval-2026 Task 1 winning system](https://arxiv.org/pdf/2606.00022): generate many constrained candidates → **pairwise** Bradley-Terry preference ranking (not absolute scores) → select. Pairwise comparison captures humor preference far better than 1–10 ratings.
   - [Bridging the Creativity Understanding Gap](https://arxiv.org/html/2502.20356): with small-scale alignment on real audience preference data, an LLM ranker on New Yorker caption contests went from 67% → **82.4% accuracy — matching world-class human experts** (Bob Mankoff: 85.3%). Key finding: **fine-tuning on actual crowd preference data massively beat persona-prompting the judge** (+3% only). Judging funny is learnable; it just needs real preference signal, which Mark's engagement metrics provide for free.
2. **Persona commitment / mixture-of-personas.** HumorGen's six cognitive archetypes (Neurotic, Cynic, Observer, Wordsmith, Optimist, Absurdist) exist to force generation out of the single "safe center" mode — each persona is a different direction into low-probability space. A committed, consistent character with opinions is also what separates Duolingo/Nutter Butter from generic brand accounts.
3. **Joke-structure scaffolding.** [Witscript](https://arxiv.org/abs/2302.02008) (Joe Toplyn, ex-head writer for Letterman/Leno) encodes professional joke algorithms as steps: extract the topic's **handles** (the interesting words), generate associations for each, link two associations via wordplay/overlap into a **punchline**, then generate an **angle** (bridge text) connecting topic to punchline. Human evaluators rated its outputs as jokes far more often than end-to-end generation. Structure-first beats vibes-first. Similarly, [OpenMic](https://arxiv.org/pdf/2601.08288) (2026) shows a multi-agent decomposition (topic → generate → critique → refine) significantly outperforms single-pass generation.
4. **Specificity and constraint injection.** Practitioner-documented and theory-consistent: arbitrary concrete constraints ("must mention the Workday login page") force the model off the high-probability path and are the cheapest surprisal injector ([Zapier's testing](https://zapier.com/blog/can-chatgpt-be-funny/); constraint-based prompting guides). Feed the model *concrete audience artifacts* (real rejection-email phrasing, real ATS names, real LinkedIn clichés) — vague input produces vague comedy.
5. **Incongruity search as an explicit step.** Rather than asking for "a funny post," ask first for the violation: "list 10 things about [topic] that are wrong/absurd/taboo-but-harmless," then build jokes only on the strongest violation. This operationalizes BVT and mirrors theory-driven detection frameworks like [THInC](https://arxiv.org/html/2409.01232v1).
6. **Temperature is a real knob but not a magic one.** [Temperature/architecture study](https://arxiv.org/pdf/2504.02858) found architecture and prompting dominate; moderately-high temperature helps diversity of candidates, which matters only because of technique #1 (you need a wide pool to rank).
7. **Transfer note:** [One Joke to Rule Them All](https://arxiv.org/html/2508.19402v1) found humor competence transfers asymmetrically across joke types — training/few-shotting on structurally rich types (dad-joke style double meanings) transfers to simpler formats, not vice versa. Few-shot examples should be structurally rich, not just topically similar.

---

## 4. Research landscape, 2024–2026 (quick reference)

| Work | Year | Takeaway for Mark |
|---|---|---|
| [A Robot Walks into a Bar](https://arxiv.org/pdf/2405.20956) (DeepMind, FAccT) | 2024 | Pro comedians: LLM default output = "cruise ship comedy from the 1950s"; alignment strips violation and POV |
| [Bridging the Creativity Understanding Gap](https://arxiv.org/html/2502.20356) | 2025 | LLM humor *ranking* reaches expert level (82.4%) with small real-preference fine-tuning; judges > persona prompts |
| [Temperature Configurations study](https://arxiv.org/pdf/2504.02858) | 2025 | Prompting/architecture >> temperature; temp helps candidate diversity |
| [Punchlines to Predictions](https://arxiv.org/pdf/2504.09049) | 2025 | Metric for detecting humor in stand-up transcripts; LLMs mediocre at spotting laugh lines |
| [Creativity & Cognition humor study](https://dl.acm.org/doi/10.1145/3698061.3734388) | 2025 | ChatGPT/Llama/Gemini fluent but fail "emotional realism and contextual appropriateness" |
| [One Joke to Rule Them All](https://arxiv.org/html/2508.19402v1) | 2025 | Humor transfer across types is asymmetric; train/few-shot on complex types |
| [Oogiri multi-dimensional benchmark](https://arxiv.org/html/2511.09133v1) | 2025 | LLMs = low-to-mid-tier human; empathy is the gap; LLM judges ρ≈0.2 with humans, positivity + self-preference bias |
| [Witscript](https://arxiv.org/abs/2302.02008) | 2023 (foundational) | Encoded pro joke-writing algorithms (handles → associations → punchline → angle) beat end-to-end generation |
| [THInC](https://arxiv.org/html/2409.01232v1) | 2024 | Theory-driven (per-theory classifier) humor detection framework |
| [OpenMic multi-agent stand-up](https://arxiv.org/pdf/2601.08288) | 2026 | Generate→critique→refine agent loop beats single-pass |
| [Timing is Everything](https://arxiv.org/html/2605.00143v1) | 2026 | Peak (not average) semantic surprise predicts laughs; experts lengthen the pause before the punch by ~41% |
| [SemEval-2026 Task 1](https://arxiv.org/pdf/2606.00022) | 2026 | Constrained humor generation as shared task; pairwise Bradley-Terry preference modeling wins |
| [HumorGen](https://arxiv.org/html/2604.09629v2) | 2026 | 6-persona candidate generation + Elo judging; data curation beats DPO/GRPO and scale; "explainer trap" |
| [Not Human, Funnier](https://arxiv.org/pdf/2602.12763) (CHI) | 2026 | Audiences like AI comedy MORE when it's self-referentially AI — disclosure is an asset |
| [Funniest Number study](https://arxiv.org/pdf/2503.24175) | 2025 | Even numbers-as-punchlines have structure: specific, odd, slightly-too-precise numbers are funnier than round ones |
| [Computational Humor Modeling survey](https://dl.acm.org/doi/10.1145/3778357) (ACM CSUR) | 2025/26 | Field survey; incongruity/surprisal remain the dominant computational handles |

---

## 5. How professional comedy writers iterate

1. **Volume then selection, never one-shot.** Late-night monologue rooms generate hundreds of jokes to air a dozen. A punch-up room exists because "it takes a team of people utilizing multiple perspectives to arrive at the best joke for each situation" ([Stage 32 punch-up workshop](https://www.stage32.com/classes/Writers-Room-Workshop-Writing-Jokes-for-Sitcoms-%20-Participate-In-a-Mock-TV-Punch-Up-Room)). The professional unit of work is *candidates per slot*, not drafts.
2. **Joke density is tracked numerically.** Sitcom benchmark: minimum ~3 jokes/page (≈1 laugh per screen minute); stand-up headliners target 4–6 laughs/minute; [30 Rock peaked at 7.44 JPM, The Office ~5–6.65, Friends 6.06](https://collider.com/comedy-shows-most-jokes-per-minute-ranked/) — and the highest-rated shows sit in a "Goldilocks zone" around 5.5–6.5 JPM, not the maximum ([analysis](https://medium.com/@vikram.venkat/the-one-with-too-many-jokes-9cb32288f463)). For a 20-second video that implies roughly **a laugh-or-surprise beat every 4–8 seconds** — hook beat, 1–3 heightens, punch/loop beat.
3. **Punch-up is targeted replacement, not rewriting.** The pass goes line by line: is this line carrying a laugh? If not, can it be replaced by a funnier line *that does the same story work*? Weak punchlines get three alternates pitched; the best survives. This maps exactly to a per-line "generate 5 alternates, pairwise-rank, swap" pass.
4. **"Find the game, then heighten"** ([UCB](https://ucbcomedy.com/training-center/sketch-101/)): pros don't brainstorm jokes; they find one unusual thing and mine it. A sketch that isn't working usually has *two* games (cut one) or heightens that break premise-logic (fix the logic, not the jokes).
5. **Kill the darlings that don't serve the game; punch word last; cut the first 20%.** Standard punch-up heuristics: most drafts start before the funny starts. In short-form, this is literal: delete the intro, start at the unusual thing.
6. **Test on audiences, tag, iterate.** Stand-ups tape every set, mark which lines got laughs, cut/rework the rest. Mark's analytics loop is exactly this instrument — per-post engagement is the laugh track, and per-arm bandit state is the tagged notebook.

---

## Pipeline implications

Concrete rules, heuristics, and prompt strategies for Mark's automated system.

### A. Generation architecture

1. **Never one-shot a joke. Pipeline = find-the-violation → scaffold → fan-out → rank → punch-up.**
   - Step 1 (*incongruity search*): given topic + audience, generate 10–15 candidate *violations* ("what's wrong/absurd/secretly true about X that is safe to say?"). Discard any that are (a) not actually violations (bland) or (b) not benign for the audience (punching down at students).
   - Step 2 (*scaffold*): for the best violation, fill an explicit structure: `target_assumption` (what the setup makes the reader believe), `connector` (the ambiguous element), `reinterpretation` (the second reading), `punch_word` (goes last). Reject any draft where the model can't name all four.
   - Step 3 (*fan-out*): generate 10–24 candidates across 4–6 fixed comedic personas (e.g., Cynic, Absurdist, Deadpan Observer, Neurotic Student, Corporate-Speak Parodist, Unhinged AI) at moderately high temperature. Personas exist to force diverse low-probability directions (HumorGen result).
   - Step 4 (*rank*): **pairwise** LLM-judge tournaments (Bradley-Terry/Elo style), never "rate 1–10". Instruct the judge to penalize: guessable punchlines, explanation after the punch, no identifiable target assumption, generic references. Periodically calibrate the judge on Mark's own engagement data (posts as preference pairs) — small real-preference alignment is what takes ranking to expert level.
   - Step 5 (*punch-up pass*): for the winner, per-line: "does this line carry surprise or story? If neither, generate 3 replacements that do the same story work but funnier; pick pairwise."
2. **Predictability filter (cheap surprisal proxy):** before final selection, have a model try to complete the setup without seeing the punchline, 3 samples. If any completion matches/paraphrases the punchline, the joke is guessable — kill it. (Direction is validated by the perplexity/surprisal literature: predictable punchline = not a joke.)
3. **Never explain the joke.** Hard rule in every writer prompt: the caption/video ends on the punch; no trailing "😂 because job hunting is hard, right?"; no restating the premise. The audience must do the resolution step. Strip any sentence after the punch word in post-processing.

### B. Prompt-level rules

4. **Feed specifics, demand specifics.** Maintain a living "specificity bank" per product: real artifacts of the audience's life (Workday logins, "we've decided to move forward with other candidates," one-way video interviews, the 47th "passionate self-starter"). Every joke prompt must inject 3–5 bank items as raw material and require at least one hyper-specific detail in the output. Ban category-level references ("job applications can be tough").
5. **Constraint injection as surprisal engine:** add one arbitrary concrete constraint per candidate batch ("must involve a fax machine", "told as a rejection-email autopsy", "the ATS speaks in first person"). Constraints force off the high-probability path.
6. **Anti-slop blacklist extended for humor:** ban hedges ("just kidding!", "we've all been there, right?"), meta-softeners, exclamation-mark clusters, "wacky" adjectives doing the humor's job, and any punchline that appears verbatim in a web search of known jokes.
7. **Direction-of-punch guardrail:** target must be an institution/process/the-brand-itself, never the audience or a vulnerable group. Encode as an explicit check in the ranking judge.

### C. Format templates to encode (each is a distinct arm for the bandit)

8. **Setup-subversion caption/text post:** target-assumption scaffold; punch word last; line break before the final line (the textual "pause").
9. **Rule-of-three:** slots 1 and 2 normal and parallel; slot 3 slightly longer and carries the violation. Works for captions, carousels (slides 1–2 establish, slide 3+ break), and threads.
10. **Escalation sketch/video:** one "first unusual thing" in the first 2 seconds; 3–5 heightens each answering "if that's true, what else is true"; each heighten must be premise-consistent and bigger; end at peak or loop back to frame 1. Beat budget: one surprise every 4–8 seconds; a 20s video = hook + 2–3 heightens + punch.
11. **Anti-humor:** deploy only against formats the platform has saturated (check trends data); play the format perfectly straight with a flat literal payoff. Low frequency — it's seasoning.
12. **Self-aware AI absurdism (the sanctioned slop lane):** commit to a rigid template + escalating lore (the brainrot lesson: absurd content, rigid format). Explicitly acknowledge machine identity — "this ad was generated by an unsupervised marketing script" is a documented perception boost (CHI 2026), and it converts the brand's actual nature into the bit. This lane doubles as the account-level "game."
13. **Callback/lore system:** persist successful bits, characters, and phrases in the DB (extend winners with a `bit` tag); schedule callbacks at intervals; never explain the lore in-post. Callbacks are the follower-conversion mechanism.

### D. Learning-loop hooks

14. **Bandit arms for humor:** add `humor_mechanism` (setup_subversion, rule_of_three, escalation, anti_humor, absurdist_lore, observational_specific, callback) and `persona` as arm types alongside existing hook_style/tone. Engagement rate is the laugh track.
15. **Judge calibration from analytics:** monthly, convert Mark's own post pairs (same platform/format, divergent engagement) into preference pairs and few-shot/fine-tune the ranking judge. This is the 67%→82.4% lever applied to the actual audience.
16. **Timing as a first-class parameter in video assembly:** insert a 300–600ms beat (silence/hold frame) before the punch word in TTS/caption timing; place the highest-surprisal line at the end; for loops, make the last shot re-contextualize the first.
17. **Weirdness ceiling check (BVT two-sided test):** ranking judge scores each candidate on `violation_strength` (0–1) and `benignness` (0–1); require both ≥ 0.5. Kills the two default failure modes: bland corporate safety (violation≈0) and off-brand offense (benign≈0).
