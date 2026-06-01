"""Slash-command capture: invocations are counted, not silently dropped."""

import json
from pathlib import Path

from claude_score.metrics import compute
from claude_score.report import build_context, render_html, to_markdown
from claude_score.transcript import parse_target


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    f = tmp_path / "session.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return f


def _user(content, **extra):
    return {"type": "user", "timestamp": "2026-05-28T10:00:00Z",
            "message": {"role": "user", "content": content}, **extra}


def test_slash_commands_counted_without_inflating_prompts(tmp_path):
    rows = [
        _user("Please build a parser, thank you."),       # real prompt
        _user("<command-name>clear</command-name>\n<command-message>x</command-message>"),
        _user("<command-name>/compact</command-name>"),   # leading slash already present
        _user("<command-name>review feature-x</command-name>"),  # carries args
        _user("Now add tests."),                          # real prompt
    ]
    sessions = parse_target(_write(tmp_path, rows))
    m = compute(sessions, candidate="demo")

    # Two genuine prompts; the three command messages are not prompts.
    assert m.prompt_count == 2
    assert m.slash_command_count == 3
    # Normalised to a single leading slash, args stripped.
    assert m.slash_command_breakdown == {"/clear": 1, "/compact": 1, "/review": 1}


def test_repeated_command_aggregates(tmp_path):
    rows = [_user("<command-name>clear</command-name>") for _ in range(3)]
    sessions = parse_target(_write(tmp_path, rows))
    m = compute(sessions, candidate="demo")
    assert m.slash_command_count == 3
    assert m.slash_command_breakdown == {"/clear": 3}


def test_sidechain_commands_excluded(tmp_path):
    rows = [
        _user("<command-name>clear</command-name>"),
        _user("<command-name>sub</command-name>", isSidechain=True),
    ]
    sessions = parse_target(_write(tmp_path, rows))
    m = compute(sessions, candidate="demo")
    assert m.slash_command_count == 1
    assert m.slash_command_breakdown == {"/clear": 1}


def test_commands_surface_in_reports(tmp_path):
    rows = [
        _user("Do the thing."),
        _user("<command-name>clear</command-name>"),
    ]
    sessions = parse_target(_write(tmp_path, rows))
    m = compute(sessions, candidate="demo")
    ctx = build_context("demo", m, [], None, sessions)

    assert ("Slash commands", "1") in ctx["key_metrics"]
    assert ctx["commands"] == [{"name": "/clear", "count": 1, "pct": 100}]
    assert "Slash commands" in render_html(ctx)
    assert "`/clear` ×1" in to_markdown(ctx)
