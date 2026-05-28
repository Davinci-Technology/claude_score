"""End-to-end smoke test against the bundled sample transcript."""

from pathlib import Path

from claude_score.badges import evaluate_trait_badges
from claude_score.metrics import compute
from claude_score.report import build_context, render_html
from claude_score.transcript import parse_target

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_session.jsonl"


def _metrics():
    sessions = parse_target(SAMPLE)
    return sessions, compute(sessions, candidate="demo")


def test_parse_filters_tool_results_and_sidechain():
    sessions, m = _metrics()
    assert len(sessions) == 1
    # 4 real human prompts; the tool_result echo and the sidechain prompt are excluded.
    assert m.prompt_count == 4


def test_tokens_and_tools_counted():
    _, m = _metrics()
    assert m.usage.output_tokens > 0
    assert m.usage.cache_read_input_tokens > 0
    assert m.tool_call_count >= 5
    assert "Edit" in m.tool_breakdown
    assert m.estimated_cost_usd > 0


def test_politeness_is_positive():
    _, m = _metrics()
    # The sample is full of please/thanks/perfect.
    assert m.politeness_score > 0


def test_correction_detected():
    _, m = _metrics()
    assert m.correction_count >= 1  # "Actually that's not quite right"


def test_badges_and_html_render():
    sessions, m = _metrics()
    badges = evaluate_trait_badges(m)
    ctx = build_context("demo", m, badges, None, sessions)
    html = render_html(ctx)
    assert "ClaudeScore" in html
    assert "demo" in html
