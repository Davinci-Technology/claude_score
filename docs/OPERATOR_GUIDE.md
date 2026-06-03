# Operator guide

The job: candidate sits down at the box, opens Claude Code, and starts
shipping features. Everything else — repo cloned, deps installed, DB
running, secrets in place — is already done. This guide is the checklist
that gets you there.

It assumes the box itself has been provisioned per [`SETUP.md`](SETUP.md)
(Python, Node, Docker, Claude Code, ClaudeScore, isolated `CLAUDE_CONFIG_DIR`,
TMDB key set). If not, do that first.

---

## Where things live on the box

```
$HOME\code\
  ├── claude_score\           # the assessment tool (this repo)
  └── movie_deck\             # the candidate's problem (cloned from the org)
$HOME\interviews\
  └── <candidate-slug>\       # one folder per candidate, created by `interview start`
$HOME\.claude-interview\      # isolated Claude Code config (your account, fresh state)
```

The candidate works in `$HOME\interviews\<their-slug>\`. They never see the
two repos under `$HOME\code\`.

---

## Once per interview week — Monday morning, before the first candidate

Do these once, in order. After this, per-candidate prep takes ~5 minutes.

### 1. Make sure the problem repo is cloned and up to date

```powershell
if (-not (Test-Path "$HOME\code\movie_deck")) {
    git clone https://github.com/Davinci-Technology/movie_deck.git "$HOME\code\movie_deck"
} else {
    cd "$HOME\code\movie_deck"; git pull --ff-only
}
```

### 2. Make sure ClaudeScore is current

```powershell
cd "$HOME\code\claude_score"
git pull --ff-only
. .\.venv\Scripts\Activate.ps1
pip install -e ".[judge]" --quiet --upgrade
```

### 3. Warm the caches (so per-candidate install is fast)

The first candidate's `pip install` and `npm install` would otherwise download
from the internet. Pre-warm so subsequent candidates install from local cache.

```powershell
# Start Docker Desktop. Wait until the system tray icon shows "Engine running".
# Then pre-pull the Postgres image so `docker compose up` is instant:
docker pull postgres:16

# Warm the pip cache for the backend deps:
cd "$HOME\code\movie_deck\backend"
python -m venv .venv-warm
.\.venv-warm\Scripts\Activate.ps1
pip download -r requirements.txt -d "$HOME\.pip-cache" --quiet
deactivate
Remove-Item -Recurse -Force .venv-warm

# Warm the npm cache for the frontend deps:
cd "$HOME\code\movie_deck\frontend"
npm install --prefer-offline --no-audit --no-fund   # populates ~/.npm
Remove-Item -Recurse -Force node_modules
```

After this, every per-candidate `pip install` and `npm install` is local-only
and runs in seconds instead of minutes.

### 4. Verify the box is ready

```powershell
cd "$HOME\code\claude_score"
. .\.venv\Scripts\Activate.ps1
python -m claude_score interview preflight
```

You want **`✓ Preflight clean — capture is unblocked.`** Fix anything
flagged red before any candidate arrives.

### 5. Do one end-to-end dry run

Use yourself as the test candidate. This catches anything the preflight
doesn't (Docker not booting, TMDB key wrong, npm version drift, etc.):

```powershell
python -m claude_score interview start "Dry Run" --problem "$HOME\code\movie_deck"
cd "$HOME\interviews\dry-run"

# Boot the starter exactly as the candidate will:
docker compose up -d db
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt; python manage.py migrate; python manage.py runserver
# In another terminal:
cd "$HOME\interviews\dry-run\frontend"; npm install; npm run dev
```

Open <http://localhost:5173>. You should see two green panels (backend
health + TMDB ping). If TMDB ping fails with `key not configured`, your
TMDB_API_KEY env var didn't get forwarded — fix per the
[Troubleshooting guide](TROUBLESHOOTING.md).

When happy, tear it down:

```powershell
cd "$HOME\interviews\dry-run"; docker compose down -v
cd "$HOME"; Remove-Item -Recurse -Force "$HOME\interviews\dry-run"
```

---

## Per candidate — ~5 minutes before they arrive

### 1. Create the candidate folder and seed the problem

```powershell
cd "$HOME\code\claude_score"; . .\.venv\Scripts\Activate.ps1
python -m claude_score interview start "Jane Doe" --problem "$HOME\code\movie_deck"
```

You'll see something like:

```
✓ Candidate folder created at C:\Users\Operator\interviews\jane-doe
  problem seeded from C:\Users\Operator\code\movie_deck
  forwarded into .env: TMDB_API_KEY
  candidate branch: jane-doe (off main; origin removed — no accidental push)
```

Because the problem source is itself a git repo, the harness **clones it**
into the candidate folder, **removes the `origin` remote**, and checks the
candidate out on a fresh branch named after them off `main`. They can use
git however they like during the session; they cannot push (and shouldn't
need to). You push their branch up after the week — see "Pushing branches
after the week" below.

If you don't see `forwarded into .env: TMDB_API_KEY`, the operator-env key
didn't propagate — open a fresh PowerShell (env-var changes don't show up
in already-open shells) and re-run.

### 2. Pre-boot the starter so M0 is green when they sit down

```powershell
$dir = "$HOME\interviews\jane-doe"
cd $dir
docker compose up -d db

cd "$dir\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --no-index --find-links "$HOME\.pip-cache" --quiet
python manage.py migrate

cd "$dir\frontend"
npm install --prefer-offline --no-audit --no-fund
```

This takes ~30 seconds end to end if the caches are warm. The candidate
will only need to start the dev servers (`python manage.py runserver` and
`npm run dev`), not install anything.

### 3. Smoke check, then leave it clean

```powershell
cd "$dir\backend"; .\.venv\Scripts\Activate.ps1
Start-Process powershell -ArgumentList "python manage.py runserver"
# In another window:
cd "$dir\frontend"; npm run dev
# Open http://localhost:5173 — confirm both panels are green
# Then close both servers (Ctrl+C in each window) so the candidate starts fresh
```

The DB container stays running. That's fine — leave it.

### 4. Open a fresh terminal in the candidate folder for them

```powershell
Start-Process powershell -WorkingDirectory $dir
```

They run `claude` in that window. That's the only command they need.

---

## When time is called

```powershell
cd "$HOME\code\claude_score"; . .\.venv\Scripts\Activate.ps1
python -m claude_score interview finish "Jane Doe" --judge
```

You get the sealed evidence bundle at `$HOME\interviews\jane-doe\` with
`report.html`, `report.md`, `solution.patch`, `git.log`, full transcripts,
and the manifest. Open `report.html` to review.

Archive the folder, then tear down the DB to free the port for the next
candidate:

```powershell
cd "$HOME\interviews\jane-doe"; docker compose down -v
Compress-Archive -Path "$HOME\interviews\jane-doe" `
                 -DestinationPath "$HOME\interviews\archive\jane-doe-$(Get-Date -Format yyyyMMdd).zip"
```

---

## End of week — cohort review

```powershell
ls "$HOME\interviews"                               # see who's been through
python -m claude_score interview status             # same, with manifests
```

The composite hiring mark per `docs/SCORING.md` combines:
- **AI collaboration (50 pts)** — automatic from each candidate's `report.html`.
- **Progress (35 pts)** — sum of feature points from
  [`docs/PROBLEMS/moviedeck.md`](PROBLEMS/moviedeck.md) (operator-only menu)
  that the candidate actually shipped, scaled.
- **Code review (15 pts)** — your read of `solution.patch` for ~10 min per candidate.

Plus ±5 per component from [`docs/HIDDEN_RUBRIC.md`](HIDDEN_RUBRIC.md).

For now: keep a one-row-per-candidate spreadsheet with those three columns,
adjustments, total, and a rank. The cohort comparison view
(`examples/sample-cohort/index.html` is a worked sample) is what you'd
share with the panel once the spreadsheet is filled in.

---

## Pushing candidates' branches after the week

Each candidate's folder is a clone of `movie_deck` with the work sitting on
a branch named after them (e.g. `jane-doe`). `origin` was removed at
`interview start` to make accidental pushes impossible. After the week,
when you're ready to preserve their branches in the org repo, re-add
`origin` with a Personal Access Token and push.

**Per candidate:**

```powershell
$dir  = "$HOME\interviews\jane-doe"
$slug = "jane-doe"
$pat  = "$env:GITHUB_PAT"   # PAT with repo write on Davinci-Technology/movie_deck

cd $dir
git remote add origin "https://$pat@github.com/Davinci-Technology/movie_deck.git"
git push origin $slug
git remote remove origin    # security hygiene: don't leave the token sitting in .git/config
```

**For all candidates in the cohort root** (one loop):

```powershell
$pat = "$env:GITHUB_PAT"
Get-ChildItem $HOME\interviews -Directory | ForEach-Object {
    $dir  = $_.FullName
    $slug = $_.Name
    if (-not (Test-Path "$dir\.git")) { return }  # skip archives, etc
    Push-Location $dir
    git remote add origin "https://$pat@github.com/Davinci-Technology/movie_deck.git" 2>$null
    git push origin $slug
    git remote remove origin
    Pop-Location
}
```

After the loop, every candidate's branch is on the org's movie_deck repo,
named after them — exactly what you'd review and merge from.

---

## Common operator mistakes

- **Forgetting Docker Desktop.** The DB container won't start, `migrate`
  fails, M0 is red before the candidate even sits down. Confirm Docker is
  running before step 2 of per-candidate prep.
- **Stale PowerShell after setting env vars.** Setting `TMDB_API_KEY` at
  the User scope doesn't affect already-open shells. After
  `setup-windows.ps1`, always open a *fresh* PowerShell before `interview start`.
- **Running `claude` from the wrong directory.** Claude Code writes its
  transcript under the *current* working directory. If you forget to `cd`
  into the candidate folder before launching `claude`, the candidate's
  transcript lands in the wrong project dir under `~/.claude-interview/`
  and `interview finish` won't find it.
- **Hopping between candidates without `docker compose down`.** The DB
  port stays bound from the previous candidate; the next candidate's
  `docker compose up` will silently use the same container (which has the
  prior candidate's data in it). Always tear it down between candidates.
- **Forgetting to run `--judge`.** Without it, the report has the
  deterministic metrics but no collaboration scores, which is the 50%
  chunk of the rubric. Always include `--judge` at finish time unless
  you're explicitly skipping LLM scoring.
