"""ClaudeScore — sense the shape of a Claude Code session.

ClaudeScore reads Claude Code session transcripts (the JSONL files Claude Code
writes under ~/.claude/projects/) and turns them into a human-readable
"pulse": deterministic metrics, a set of fun behavioural badges, and an
optional LLM-judged style assessment.

Two intended modes:
  * interview  — analyse one candidate's session(s), produce a scorecard.
  * hackathon  — analyse many participants, produce a leaderboard + awards.

v1 ships the interview path (transcript-first, standalone CLI, HTML report).
"""

__version__ = "0.1.0"
