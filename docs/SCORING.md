# ClaudeScore interview rubric

**Context:** second-round hire, Junior / Mid software developers. Open-ended
2-hour build (Django + Postgres + JS/TS). Candidates use Claude Code only.

The thing we are actually testing is **how well someone drives an AI coding
agent to solve a real, open-ended problem under time pressure** — not
line-by-line code correctness. The final mark reflects that.

---

## The composite mark (0–100)

| Component | Weight | Where it comes from |
|---|---:|---|
| **AI collaboration & process** | **50** | ClaudeScore judge scores + metrics |
| **Progress — how far they got** | **35** | Milestone ladder in the problem (M0–M5) + a smoke run |
| **Code review (holistic, light)** | **15** | Reviewer reads `solution.patch` for ~10 min, scores 1–5 |

Weights are deliberately process-heavy. Tune them in one place if a future role
needs a different balance.

### Bands
- **85–100** — Strong hire. Drove Claude expertly and got impressively far.
- **70–84** — Hire. Solid collaboration, real progress.
- **55–69** — Borderline / lean. Discuss as a panel.
- **< 55** — No hire on this exercise.

---

## 1. AI collaboration & process — 50 pts

This is the heart of it. Source is the **ClaudeScore LLM judge** (1–5 on each
axis) plus a few deterministic metrics as corroboration.

**Scored PROCESS axes (from the judge):** average these four, each 1–5 → scale to 50.

| Axis | What a 5 looks like | What a 1–2 looks like |
|---|---|---|
| **Prompt quality** | Clear goals, useful context, good constraints; breaks work down | Vague one-liners, no context, expects mind-reading |
| **Delegation & control** | Delegates whole units AND keeps the wheel — directs, steers, retains control | Either micromanages every keystroke OR blindly accepts everything ("vibe coding") |
| **Review & verification** | Reads diffs, questions choices, runs it / checks tests, catches mistakes | Never inspects output; never confirms it works |
| **Recovery** | Debugs methodically, re-scopes when stuck, uses errors as signal | Spirals, repeats the same failing prompt, gives up |

> `process_pts = (prompt_quality + delegation_control + review_verification + recovery) / 20 × 50`

**Tone is reported but NOT scored for hire.** Politeness is a culture
data-point, not a competence signal — don't let it move the mark.

**Metric corroboration (flags, not points):** use these to sanity-check the
judge, and note anything extreme in the writeup.
- `correction_rate` very high → fought the agent / unclear direction.
- `tools_per_prompt` very low + many prompts → micromanaging.
- `cache_hit_ratio` very low → thrashing context / restarting a lot.
- `slash_command` usage → fluency with the tool (using `/clear`, custom
  commands, agents deliberately is a plus, not a minus).
- `rewinds` → course-correction. A few rewinds is healthy iteration (they
  noticed a wrong turn and backed out). Many rewinds with little progress can
  signal thrashing — read it together with the progress score, not alone.

### 1b. The judge now also scores the PRODUCT (what they built)

The LLM judge is **analytic** (independent 1–5 per dimension) and, when given
the candidate's diff vs the boilerplate (`solution.patch`) and a smoke-test
report, also scores four PRODUCT dimensions plus an `overall` (1–5) and a
`recommendation` (strong_hire / hire / lean_no_hire / no_hire):

| Dimension | Feeds | Note |
|---|---|---|
| **Feature completeness** | Component 2 (Progress) | Counts only what *works* (smoke-anchored), judged on the diff, not the boilerplate |
| **Code quality** | Component 3 (Code review) | Readability, error handling, validation, type safety, secrets, DRY; **over-engineering is a defect** |
| **Architecture** | Component 3 (Code review) | Business logic out of views/`save()`; clear API/serializer + frontend layering. Scores the *principle*, not a naming convention |
| **Testing** | Component 3 (Code review) | Tests judged by whether they'd catch a regression, not by mere presence |

These are a **strict, evidence-grounded first pass** at Components 2 and 3 — the
interviewer still confirms (especially feature credit via the operator menu).
Treat the judge's product scores as input, not gospel.

**Strict calibration (read this).** The judge is anchored against grade
inflation: **3 = competent (what a hireable mid-level ships in 2h), 5 = rare and
must be evidence-earned**, "it runs" is a 3 not a 5, and over-engineering is
penalised. Each score carries a one-line evidence citation in the report; a
dimension it can't observe is marked `CANNOT_ASSESS` rather than guessed
upward. (Design grounded in Google eng-practices code-review standards, the
HackSoft Django service-layer convention, and BARS / LLM-as-judge calibration
research — see the judge prompt in `claude_score/judge.py`.)

---

## 2. Progress — how far they got — 35 pts

Each problem has an **operator-only feature menu** with point values, kept
in `docs/PROBLEMS/<problem>.md` (e.g. [`PROBLEMS/moviedeck.md`](PROBLEMS/moviedeck.md)).
The candidate-facing repo does **not** show points or implementation hints
— candidates form their own feature list by reading the problem's prose
user journeys. This is the "how far in 2 hours" axis, with multiple paths
to the same score.

**Computing the mark.** Sum the points of features that *actually work
end-to-end at submission time*, then scale to 35:

> `progress_pts = min(35, feature_points_shipped × 35 / menu_total)`

`menu_total` is published per problem (e.g. ~53 for MovieDeck). The cap
means a candidate doesn't have to do the whole menu — landing ~two-thirds of
the menu earns full marks. A candidate can clear the cap by going deep on
fewer features (full credit on stretch + solid foundation) just as easily as
by going broad.

**Hard gate: the app must run at submission time.** If the candidate's
final state doesn't boot — `python manage.py runserver` errors, `npm run
dev` errors, the page is white — **no progress points are awarded**,
regardless of how much code was written. (The harness automatically
commits the final state on `interview finish`, so this is judged from
that state — candidates aren't expected to commit anything themselves.)
A candidate who can't keep their build green spent their time poorly.

**Crediting a feature.** A feature counts when it works end-to-end in the
running app, not when it's "mostly there." Partial credit on a single
feature (e.g. add works, remove is broken) is allowed but should be the
exception, not the rule — two interviewers agree on the partial value.

**Auto-detection.** ClaudeScore can probe many features automatically (does
this model exist, does this endpoint respond, does the build pass). The
auto-detected total is a *suggestion*; the interviewer can override per
feature in the cohort scoring sheet.

---

## 3. Code review — holistic, light — 15 pts

Reviewer spends ~10 minutes in `solution.patch` and the final tree. **Do not
line-audit.** Score 1–5 (→ ×3) on a gut read of:
- Is the structure sane? Reasonable Django/JS idioms?
- Naming and readability — could a teammate pick this up?
- Did they write *any* tests / validation, or just happy-path?
- Any glaring correctness or security smell (raw SQL, secrets, no input checks)?

A junior who shipped clean, modest, working code should score well here.

---

## 4. Hidden adjustments — operator only

[`docs/HIDDEN_RUBRIC.md`](HIDDEN_RUBRIC.md) lists operator-only adjustments
to the Code Review and AI Collaboration components, capped at ±5 each. It
exists because some signals (TypeScript strict mode, paste-and-disengage,
N+1 queries, swallowed exceptions) are more valuable when they're organic
— spelling them out would turn them into a checklist to game.

The hidden rubric **never raises the cap** of the composite mark; it
nudges within the existing 50 / 35 / 15 weights. Do not share that file
with candidates.

---

## Red flags (notes for the panel — not auto-fail)
- **Write-only session** — lots of writes, almost no reads. They never reviewed
  Claude's work.
- **Huge paste** — a large chunk of code appears with no preceding prompt that
  would have produced it (possible outside source). Surfaces as an anomaly.
- **Early give-up** — low progress + a session much shorter than 2h.
- **Off-box tools** — anything suggesting they didn't work in Claude Code as
  instructed.

## Anti-gaming
- Politeness, token spend, and raw prompt count are **not** rewarded on their
  own. A candidate cannot climb the mark by being chatty or burning tokens.
- The judge is grounded in the transcript and asked to cite; spot-check its
  citations on borderline candidates rather than trusting the number.

---

## Producing the mark

1. `claude_score interview finish "<name>" --judge` → `report.html` + the judge
   scores and metrics.
2. Fill the three components above into the worksheet (or a spreadsheet).
3. Two interviewers score independently, then reconcile. The transcript replay
   in the report is the shared evidence.
