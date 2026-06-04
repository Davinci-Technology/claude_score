"""The upgraded strict judge: schema parsing and report rendering.

No API key needed — we test parse_judge_json (shared by the API and in-session
subagent paths) and that the new fields (overall, recommendation, per-dimension
rationale, product dimensions) flow through build_context -> HTML/Markdown.
"""

from claude_score.judge import JudgeResult, build_judge_message, parse_judge_json
from claude_score.metrics import Metrics
from claude_score.report import build_context, render_html, to_markdown


RAW = {
    "scores": {
        "prompt_quality": 4, "delegation_control": 3, "review_verification": 4,
        "recovery": None,  # CANNOT_ASSESS -> must be dropped, not coerced
        "feature_completeness": 3, "code_quality": 2, "architecture": 4, "testing": 2,
    },
    "rationale": {
        "code_quality": "Broad except: clauses swallow errors in services/tmdb.py.",
        "recovery": "CANNOT_ASSESS: nothing broke in the session.",
    },
    "overall": 3,
    "recommendation": "lean_no_hire",
    "summary": "Competent backend, thin frontend; tests are mostly happy-path.",
    "strengths": ["Clean services layer."],
    "concerns": ["No input validation on the deck endpoint."],
}


def test_parse_drops_null_scores_and_keeps_new_fields():
    jr = parse_judge_json(RAW, model="test-model")
    assert "recovery" not in jr.scores          # null dropped
    assert jr.scores["code_quality"] == 2.0
    assert jr.overall == 3.0
    assert jr.recommendation == "lean_no_hire"
    assert "swallow errors" in jr.rationale["code_quality"]
    assert jr.model == "test-model"


def test_report_renders_overall_dims_and_rationale():
    jr = parse_judge_json(RAW, model="subagent")
    ctx = build_context("Cand", Metrics(candidate="Cand"), [], jr, [])

    # product dimensions and grouping are present
    labels = {s["label"] for s in ctx["judge_scores"]}
    assert {"Code quality", "Architecture", "Feature completeness", "Testing"} <= labels
    assert "recovery" not in {s["label"].lower() for s in ctx["judge_scores"]}

    html = render_html(ctx)
    assert "overall" in html.lower()
    assert "lean no hire" in html  # recommendation underscores -> spaces
    assert "swallow errors" in html  # rationale surfaced

    md = to_markdown(ctx)
    assert "Overall: 3/5" in md
    assert "| Code quality | 2/5 |" in md
    assert "lean no hire" in md


def test_build_judge_message_includes_diff_and_smoke():
    msg = build_judge_message([], candidate="X", code_diff="DIFFBODY", smoke_report="42 tests OK")
    assert "DIFFBODY" in msg and "CODE DIFF vs the provided boilerplate" in msg
    assert "42 tests OK" in msg and "SMOKE-TEST REPORT" in msg
    # Without inputs, it tells the judge to CANNOT_ASSESS the product dims.
    bare = build_judge_message([], candidate="X")
    assert "not provided" in bare
