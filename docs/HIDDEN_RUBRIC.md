# Hidden rubric — operator only

**Do not share this file with candidates.** It exists so the hiring panel
can score signals that *shouldn't* be on the candidate-visible feature menu
— either because spelling them out would turn them into a checklist to
optimise, or because the signal is more valuable when it's organic.

The hidden rubric **adjusts within** the existing rubric weights (50 / 35 /
15). It does not raise the cap. Specifically, it nudges the **Code Review
(15 pts)** and **AI Collaboration (50 pts)** components by up to ±5 each.

> **A note on pasting.** Pasting the problem statement (or large parts of
> it) into Claude is **not** a penalty by itself. The signal we care about
> is whether the candidate then *iterates* — refining, reviewing,
> course-correcting — or *disengages* and lets Claude grind autonomously
> with no oversight. Paste-then-iterate is exactly what we want.

---

## A. Code-quality adjustments

Apply during your ~10-minute read of `solution.patch` and the final tree.
Sum the penalties and bonuses; cap at ±5 around the holistic Code Review
score.

### Penalties — code that would make a senior wince

| Signal | Adjustment |
|---|---:|
| TypeScript `any` or `// @ts-ignore` anywhere in their code | −2 |
| Hard-coded secrets in source (TMDB key, DB password, etc.) instead of env vars | −2 |
| N+1 queries in any list endpoint | −2 |
| Wrong HTTP status codes (200 on create, 200 on validation error, etc.) | −1 |
| No input validation on the create endpoint | −1 |
| Catching exceptions and swallowing them silently | −1 |
| Direct DOM manipulation in React (`innerHTML`, `document.querySelector` for state) | −1 |

### Bonuses — things a senior notices and appreciates

| Signal | Adjustment |
|---|---:|
| Sensible error responses (useful messages, problem-details shape) | +1 |
| Proper HTTP status codes throughout | +1 |
| Idempotent endpoints where appropriate | +1 |
| Frontend accessibility basics (alt text, semantic HTML, keyboard nav) | +1 |
| A useful `NOTES.md` (decisions, trade-offs, what they'd do next) | +1 |

### Why these are hidden

- **TypeScript strict** — telling them "we evaluate TS strict mode" makes
  it a 2-line tweak. Not telling them rewards candidates who naturally
  reach for type safety.
- **Hard-coded secrets** — universally wrong; we want to know who knows
  that without being told.
- **HTTP status codes** — junior tells; if they need to be reminded to
  return 201 on create, they're junior even after 5 years.
- **N+1 queries** — Claude *will* generate these. Who catches it?

---

## B. Process adjustments

Apply after reading the scorecard's prompt replay and the judge's notes,
or by skimming the transcript directly for borderline candidates. Cap at
±5 around the AI Collaboration score.

### Penalties — failure modes in driving the agent

| Signal | Adjustment |
|---|---:|
| **Paste-and-walk-away.** Large problem statement pasted, then an extended stretch (15+ min) with minimal prompts / no review of Claude's output. | −3 |
| Accepting substantial code changes without *ever* inspecting them (no Read calls between Edits, no questions to Claude) | −2 |
| Re-running the same failing prompt instead of diagnosing | −1 |
| Wall-of-text prompts: dumping unrelated context as a heuristic to "get better output" | −1 |

### Bonuses — signs of a strong agent driver

| Signal | Adjustment |
|---|---:|
| Asked Claude to explain its choices and pushed back when wrong | +2 |
| Caught a bug Claude introduced and corrected it themselves | +2 |
| Used planning tools / extended thinking / TodoWrite deliberately | +1 |
| Wrote prompts that included examples or constraints, not just goals | +1 |

---

## C. How to apply

1. Run `claude_score interview finish <name> --judge` and open `report.html`.
2. Skim the prompt replay and the judge's notes for the process signals
   in section B. Tally adjustments.
3. Open `solution.patch` and the final tree. Spend ~10 minutes on the
   code-quality signals in section A. Tally adjustments.
4. Apply each cap (±5). The composite mark is:

   ```
   composite = collaboration + collaboration_adjustment      # capped ±5
             + progress                                       # from feature menu
             + code_review + code_review_adjustment           # capped ±5
   ```

5. Note the adjustments in your scoring sheet. When two interviewers
   reconcile, surface any −2/+2 items you each saw — those are the
   discussion-worthy signals.

---

## D. What NOT to penalise

- **Pasting the problem statement.** As above — only paste-and-disengage
  is a problem.
- **Long sessions of high autonomy** where the candidate is still
  reviewing, asking questions, and steering. High autonomy with
  engagement is the *goal*, not a red flag.
- **Choices we don't share.** If they pick raw CSS instead of a UI
  library, neither library choice is a hidden penalty. We hire people
  with judgement, not people who guess our preferences.
- **Tone.** Already a reported-but-not-scored field on the rubric — keep
  it that way here too.
- **Git discipline.** Candidates are explicitly told they don't have to
  commit anything (the harness auto-commits the final state). So don't
  penalise "no intermediate commits" or reward "frequent commits" — those
  signals aren't part of this assessment.
