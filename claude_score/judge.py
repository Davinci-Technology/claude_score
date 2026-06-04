"""Optional LLM 'judge' pass.

Sends the session transcript (and, when available, the candidate's code diff vs
the boilerplate plus a smoke-test report) to Claude and asks for a STRICT,
analytic, multi-dimension assessment across two halves:

* PROCESS (from the transcript): prompt_quality, delegation_control,
  review_verification, recovery — how skilfully they drove the agent.
* PRODUCT (from the diff + smoke report): feature_completeness, code_quality,
  architecture, testing — what they actually built on top of the starter.

Each dimension is scored 1-5 against behavioural anchors (3 = competent, 5 =
rare), with per-dimension evidence in ``rationale`` and a ``null`` allowed for
anything that CANNOT_ASSESS. The rubric is deliberately calibrated to spread
scores and resist grade inflation.

This is optional. If the ``anthropic`` package isn't installed or no API key is
available, :func:`is_available` returns False and the CLI simply skips it.
``build_judge_message`` and ``parse_judge_json`` are exposed so the identical
rubric can be run through an in-session subagent when no API key is configured.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .models import Session

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"

_SYSTEM = """You are a STRICT staff-level engineer scoring a candidate's 2-hour, \
AI-assisted (Claude Code) coding interview. You judge two things: (A) HOW skilfully \
they drove the agent, from the session transcript, and (B) WHAT they actually built \
on top of the provided boilerplate, from the code diff and a smoke-test report.

Your job is to DISCRIMINATE, not to be nice. Most attempts have real gaps. Do not
give everyone 4s and 5s — that makes the score useless. Be blunt, specific, and a
little ruthless in the prose: name the weaknesses plainly. Never be gratuitously
mean, but do not soften real problems.

=== CALIBRATION (read carefully — anchors are behavioural, not vibes) ===
For every dimension, 1-5 means:
  1 = Poor. Clear deficiency a senior would flag immediately.
  2 = Below bar. Notable gaps; would need rework.
  3 = COMPETENT. Exactly what a hireable mid-level engineer ships in 2 hours. This
      is the DEFAULT, not a disappointment.
  4 = Strong. Clearly above the typical attempt, with specific evidence.
  5 = Exceptional and RARE. Reserve for genuinely excellent work; cite the precise
      evidence that earns it. Few real candidates hit 5 on more than a dimension or two.
Anchor instincts: a normal solid attempt should land mostly on 3 with a couple of
4s and a couple of 2s. If you find yourself writing 4-5 everywhere, you are
inflating — re-read for what's missing. "It runs" is a 3, not a 5.

=== SCORING DISCIPLINE ===
- Score each dimension INDEPENDENTLY (no halo: a great communicator can ship weak code).
- Ground EVERY score in specific evidence (a quoted prompt, a file/symbol from the
  diff, a smoke-test line). Put that evidence in `rationale`.
- If you genuinely cannot observe a dimension from the material provided, set its
  score to null and write "CANNOT_ASSESS: <why>" in its rationale. NEVER guess upward.

=== DIMENSION A — PROCESS (judge from the TRANSCRIPT) ===
- prompt_quality: clarity, context, decomposition, constraints/examples (not just
  goals). 5 = consistently sharp, well-scoped prompts that set role/constraints.
  2 = vague one-liners expecting mind-reading.
- delegation_control: SELECTIVE delegation while retaining control is the goal.
  5 = delegates whole units AND directs/steers, keeps the wheel. Penalise BOTH
  extremes: blind full-automation (accepts everything, "vibe coding") AND
  micromanaging every keystroke. Paste-then-iterate is GOOD; paste-and-disengage is bad.
- review_verification: did they review the agent's diffs and independently confirm it
  works — reading changes, questioning choices, running it, writing/checking tests,
  catching errors? 5 = actively reviews and verifies, catches issues. 1-2 = accepts
  output unread, never runs/tests it.
- recovery: when something broke, did they diagnose and add context, or spam the same
  prompt / flail? If nothing broke, CANNOT_ASSESS rather than a free 5.

=== DIMENSION B — PRODUCT (judge from the DIFF + SMOKE REPORT; judge ONLY what they
added on top of boilerplate, NOT the starter we gave them) ===
- feature_completeness: how much of the intended feature set actually WORKS end-to-end
  (lean on the smoke report). 5 = the core journey works plus polish; 3 = core CRUD
  works; 1-2 = scaffolding only / doesn't run. "Code exists" without evidence it runs
  is NOT completeness.
- code_quality: readability/naming, error handling, input validation, type safety,
  secrets handling, no SQL/secret leaks, DRY without OVER-ENGINEERING. Over-engineering
  (needless generality/abstraction for a 2-hour task) is a DEFECT — dock for it.
  Anchor the top to net code-health a senior would happily inherit, not perfection.
- architecture: separation of concerns and layout. Reward business logic kept OUT of
  views and model.save() (e.g. a services/selectors layer), clear API/serializer
  boundaries, sensible file/folder structure, a coherent frontend split
  (api-client / hooks / components / types). Score the PRINCIPLE, not a specific
  file-naming convention — do not penalise defensible alternatives.
- testing: tests judged by QUALITY not presence. 5 = meaningful tests that would fail
  if the code broke, at the right level (unit/integration), covering tricky paths
  (errors, edge cases). 3 = some real tests. 1-2 = no tests or trivial/always-pass tests.

Respond with ONLY a JSON object, no prose around it, matching this schema (use null for
any score you CANNOT_ASSESS):
{
  "scores": {
    "prompt_quality": 1-5 | null,
    "delegation_control": 1-5 | null,
    "review_verification": 1-5 | null,
    "recovery": 1-5 | null,
    "feature_completeness": 1-5 | null,
    "code_quality": 1-5 | null,
    "architecture": 1-5 | null,
    "testing": 1-5 | null
  },
  "rationale": {"<each dimension above>": "one line citing specific evidence, or CANNOT_ASSESS: why"},
  "overall": 1-5,
  "recommendation": "strong_hire | hire | lean_no_hire | no_hire",
  "summary": "3-5 sentences, blunt and specific: what they did well and where they fell short",
  "strengths": ["specific, evidence-cited"],
  "concerns": ["specific, evidence-cited — do not pad; real issues only"]
}"""


@dataclass
class JudgeResult:
    scores: dict[str, float] = field(default_factory=dict)
    rationale: dict[str, str] = field(default_factory=dict)
    overall: float | None = None
    recommendation: str = ""
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


def _cap(text: str, limit: int) -> str:
    """Truncate with a visible marker so the judge knows content was cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n...[diff truncated at {limit} chars — later files omitted]..."


def build_judge_message(
    sessions: list[Session],
    candidate: str = "candidate",
    code_diff: str | None = None,
    smoke_report: str | None = None,
    max_diff_chars: int = 120_000,
) -> str:
    """Assemble the user message the judge scores. Exposed so the same prompt can
    be reused outside the API path (e.g. an in-session subagent when no key is set).

    ``max_diff_chars`` is generous by default: a real 2-hour candidate diff often
    runs past 40-90k chars, and truncating it mid-file silently hides whole files
    (e.g. views, the frontend) from the product dimensions. Lower it only if you
    are hitting a model's context limit."""
    transcript = _render_transcript(sessions)
    parts = [
        f"Candidate: {candidate}",
        "",
        "## SESSION TRANSCRIPT (evidence for the PROCESS dimensions)",
        "Human prompts (USER) interleaved with a summary of Claude's actions (CLAUDE):",
        "",
        transcript,
    ]
    if code_diff and code_diff.strip():
        parts += [
            "",
            "## CODE DIFF vs the provided boilerplate (evidence for the PRODUCT "
            "dimensions — judge ONLY what the candidate added/changed, not the starter)",
            "",
            _cap(code_diff.strip(), max_diff_chars),
        ]
    else:
        parts += [
            "",
            "## CODE DIFF: not provided. Score feature_completeness, code_quality, "
            "architecture, and testing as null/CANNOT_ASSESS unless clearly inferable "
            "from the transcript.",
        ]
    if smoke_report and smoke_report.strip():
        parts += [
            "",
            "## SMOKE-TEST REPORT (objective evidence: does it build / migrate / "
            "test / run?)",
            "",
            smoke_report.strip()[:8_000],
        ]
    return "\n".join(parts)


def parse_judge_json(data: dict, model: str = "") -> JudgeResult:
    """Build a JudgeResult from the judge's JSON (shared by API + subagent paths)."""
    raw_scores = data.get("scores") or {}
    scores = {
        k: float(v) for k, v in raw_scores.items()
        if isinstance(v, (int, float))
    }
    overall = data.get("overall")
    return JudgeResult(
        scores=scores,
        rationale={k: str(v) for k, v in (data.get("rationale") or {}).items()},
        overall=float(overall) if isinstance(overall, (int, float)) else None,
        recommendation=str(data.get("recommendation", "")),
        summary=str(data.get("summary", "")),
        strengths=list(data.get("strengths", []) or []),
        concerns=list(data.get("concerns", []) or []),
        suggested_badges=list(data.get("suggested_badges", []) or []),
        model=model,
    )


def judge_candidate(
    sessions: list[Session],
    candidate: str = "candidate",
    model: str = DEFAULT_JUDGE_MODEL,
    code_diff: str | None = None,
    smoke_report: str | None = None,
) -> JudgeResult:
    if not is_available():
        return JudgeResult(
            error="Judge unavailable: set ANTHROPIC_API_KEY and `pip install anthropic`."
        )
    import anthropic

    if not _render_transcript(sessions).strip():
        return JudgeResult(error="No human prompts found to judge.")

    user_msg = build_judge_message(sessions, candidate, code_diff, smoke_report)
    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        data = _extract_json(raw)
    except Exception as exc:  # network, parse, auth — report, don't crash.
        return JudgeResult(error=f"Judge call failed: {exc}", model=model)

    return parse_judge_json(data, model=model)
