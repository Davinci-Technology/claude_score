"""Render an analysis into an HTML report and a Markdown summary."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .badges import AwardedBadge
from .judge import JudgeResult
from .metrics import Metrics
from .models import Session

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _fmt_duration(seconds: float) -> str:
    if not seconds:
        return "n/a"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def build_context(
    candidate: str,
    metrics: Metrics,
    badges: list[AwardedBadge],
    judge: JudgeResult | None,
    sessions: list[Session],
) -> dict[str, Any]:
    replay = []
    for session in sessions:
        for p in session.main_prompts():
            ts = p.timestamp.strftime("%H:%M:%S") if p.timestamp else ""
            text = p.clean_text
            replay.append({"time": ts, "text": text[:1000]})

    key_metrics = [
        ("Sessions", str(metrics.session_count)),
        ("Prompts", str(metrics.prompt_count)),
        ("Assistant turns", str(metrics.assistant_turn_count)),
        ("Tool calls", str(metrics.tool_call_count)),
        ("Slash commands", str(metrics.slash_command_count)),
        ("Rewinds", str(metrics.rewind_count)),
        ("Work tokens", f"{metrics.work_tokens:,}"),
        ("Output tokens", f"{metrics.usage.output_tokens:,}"),
        ("Est. cost (USD)", f"${metrics.estimated_cost_usd:.2f}"),
        ("Cache reuse", f"{metrics.cache_hit_ratio:.0%}"),
        ("Tools / prompt", f"{metrics.tools_per_prompt:.1f}"),
        ("Tokens / prompt", f"{metrics.tokens_per_prompt:,.0f}"),
        ("Avg prompt length", f"{metrics.mean_prompt_words:.0f} words"),
        ("Correction rate", f"{metrics.correction_rate:.0%}"),
        ("Politeness", f"{metrics.politeness_score:+.2f}"),
        ("Session time", _fmt_duration(metrics.duration_seconds)),
        ("Thinking turns", str(metrics.thinking_turns)),
    ]

    tool_total = sum(metrics.tool_breakdown.values()) or 1
    tools = [
        {"name": name, "count": count, "pct": round(100 * count / tool_total)}
        for name, count in metrics.tool_breakdown.items()
    ]

    cmd_total = sum(metrics.slash_command_breakdown.values()) or 1
    commands = [
        {"name": name, "count": count, "pct": round(100 * count / cmd_total)}
        for name, count in metrics.slash_command_breakdown.items()
    ]

    judge_scores = []
    if judge and judge.scores:
        labels = {
            "prompt_quality": "Prompt quality",
            "autonomy": "Autonomy",
            "review_discipline": "Review discipline",
            "recovery": "Recovery",
            "tone": "Tone",
        }
        for key, label in labels.items():
            if key in judge.scores:
                judge_scores.append(
                    {"label": label, "value": judge.scores[key], "pct": round(20 * judge.scores[key])}
                )

    return {
        "candidate": candidate,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "metrics": metrics,
        "key_metrics": key_metrics,
        "badges": badges,
        "tools": tools,
        "commands": commands,
        "judge": judge,
        "judge_scores": judge_scores,
        "replay": replay,
        "models": metrics.models_used,
    }


def render_html(context: dict[str, Any]) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("HTML report needs jinja2 (`pip install jinja2`).") from exc

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("report.html.j2").render(**context)


def write_html(context: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.write_text(render_html(context), encoding="utf-8")
    return path


def to_markdown(context: dict[str, Any]) -> str:
    m: Metrics = context["metrics"]
    lines = [
        f"# ClaudeScore — {context['candidate']}",
        f"_Generated {context['generated_at']}_",
        "",
        "## Metrics",
    ]
    for label, value in context["key_metrics"]:
        lines.append(f"- **{label}:** {value}")

    lines += ["", "## Badges"]
    if context["badges"]:
        for b in context["badges"]:
            lines.append(f"- {b.emoji} **{b.name}** — {b.description} ({b.citation})")
    else:
        lines.append("- (none triggered)")

    if m.slash_command_breakdown:
        lines += ["", "## Slash commands"]
        for name, count in m.slash_command_breakdown.items():
            lines.append(f"- `{name}` ×{count}")

    judge: JudgeResult | None = context.get("judge")
    if judge and not judge.error:
        lines += ["", "## Judge assessment", "", judge.summary]
        if judge.scores:
            lines.append("")
            lines.append(
                "Scores: "
                + ", ".join(f"{k}={v:g}/5" for k, v in judge.scores.items())
            )
        if judge.strengths:
            lines += ["", "**Strengths**"] + [f"- {s}" for s in judge.strengths]
        if judge.concerns:
            lines += ["", "**Concerns**"] + [f"- {c}" for c in judge.concerns]
    elif judge and judge.error:
        lines += ["", f"_Judge skipped: {judge.error}_"]

    return "\n".join(lines) + "\n"
