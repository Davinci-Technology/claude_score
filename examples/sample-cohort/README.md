# Sample end-of-week cohort report

A worked example of the final report you'd share with the hiring panel
after a week of interviews. Open `index.html` in a browser.

**This is demonstration data.** The candidate names (Riley Chen, Sam Patel,
Jordan Kim) are fictional; the underlying Claude Code transcripts are real
prior project work on this box. The human-entered Progress / Code Review
sub-scores and the hidden-rubric adjustments are stubbed plausibly to
illustrate the final shape — in a real week, interviewers fill those in
after reviewing each candidate per [`docs/SCORING.md`](../../docs/SCORING.md)
and [`docs/HIDDEN_RUBRIC.md`](../../docs/HIDDEN_RUBRIC.md).

## What's in `index.html`

1. **Recommendation** — ranked table with composite mark (0–100) and a
   recommendation band per candidate.
2. **Component breakdown** — stacked-bar view of how each candidate's
   composite splits across the rubric's 50 / 35 / 15.
3. **Per-candidate detail** — panel-friendly observations, features shipped,
   and the specific hidden-rubric adjustments the interviewer applied.
4. **Metrics evidence** — raw metrics table backing the marks: prompts,
   tools/prompt, work tokens, cache reuse, rewinds.
5. **Links to each candidate's full scorecard** for the detailed transcript
   and badge breakdown.

## Files

| File | What it is |
|---|---|
| `index.html` | Final cohort report (start here) |
| `riley-chen.html` | Per-candidate scorecard (high autonomy, lots shipped) |
| `sam-patel.html` | Per-candidate scorecard (balanced, caught a Claude bug) |
| `jordan-kim.html` | Per-candidate scorecard (focused, cleanest code) |
| `generate.py` | The script that produced everything in this folder |

## Regenerating

```bash
pip install -e .       # from the claude_score repo root
python examples/sample-cohort/generate.py
```

Edit `CANDIDATES` in `generate.py` to swap real session folders or to
adjust the stubbed `HumanScores` numbers.

## What's not in this sample

- The optional **LLM judge pass** (per-axis 1–5 scores plus a written
  read) is not run on these per-candidate scorecards for speed. Pass
  `--judge` when generating real reports and each per-candidate scorecard
  gains those sections automatically.
- The **auto-progress detector** (which would check the candidate's code
  against the feature menu and fill in the Progress sub-score for you) is
  on the roadmap; until it lands, the Progress and Code Review numbers
  are filled in by hand per `docs/SCORING.md`.
