"""Interview harness.

Wraps the three operational gaps that surfaced during design into one workflow
so nothing can drift on interview day:

1. **Per-candidate isolation** — each candidate gets their own working
   directory, so their Claude Code transcripts land in their own project
   folder under ``~/.claude/projects/`` and never co-mingle.
2. **Solution capture** — the working dir is a git repo. We commit the
   starting state, commit the final state on finish, and snapshot the diff
   into a patch file so you can grade the result alongside the process.
3. **Env lockdown** — a preflight check confirms that nothing on the box
   would silently suppress transcript capture.

After ``finish``, the candidate folder is a self-contained evidence bundle:
the working tree, the git history, a copy of every transcript JSONL, a
``solution.patch``, and the ClaudeScore scorecard (``report.html`` + ``report.md``).

The module is pure Python so it runs the same on Windows, macOS, and Linux.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import discovery
from .badges import evaluate_trait_badges
from .judge import DEFAULT_JUDGE_MODEL, judge_candidate
from .metrics import compute
from .report import build_context, to_markdown, write_html
from .transcript import parse_target

DEFAULT_ROOT = Path.home() / "interviews"
MANIFEST = "candidate.json"

# Env vars that, if set on the box, would silently suppress transcript capture
# (or otherwise compromise the evidence we need to analyse).
_SUPPRESS_VARS = ["CLAUDE_CODE_SKIP_PROMPT_HISTORY"]
# Light advisory: these don't break transcripts but are worth surfacing.
_ADVISORY_VARS = ["DISABLE_TELEMETRY", "DO_NOT_TRACK", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"]


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------

@dataclass
class Issue:
    severity: str  # "error" | "warn" | "ok"
    message: str


@dataclass
class CandidateManifest:
    candidate: str
    slug: str
    started_at: str
    workdir: str
    problem_source: Optional[str] = None
    forwarded_env_keys: list[str] = field(default_factory=list)
    # When the problem source is itself a git repo, the harness clones it and
    # checks the candidate out on a fresh branch named after them; this is
    # that branch name. None when the problem was a plain directory.
    candidate_branch: Optional[str] = None
    base_branch: Optional[str] = None  # branch the candidate branch was cut from
    finished_at: Optional[str] = None
    project_dir: Optional[str] = None
    notes: str = ""


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-")
    return s or "candidate"


def _git_available() -> bool:
    return shutil.which("git") is not None


def _git(cwd: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _commit_all(repo: Path, message: str) -> None:
    """Stage everything and make a (possibly empty) commit with a stable identity."""
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c", "user.email=interview@claude_score.local",
        "-c", "user.name=ClaudeScore",
        "commit", "-q", "--allow-empty", "-m", message,
    )


# ----------------------------------------------------------------------------
# Preflight (env lockdown verification)
# ----------------------------------------------------------------------------

def preflight() -> list[Issue]:
    """Return any issues that would compromise capture on this box."""
    issues: list[Issue] = []

    for var in _SUPPRESS_VARS:
        if os.environ.get(var):
            issues.append(Issue(
                "error",
                f"{var} is set in the environment — Claude Code will not write "
                f"a transcript. Unset it before the interview.",
            ))

    if shutil.which("claude") is None:
        issues.append(Issue(
            "error",
            "`claude` command not found on PATH. Install Claude Code on the box.",
        ))

    if not _git_available():
        issues.append(Issue(
            "warn",
            "`git` not found on PATH. The harness can run without it, but you "
            "lose the solution-capture diff/log.",
        ))

    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append(Issue("warn", f"{settings_path} is not valid JSON."))
            data = {}
        cleanup = data.get("cleanupPeriodDays")
        if isinstance(cleanup, (int, float)) and cleanup < 60:
            issues.append(Issue(
                "warn",
                f"cleanupPeriodDays={cleanup} in {settings_path}. Transcripts "
                f"may be auto-deleted; bump to 90+ for safer retention.",
            ))
    else:
        issues.append(Issue(
            "warn",
            f"{settings_path} not found — defaults apply (~30 day transcript "
            f"retention). Archive each candidate's folder immediately.",
        ))

    projects = discovery.projects_root()
    if projects.exists() and not os.access(projects, os.W_OK):
        issues.append(Issue("error", f"{projects} is not writable."))

    advisory = [v for v in _ADVISORY_VARS if os.environ.get(v)]
    if advisory:
        issues.append(Issue(
            "warn",
            f"Telemetry-suppressing env vars set: {', '.join(advisory)}. "
            f"These don't break transcripts but disable the optional OTEL path.",
        ))

    if not issues:
        issues.append(Issue("ok", "Preflight clean — capture is unblocked."))
    return issues


# ----------------------------------------------------------------------------
# Start: set up a per-candidate working dir
# ----------------------------------------------------------------------------

_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


def _forward_env_from_example(candidate_dir: Path) -> list[str]:
    """If the problem ships a ``.env.example``, fill any declared keys from the operator's env.

    For each ``KEY=...`` line found in ``.env.example``, if ``KEY`` is set in
    ``os.environ`` with a non-empty value, write ``KEY=<value>`` into
    ``candidate_dir/.env``. Keys not present in the operator's environment are
    left out (the candidate's app should already handle a missing key
    gracefully — that's a starter requirement, not an interview surprise).

    Returns the list of keys forwarded, for logging / manifesting.
    """
    example = candidate_dir / ".env.example"
    if not example.is_file():
        return []

    forwarded: list[tuple[str, str]] = []
    for line in example.read_text(encoding="utf-8").splitlines():
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key = match.group(1)
        value = os.environ.get(key, "").strip()
        if value:
            forwarded.append((key, value))

    if forwarded:
        env_path = candidate_dir / ".env"
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        existing_keys = {
            m.group(1)
            for line in existing.splitlines()
            if (m := _ENV_LINE.match(line))
        }
        new_lines = [
            f"{key}={value}"
            for key, value in forwarded
            if key not in existing_keys
        ]
        if new_lines:
            sep = "" if not existing or existing.endswith("\n") else "\n"
            env_path.write_text(existing + sep + "\n".join(new_lines) + "\n", encoding="utf-8")
    return [key for key, _ in forwarded]


def _seed_problem(candidate_dir: Path, problem: Path) -> str:
    """Copy or extract the problem source into the candidate's working dir."""
    if problem.is_dir():
        for item in problem.iterdir():
            dest = candidate_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        return str(problem)
    if problem.suffix.lower() in {".zip", ".tar", ".gz", ".tgz", ".bz2"}:
        shutil.unpack_archive(str(problem), str(candidate_dir))
        return str(problem)
    if problem.is_file():
        shutil.copy2(problem, candidate_dir / problem.name)
        return str(problem)
    raise FileNotFoundError(f"Problem source not found: {problem}")


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _current_branch(repo: Path) -> Optional[str]:
    out = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return out.stdout.strip() or None if out.returncode == 0 else None


def _clone_problem(problem: Path, candidate_dir: Path, slug: str) -> tuple[str, str]:
    """Clone an existing repo into ``candidate_dir`` and cut a fresh candidate branch.

    Returns ``(candidate_branch, base_branch)``. The clone keeps the problem's
    full history (so candidates see the boilerplate's commits and can rebase /
    sub-branch normally), but the ``origin`` remote is **removed** — candidates
    are explicitly told not to push, and we make it impossible for them to do
    so by accident. The operator re-adds the remote after the interview to
    push the candidate's branch up.
    """
    # candidate_dir must not exist for `git clone <repo> <dest>` to behave well.
    if candidate_dir.exists() and not any(candidate_dir.iterdir()):
        candidate_dir.rmdir()
    subprocess.run(
        ["git", "clone", "--quiet", str(problem), str(candidate_dir)],
        check=True, capture_output=True, text=True,
    )
    # Note the base branch (whatever HEAD points at after clone — usually 'main').
    base = _current_branch(candidate_dir) or "main"
    # No remote pushing during the interview.
    _git(candidate_dir, "remote", "remove", "origin")
    # Check the candidate out on a branch named after them.
    _git(candidate_dir, "checkout", "-q", "-b", slug)
    return slug, base


def start(
    candidate: str,
    problem: Optional[Path] = None,
    root: Path = DEFAULT_ROOT,
    force: bool = False,
) -> Path:
    """Create a candidate working directory and seed the problem.

    Two modes depending on what ``problem`` points at:

    * **git repo** — clone the repo, remove ``origin`` (so the candidate
      cannot push), and check the candidate out on a fresh branch named
      after them off the repo's default branch. They use git normally
      (commits, sub-branches) but cannot accidentally push. The operator
      pushes the candidate's branch after the interview week, with a
      token, per ``docs/OPERATOR_GUIDE.md``.

    * **plain directory or archive** — copy files in and start a fresh
      git repo with a single ``interview start`` commit (legacy behaviour;
      used by tests and by problems that aren't git repos themselves).
    """
    slug = slugify(candidate)
    candidate_dir = root / slug
    if candidate_dir.exists() and any(candidate_dir.iterdir()) and not force:
        raise FileExistsError(
            f"{candidate_dir} already exists and is non-empty. Use force=True to overwrite."
        )

    problem_source: Optional[str] = None
    candidate_branch: Optional[str] = None
    base_branch: Optional[str] = None

    if problem and Path(problem).is_dir() and _is_git_repo(Path(problem)) and _git_available():
        # Clone mode.
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_branch, base_branch = _clone_problem(Path(problem), candidate_dir, slug)
        problem_source = str(problem)
    else:
        # Copy / legacy mode.
        candidate_dir.mkdir(parents=True, exist_ok=True)
        if problem:
            problem_source = _seed_problem(candidate_dir, Path(problem))
        if _git_available():
            _git(candidate_dir, "init", "-q")

    forwarded_env = _forward_env_from_example(candidate_dir)

    # Only the legacy mode needs an artificial 'interview start' commit; in
    # clone mode the boilerplate's existing history is the baseline.
    if _git_available() and base_branch is None:
        _commit_all(candidate_dir, "interview start")

    manifest = CandidateManifest(
        candidate=candidate,
        slug=slug,
        started_at=datetime.now().isoformat(timespec="seconds"),
        workdir=str(candidate_dir.resolve()),
        problem_source=problem_source,
        forwarded_env_keys=forwarded_env,
        candidate_branch=candidate_branch,
        base_branch=base_branch,
    )
    (candidate_dir / MANIFEST).write_text(
        json.dumps(asdict(manifest), indent=2), encoding="utf-8"
    )
    return candidate_dir


# ----------------------------------------------------------------------------
# Finish: seal everything into an evidence bundle
# ----------------------------------------------------------------------------

def _first_cwd(jsonl: Path) -> Optional[str]:
    """Read the ``cwd`` recorded on the first event of a transcript that has one.

    A munged project dir corresponds to a single working directory, so the
    first event carrying a ``cwd`` identifies where the whole session ran.
    """
    try:
        with jsonl.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = entry.get("cwd")
                if cwd:
                    return cwd
    except OSError:
        return None
    return None


def _is_within(cwd: str, base: Path) -> bool:
    """True if ``cwd`` is ``base`` itself or a directory nested inside it."""
    try:
        Path(cwd).resolve().relative_to(base)
        return True
    except (ValueError, OSError):
        return False


def _transcripts_under_cwd(target_cwd: Path) -> list[Path]:
    """Every transcript whose session ran in target_cwd *or a subdirectory of it*.

    We don't try to reverse Claude Code's CWD munging — we read the ``cwd`` field
    off each transcript and keep the ones nested under the candidate folder. This
    catches sessions a candidate started from a subfolder (e.g. ``.../backend``),
    which land in a separate project dir, so the whole folder aggregates as one
    candidate.
    """
    target = target_cwd.resolve()
    projects = discovery.projects_root()
    if not projects.is_dir():
        return []

    hits: list[Path] = []
    for project_dir in sorted(projects.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl in sorted(project_dir.glob("*.jsonl")):
            cwd = _first_cwd(jsonl)
            if cwd and _is_within(cwd, target):
                hits.append(jsonl)
    return hits


def finish(
    candidate: str,
    root: Path = DEFAULT_ROOT,
    judge: bool = False,
    model: str = DEFAULT_JUDGE_MODEL,
) -> Path:
    """Close out a candidate's interview and produce the evidence bundle."""
    slug = slugify(candidate)
    candidate_dir = root / slug
    manifest_path = candidate_dir / MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No interview started for '{candidate}'. Expected {manifest_path}."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. Solution capture: final commit + patch + log.
    if _git_available() and (candidate_dir / ".git").is_dir():
        _commit_all(candidate_dir, "interview end")

        # Pick the base ref to diff against. In clone mode the manifest records
        # ``base_branch`` (typically 'main'), so we get the full candidate delta
        # regardless of how many commits they made. In legacy mode there is no
        # base branch, so fall back to the first commit on HEAD.
        base_ref = manifest.get("base_branch")
        if not base_ref:
            first = _git(candidate_dir, "rev-list", "--max-parents=0", "HEAD")
            base_ref = first.stdout.strip().splitlines()[0] if first.stdout.strip() else "HEAD"

        diff = _git(candidate_dir, "diff", f"{base_ref}..HEAD")
        (candidate_dir / "solution.patch").write_text(diff.stdout, encoding="utf-8")

        # Show the candidate's commits (every commit they made on their branch
        # since cutting off the base), plus the branch they ended on.
        log = _git(candidate_dir, "log", "--oneline", f"{base_ref}..HEAD")
        (candidate_dir / "git.log").write_text(log.stdout, encoding="utf-8")
        manifest["final_branch"] = _current_branch(candidate_dir)
        # List every branch they touched, for the operator to know what to push.
        branches = _git(candidate_dir, "branch", "--format=%(refname:short)")
        manifest["local_branches"] = [
            b for b in branches.stdout.splitlines() if b.strip()
        ]

    # 2. Locate and copy in the candidate's transcripts. Every session that ran
    #    inside the candidate folder (or any subfolder) is gathered here, even
    #    across multiple project dirs, so the whole folder aggregates as one
    #    candidate.
    transcripts = _transcripts_under_cwd(candidate_dir)
    transcript_copy = candidate_dir / "transcripts"
    transcript_copy.mkdir(exist_ok=True)
    if not transcripts:
        # Don't fail outright — record it on the manifest and let the
        # interviewer investigate. The scorecard will simply be empty.
        manifest["project_dir"] = None
        manifest["transcript_warning"] = (
            f"No transcript folder under {discovery.projects_root()} matched "
            f"cwd={candidate_dir.resolve()} or any subfolder. Did the candidate "
            f"run `claude` inside the candidate folder?"
        )
    else:
        project_dirs: list[str] = []
        for jsonl in transcripts:
            dest = transcript_copy / jsonl.name
            if dest.exists():
                # Same session-id filename from two project dirs — disambiguate.
                dest = transcript_copy / f"{jsonl.parent.name}__{jsonl.name}"
            shutil.copy2(jsonl, dest)
            if str(jsonl.parent) not in project_dirs:
                project_dirs.append(str(jsonl.parent))
        # Keep the singular field for back-compat; list them all alongside it.
        manifest["project_dir"] = project_dirs[0]
        manifest["project_dirs"] = project_dirs

    # 3. Analyse and write the scorecard. Feed the judge the candidate's diff vs
    #    the boilerplate (solution.patch) and a smoke-test report if the operator
    #    dropped one in the candidate folder, so it can score the PRODUCT too.
    sessions = parse_target(transcript_copy) if any(transcript_copy.iterdir()) else []
    metrics = compute(sessions, candidate=manifest["candidate"])
    badges = evaluate_trait_badges(metrics)
    judge_result = None
    if judge and sessions:
        patch = candidate_dir / "solution.patch"
        code_diff = patch.read_text(encoding="utf-8", errors="replace") if patch.exists() else None
        smoke_file = next(
            (candidate_dir / n for n in ("smoke.txt", "smoke_report.txt", "smoke.md")
             if (candidate_dir / n).exists()),
            None,
        )
        smoke_report = smoke_file.read_text(encoding="utf-8", errors="replace") if smoke_file else None
        judge_result = judge_candidate(
            sessions, candidate=manifest["candidate"], model=model,
            code_diff=code_diff, smoke_report=smoke_report,
        )
    context = build_context(manifest["candidate"], metrics, badges, judge_result, sessions)
    write_html(context, candidate_dir / "report.html")
    (candidate_dir / "report.md").write_text(to_markdown(context), encoding="utf-8")

    # 4. Seal the manifest.
    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return candidate_dir


# ----------------------------------------------------------------------------
# Status: list known candidates under a root
# ----------------------------------------------------------------------------

@dataclass
class CandidateRow:
    slug: str
    candidate: str
    started_at: str
    finished_at: Optional[str]
    workdir: str


def status(root: Path = DEFAULT_ROOT) -> list[CandidateRow]:
    if not root.is_dir():
        return []
    rows: list[CandidateRow] = []
    for child in sorted(root.iterdir()):
        manifest = child / MANIFEST
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows.append(CandidateRow(
            slug=data.get("slug", child.name),
            candidate=data.get("candidate", child.name),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at"),
            workdir=data.get("workdir", str(child)),
        ))
    return rows
