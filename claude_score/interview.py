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


def start(
    candidate: str,
    problem: Optional[Path] = None,
    root: Path = DEFAULT_ROOT,
    force: bool = False,
) -> Path:
    """Create a candidate working directory, seed the problem, and commit it."""
    slug = slugify(candidate)
    candidate_dir = root / slug
    if candidate_dir.exists() and any(candidate_dir.iterdir()) and not force:
        raise FileExistsError(
            f"{candidate_dir} already exists and is non-empty. Use force=True to overwrite."
        )
    candidate_dir.mkdir(parents=True, exist_ok=True)

    problem_source = _seed_problem(candidate_dir, problem) if problem else None
    forwarded_env = _forward_env_from_example(candidate_dir)

    if _git_available():
        _git(candidate_dir, "init", "-q")
        _commit_all(candidate_dir, "interview start")

    manifest = CandidateManifest(
        candidate=candidate,
        slug=slug,
        started_at=datetime.now().isoformat(timespec="seconds"),
        workdir=str(candidate_dir.resolve()),
        problem_source=problem_source,
        forwarded_env_keys=forwarded_env,
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
        diff = _git(candidate_dir, "diff", "HEAD~1", "HEAD")
        (candidate_dir / "solution.patch").write_text(diff.stdout, encoding="utf-8")
        log = _git(candidate_dir, "log", "--oneline")
        (candidate_dir / "git.log").write_text(log.stdout, encoding="utf-8")

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

    # 3. Analyse and write the scorecard.
    sessions = parse_target(transcript_copy) if any(transcript_copy.iterdir()) else []
    metrics = compute(sessions, candidate=manifest["candidate"])
    badges = evaluate_trait_badges(metrics)
    judge_result = (
        judge_candidate(sessions, candidate=manifest["candidate"], model=model)
        if judge and sessions
        else None
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
