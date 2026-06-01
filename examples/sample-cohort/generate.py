"""Generate the sample cohort report.

Produces:
  - three per-candidate HTML scorecards (using real Claude Code session data
    on the current box, mapped to three fictional candidate names),
  - an index.html that compares them side-by-side.

Re-run any time to refresh the sample. The output filenames are stable so
they overwrite cleanly.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from claude_score import discovery
from claude_score.badges import evaluate_trait_badges
from claude_score.metrics import Metrics, compute
from claude_score.report import build_context, write_html
from claude_score.transcript import parse_target


@dataclass
class SampleCandidate:
    name: str
    blurb: str  # one-line read of their style, shown on the cohort page
    source_project: str  # munged project dir under ~/.claude/projects/
    filename: str  # output HTML filename (sibling of index.html)


# Three "candidates" mapped to real session data on this box. The labels are
# fictional — the underlying transcripts are real-but-from-prior-work, which
# is enough to give the manager a faithful read of what the tool produces.
CANDIDATES = [
    SampleCandidate(
        name="Riley Chen",
        blurb="High-volume, high-autonomy. Burned through tokens, "
              "let Claude run on long leashes.",
        source_project="C--Users-AliSalmani-Documents-davinci-projects-multipic",
        filename="riley-chen.html",
    ),
    SampleCandidate(
        name="Sam Patel",
        blurb="Mid-volume, balanced. Read as much as they wrote.",
        source_project="C--Users-AliSalmani-Documents-davinci-projects-epic-fleet",
        filename="sam-patel.html",
    ),
    SampleCandidate(
        name="Jordan Kim",
        blurb="Focused session. Fewer prompts, careful pacing.",
        source_project="C--Users-AliSalmani-Documents-davinci-projects-nhc-ai-lab",
        filename="jordan-kim.html",
    ),
]


def _analyze(candidate: SampleCandidate) -> tuple[Metrics, list, Path]:
    project = discovery.resolve_target(candidate.source_project)
    sessions = parse_target(project)
    metrics = compute(sessions, candidate=candidate.name)
    badges = evaluate_trait_badges(metrics)
    out_dir = Path(__file__).parent
    out_path = out_dir / candidate.filename
    ctx = build_context(candidate.name, metrics, badges, None, sessions)
    write_html(ctx, out_path)
    return metrics, badges, out_path


# --- cohort index ---------------------------------------------------------


COHORT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClaudeScore — Sample cohort</title>
<style>
  :root {{
    --bg: #0f1117; --card: #181b24; --line: #272b36; --txt: #e6e8ee;
    --muted: #9aa3b2; --accent: #6ee7b7; --accent2: #60a5fa; --warn: #f59e0b;
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
  table {{ width: 100%; border-collapse: collapse; background: var(--card);
    border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
  th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--line); }}
  th {{ background: #11141c; color: var(--muted); font-size: 12px;
    text-transform: uppercase; letter-spacing: .4px; }}
  tr:last-child td {{ border-bottom: none; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td a {{ color: var(--accent2); text-decoration: none; font-weight: 600; }}
  td a:hover {{ text-decoration: underline; }}
  .blurb {{ color: var(--muted); font-size: 12.5px; max-width: 360px; }}
  .badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
  .candidate-card {{ background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 16px 18px; margin: 10px 0; }}
  .candidate-card .top {{ display: flex; align-items: center; gap: 12px; }}
  .candidate-card .name {{ font-size: 18px; font-weight: 700; }}
  .candidate-card .blurb {{ color: var(--muted); font-size: 13px; margin: 4px 0 10px; }}
  .pill {{ display: inline-block; background: #11141c; border: 1px solid var(--line);
    border-radius: 999px; padding: 3px 10px; font-size: 12px; color: var(--txt); }}
  footer {{ margin-top: 40px; color: var(--muted); font-size: 12px;
    border-top: 1px solid var(--line); padding-top: 16px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">◍ ClaudeScore</div>
    <h1>Sample cohort report</h1>
    <div class="sub">Three candidates, one week of interviews, one comparison page.</div>
  </header>

  <div class="note">
    <strong>Note:</strong> this is a demonstration of what an end-of-week
    cohort report looks like. The candidate names are fictional; the
    underlying session data is real Claude Code transcripts from prior project
    work on this box. Metric shapes, badge logic, and the comparison layout
    are exactly what a real interview week would produce.
  </div>

  <h2>Comparison at a glance</h2>
  <table>
    <thead>
      <tr>
        <th>Candidate</th>
        <th class="num">Prompts</th>
        <th class="num">Tools / prompt</th>
        <th class="num">Work tokens</th>
        <th class="num">Cache reuse</th>
        <th class="num">Corrections</th>
        <th class="num">Rewinds</th>
        <th>Style</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>

  <h2>Per-candidate snapshots</h2>
{cards}

  <footer>
    Composite hiring marks (collaboration / progress / code review) are
    computed on a per-candidate worksheet that combines these automated
    metrics with the interviewer's progress score and code-review score. See
    <code>docs/SCORING.md</code> in the ClaudeScore repo for the full rubric.
  </footer>
</div>
</body>
</html>"""


def _row(c: SampleCandidate, m: Metrics) -> str:
    return (
        "      <tr>"
        f'<td><a href="{c.filename}">{html.escape(c.name)}</a></td>'
        f'<td class="num">{m.prompt_count}</td>'
        f'<td class="num">{m.tools_per_prompt:.1f}</td>'
        f'<td class="num">{m.work_tokens:,}</td>'
        f'<td class="num">{m.cache_hit_ratio:.0%}</td>'
        f'<td class="num">{m.correction_rate:.0%}</td>'
        f'<td class="num">{getattr(m, "rewind_count", 0)}</td>'
        f'<td class="blurb">{html.escape(c.blurb)}</td>'
        "</tr>"
    )


def _card(c: SampleCandidate, m: Metrics, badges) -> str:
    pill_html = "".join(
        f'<span class="pill">{b.emoji} {html.escape(b.name)}</span> '
        for b in badges[:5]
    )
    return (
        '<div class="candidate-card">'
        f'<div class="top"><div class="name">{html.escape(c.name)}</div>'
        f'<a href="{c.filename}" class="pill">open full report →</a></div>'
        f'<div class="blurb">{html.escape(c.blurb)}</div>'
        f'<div class="badges">{pill_html}</div>'
        "</div>"
    )


def main() -> int:
    results = []
    for c in CANDIDATES:
        print(f"Analyzing {c.name} ({c.source_project}) ...")
        metrics, badges, path = _analyze(c)
        print(f"  -> {path.name}: {metrics.prompt_count} prompts, "
              f"{metrics.work_tokens:,} work tokens, {len(badges)} badges")
        results.append((c, metrics, badges))

    rows = "\n".join(_row(c, m) for c, m, _ in results)
    cards = "\n".join(_card(c, m, b) for c, m, b in results)
    index_html = COHORT_TEMPLATE.format(rows=rows, cards=cards)
    index_path = Path(__file__).parent / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"\nCohort index written to {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
