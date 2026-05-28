# Context for Claude — ClaudeScore Interview Box

You are running on a dedicated device whose only job is to host coding interviews where candidates use Claude Code to solve a problem. This file is auto-loaded by Claude Code; keep it in mind for the whole session.

## What this box is for

This box is the **ClaudeScore interview station**. Candidates sit at it during a hiring interview, run `claude` from a per-candidate working directory, and solve a coding problem using only the Claude CLI. After the interview, ClaudeScore parses their session transcript and produces a scorecard.

(You are running inside the ClaudeScore repo itself — <https://github.com/Davinci-Technology/claude_score>. If you are a developer working on the package rather than an operator setting up the box, see `README.md` and `ROADMAP.md` instead.)

## What you will be asked to do

The interviewer ("the operator") will typically ask for one of three things:

1. **"Set this box up."** First-time provisioning. Follow `docs/SETUP.md` end to end. Don't skip the env lockdown step — that's the whole reason this device exists.
2. **"Start an interview for `<name>`."** Run the preflight, then `python -m claude_score interview start "<name>" --problem ./problem`. Confirm the candidate folder exists and tell the operator the next command for the candidate to run.
3. **"Finish the interview for `<name>`."** Run `python -m claude_score interview finish "<name>" --judge` and report where the sealed bundle is.

When in doubt about which mode you're in, ask the operator before changing anything.

## Hard rules

- **Never** run `python -m claude_score interview finish` while a candidate is still working. It seals the bundle and writes a final git commit.
- **Never** set `CLAUDE_CODE_SKIP_PROMPT_HISTORY` or pass `--no-session-persistence`. That suppresses the transcript and defeats the tool's purpose.
- **Never** push transcripts, candidate folders, or the contents of `~/interviews/` anywhere off the box without explicit permission.
- **Never** unset `CLAUDE_CONFIG_DIR` or run Claude Code/ClaudeScore against `~/.claude/`. The whole isolation story breaks if you do.
- **Never** install Claude Desktop on this box, and don't open claude.ai in a browser here. The CLI alone keeps the operator's chat history off this device; the Desktop/web do not.
- Bash/PowerShell commands you run are part of the operator's session, not a candidate's session. Keep operator and candidate work clearly separated.

## Where things live (defaults)

This box uses an **isolated Claude Code config directory** so the operator's personal account can be used for billing without exposing any prior CLI history. The env var `CLAUDE_CONFIG_DIR` points Claude Code and ClaudeScore at the same isolated location.

| Thing | Path |
|---|---|
| ClaudeScore source | `~/code/claude_score/` (clone target in `SETUP.md`) |
| Claude Code state | `~/.claude-interview/` (not `~/.claude/`) |
| Transcripts | `~/.claude-interview/projects/<munged-cwd>/*.jsonl` |
| Settings | `~/.claude-interview/settings.json` |
| Candidate folders | `~/interviews/<candidate-slug>/` |
| Problem statements | Wherever the operator points `--problem` at |

If `CLAUDE_CONFIG_DIR` is unset on this box, treat that as a setup error — re-run `scripts/setup-windows.ps1` or follow `docs/SETUP.md` step 5.

## The four phases of a candidate's day

```
preflight  →  start  →  candidate runs `claude`  →  finish  →  archive
```

`docs/SETUP.md` covers the first ever boot of the box. `docs/INTERVIEW_DAY.md` covers every interview after that.

## Tone

Be concise with the operator. They are running a hiring loop and don't want a wall of text between commands. Confirm what you did, name the next step, stop.
