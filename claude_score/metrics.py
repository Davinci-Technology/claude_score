"""Deterministic metrics computed from parsed sessions.

Everything here is cheap and exact (no LLM). A "candidate" is one or more
sessions belonging to the same person — typically every ``*.jsonl`` file in
their project directory on the interview box.

Token cost is an *estimate*: the rates in ``PRICING`` are approximate
per-million-token prices and should be verified against your current
Anthropic pricing before you quote dollar figures to anyone.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from .models import Session, Usage

# Approximate USD per 1M tokens. ESTIMATES — verify before quoting.
# Keyed by a substring matched against the model id.
PRICING = {
    "opus":   {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.50},
    "sonnet": {"input": 3.0,  "output": 15.0, "cache_write": 3.75,  "cache_read": 0.30},
    "haiku":  {"input": 0.80, "output": 4.0,  "cache_write": 1.0,   "cache_read": 0.08},
}
_DEFAULT_RATES = PRICING["sonnet"]

# Tool name -> behavioural category.
TOOL_CATEGORIES = {
    "Edit": "write", "Write": "write", "NotebookEdit": "write", "MultiEdit": "write",
    "Read": "read", "Grep": "read", "Glob": "read", "NotebookRead": "read",
    "Bash": "shell", "PowerShell": "shell", "BashOutput": "shell",
    "WebFetch": "research", "WebSearch": "research",
    "Task": "delegate", "Agent": "delegate",
    "TodoWrite": "plan", "TaskCreate": "plan", "ExitPlanMode": "plan",
}

_POLITE = [
    "please", "thank", "thanks", "appreciate", "could you", "would you",
    "if you could", "kindly", "no rush", "whenever you can", "great job",
    "well done", "nice work", "awesome", "perfect", "sorry", "my bad",
    "you're right", "good point",
]
_TERSE = [
    "just do", "do it now", "obviously", "stupid", "wrong again", "no.",
    "stop", "redo", "again.", "i said", "listen", "hurry", "asap",
]
_PROFANITY = ["damn", "hell", "wtf", "crap", "shit", "fuck"]
_CORRECTION = [
    "no,", "no.", "that's wrong", "thats wrong", "not what i", "actually",
    "undo", "revert", "instead", "i said", "still broken", "doesn't work",
    "does not work", "that broke", "you broke", "not right", "incorrect",
    "try again", "that's not", "thats not",
]


@dataclass
class Metrics:
    candidate: str = "unknown"
    session_count: int = 0

    prompt_count: int = 0
    assistant_turn_count: int = 0
    tool_call_count: int = 0
    tool_result_count: int = 0

    usage: Usage = field(default_factory=Usage)
    estimated_cost_usd: float = 0.0
    models_used: dict[str, int] = field(default_factory=dict)

    duration_seconds: float = 0.0
    prompt_gaps_seconds: list[float] = field(default_factory=list)

    prompt_word_counts: list[int] = field(default_factory=list)
    tool_breakdown: dict[str, int] = field(default_factory=dict)
    category_breakdown: dict[str, int] = field(default_factory=dict)

    polite_hits: int = 0
    terse_hits: int = 0
    profanity_hits: int = 0
    correction_count: int = 0
    thinking_turns: int = 0
    shouted_prompts: int = 0  # prompts that are mostly UPPERCASE

    # --- derived convenience properties -------------------------------------

    @property
    def cache_hit_ratio(self) -> float:
        denom = (
            self.usage.input_tokens
            + self.usage.cache_creation_input_tokens
            + self.usage.cache_read_input_tokens
        )
        return self.usage.cache_read_input_tokens / denom if denom else 0.0

    @property
    def tools_per_prompt(self) -> float:
        return self.tool_call_count / self.prompt_count if self.prompt_count else 0.0

    @property
    def work_tokens(self) -> int:
        return self.usage.work_tokens

    @property
    def tokens_per_prompt(self) -> float:
        """Work tokens per prompt (excludes cache reads)."""
        return self.usage.work_tokens / self.prompt_count if self.prompt_count else 0.0

    @property
    def cost_per_prompt(self) -> float:
        return self.estimated_cost_usd / self.prompt_count if self.prompt_count else 0.0

    @property
    def mean_prompt_words(self) -> float:
        return statistics.mean(self.prompt_word_counts) if self.prompt_word_counts else 0.0

    @property
    def correction_rate(self) -> float:
        return self.correction_count / self.prompt_count if self.prompt_count else 0.0

    @property
    def politeness_score(self) -> float:
        """A bounded -1..+1 heuristic. Positive = warm, negative = terse."""
        if not self.prompt_count:
            return 0.0
        raw = (self.polite_hits - self.terse_hits - 2 * self.profanity_hits)
        return max(-1.0, min(1.0, raw / self.prompt_count))

    @property
    def write_to_read_ratio(self) -> float:
        reads = self.category_breakdown.get("read", 0)
        writes = self.category_breakdown.get("write", 0)
        return writes / reads if reads else float(writes)


def _rates_for(model: str | None) -> dict[str, float]:
    if not model:
        return _DEFAULT_RATES
    for key, rates in PRICING.items():
        if key in model:
            return rates
    return _DEFAULT_RATES


def _cost(usage: Usage, model: str | None) -> float:
    r = _rates_for(model)
    return (
        usage.input_tokens * r["input"]
        + usage.output_tokens * r["output"]
        + usage.cache_creation_input_tokens * r["cache_write"]
        + usage.cache_read_input_tokens * r["cache_read"]
    ) / 1_000_000


def _count_hits(text: str, needles: Iterable[str]) -> int:
    low = text.lower()
    return sum(low.count(n) for n in needles)


def _is_shout(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.7


def compute(sessions: list[Session], candidate: str = "unknown") -> Metrics:
    m = Metrics(candidate=candidate, session_count=len(sessions))
    model_counter: Counter[str] = Counter()
    tool_counter: Counter[str] = Counter()
    cat_counter: Counter[str] = Counter()

    for session in sessions:
        if session.duration_seconds:
            m.duration_seconds += session.duration_seconds

        prompts = session.main_prompts()
        m.prompt_count += len(prompts)
        last_ts = None
        for p in prompts:
            m.prompt_word_counts.append(len(p.clean_text.split()))
            m.polite_hits += _count_hits(p.clean_text, _POLITE)
            m.terse_hits += _count_hits(p.clean_text, _TERSE)
            m.profanity_hits += _count_hits(p.clean_text, _PROFANITY)
            m.correction_count += 1 if any(
                c in p.clean_text.lower() for c in _CORRECTION
            ) else 0
            if _is_shout(p.clean_text):
                m.shouted_prompts += 1
            if last_ts and p.timestamp:
                gap = (p.timestamp - last_ts).total_seconds()
                if 0 < gap < 3600:  # ignore overnight gaps
                    m.prompt_gaps_seconds.append(gap)
            if p.timestamp:
                last_ts = p.timestamp

        for turn in session.assistant_turns:
            m.assistant_turn_count += 1
            m.usage += turn.usage
            m.estimated_cost_usd += _cost(turn.usage, turn.model)
            if turn.model:
                model_counter[turn.model] += 1
            if turn.has_thinking:
                m.thinking_turns += 1
            for call in turn.tool_calls:
                m.tool_call_count += 1
                tool_counter[call.name] += 1
                cat_counter[TOOL_CATEGORIES.get(call.name, "other")] += 1

        m.tool_result_count += session.tool_result_count

    m.models_used = dict(model_counter)
    m.tool_breakdown = dict(tool_counter.most_common())
    m.category_breakdown = dict(cat_counter)
    return m
