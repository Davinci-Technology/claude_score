"""Parse Claude Code JSONL transcripts into :class:`Session` objects.

The transcript format is line-delimited JSON. Each line is one event. We care
about three event types:

  * type == "user"      -> either a real human prompt OR a tool result that
                           Claude Code echoes back as a "user" role message.
  * type == "assistant" -> model output: text, thinking, tool_use blocks,
                           plus token usage.
  * type == "summary"   -> a short auto-generated session summary.

Everything else (file-history-snapshot, system, etc.) is ignored.

The parser is deliberately defensive: transcripts evolve across Claude Code
versions, so unknown fields are skipped and malformed lines are tolerated.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .models import AssistantTurn, DagNode, Session, SlashCommand, ToolCall, UserPrompt, Usage

# Wrapper blocks that Claude Code injects into the human prompt stream but that
# the candidate did not actually type. Stripped before text/tone analysis.
_NOISE_PATTERNS = [
    re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL),
    re.compile(r"<command-name>.*?</command-name>", re.DOTALL),
    re.compile(r"<command-message>.*?</command-message>", re.DOTALL),
    re.compile(r"<command-args>.*?</command-args>", re.DOTALL),
    re.compile(r"<local-command-stdout>.*?</local-command-stdout>", re.DOTALL),
    re.compile(r"<command-stdout>.*?</command-stdout>", re.DOTALL),
]

# Slash commands / skills the human invoked. Claude Code records the command
# name in this tag inside the user stream; we capture it before _NOISE_PATTERNS
# strips it so the invocation is counted rather than silently dropped.
_COMMAND_NAME = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)


def _command_names(raw: str) -> list[str]:
    """Pull normalised slash-command names (leading slash, no args) from a raw
    user message. Returns ``[]`` for ordinary prompts."""
    names: list[str] = []
    for hit in _COMMAND_NAME.findall(raw):
        # The tag may carry args ("/foo bar"); keep just the command token.
        token = hit.strip().split()[0] if hit.strip() else ""
        name = "/" + token.lstrip("/")
        if name != "/":
            names.append(name)
    return names


def _parse_ts(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        # Transcripts use ISO-8601, usually with a trailing 'Z'.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean(text: str) -> str:
    """Strip injected wrapper blocks so tone analysis sees only what was typed."""
    cleaned = text
    for pat in _NOISE_PATTERNS:
        cleaned = pat.sub("", cleaned)
    return cleaned.strip()


def _extract_text_blocks(content: list[dict[str, Any]]) -> str:
    return "\n".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


def _is_tool_result(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def _node_kind(entry: dict[str, Any]) -> str:
    """Classify a transcript entry for the conversation DAG (rewind detection)."""
    etype = entry.get("type")
    if etype == "assistant":
        return "assistant"
    if etype == "user":
        if entry.get("isMeta"):
            return "other"
        content = (entry.get("message") or {}).get("content")
        if _is_tool_result(content):
            return "tool_result"
        if isinstance(content, str) and content.strip():
            return "human"
        if isinstance(content, list) and _extract_text_blocks(content):
            return "human"
        return "other"
    return "other"


def parse_file(path: str | Path) -> Session:
    """Parse a single ``*.jsonl`` transcript file into a :class:`Session`."""
    path = Path(path)
    session = Session(file_path=str(path))
    timestamps: list[datetime] = []
    node_order = 0

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue

            _absorb_metadata(session, entry)
            ts = _parse_ts(entry.get("timestamp"))
            if ts:
                timestamps.append(ts)

            uuid = entry.get("uuid")
            if uuid:
                node_order += 1
                session.dag_nodes.append(DagNode(
                    uuid=uuid,
                    parent_uuid=entry.get("parentUuid"),
                    kind=_node_kind(entry),
                    is_sidechain=bool(entry.get("isSidechain")),
                    order=node_order,
                ))

            etype = entry.get("type")
            if etype == "user":
                _handle_user(session, entry, ts)
            elif etype == "assistant":
                _handle_assistant(session, entry, ts)
            elif etype == "summary":
                summary = entry.get("summary")
                if summary:
                    session.summaries.append(str(summary))

    if timestamps:
        session.started_at = min(timestamps)
        session.ended_at = max(timestamps)
    return session


def _absorb_metadata(session: Session, entry: dict[str, Any]) -> None:
    if session.session_id is None and entry.get("sessionId"):
        session.session_id = entry["sessionId"]
    if session.cwd is None and entry.get("cwd"):
        session.cwd = entry["cwd"]
    if session.git_branch is None and entry.get("gitBranch"):
        session.git_branch = entry["gitBranch"]
    if session.version is None and entry.get("version"):
        session.version = entry["version"]


def _handle_user(session: Session, entry: dict[str, Any], ts: datetime | None) -> None:
    if entry.get("isMeta"):
        return
    message = entry.get("message") or {}
    content = message.get("content")
    is_sidechain = bool(entry.get("isSidechain"))

    if _is_tool_result(content):
        session.tool_result_count += 1
        return

    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        raw = _extract_text_blocks(content)
    else:
        return

    for name in _command_names(raw):
        session.slash_commands.append(
            SlashCommand(name=name, timestamp=ts, is_sidechain=is_sidechain)
        )

    clean = _clean(raw)
    if not clean:
        # Pure noise (e.g. a bare system reminder or a slash command with no
        # typed text) — not a real prompt. The command, if any, is recorded above.
        return

    session.user_prompts.append(
        UserPrompt(
            raw_text=raw,
            clean_text=clean,
            timestamp=ts,
            uuid=entry.get("uuid"),
            is_sidechain=is_sidechain,
        )
    )


def _handle_assistant(
    session: Session, entry: dict[str, Any], ts: datetime | None
) -> None:
    message = entry.get("message") or {}
    content = message.get("content") or []
    is_sidechain = bool(entry.get("isSidechain"))

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    has_thinking = False

    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "thinking":
                has_thinking = True
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCall(
                        name=block.get("name", "unknown"),
                        input=block.get("input", {}) or {},
                        id=block.get("id"),
                        timestamp=ts,
                    )
                )
    elif isinstance(content, str):
        text_parts.append(content)

    session.assistant_turns.append(
        AssistantTurn(
            text="\n".join(text_parts).strip(),
            has_thinking=has_thinking,
            tool_calls=tool_calls,
            usage=Usage.from_raw(message.get("usage", {}) or {}),
            model=message.get("model"),
            timestamp=ts,
            is_sidechain=is_sidechain,
        )
    )


def parse_target(target: str | Path) -> list[Session]:
    """Parse a target that is a single ``.jsonl`` file or a directory of them.

    A directory is treated as a project folder: every ``*.jsonl`` inside is
    parsed and returned (one session per file). This is the shape of a
    candidate's work on the interview box — point ClaudeScore at their project
    directory under ``~/.claude/projects/``.
    """
    target = Path(target)
    if target.is_dir():
        files = sorted(target.glob("*.jsonl"))
        return [parse_file(f) for f in files]
    if target.is_file():
        return [parse_file(target)]
    raise FileNotFoundError(f"No such transcript file or directory: {target}")


def iter_jsonl(target: str | Path) -> Iterable[Path]:
    target = Path(target)
    if target.is_dir():
        yield from sorted(target.glob("*.jsonl"))
    elif target.is_file():
        yield target
