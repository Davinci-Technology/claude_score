"""Tests for the interview harness.

The end-to-end finish test fakes the Claude Code projects dir via the
``CLAUDE_CONFIG_DIR`` env var (which ``discovery.projects_root()`` honours)
and drops a synthetic JSONL whose ``cwd`` points at the candidate folder.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from claude_score import interview


def test_slugify_handles_messy_input():
    assert interview.slugify("Jane  Doe") == "jane-doe"
    assert interview.slugify("Émile O'Connor") == "mile-o-connor"
    assert interview.slugify("---") == "candidate"
    assert interview.slugify("a_b-c") == "a_b-c"


def test_preflight_returns_issues():
    issues = interview.preflight()
    assert isinstance(issues, list) and issues
    # Every issue should have a known severity.
    assert all(i.severity in {"error", "warn", "ok"} for i in issues)


def test_start_creates_dir_and_manifest(tmp_path: Path):
    root = tmp_path / "interviews"
    candidate_dir = interview.start("Jane Doe", problem=None, root=root)

    assert candidate_dir == root / "jane-doe"
    manifest = json.loads((candidate_dir / interview.MANIFEST).read_text("utf-8"))
    assert manifest["candidate"] == "Jane Doe"
    assert manifest["slug"] == "jane-doe"
    assert manifest["workdir"]


def test_start_seeds_problem_files(tmp_path: Path):
    problem = tmp_path / "problem"
    problem.mkdir()
    (problem / "README.md").write_text("Build a thing.", encoding="utf-8")
    (problem / "task.py").write_text("# starter\n", encoding="utf-8")

    candidate_dir = interview.start(
        "Sam", problem=problem, root=tmp_path / "interviews"
    )
    assert (candidate_dir / "README.md").read_text("utf-8") == "Build a thing."
    assert (candidate_dir / "task.py").exists()


def _synthetic_transcript(cwd: Path) -> str:
    """Minimal valid JSONL that ``_find_project_for_cwd`` will match on."""
    cwd_str = str(cwd).replace("\\", "\\\\")
    return "\n".join([
        json.dumps({
            "type": "user", "sessionId": "fake", "cwd": str(cwd),
            "timestamp": "2026-05-28T10:00:00Z", "isSidechain": False,
            "message": {"role": "user", "content": "please add a /health endpoint, thanks!"},
        }),
        json.dumps({
            "type": "assistant", "sessionId": "fake",
            "timestamp": "2026-05-28T10:00:05Z", "isSidechain": False,
            "message": {
                "model": "claude-sonnet-4-6", "role": "assistant",
                "content": [
                    {"type": "text", "text": "Sure."},
                    {"type": "tool_use", "id": "t1", "name": "Write",
                     "input": {"file_path": "app.py"}},
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        }),
    ]) + "\n"


def test_finish_end_to_end(tmp_path: Path, monkeypatch):
    # Make ~/.claude live inside tmp_path so we don't touch the real one.
    fake_home = tmp_path / "home"
    (fake_home / "projects").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(fake_home))

    root = tmp_path / "interviews"
    candidate_dir = interview.start("Pat Lee", root=root)

    # Drop a synthetic transcript into a fake project folder whose first
    # event's cwd points at the candidate dir.
    project_dir = fake_home / "projects" / "fake-project"
    project_dir.mkdir(parents=True)
    (project_dir / "fake.jsonl").write_text(
        _synthetic_transcript(candidate_dir), encoding="utf-8"
    )

    sealed = interview.finish("Pat Lee", root=root)
    assert sealed == candidate_dir
    assert (sealed / "report.html").exists()
    assert (sealed / "report.md").exists()
    assert (sealed / "transcripts" / "fake.jsonl").exists()

    manifest = json.loads((sealed / interview.MANIFEST).read_text("utf-8"))
    assert manifest["finished_at"]
    assert manifest["project_dir"] and "fake-project" in manifest["project_dir"]

    # Git-dependent artifacts only if git is on PATH.
    if shutil.which("git"):
        assert (sealed / "solution.patch").exists()
        assert (sealed / "git.log").exists()


def test_finish_records_warning_when_no_transcript(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / "projects").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(fake_home))

    root = tmp_path / "interviews"
    interview.start("Ghost", root=root)

    sealed = interview.finish("Ghost", root=root)
    manifest = json.loads((sealed / interview.MANIFEST).read_text("utf-8"))
    assert manifest.get("project_dir") is None
    assert "transcript_warning" in manifest
