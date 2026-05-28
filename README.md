# ◍ ClaudeScore

**Sense how a developer collaborates with Claude Code.**

ClaudeScore reads Claude Code session transcripts and turns them into a readable
"pulse": exact usage metrics, a set of fun behavioural badges, and an optional
LLM-judged style assessment. It was built for two internal uses:

- **Interview mode** — a candidate codes on a dedicated box using only Claude
  Code. Afterwards, point ClaudeScore at their session and get a one-page
  scorecard for the interviewers: how they prompted, whether they reviewed the
  agent's work, how they recovered from mistakes, token economy, and tone.
- **Hackathon mode** (the "vibe coding challenge") — analyse many participants
  and hand out competitive awards: Most Polite, Biggest Spender, Cleanest Run,
  Cache King, and friends. *(Cohort scoring is built; a leaderboard front-end
  is on the roadmap.)*

It is **transcript-first**: it reads the JSONL files Claude Code already writes
to `~/.claude/projects/`, so there's nothing to install on the candidate's
session and nothing to configure mid-interview. Remote Control and Dispatch
sessions land in the same place, so they're covered too.

## Why this works

Every Claude Code session writes a complete JSONL transcript. Each line carries
the human's prompt text, the model's text/thinking/tool calls, exact token
usage (including cache), timestamps, and the model used. That's enough to
reconstruct *how* someone worked — not just what they shipped.

## Install

```bash
cd claude_score
pip install -e .            # core (jinja2)
pip install -e ".[judge]"   # also enable the LLM judge pass (needs anthropic)
```

## Usage

### Interview workflow (the main path)

```bash
# Before the candidate sits down: verify the box is ready.
claude_score interview preflight

# Set up a per-candidate working dir and seed the problem.
claude_score interview start "Jane Doe" --problem ./problem-statement
# -> ~/interviews/jane-doe/ (with git init + initial commit)
# -> prints: cd into it and run `claude`

# When time's up, seal everything into one evidence bundle.
claude_score interview finish "Jane Doe" --judge
# -> ~/interviews/jane-doe/report.html, report.md
# -> ~/interviews/jane-doe/solution.patch + git.log
# -> ~/interviews/jane-doe/transcripts/*.jsonl
# -> ~/interviews/jane-doe/candidate.json (sealed manifest)

# Where are we?
claude_score interview status
```

The harness closes the three operational gaps: per-candidate isolation
(each candidate gets their own working dir, so transcripts don't mingle),
solution capture (`git init` at start, snapshot the diff at finish), and
env lockdown (`preflight` checks for suppression env vars and short
retention windows).

### Ad-hoc analysis

```bash
# What sessions exist on this machine?
claude_score list

# Analyze the bundled demo
claude_score analyze examples/sample_session.jsonl --candidate "Demo" --html demo.html

# Analyze any project folder (point at the munged dir name or path)
claude_score analyze C--Users-jane-interview-task --candidate "Jane Doe" --html jane.html

# Add the LLM judge pass (requires ANTHROPIC_API_KEY)
claude_score analyze examples/sample_session.jsonl --judge --html demo.html
```

`analyze` prints a terminal summary and, with `--html`/`--md`, writes a
shareable report. A `target` can be a `.jsonl` file, a project directory, a
munged project name under `~/.claude/projects/`, or a session id.

## What it measures

**Deterministic (exact, no LLM):** prompt count & length, tool-call mix and
tools-per-prompt (autonomy vs micromanagement), token totals + cache-reuse
ratio, estimated cost, correction rate, session duration and pacing, and a
politeness heuristic.

**LLM judge (optional):** prompt quality, autonomy, review discipline,
recovery, and tone scored 1–5, plus a short written read and badge suggestions
grounded in the transcript.

## Badges

Trait badges (interview, absolute) and cohort badges (hackathon, competitive)
live in `claude_score/badges.py` and are easy to tune. Examples: 🙏 The Diplomat,
😤 The Drill Sergeant, 🐋 The Whale, 🪙 The Miser, 🎯 One-Shot,
🌀 The Micromanager, 🧘 The Trusting, 🦉 The Reviewer, ♻️ The Cache Whisperer.

## Caveats

- Token **cost** is an estimate; verify the rates in `metrics.py:PRICING`.
- Politeness and badge thresholds are **directional heuristics**, not a
  personality test — use them as conversation starters, not gospel.
- Claude Code *on the web* runs in the cloud and is not stored locally, so for
  the interview box use the local CLI (Remote Control / Dispatch are fine).

See [ROADMAP.md](ROADMAP.md) for what's next (hooks for live proctoring, OTEL
for cross-machine leaderboards, a hackathon dashboard).
