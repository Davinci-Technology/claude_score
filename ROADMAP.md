# ClaudeScore roadmap

v1 (this scaffold) is **transcript-first, standalone CLI, HTML report,
light-touch** — exactly what the upcoming hiring interview needs. Below is how
it grows into the full "vibe coding challenge" platform.

## Now (v1 — done)
- [x] JSONL transcript parser (handles tool-result echoes, sidechains, meta noise)
- [x] Deterministic metrics (tokens, cost, cache, tools, pacing, politeness, corrections)
- [x] Trait badges (per candidate) + cohort badges (competitive)
- [x] Optional LLM judge pass (tone / prompt quality / autonomy / review / recovery)
- [x] HTML + Markdown scorecard, CLI (`list`, `analyze`)
- [x] Interview harness: `preflight`, `start`, `finish`, `status` — per-candidate isolation, solution capture (git diff/log), env lockdown checks, sealed evidence bundle.

## Next — nice-to-haves before the first interview
- [ ] PDF export of the scorecard (the `intw/` folder already generates candidate PDFs — reuse that path).
- [ ] Light anomaly flags (still light-touch, no blocking): detect large pastes or non-Claude AI processes during the window and surface as report warnings, not gates.
- [ ] `claude_score cohort <dir>` command: analyze many candidates side-by-side, emit cohort awards + a comparison page (also the bridge to the hackathon mode).

## Later — live proctoring (real-time hooks)
- [ ] Ship a `settings.json` hook bundle (UserPromptSubmit / PreToolUse / Stop) that streams events to a local collector during the session.
- [ ] Live interviewer dashboard: watch prompts/tool calls as they happen.
- [ ] Tamper-evidence: hooks corroborate the transcript.

## Later — hackathon at scale (OTEL)
- [ ] Point each participant's Claude Code at an OTEL collector (`CLAUDE_CODE_ENABLE_TELEMETRY=1`) for cross-machine token/cost metrics.
- [ ] Leaderboard web app (FastAPI + React, or fold into `claude_code_coach`): live standings, the awards ceremony, badge citations.
- [ ] Team / bracket support, time-boxed rounds, per-feature scoring.

## Design notes
- The **analysis engine is mode-agnostic**: interview and hackathon share parsing, metrics, and badges. Only capture (transcript vs hooks vs OTEL) and presentation differ.
- Keep the core dependency-light (stdlib + jinja2). The judge (`anthropic`) and any future web layer stay optional.
- All thresholds and pricing live in one place per module so they're trivial to tune per cohort.
