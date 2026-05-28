"""Typed representations of a parsed Claude Code session.

These dataclasses are intentionally close to what actually appears in the
JSONL transcript, but cleaned up: tool results echoed back as "user" messages
are not treated as human prompts, sidechain (subagent) traffic is flagged so
metrics can include or exclude it, and token usage is normalised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Usage:
    """Token usage for a single assistant turn (or summed across many)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens
            + other.cache_read_input_tokens,
        )

    @property
    def billable_input(self) -> int:
        """Fresh input + cache writes + cache reads — everything sent up."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def work_tokens(self) -> int:
        """New tokens processed: fresh input + cache writes + output.

        Excludes cache *reads*, which re-bill the same context every turn and
        otherwise dominate (and inflate) any 'total tokens' headline.
        """
        return self.input_tokens + self.cache_creation_input_tokens + self.output_tokens

    @property
    def total(self) -> int:
        """Everything, including cache reads. Use for cost; not for headlines."""
        return self.billable_input + self.output_tokens

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Usage":
        return cls(
            input_tokens=int(raw.get("input_tokens", 0) or 0),
            output_tokens=int(raw.get("output_tokens", 0) or 0),
            cache_creation_input_tokens=int(
                raw.get("cache_creation_input_tokens", 0) or 0
            ),
            cache_read_input_tokens=int(raw.get("cache_read_input_tokens", 0) or 0),
        )


@dataclass
class ToolCall:
    """A single tool invocation made by the assistant."""

    name: str
    input: dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class UserPrompt:
    """A genuine human prompt (not a tool result echoed back as a user turn)."""

    raw_text: str
    clean_text: str
    timestamp: Optional[datetime] = None
    uuid: Optional[str] = None
    is_sidechain: bool = False


@dataclass
class AssistantTurn:
    """One assistant message: its text, tool calls, thinking flag and usage."""

    text: str = ""
    has_thinking: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: Optional[str] = None
    timestamp: Optional[datetime] = None
    is_sidechain: bool = False


@dataclass
class Session:
    """A single Claude Code session parsed from one JSONL file."""

    session_id: Optional[str] = None
    file_path: Optional[str] = None
    cwd: Optional[str] = None
    git_branch: Optional[str] = None
    version: Optional[str] = None

    user_prompts: list[UserPrompt] = field(default_factory=list)
    assistant_turns: list[AssistantTurn] = field(default_factory=list)
    tool_result_count: int = 0
    summaries: list[str] = field(default_factory=list)

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    def main_prompts(self) -> list[UserPrompt]:
        """Human prompts in the primary conversation (excludes subagents)."""
        return [p for p in self.user_prompts if not p.is_sidechain]

    def main_turns(self) -> list[AssistantTurn]:
        return [t for t in self.assistant_turns if not t.is_sidechain]

    def all_tool_calls(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for turn in self.assistant_turns:
            calls.extend(turn.tool_calls)
        return calls

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
