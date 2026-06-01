"""Rewind detection from the conversation DAG.

A rewind keeps the abandoned messages and appends a new branch, so a human
prompt that is not an ancestor of the final message was rewound away. Tool-call
fan-out also creates same-parent siblings, so the linear and fan-out cases must
report zero.
"""

import json
from pathlib import Path

from claude_score.metrics import compute
from claude_score.transcript import parse_target


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    f = tmp_path / "session.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return f


def _human(uuid, parent, text):
    return {"type": "user", "uuid": uuid, "parentUuid": parent,
            "timestamp": "2026-05-28T10:00:00Z",
            "message": {"role": "user", "content": text}}


def _asst(uuid, parent):
    return {"type": "assistant", "uuid": uuid, "parentUuid": parent,
            "timestamp": "2026-05-28T10:00:01Z",
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": 10, "output_tokens": 5}}}


def _tool_result(uuid, parent):
    return {"type": "user", "uuid": uuid, "parentUuid": parent,
            "timestamp": "2026-05-28T10:00:02Z",
            "message": {"role": "user",
                        "content": [{"type": "tool_result", "content": "done"}]}}


def test_linear_session_has_no_rewinds(tmp_path):
    rows = [
        _human("u1", None, "first"),
        _asst("u2", "u1"),
        _human("u3", "u2", "second"),
        _asst("u4", "u3"),
    ]
    m = compute(parse_target(_write(tmp_path, rows)))
    assert m.rewind_count == 0
    assert m.rewound_prompt_count == 0


def test_tool_fanout_is_not_a_rewind(tmp_path):
    # Assistant tool call: both the tool_result and the assistant's next step
    # hang off the same parent — a same-parent sibling pair that is NOT a rewind.
    rows = [
        _human("u1", None, "do the thing"),
        _asst("u2", "u1"),            # makes a tool call
        _tool_result("u3", "u2"),     # tool output (sibling)
        _asst("u4", "u2"),            # continuation (sibling of the tool_result)
    ]
    m = compute(parse_target(_write(tmp_path, rows)))
    assert m.rewind_count == 0
    assert m.rewound_prompt_count == 0


def test_rewound_prompt_is_detected(tmp_path):
    # u3/u4 are abandoned; the candidate rewound to u2 and re-asked as u5.
    rows = [
        _human("u1", None, "first"),
        _asst("u2", "u1"),
        _human("u3", "u2", "second attempt (abandoned)"),
        _asst("u4", "u3"),
        _human("u5", "u2", "second attempt (redo)"),   # branched from u2
        _asst("u6", "u5"),                              # leaf
    ]
    m = compute(parse_target(_write(tmp_path, rows)))
    assert m.rewind_count == 1
    assert m.rewound_prompt_count == 1


def test_multiple_discards_from_one_point_count_as_one_rewind(tmp_path):
    # Two prompts discarded off the same point u2 => one rewind, two prompts.
    rows = [
        _human("u1", None, "start"),
        _asst("u2", "u1"),
        _human("u3", "u2", "try A (abandoned)"),
        _human("u4", "u3", "try A.2 (abandoned)"),
        _human("u5", "u2", "try B (kept)"),
        _asst("u6", "u5"),
    ]
    m = compute(parse_target(_write(tmp_path, rows)))
    assert m.rewind_count == 1
    assert m.rewound_prompt_count == 2
