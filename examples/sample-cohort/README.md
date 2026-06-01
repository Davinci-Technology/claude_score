# Sample cohort report

A worked example of what ClaudeScore produces at the end of an interview week.
Open `index.html` in a browser.

**This is demonstration data.** The candidate names (Riley Chen, Sam Patel,
Jordan Kim) are fictional; the underlying Claude Code transcripts are from
real prior project work on this box. That means metric shapes, badge logic,
and the comparison layout faithfully represent what a real cohort report
will look like — only the names and the framing are demo.

## Files

| File | What it is |
|---|---|
| `index.html` | Cohort comparison page — links to each candidate's full scorecard |
| `riley-chen.html` | Per-candidate scorecard (heavy user, high autonomy) |
| `sam-patel.html` | Per-candidate scorecard (mid-volume, balanced) |
| `jordan-kim.html` | Per-candidate scorecard (focused session, fewer prompts) |
| `generate.py` | The script that produced everything in this folder |

## Regenerating

```bash
pip install -e .       # from the claude_score repo root
python examples/sample-cohort/generate.py
```

The outputs overwrite cleanly. Edit `CANDIDATES` in `generate.py` to point at
different session folders on your box, or change the blurbs.

## What's not in this sample yet

- The **composite hiring mark** (collaboration 50 + progress 35 + code review 15 → 0–100) is described in `docs/SCORING.md` but is computed on a per-candidate worksheet that combines automated metrics with human-entered scores. The cohort view shown here is metrics-only.
- The optional **LLM judge pass** (per-axis 1–5 scores plus a written read) is not run in this sample for speed. Pass `--judge` when generating real reports and the scorecard adds those sections automatically.
- The **auto-progress detector** (which checks the candidate's code for feature completion against the problem's feature menu) is in `ROADMAP.md` and will land alongside the cohort command.
