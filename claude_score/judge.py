"""Optional LLM 'judge' pass.

Sends a compact, cleaned rendering of the session to Claude and asks for a
structured assessment of *how the person worked with the agent* — tone, prompt
quality, autonomy, review discipline, recovery from mistakes — plus a short
write-up and a few badge suggestions with citations.

This is optional. If the ``anthropic`` package isn't installed or no API key is
available, :func:`is_available` returns False and the CLI simply skips it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .models import Session

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"

_SYSTEM = """You are an expert engineering interviewer evaluating HOW a developer \
collaborates with an AI coding agent (Claude Code), based on the transcript of \
their session. You are NOT judging whether the final code is correct — you are \
judging their working style: prompt quality, autonomy vs micromanagement, whether \
they reviewed the agent's output, how they recovered from mistakes, and their tone.

Be fair, specific, and concise. Ground every observation in the transcript.

Important framing rules — please internalise:

- **Pasting the problem statement is NOT a problem in itself.** What matters
  is whether the candidate iterates afterwards — refining, reviewing,
  course-correcting. Paste-then-iterate is exactly the behaviour we want.
- **High autonomy is only good when paired with engagement.** A candidate
  who delegates whole units of work AND comes back to inspect, question,
  test, or steer — that is the strongest collaboration profile. A candidate
  who delegates and then sits idle while Claude grinds (long gaps with no
  follow-up, no Read calls between Edits, no corrections) is the opposite.
- **Specifically watch for these failure modes** and surface them in
  `concerns` if present:
    * "Paste-and-disengage": a large dump (problem statement or other) is
      followed by an extended stretch with minimal follow-up prompts and
      no evidence of review. Cite the dump and the silence that followed.
    * "No-review autonomy": Claude makes substantial code changes and the
      candidate accepts without inspecting (no Read after Edit), without
      questions, without testing.
    * "Spam the same prompt": when something fails, the candidate re-runs
      the same prompt instead of diagnosing or adding context.
    * "Wall-of-text": dumping unrelated context as if more input
      produces better output.
- **Specifically credit these behaviours** in `strengths` if present:
    * Asking Claude to explain a choice, then pushing back when wrong.
    * Catching a bug Claude introduced and correcting it themselves.
    * Using planning tools, TodoWrite, or extended thinking deliberately.
    * Prompts that include constraints / examples, not just goals.

Respond with ONLY a JSON object, no prose around it, matching this schema:
{
  "scores": {
    "prompt_quality": 1-5,
    "autonomy": 1-5,
    "review_discipline": 1-5,
    "recovery": 1-5,
    "tone": 1-5
  },
  "summary": "2-4 sentence overall read of their collaboration style",
  "strengths": ["..."],
  "concerns": ["..."],
  "suggested_badges": [{"emoji": "🎯", "name": "...", "reason": "one line, cite the transcript"}]
}"""


@dataclass
class JudgeResult:
    scores: dict[str, float] = field(default_factory=dict)
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    suggested_badges: list[dict] = field(default_factory=list)
    model: str = ""
    error: str | None = None


def is_available() -> bool:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _render_transcript(sessions: list[Session], max_chars: int = 24_000) -> str:
    """Render an interleaved, truncated view: human prompts + agent actions."""
    lines: list[str] = []
    for session in sessions:
        # Re-merge prompts and turns by timestamp for a readable flow.
        events: list[tuple] = []
        for p in session.main_prompts():
            events.append((p.timestamp, "user", p.clean_text))
        for t in session.main_turns():
            tools = ", ".join(c.name for c in t.tool_calls)
            snippet = t.text[:280]
            label = snippet + (f"  [tools: {tools}]" if tools else "")
            events.append((t.timestamp, "assistant", label.strip()))
        events.sort(key=lambda e: (e[0] is None, e[0]))
        for _, role, text in events:
            if not text:
                continue
            prefix = "USER" if role == "user" else "CLAUDE"
            lines.append(f"{prefix}: {text[:600]}")

    rendered = "\n".join(lines)
    if len(rendered) > max_chars:
        head = rendered[: max_chars // 2]
        tail = rendered[-max_chars // 2 :]
        rendered = f"{head}\n...[transcript truncated]...\n{tail}"
    return rendered


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def judge_candidate(
    sessions: list[Session],
    candidate: str = "candidate",
    model: str = DEFAULT_JUDGE_MODEL,
) -> JudgeResult:
    if not is_available():
        return JudgeResult(
            error="Judge unavailable: set ANTHROPIC_API_KEY and `pip install anthropic`."
        )
    import anthropic

    transcript = _render_transcript(sessions)
    if not transcript.strip():
        return JudgeResult(error="No human prompts found to judge.")

    client = anthropic.Anthropic()
    user_msg = (
        f"Candidate: {candidate}\n\n"
        f"Session transcript (human prompts and a summary of Claude's actions):\n\n"
        f"{transcript}"
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        data = _extract_json(raw)
    except Exception as exc:  # network, parse, auth — report, don't crash.
        return JudgeResult(error=f"Judge call failed: {exc}", model=model)

    return JudgeResult(
        scores={k: float(v) for k, v in (data.get("scores") or {}).items()},
        summary=str(data.get("summary", "")),
        strengths=list(data.get("strengths", []) or []),
        concerns=list(data.get("concerns", []) or []),
        suggested_badges=list(data.get("suggested_badges", []) or []),
        model=model,
    )
