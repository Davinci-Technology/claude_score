# Candidate turnaround — operator checklists

Run this on the ClaudeScore interview box (Windows) **between candidates**, in
order: first **back up** the candidate who just finished (Checklist A), then
**prepare** the box for the next person (Checklist B). Everything here mirrors
the live process — adjust names/paths as needed.

**Conventions**
- Candidate working folder: `Desktop\<Name>\movie_deck` (one folder per candidate)
- Hidden archive root: `C:\Users\<you>\interview-archive\<Name>`
- Problem repo: `Davinci-Technology/movie_deck`; boilerplate = `main` branch
- Scoring tool: this repo (claude_score), branch **`judge-v2-strict`**
- Pushes need a **fresh write-scoped GitHub token**, used inline in the URL and
  **revoked afterward**. The box stores no token (so candidates can't push).

---

## Checklist A — Back up the finishing candidate

Do this **before touching anything else**, so nothing is lost. Never modify the
candidate's files — only add to a record folder and copy.

- [ ] **Stop their dev processes** (so files aren't locked):
  - `Get-Process python | Stop-Process -Force` (kills the `runserver` reloader pair)
  - `Get-Process node,esbuild | Stop-Process -Force`
- [ ] **Consolidate + push their branch(es)** to the remote (primary code backup). From `Desktop\<Name>\movie_deck`:
  - capture any uncommitted work first: `git add -A && git commit -m "final working state"` (as the candidate)
  - merge their side branches into `<Name>` if they made several
  - `git -c credential.helper= push "https://<TOKEN>@github.com/Davinci-Technology/movie_deck.git" <Name>:<Name>` (push each branch you want kept)
- [ ] **Archive from durable sources — do NOT move the live folder.**
  > ⚠️ Don't `robocopy /MOVE` (or `mv`) the candidate folder and then delete the source. `node_modules` / `.venv` / `.git` get locked (PyCharm `fsnotifier`, Docker compose working-dir, Windows SYSTEM); a partial move + `Remove-Item -Force` on the source **deletes files that were never moved**. The remote (code+report) and `~\.claude` (transcript) are the durable copies — rebuild the archive from those.
  - **Re-clone** the candidate's branch into the archive (full history, all branches, committed report):
    - `git clone "https://<TOKEN>@github.com/Davinci-Technology/movie_deck.git" "C:\Users\<you>\interview-archive\<Name>\movie_deck"`
    - `git -C ...\<Name>\movie_deck checkout <Name>` then `git -C ... remote set-url origin https://github.com/Davinci-Technology/movie_deck.git` (strip the token)
  - **Copy the transcript** (the original always stays in `~\.claude` — only ever copy it):
    `interview-archive\<Name>\_assessment_record\transcripts\` ← `~\.claude\projects\C--…-Desktop-<Name>*\*.jsonl`
  - **Regenerate the record:** `solution.diff` ← `git diff main..<Name>` (from the clone); copy `movie_deck\assessment\report.html`+`report.md`; write `REPLAY.md`. `smoke.txt` is re-derivable (backend `manage.py test` + frontend `tsc -b && vite build` on a throwaway `git worktree`) and the committed report already reflects it.
  - `attrib +h "C:\Users\<you>\interview-archive"`
- [ ] **Verify the archive is complete**: transcript present, `movie_deck\.git` present (all branches), `report.md` present. **Only after this** —
- [ ] **Remove the Desktop folder** with `Remove-Item -Recurse -Force` (a clean delete of a fully-archived folder — never `Remove-Item` a half-moved source). Stubborn IDE/SYSTEM locks on `node_modules`/`.git` clear on **reboot**; if it won't delete, hide it (`attrib +h`) and let the next reboot finish it.
- [ ] **Protect the transcript**: set `cleanupPeriodDays: 90` in `~\.claude\settings.json` so the live copy isn't auto-purged.

---

## Checklist B — Prepare the box for the next candidate

Only after Checklist A is **verified**.

- [ ] **Gate:** confirm the previous candidate is fully archived. Do not proceed otherwise.
- [ ] **Remove the previous candidate's Desktop folder** (it's safe in the archive). Empty shells held by an IDE/Explorer/SYSTEM clear on reboot.
- [ ] **Reset the database** to a clean slate:
  - `docker rm -f moviedeck-db; docker volume rm movie_deck_moviedeck-db-data`
  - `docker compose up -d db` (from the new clone) → wait for `healthy`
- [ ] **Create exactly one** `Desktop\<NewName>` and clone the boilerplate:
  - `git clone -b main "https://<TOKEN>@github.com/Davinci-Technology/movie_deck.git" "Desktop\<NewName>\movie_deck"`
  - `git -C ... remote set-url origin https://github.com/Davinci-Technology/movie_deck.git` (strip the token)
- [ ] **Cut + push their branch**: `git checkout -b <NewName>` → push `<NewName>:<NewName>` with the token.
- [ ] **Lock down git** (commit/branch locally, NO push):
  - `git config user.name "<NewName>"; git config user.email "<newname>@interview.local"`
  - `git config credential.helper ""` (disable the helper for this repo)
  - confirm: origin URL has no token; `GIT_TERMINAL_PROMPT=0 git push --dry-run` fails on auth; a local `--allow-empty` commit on a throwaway branch succeeds
- [ ] **Wire the TMDB key** (operator-provided):
  - `TMDB_API_KEY=<v3 key>` in `Desktop\<NewName>\movie_deck\.env`
  - ignore any pasted `tmdb-credentials.json` via `.git\info\exclude` (keeps the tracked `.gitignore` and the working tree clean)
  - validate: `curl "https://api.themoviedb.org/3/movie/550?api_key=<key>"` → HTTP 200
- [ ] **Preflight the box**:
  - tools present: `claude --version`, `git`, `node`, `docker`, `python`
  - Docker daemon up + `moviedeck-db` healthy
  - capture **not** suppressed: `CLAUDE_CODE_SKIP_PROMPT_HISTORY` empty (User + Machine); `cleanupPeriodDays` ≥ 60
- [ ] **Privacy sweep** (what the candidate can see):
  - Desktop shows only `<NewName>` + shortcuts — no prior candidate folders or reports
  - `Documents\Projects` (claude_score + tooling) hidden; `interview-archive` hidden
- [ ] **Reboot** for a fully clean session (recommended — releases leftover locks).
- [ ] **Hand off:** candidate opens a terminal in `Desktop\<NewName>\movie_deck`, runs `claude`, follows `BOOT.md`. That is the only command they run.

---

## Re-judging an archived candidate later

- Clone claude_score **`judge-v2-strict`**, `python -m venv .venv`, `pip install -e .`.
- `python -m claude_score analyze "interview-archive\<Name>\_assessment_record\transcripts" --candidate <Name> --judge --diff "...\solution.diff" --smoke "...\smoke.txt"`
- No `ANTHROPIC_API_KEY`? Run the judge through an in-session subagent using
  `claude_score.judge.build_judge_message` + `parse_judge_json` (identical rubric).
