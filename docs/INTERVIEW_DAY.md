# Interview-day runbook

Five steps per candidate. The whole thing is designed to be 30 seconds of operator effort on each side of the interview.

Activate the venv first if you opened a fresh shell:

```powershell
cd $HOME\code\claude_score
. .\.venv\Scripts\Activate.ps1
```

## 1. Preflight (before the candidate arrives)

```powershell
python -m claude_score interview preflight
```

Expect `✓ Preflight clean — capture is unblocked.` If anything is `[error]`, fix it before proceeding — see `TROUBLESHOOTING.md`.

## 2. Start the interview (candidate is about to begin)

```powershell
python -m claude_score interview start "Jane Doe" --problem .\path\to\problem
```

`--problem` can be a directory, a single file, or a `.zip` archive — its contents are copied into the candidate folder and committed as the starting state.

**Secrets get forwarded automatically.** If the problem ships an `.env.example` (MovieDeck does, declaring `TMDB_API_KEY`), `interview start` reads every key listed there from your environment and writes them into the candidate's `.env`. The candidate never sees the values, never has to sign up for anything, and your `.env` is gitignored so the secret doesn't end up in their commit history.

You'll see something like:

```
✓ Candidate folder created at C:\Users\Operator\interviews\jane-doe
  problem seeded from .\path\to\problem
  forwarded into .env: TMDB_API_KEY

Next steps:
  1. cd "C:\Users\Operator\interviews\jane-doe"
  2. claude
  3. when done: python -m claude_score interview finish "Jane Doe"
```

## 3. Hand off to the candidate

Open a fresh terminal in the candidate folder for them:

```powershell
cd $HOME\interviews\jane-doe
claude
```

That's the **only** command they should run. The rule is "use Claude Code to solve the problem." A standalone shell or browser tab defeats the data collection.

## 4. Finish (time's up)

```powershell
python -m claude_score interview finish "Jane Doe" --judge
```

`--judge` runs the optional LLM pass that adds tone / prompt-quality / autonomy / review-discipline / recovery scores. Omit if you don't have `ANTHROPIC_API_KEY` set on this box.

The bundle ends up at `$HOME\interviews\jane-doe\` with:

- `report.html` and `report.md` — the scorecard you share with interviewers
- `solution.patch` and `git.log` — the candidate's actual work
- `transcripts/*.jsonl` — full conversation with Claude
- `candidate.json` — sealed manifest with timestamps and metadata

Open the HTML to review:

```powershell
Invoke-Item .\report.html
```

## 5. Archive

After the hiring discussion, archive the candidate folder somewhere safe:

```powershell
Compress-Archive -Path "$HOME\interviews\jane-doe" `
                 -DestinationPath "$HOME\interviews\archive\jane-doe-$(Get-Date -Format yyyyMMdd).zip"
```

You can now delete `$HOME\interviews\jane-doe\` if you need the disk space; the zip is the sealed record.

## Listing what's on the box

At any point:

```powershell
python -m claude_score interview status
```

shows every candidate folder under `~/interviews/` and whether each one is in-progress or finished.

---

## What to do if a candidate restarts Claude mid-interview

That's fine. Claude Code starts a new session JSONL each time but they all land in the same project folder (because the candidate's working dir is the same). `interview finish` copies the whole folder, so everything is captured.

## What to do if a candidate uses `/clear`

Also fine. `/clear` ends one session and starts another — both transcripts are written to disk and both are picked up.

## What to do if a candidate runs `claude` from the wrong directory

Sessions started from the candidate folder **or any subfolder of it** (e.g. `.../jane-doe/backend`) are gathered automatically — `finish` matches on each session's recorded working directory, not just an exact path, so they all aggregate as one candidate.

Only a session started entirely **outside** the candidate folder is missed. If that happens, `finish` records a `transcript_warning` on the manifest ("No transcript folder … matched cwd=… or any subfolder"). Tell the candidate to exit and `cd` into the candidate folder before running `claude` again, or manually copy their transcript JSONLs into the candidate folder's `transcripts/` directory and re-run `finish`.
