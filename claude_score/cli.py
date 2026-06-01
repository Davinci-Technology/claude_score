"""ClaudeScore command-line interface.

Commands:
  claude_score list                       list Claude Code projects/sessions on this box
  claude_score analyze <target> [opts]    analyze a session/project and report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, discovery, interview, report
from .badges import evaluate_trait_badges
from .judge import DEFAULT_JUDGE_MODEL, judge_candidate
from .metrics import compute
from .transcript import parse_target


def _configure_stdout() -> None:
    """Make the badges/glyphs printable on consoles that default to cp1252."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _emit(msg: str = "") -> None:
    print(msg)


def cmd_list(args: argparse.Namespace) -> int:
    projects = discovery.list_projects()
    if not projects:
        _emit(f"No transcripts found under {discovery.projects_root()}")
        return 1
    _emit(f"Claude Code projects under {discovery.projects_root()}:\n")
    for p in projects[: args.limit]:
        when = p.last_modified.strftime("%Y-%m-%d %H:%M")
        _emit(f"  {p.session_count:>3} sessions  {when}  {p.readable_hint}")
        _emit(f"       └─ name: {p.name}")
    _emit(f"\nAnalyze one with:  claude_score analyze <name>")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    try:
        target = discovery.resolve_target(args.target)
    except FileNotFoundError as exc:
        _emit(f"error: {exc}")
        return 1

    sessions = parse_target(target)
    if not sessions:
        _emit(f"error: no sessions parsed from {target}")
        return 1

    candidate = args.candidate or Path(target).stem
    metrics = compute(sessions, candidate=candidate)
    badges = [] if args.no_badges else evaluate_trait_badges(metrics)

    judge_result = None
    if args.judge:
        _emit("Running LLM judge pass ...")
        judge_result = judge_candidate(sessions, candidate=candidate, model=args.model)
        if judge_result.error:
            _emit(f"  (judge: {judge_result.error})")

    _print_summary(candidate, metrics, badges, judge_result)

    context = report.build_context(candidate, metrics, badges, judge_result, sessions)
    if args.html:
        path = report.write_html(context, args.html)
        _emit(f"\nHTML report written to {path}")
    if args.md:
        Path(args.md).write_text(report.to_markdown(context), encoding="utf-8")
        _emit(f"Markdown summary written to {args.md}")
    if not args.html and not args.md:
        _emit("\nTip: add --html report.html for a shareable scorecard.")
    return 0


def _print_summary(candidate, metrics, badges, judge_result) -> None:
    _emit("")
    _emit(f"◍ ClaudeScore — {candidate}")
    _emit("─" * 48)
    _emit(f"  sessions        {metrics.session_count}")
    _emit(f"  prompts         {metrics.prompt_count}")
    _emit(f"  tool calls      {metrics.tool_call_count}  ({metrics.tools_per_prompt:.1f}/prompt)")
    _emit(f"  work tokens     {metrics.work_tokens:,}  (~${metrics.estimated_cost_usd:.2f}, excl. cache reads)")
    _emit(f"  cache reuse     {metrics.cache_hit_ratio:.0%}")
    _emit(f"  avg prompt      {metrics.mean_prompt_words:.0f} words")
    _emit(f"  corrections     {metrics.correction_rate:.0%} of prompts")
    if metrics.rewind_count or metrics.slash_command_count:
        _emit(f"  rewinds         {metrics.rewind_count}  "
              f"({metrics.rewound_prompt_count} prompt(s) redone)")
        _emit(f"  slash commands  {metrics.slash_command_count}")
    _emit(f"  politeness      {metrics.politeness_score:+.2f}")
    if metrics.tool_breakdown:
        top = ", ".join(f"{n}×{c}" for n, c in list(metrics.tool_breakdown.items())[:5])
        _emit(f"  top tools       {top}")
    if badges:
        _emit("\n  badges:")
        for b in badges:
            _emit(f"    {b.emoji} {b.name} — {b.citation}")
    if judge_result and not judge_result.error and judge_result.summary:
        _emit("\n  judge:")
        _emit(f"    {judge_result.summary}")


_SEVERITY_GLYPH = {"error": "✗", "warn": "⚠", "ok": "✓"}


def cmd_interview_preflight(args: argparse.Namespace) -> int:
    issues = interview.preflight()
    _emit("Preflight checks:\n")
    fatal = 0
    for issue in issues:
        glyph = _SEVERITY_GLYPH.get(issue.severity, "?")
        _emit(f"  {glyph} [{issue.severity}] {issue.message}")
        if issue.severity == "error":
            fatal += 1
    _emit("")
    if fatal:
        _emit(f"{fatal} blocking issue(s). Fix these before the interview starts.")
        return 1
    _emit("Box is ready to host an interview.")
    return 0


def cmd_interview_start(args: argparse.Namespace) -> int:
    problem = Path(args.problem) if args.problem else None
    if problem and not problem.exists():
        _emit(f"error: problem source not found: {problem}")
        return 1
    try:
        candidate_dir = interview.start(
            args.candidate,
            problem=problem,
            root=Path(args.root),
            force=args.force,
        )
    except FileExistsError as exc:
        _emit(f"error: {exc}")
        return 1

    _emit(f"\n✓ Candidate folder created at {candidate_dir}")
    if problem:
        _emit(f"  problem seeded from {problem}")

    # Report any env vars forwarded from the operator's environment into the
    # candidate's .env so the operator can confirm before handing off.
    manifest_path = candidate_dir / interview.MANIFEST
    if manifest_path.exists():
        import json as _json
        manifest_data = _json.loads(manifest_path.read_text(encoding="utf-8"))
        forwarded = manifest_data.get("forwarded_env_keys") or []
        if forwarded:
            _emit(f"  forwarded into .env: {', '.join(forwarded)}")

    _emit("\nNext steps:")
    _emit(f"  1. cd \"{candidate_dir}\"")
    _emit("  2. claude")
    _emit(f"  3. when done: claude_score interview finish \"{args.candidate}\""
          + (f" --root \"{args.root}\"" if args.root != str(interview.DEFAULT_ROOT) else ""))
    return 0


def cmd_interview_finish(args: argparse.Namespace) -> int:
    try:
        candidate_dir = interview.finish(
            args.candidate,
            root=Path(args.root),
            judge=args.judge,
            model=args.model,
        )
    except FileNotFoundError as exc:
        _emit(f"error: {exc}")
        return 1

    manifest = candidate_dir / interview.MANIFEST
    _emit(f"\n✓ Sealed evidence bundle at {candidate_dir}")
    _emit("  contents:")
    for name in ("report.html", "report.md", "solution.patch", "git.log",
                 "transcripts/", interview.MANIFEST):
        target = candidate_dir / name
        marker = "✓" if target.exists() else "—"
        _emit(f"    {marker} {name}")
    if manifest.exists():
        data = __import__("json").loads(manifest.read_text(encoding="utf-8"))
        if data.get("transcript_warning"):
            _emit(f"\n⚠ {data['transcript_warning']}")
    return 0


def cmd_interview_status(args: argparse.Namespace) -> int:
    rows = interview.status(Path(args.root))
    if not rows:
        _emit(f"No candidates under {args.root}.")
        return 0
    _emit(f"Candidates under {args.root}:\n")
    for r in rows:
        state = "finished" if r.finished_at else "in progress"
        _emit(f"  [{state:11s}] {r.candidate}  (slug: {r.slug})")
        _emit(f"               started {r.started_at}"
              + (f"  finished {r.finished_at}" if r.finished_at else ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude_score",
        description="Sense how a developer collaborates with Claude Code.",
    )
    parser.add_argument("--version", action="version", version=f"claude_score {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list Claude Code projects on this machine")
    p_list.add_argument("--limit", type=int, default=25, help="max projects to show")
    p_list.set_defaults(func=cmd_list)

    p_an = sub.add_parser("analyze", help="analyze a session/project directory")
    p_an.add_argument("target", help="a .jsonl file, project directory, project name, or session id")
    p_an.add_argument("--candidate", help="label for the person (defaults to target name)")
    p_an.add_argument("--html", help="write an HTML report to this path")
    p_an.add_argument("--md", help="write a Markdown summary to this path")
    p_an.add_argument("--judge", action="store_true", help="run the optional LLM judge pass")
    p_an.add_argument("--model", default=DEFAULT_JUDGE_MODEL, help="model for the judge pass")
    p_an.add_argument("--no-badges", action="store_true", help="skip trait badges")
    p_an.set_defaults(func=cmd_analyze)

    # --- interview harness -------------------------------------------------
    p_iv = sub.add_parser(
        "interview",
        help="run the per-candidate interview workflow (preflight/start/finish/status)",
    )
    iv_sub = p_iv.add_subparsers(dest="iv_command", required=True)

    p_pre = iv_sub.add_parser("preflight", help="verify the box is ready to host an interview")
    p_pre.set_defaults(func=cmd_interview_preflight)

    p_start = iv_sub.add_parser("start", help="create a per-candidate working dir + seed the problem")
    p_start.add_argument("candidate", help="candidate name (used as a slug for the folder)")
    p_start.add_argument("--problem", help="problem source: a directory, file, or archive (.zip/.tar/.tgz)")
    p_start.add_argument("--root", default=str(interview.DEFAULT_ROOT),
                         help=f"root dir for candidate folders (default: {interview.DEFAULT_ROOT})")
    p_start.add_argument("--force", action="store_true", help="overwrite an existing candidate folder")
    p_start.set_defaults(func=cmd_interview_start)

    p_fin = iv_sub.add_parser("finish", help="seal the candidate folder + run analysis")
    p_fin.add_argument("candidate", help="candidate name (must match the start command)")
    p_fin.add_argument("--root", default=str(interview.DEFAULT_ROOT),
                       help=f"root dir for candidate folders (default: {interview.DEFAULT_ROOT})")
    p_fin.add_argument("--judge", action="store_true", help="run the optional LLM judge pass")
    p_fin.add_argument("--model", default=DEFAULT_JUDGE_MODEL, help="model for the judge pass")
    p_fin.set_defaults(func=cmd_interview_finish)

    p_st = iv_sub.add_parser("status", help="list candidates under the interview root")
    p_st.add_argument("--root", default=str(interview.DEFAULT_ROOT),
                      help=f"root dir for candidate folders (default: {interview.DEFAULT_ROOT})")
    p_st.set_defaults(func=cmd_interview_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
