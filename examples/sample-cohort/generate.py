"""Generate the sample end-of-week cohort report.

Produces:
  - three per-candidate HTML scorecards (using real Claude Code session data
    on the current box, mapped to three fictional candidate names);
  - an ``index.html`` that is the manager-facing final report — composite
    marks from the docs/SCORING.md rubric, ranking, recommendation bands,
    component breakdowns, hidden-rubric adjustments, and panel observations.

The per-candidate "human-entered" numbers (Progress and Code Review
sub-scores, plus the hidden-rubric adjustments) are stubbed inline here as
plausible values, since this is a sample. In a real interview week these
would be filled in by interviewers after reviewing each candidate's report.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path

from claude_score import discovery
from claude_score.badges import evaluate_trait_badges
from claude_score.metrics import Metrics, compute
from claude_score.report import build_context, write_html
from claude_score.transcript import parse_target


MENU_TOTAL = 53  # MovieDeck feature menu total (see problems/moviedeck README)


@dataclass
class HumanScores:
    """Sub-scores an interviewer fills in after reviewing the report.

    Defined by the rubric:
      - collaboration: raw 0–50, before hidden adjustments (mean of the four
        judge axes ×2/5×50, but recorded as the actual integer).
      - progress: raw 0–35, before hidden adjustments. From the feature menu.
      - code_review: raw 0–15, before hidden adjustments. Holistic.

    Hidden adjustments are capped at ±5 per component (see HIDDEN_RUBRIC.md).
    """
    collaboration: int       # 0..50
    progress: int            # 0..35
    code_review: int         # 0..15
    adj_collab: int          # +/- (capped ±5 by interviewer)
    adj_code_review: int     # +/- (capped ±5)
    collab_adj_notes: list[str] = field(default_factory=list)
    review_adj_notes: list[str] = field(default_factory=list)

    @property
    def composite(self) -> int:
        return (
            max(0, min(50, self.collaboration + self.adj_collab))
            + self.progress
            + max(0, min(15, self.code_review + self.adj_code_review))
        )


@dataclass
class SampleCandidate:
    name: str
    one_liner: str
    source_project: str
    filename: str
    scores: HumanScores
    panel_observations: list[str]
    features_shipped: list[str]   # human-readable, for the report


# --- the fictional cohort, hand-tuned to look like a realistic 3-person week
CANDIDATES = [
    SampleCandidate(
        name="Riley Chen",
        one_liner=(
            "High-volume, high-autonomy. Shipped a lot. Let Claude run on long "
            "leashes; sometimes too long."
        ),
        source_project="C--Users-AliSalmani-Documents-davinci-projects-multipic",
        filename="riley-chen.html",
        scores=HumanScores(
            collaboration=38,
            progress=28,
            code_review=9,
            adj_collab=-2,
            adj_code_review=-1,
            collab_adj_notes=[
                "−2: no-review autonomy on the TMDB search component "
                "(accepted a 200-line Edit without inspecting).",
            ],
            review_adj_notes=[
                "−1: TypeScript `any` in 6 places across the deck reducer "
                "and the API client.",
            ],
        ),
        panel_observations=[
            "Most features shipped of the cohort (~45 of 53 menu points).",
            "Strong autonomy and trust in Claude — but watch the review "
            "discipline; let some questionable code through.",
            "Tone tense in the second hour when tests started failing.",
        ],
        features_shipped=[
            "F1 search", "F2 detail", "B1 deck save/remove", "B2 ratings",
            "B3 slicing", "B4 resilient upstream", "UI1 list",
            "UI2 controls", "UI3 instant feel", "UI4 states",
            "S2 recommendations",
        ],
    ),
    SampleCandidate(
        name="Sam Patel",
        one_liner=(
            "Balanced, careful. Caught a real Claude mistake mid-session and "
            "fixed it cleanly. Solid all-rounder."
        ),
        source_project="C--Users-AliSalmani-Documents-davinci-projects-epic-fleet",
        filename="sam-patel.html",
        scores=HumanScores(
            collaboration=42,
            progress=22,
            code_review=12,
            adj_collab=+1,
            adj_code_review=+1,
            collab_adj_notes=[
                "+1: caught a Claude-introduced bug in the rating "
                "endpoint (off-by-one on validation) and corrected it "
                "themselves without re-prompting.",
            ],
            review_adj_notes=[
                "+1: thoughtful NOTES.md with trade-offs called out.",
            ],
        ),
        panel_observations=[
            "Most balanced collaboration profile of the cohort.",
            "Mid-volume on features (~35 of 53 menu points) but each is "
            "solid; no half-finished work.",
            "Reasoned out loud with Claude about caching strategy before "
            "implementing — that conversation is worth reading in the "
            "transcript.",
        ],
        features_shipped=[
            "F1 search", "F2 detail", "B1 deck save/remove", "B2 ratings",
            "B3 slicing", "B4 resilient upstream", "B5 discoverable API",
            "UI1 list", "UI2 controls", "UI4 states",
        ],
    ),
    SampleCandidate(
        name="Jordan Kim",
        one_liner=(
            "Focused, deliberate. Smaller scope but the cleanest code in "
            "the cohort. Asked good questions throughout."
        ),
        source_project="C--Users-AliSalmani-Documents-davinci-projects-nhc-ai-lab",
        filename="jordan-kim.html",
        scores=HumanScores(
            collaboration=45,
            progress=16,
            code_review=14,
            adj_collab=+2,
            adj_code_review=+1,
            collab_adj_notes=[
                "+2: pushed back on Claude's first schema suggestion, "
                "asked it to justify a choice of `IntegerField` over "
                "`PositiveSmallIntegerField`. Engaged across the session.",
            ],
            review_adj_notes=[
                "+1: proper HTTP status codes throughout (201 on create, "
                "204 on delete, 422 on validation).",
            ],
        ),
        panel_observations=[
            "Fewest features shipped (~25 of 53 menu points) — didn't "
            "attempt stretch.",
            "Highest code quality in the cohort: tests, sensible error "
            "responses, no `any` in the TypeScript.",
            "Possibly risk-averse — discuss whether scope or quality is "
            "the more useful signal for the role.",
        ],
        features_shipped=[
            "F1 search", "F2 detail", "B1 deck save/remove", "B2 ratings",
            "B6 scaling list", "UI1 list", "UI4 states", "S6 regression-proof",
        ],
    ),
]


def _band(composite: int) -> tuple[str, str]:
    """Return (label, css-class) for the rubric's recommendation bands."""
    if composite >= 85:
        return "Strong hire", "band-strong"
    if composite >= 70:
        return "Hire", "band-hire"
    if composite >= 55:
        return "Borderline — discuss", "band-borderline"
    return "No hire", "band-no"


def _analyze(candidate: SampleCandidate) -> tuple[Metrics, list, Path]:
    project = discovery.resolve_target(candidate.source_project)
    sessions = parse_target(project)
    metrics = compute(sessions, candidate=candidate.name)
    badges = evaluate_trait_badges(metrics)
    out_path = Path(__file__).parent / candidate.filename
    ctx = build_context(candidate.name, metrics, badges, None, sessions)
    write_html(ctx, out_path)
    return metrics, badges, out_path


# --- final report HTML ----------------------------------------------------

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClaudeScore — Final cohort report</title>
<style>
  :root {{
    --bg: #0f1117; --card: #181b24; --line: #272b36; --txt: #e6e8ee;
    --muted: #9aa3b2; --accent: #6ee7b7; --accent2: #60a5fa; --warn: #f59e0b;
    --red: #f87171; --green: #6ee7b7;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--txt);
    font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 80px; }}
  header {{ border-bottom: 1px solid var(--line); padding-bottom: 20px; margin-bottom: 24px; }}
  .brand {{ color: var(--accent); font-weight: 700; letter-spacing: .5px; font-size: 13px;
    text-transform: uppercase; }}
  h1 {{ margin: 4px 0 2px; font-size: 30px; }}
  .sub {{ color: var(--muted); font-size: 13px; }}
  .note {{ background: #1d1f29; border: 1px solid var(--line); border-left: 3px solid var(--warn);
    padding: 12px 14px; border-radius: 8px; color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: .6px; color: var(--muted);
    margin: 36px 0 14px; }}

  /* Ranking table */
  .rank-table {{ width: 100%; border-collapse: collapse; background: var(--card);
    border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
  .rank-table th, .rank-table td {{ padding: 14px 16px; text-align: left;
    border-bottom: 1px solid var(--line); vertical-align: top; }}
  .rank-table th {{ background: #11141c; color: var(--muted); font-size: 12px;
    text-transform: uppercase; letter-spacing: .4px; }}
  .rank-table tr:last-child td {{ border-bottom: none; }}
  .rank-table td.rank {{ font-size: 22px; font-weight: 700; color: var(--muted); width: 50px; }}
  .rank-table td.composite {{ font-size: 26px; font-weight: 800; text-align: center; width: 110px;
    font-variant-numeric: tabular-nums; }}
  .rank-table td.composite .of {{ font-size: 12px; color: var(--muted); font-weight: 400; }}
  .rank-table .name a {{ color: var(--accent2); text-decoration: none; font-weight: 700; font-size: 17px; }}
  .rank-table .name a:hover {{ text-decoration: underline; }}
  .rank-table .summary {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
  .band {{ display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 11px; font-weight: 700; letter-spacing: .4px; text-transform: uppercase; }}
  .band-strong {{ background: rgba(110, 231, 183, .15); color: var(--green); border: 1px solid var(--green); }}
  .band-hire {{ background: rgba(96, 165, 250, .15); color: var(--accent2); border: 1px solid var(--accent2); }}
  .band-borderline {{ background: rgba(245, 158, 11, .15); color: var(--warn); border: 1px solid var(--warn); }}
  .band-no {{ background: rgba(248, 113, 113, .15); color: var(--red); border: 1px solid var(--red); }}

  /* Component breakdown */
  .breakdown {{ display: grid; grid-template-columns: 180px 1fr 70px; gap: 8px 14px;
    align-items: center; margin: 6px 0; }}
  .breakdown .n {{ color: var(--muted); font-size: 13px; }}
  .breakdown .num {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; font-size: 13px; }}
  .stack {{ display: flex; height: 10px; background: #11141c; border-radius: 6px; overflow: hidden; }}
  .stack .seg-c {{ background: linear-gradient(90deg, var(--accent2), #4f8cf7); }}
  .stack .seg-p {{ background: linear-gradient(90deg, var(--accent), #4adb98); }}
  .stack .seg-r {{ background: linear-gradient(90deg, var(--warn), #e8910b); }}
  .legend {{ display: flex; gap: 18px; margin: 4px 0 18px; font-size: 12px; color: var(--muted); }}
  .legend .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }}
  .legend .d-c {{ background: var(--accent2); }}
  .legend .d-p {{ background: var(--accent); }}
  .legend .d-r {{ background: var(--warn); }}

  /* Candidate detail cards */
  .candidate {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 20px 22px; margin: 14px 0; }}
  .candidate .top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
    margin-bottom: 6px; }}
  .candidate .name {{ font-size: 19px; font-weight: 700; }}
  .candidate .one {{ color: var(--muted); font-size: 13px; margin-bottom: 14px; }}
  .candidate ul {{ margin: 6px 0; padding-left: 18px; font-size: 14px; }}
  .candidate ul li {{ margin: 4px 0; }}
  .candidate .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 16px; }}
  .candidate h3 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--muted); margin: 14px 0 6px; }}
  .pill {{ display: inline-block; background: #11141c; border: 1px solid var(--line);
    border-radius: 999px; padding: 3px 10px; font-size: 12px; color: var(--txt); }}
  .adj-pos {{ color: var(--green); font-weight: 700; }}
  .adj-neg {{ color: var(--red); font-weight: 700; }}

  /* Metrics evidence table at the bottom */
  .metrics-table {{ width: 100%; border-collapse: collapse; background: var(--card);
    border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
  .metrics-table th, .metrics-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); }}
  .metrics-table th {{ background: #11141c; color: var(--muted); font-size: 12px;
    text-transform: uppercase; letter-spacing: .4px; text-align: left; }}
  .metrics-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .metrics-table tr:last-child td {{ border-bottom: none; }}

  footer {{ margin-top: 40px; color: var(--muted); font-size: 12px;
    border-top: 1px solid var(--line); padding-top: 16px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">◍ ClaudeScore</div>
    <h1>Final cohort report</h1>
    <div class="sub">{cohort_n} candidates · MovieDeck (TMDB) · 2-hour live build per candidate</div>
  </header>

  <div class="note">
    <strong>Sample report.</strong> The candidate names are fictional; the
    underlying session data is real Claude Code transcripts from prior
    project work on this box. The Progress and Code Review numbers (and
    the hidden-rubric adjustments) are stubbed plausibly to illustrate the
    final shape — in a real interview week these are filled in by
    interviewers per <code>docs/SCORING.md</code> and <code>docs/HIDDEN_RUBRIC.md</code>.
  </div>

  <h2>Recommendation</h2>
  <table class="rank-table">
    <thead>
      <tr>
        <th>Rank</th>
        <th>Candidate</th>
        <th>Composite</th>
        <th>Recommendation</th>
      </tr>
    </thead>
    <tbody>
{rank_rows}
    </tbody>
  </table>

  <h2>Component breakdown</h2>
  <div class="legend">
    <span><span class="dot d-c"></span>Collaboration (50)</span>
    <span><span class="dot d-p"></span>Progress (35)</span>
    <span><span class="dot d-r"></span>Code review (15)</span>
  </div>
  {breakdown_blocks}

  <h2>Per-candidate detail</h2>
{candidate_cards}

  <h2>Metrics evidence</h2>
  <table class="metrics-table">
    <thead>
      <tr>
        <th>Candidate</th>
        <th class="num">Prompts</th>
        <th class="num">Tools / prompt</th>
        <th class="num">Work tokens</th>
        <th class="num">Cache reuse</th>
        <th class="num">Rewinds</th>
      </tr>
    </thead>
    <tbody>
{metric_rows}
    </tbody>
  </table>

  <footer>
    Final mark = collaboration (50, from judge axes) + progress (35, from
    feature menu) + code review (15, holistic), each adjusted ±5 by the
    hidden rubric. Bands per <code>docs/SCORING.md</code>: 85+ strong hire,
    70–84 hire, 55–69 borderline, &lt;55 no hire.
  </footer>
</div>
</body>
</html>"""


def _rank_row(rank: int, c: SampleCandidate) -> str:
    band_label, band_class = _band(c.scores.composite)
    return (
        "      <tr>"
        f'<td class="rank">#{rank}</td>'
        '<td class="name">'
        f'<a href="{c.filename}">{html.escape(c.name)}</a>'
        f'<div class="summary">{html.escape(c.one_liner)}</div>'
        "</td>"
        f'<td class="composite">{c.scores.composite}<div class="of">/ 100</div></td>'
        f'<td><span class="band {band_class}">{band_label}</span></td>'
        "</tr>"
    )


def _adj_label(adj: int) -> str:
    if adj == 0:
        return ""
    cls = "adj-pos" if adj > 0 else "adj-neg"
    sign = "+" if adj > 0 else ""
    return f' <span class="{cls}">({sign}{adj})</span>'


def _breakdown_block(c: SampleCandidate) -> str:
    s = c.scores
    c_adj = max(0, min(50, s.collaboration + s.adj_collab))
    p_adj = s.progress
    r_adj = max(0, min(15, s.code_review + s.adj_code_review))
    total = c_adj + p_adj + r_adj or 1
    return (
        '<div style="margin: 10px 0;">'
        f'<div style="margin-bottom: 6px;"><strong>{html.escape(c.name)}</strong> '
        f'<span class="sub" style="color:#9aa3b2; font-size:12px;">'
        f'{c_adj}/50 collab · {p_adj}/35 progress · {r_adj}/15 review · '
        f'<strong style="color:#e6e8ee">{c.scores.composite}/100</strong>'
        "</span></div>"
        '<div class="stack">'
        f'<div class="seg-c" style="width: {c_adj / total * 100:.1f}%"></div>'
        f'<div class="seg-p" style="width: {p_adj / total * 100:.1f}%"></div>'
        f'<div class="seg-r" style="width: {r_adj / total * 100:.1f}%"></div>'
        "</div>"
        "</div>"
    )


def _candidate_card(c: SampleCandidate) -> str:
    s = c.scores
    obs_li = "".join(f"<li>{html.escape(o)}</li>" for o in c.panel_observations)
    features_pills = " ".join(
        f'<span class="pill">{html.escape(f)}</span>' for f in c.features_shipped
    )
    band_label, band_class = _band(c.scores.composite)

    collab_notes = "".join(f"<li>{html.escape(n)}</li>" for n in s.collab_adj_notes) or "<li>—</li>"
    review_notes = "".join(f"<li>{html.escape(n)}</li>" for n in s.review_adj_notes) or "<li>—</li>"

    return (
        '<div class="candidate">'
        '<div class="top">'
        f'<div class="name">{html.escape(c.name)} '
        f'<span class="band {band_class}" style="font-size:10px; vertical-align: middle;">{band_label}</span></div>'
        f'<div><a href="{c.filename}" class="pill">open full scorecard →</a></div>'
        "</div>"
        f'<div class="one">{html.escape(c.one_liner)}</div>'

        "<h3>Panel observations</h3>"
        f'<ul>{obs_li}</ul>'

        "<h3>Features shipped</h3>"
        f"<div>{features_pills}</div>"

        '<div class="grid">'
        "<div>"
        f"<h3>Collaboration adjustments{_adj_label(s.adj_collab)}</h3>"
        f"<ul>{collab_notes}</ul>"
        "</div>"
        "<div>"
        f"<h3>Code-review adjustments{_adj_label(s.adj_code_review)}</h3>"
        f"<ul>{review_notes}</ul>"
        "</div>"
        "</div>"
        "</div>"
    )


def _metric_row(c: SampleCandidate, m: Metrics) -> str:
    return (
        "      <tr>"
        f'<td><a href="{c.filename}" style="color:#60a5fa;text-decoration:none">{html.escape(c.name)}</a></td>'
        f'<td class="num">{m.prompt_count}</td>'
        f'<td class="num">{m.tools_per_prompt:.1f}</td>'
        f'<td class="num">{m.work_tokens:,}</td>'
        f'<td class="num">{m.cache_hit_ratio:.0%}</td>'
        f'<td class="num">{getattr(m, "rewind_count", 0)}</td>'
        "</tr>"
    )


def main() -> int:
    results: list[tuple[SampleCandidate, Metrics]] = []
    for c in CANDIDATES:
        print(f"Analyzing {c.name} ({c.source_project}) ...")
        metrics, _, path = _analyze(c)
        print(f"  -> {path.name}: composite {c.scores.composite}/100 "
              f"({_band(c.scores.composite)[0]})")
        results.append((c, metrics))

    # Rank descending by composite.
    ranked = sorted(results, key=lambda x: -x[0].scores.composite)
    rank_rows = "\n".join(_rank_row(i + 1, c) for i, (c, _) in enumerate(ranked))
    breakdown_blocks = "\n".join(_breakdown_block(c) for c, _ in ranked)
    candidate_cards = "\n".join(_candidate_card(c) for c, _ in ranked)
    metric_rows = "\n".join(_metric_row(c, m) for c, m in ranked)

    index_html = INDEX_TEMPLATE.format(
        cohort_n=len(ranked),
        rank_rows=rank_rows,
        breakdown_blocks=breakdown_blocks,
        candidate_cards=candidate_cards,
        metric_rows=metric_rows,
    )
    index_path = Path(__file__).parent / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"\nFinal report written to {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
