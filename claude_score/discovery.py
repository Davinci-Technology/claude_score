"""Locate Claude Code transcripts on disk.

Claude Code stores transcripts under ``~/.claude/projects/<munged-cwd>/``
where ``<munged-cwd>`` is the working directory with path separators and other
characters replaced by ``-``. We can't perfectly reverse the munging (it is
lossy), but we can list projects and rank them by recency, which is all the
CLI needs for a "what's available?" view.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def projects_root() -> Path:
    """Return ~/.claude/projects, honouring CLAUDE_CONFIG_DIR if set."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(base) if base else Path.home() / ".claude"
    return root / "projects"


@dataclass
class ProjectDir:
    name: str          # the munged directory name
    path: Path         # absolute path to the project dir
    session_count: int
    last_modified: datetime
    readable_hint: str  # best-effort un-munged path for display


def _unmunge(name: str) -> str:
    """Best-effort, lossy reconstruction of the original working directory."""
    # Leading "C--Users-..." -> "C:/Users/...". Not exact, just a display hint.
    hint = name
    if len(hint) > 1 and hint[1:3] == "--":
        hint = hint[0] + ":" + hint[2:]
    return hint.replace("-", "/")


def list_projects() -> list[ProjectDir]:
    root = projects_root()
    if not root.is_dir():
        return []
    projects: list[ProjectDir] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        sessions = list(child.glob("*.jsonl"))
        if not sessions:
            continue
        last = max((s.stat().st_mtime for s in sessions), default=0)
        projects.append(
            ProjectDir(
                name=child.name,
                path=child,
                session_count=len(sessions),
                last_modified=datetime.fromtimestamp(last),
                readable_hint=_unmunge(child.name),
            )
        )
    projects.sort(key=lambda p: p.last_modified, reverse=True)
    return projects


def resolve_target(token: str) -> Path:
    """Resolve a CLI target token into a path.

    Accepts, in order of precedence:
      * an existing file or directory path,
      * a munged project name under ~/.claude/projects/,
      * a session id (matched against *.jsonl filenames in any project).
    """
    p = Path(token)
    if p.exists():
        return p

    root = projects_root()
    candidate = root / token
    if candidate.is_dir():
        return candidate

    # Treat as a session id: search for <id>.jsonl across all projects.
    if root.is_dir():
        for jsonl in root.glob(f"*/{token}.jsonl"):
            return jsonl
        for jsonl in root.glob(f"*/*{token}*.jsonl"):
            return jsonl

    raise FileNotFoundError(
        f"Could not resolve '{token}' to a file, project, or session id."
    )
