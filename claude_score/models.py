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
class SlashCommand:
    """A slash command the human invoked (e.g. ``/clear``, ``/compact``, a
    custom command or skill). Recorded separately from prompts: Claude Code
    injects these into the user stream wrapped in ``<command-name>`` tags, and
    they are stripped from prompt text before tone/quality analysis."""

    name: str  # normalised with a leading slash, args excluded
    timestamp: Optional[datetime] = None
    is_sidechain: bool = False


@dataclass
class DagNode:
    """A node in the conversation tree, used to detect rewinds.

    Claude Code transcripts are append-only: a rewind keeps the abandoned
    messages and appends a new branch, so the ``parentUuid``/``uuid`` graph
    becomes a tree. A human prompt that ends up on a branch which is *not* an
    ancestor of the session's final message was rewound away. We keep every
    node (including tool results) so the ancestor walk is accurate.
    """

    uuid: str
    parent_uuid: Optional[str] = None
    kind: str = "other"  # 'human' | 'assistant' | 'tool_result' | 'other'
    is_sidechain: bool = False
    order: int = 0  # append order within the file (the last one is the leaf)


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
    slash_commands: list[SlashCommand] = field(default_factory=list)
    dag_nodes: list[DagNode] = field(default_factory=list)
    tool_result_count: int = 0
    summaries: list[str] = field(default_factory=list)

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    def main_prompts(self) -> list[UserPrompt]:
        """Human prompts in the primary conversation (excludes subagents)."""
        return [p for p in self.user_prompts if not p.is_sidechain]

    def main_turns(self) -> list[AssistantTurn]:
        return [t for t in self.assistant_turns if not t.is_sidechain]

    def main_slash_commands(self) -> list[SlashCommand]:
        """Slash commands in the primary conversation (excludes subagents)."""
        return [c for c in self.slash_commands if not c.is_sidechain]

    def rewind_stats(self) -> tuple[int, int]:
        """Best-effort ``(rewind_count, rewound_prompt_count)`` from the DAG.

        A *rewound prompt* is a human prompt on a branch that is not an ancestor
        of the session's final (leaf) message — i.e. the candidate typed it, then
        rewound past it. A *rewind* is a distinct point they rewound back to
        (several discarded prompts off the same point count as one rewind).

        This is immune to tool-call fan-out: tool results and assistant
        continuations create same-parent siblings too, but they are never human
        prompts, so they cannot be mistaken for a rewind. There is no explicit
        rewind marker in the transcript, so this is heuristic; known Claude Code
        bugs around compaction/resume can corrupt the tree and skew it.
        """
        nodes = {n.uuid: n for n in self.dag_nodes if n.uuid and not n.is_sidechain}
        if not nodes:
            return (0, 0)

        # The active leaf is the last-appended node (append-only file).
        leaf = max(nodes.values(), key=lambda n: n.order)
        surviving: set[str] = set()
        cur: Optional[str] = leaf.uuid
        while cur and cur in nodes and cur not in surviving:
            surviving.add(cur)
            cur = nodes[cur].parent_uuid

        rewound = [
            n for n in nodes.values()
            if n.kind == "human" and n.uuid not in surviving
        ]
        if not rewound:
            return (0, 0)

        # Group discarded prompts by the surviving node they branched from.
        divergence: set[str] = set()
        for n in rewound:
            p = n.parent_uuid
            guard: set[str] = set()
            while p and p in nodes and p not in surviving and p not in guard:
                guard.add(p)
                p = nodes[p].parent_uuid
            divergence.add(p or "<root>")
        return (len(divergence), len(rewound))

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
