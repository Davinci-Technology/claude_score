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

**Scored axes (from the judge):** average these four, each 1–5 → scale to 50.

| Axis | What a 5 looks like | What a 1–2 looks like |
|---|---|---|
| **Prompt quality** | Clear goals, useful context, good constraints; breaks work down | Vague one-liners, no context, expects mind-reading |
| **Autonomy** | Delegates whole units of work, lets Claude run, steps in when needed | Either micromanages every keystroke OR blindly accepts everything |
| **Review discipline** | Reads diffs, asks Claude to justify, catches mistakes before they compound | Never inspects output; ships whatever appears |
| **Recovery** | Debugs methodically, re-scopes when stuck, uses errors as signal | Spirals, repeats the same failing prompt, gives up |

> `process_pts = (prompt_quality + autonomy + review_discipline + recovery) / 20 × 50`

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

---

## 2. Progress — how far they got — 35 pts

The problem ships a **milestone ladder (M0–M5)**. Award points per milestone
reached, with partial credit. This is the "how far in 2 hours" axis.

| Milestone | Pts | Gate |
|---|---:|---|
| **M0** Project runs, DB connected, migrations apply | 5 | `must run` |
| **M1** Core model + CRUD API persists to Postgres | 8 | |
| **M2** Status workflow + server-side validation | 6 | |
| **M3** Minimal JS/TS UI talking to the API | 6 | |
| **M4** Edge cases, error handling, a few tests | 6 | |
| **M5** One stretch goal (auth / drag-drop / Docker / …) | 4 | |

Partial credit is fine (e.g. CRUD works but delete is broken → 5/8). If **M0
doesn't run at all**, cap progress at 5 regardless of code volume — a candidate
who can't get it running spent the time poorly.

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
