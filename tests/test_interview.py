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


def _git(*args: str, cwd: Path) -> None:
    """Shell out to git in a test, raising if it fails. Used to set up fixtures."""
    import subprocess
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True,
    )


def _make_problem_repo(tmp_path: Path) -> Path:
    """Build a tiny problem repo to clone in tests."""
    import shutil as _sh
    if not _sh.which("git"):
        import pytest as _pytest
        _pytest.skip("git not on PATH")
    repo = tmp_path / "problem-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Problem\n", encoding="utf-8")
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("add", "README.md", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    return repo


def test_start_clones_problem_repo_and_creates_candidate_branch(tmp_path: Path):
    repo = _make_problem_repo(tmp_path)

    candidate_dir = interview.start(
        "Jane Doe", problem=repo, root=tmp_path / "interviews"
    )

    # Clone preserved the boilerplate's history.
    assert (candidate_dir / ".git").is_dir()
    assert (candidate_dir / "README.md").read_text("utf-8") == "# Problem\n"

    # Candidate is on a branch named after them.
    manifest = json.loads((candidate_dir / interview.MANIFEST).read_text("utf-8"))
    assert manifest["candidate_branch"] == "jane-doe"
    assert manifest["base_branch"] in {"main", "master"}

    # Origin was removed so the candidate cannot accidentally push.
    import subprocess
    remotes = subprocess.run(
        ["git", "remote"], cwd=candidate_dir, capture_output=True, text=True,
    )
    assert remotes.stdout.strip() == ""


def test_finish_diffs_against_base_branch_for_multi_commit_candidate(
    tmp_path: Path, monkeypatch
):
    """A candidate making multiple commits gets the full delta in solution.patch."""
    repo = _make_problem_repo(tmp_path)
    fake_home = tmp_path / "home"
    (fake_home / "projects").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(fake_home))

    candidate_dir = interview.start(
        "Multi Commit", problem=repo, root=tmp_path / "interviews"
    )

    # Simulate the candidate making three independent commits on their branch.
    for n in range(1, 4):
        (candidate_dir / f"feature_{n}.py").write_text(f"# feature {n}\n", encoding="utf-8")
        _git("add", f"feature_{n}.py", cwd=candidate_dir)
        _git("commit", "-q", "-m", f"feat {n}", cwd=candidate_dir)

    interview.finish("Multi Commit", root=tmp_path / "interviews")

    patch = (candidate_dir / "solution.patch").read_text(encoding="utf-8")
    # All three commits' content should be in the patch — not just the last one.
    for n in range(1, 4):
        assert f"feature_{n}.py" in patch, f"feature_{n}.py missing from diff"

    log = (candidate_dir / "git.log").read_text(encoding="utf-8")
    assert log.count("\n") >= 3  # at least three commits on the branch


def test_start_forwards_env_from_example(tmp_path: Path, monkeypatch):
    """When the problem declares vars via .env.example, fill them from operator env."""
    problem = tmp_path / "problem"
    problem.mkdir()
    (problem / ".env.example").write_text(
        "# comments are ignored\n"
        "TMDB_API_KEY=\n"
        "GOOGLE_OAUTH_CLIENT_ID=\n"
        "NOT_IN_OPERATOR_ENV=\n",
        encoding="utf-8",
    )
    (problem / "README.md").write_text("...", encoding="utf-8")

    monkeypatch.setenv("TMDB_API_KEY", "the-tmdb-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "the-client-id")
    monkeypatch.delenv("NOT_IN_OPERATOR_ENV", raising=False)

    candidate_dir = interview.start(
        "Pat", problem=problem, root=tmp_path / "interviews"
    )

    env_path = candidate_dir / ".env"
    assert env_path.exists()
    env_text = env_path.read_text(encoding="utf-8")
    assert "TMDB_API_KEY=the-tmdb-secret" in env_text
    assert "GOOGLE_OAUTH_CLIENT_ID=the-client-id" in env_text
    assert "NOT_IN_OPERATOR_ENV" not in env_text

    manifest = json.loads((candidate_dir / interview.MANIFEST).read_text("utf-8"))
    assert set(manifest["forwarded_env_keys"]) == {
        "TMDB_API_KEY",
        "GOOGLE_OAUTH_CLIENT_ID",
    }


def test_start_skips_env_forwarding_when_no_example(tmp_path: Path, monkeypatch):
    problem = tmp_path / "problem"
    problem.mkdir()
    (problem / "README.md").write_text("...", encoding="utf-8")
    monkeypatch.setenv("TMDB_API_KEY", "should-not-be-forwarded")

    candidate_dir = interview.start(
        "Lee", problem=problem, root=tmp_path / "interviews"
    )

    assert not (candidate_dir / ".env").exists()
    manifest = json.loads((candidate_dir / interview.MANIFEST).read_text("utf-8"))
    assert manifest["forwarded_env_keys"] == []


def _synthetic_transcript(cwd: Path) -> str:
    """Minimal valid JSONL that ``_transcripts_under_cwd`` will match on."""
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


def test_finish_aggregates_sessions_from_subdirectories(tmp_path: Path, monkeypatch):
    """Sessions started from a subfolder of the candidate dir land in a separate
    project dir; finish should still gather them as the same candidate."""
    fake_home = tmp_path / "home"
    (fake_home / "projects").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(fake_home))

    root = tmp_path / "interviews"
    candidate_dir = interview.start("Dana Kim", root=root)

    # Session 1: ran in the candidate folder itself.
    top = fake_home / "projects" / "proj-top"
    top.mkdir(parents=True)
    (top / "s1.jsonl").write_text(_synthetic_transcript(candidate_dir), encoding="utf-8")

    # Session 2: ran in a subfolder — a different munged project dir.
    sub = fake_home / "projects" / "proj-sub"
    sub.mkdir(parents=True)
    (sub / "s2.jsonl").write_text(
        _synthetic_transcript(candidate_dir / "backend"), encoding="utf-8"
    )

    # An unrelated session elsewhere on the box must NOT be swept in.
    other = fake_home / "projects" / "proj-other"
    other.mkdir(parents=True)
    (other / "s3.jsonl").write_text(
        _synthetic_transcript(tmp_path / "somewhere-else"), encoding="utf-8"
    )

    sealed = interview.finish("Dana Kim", root=root)
    copied = sorted(p.name for p in (sealed / "transcripts").glob("*.jsonl"))
    assert copied == ["s1.jsonl", "s2.jsonl"]

    manifest = json.loads((sealed / interview.MANIFEST).read_text("utf-8"))
    assert len(manifest["project_dirs"]) == 2


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
