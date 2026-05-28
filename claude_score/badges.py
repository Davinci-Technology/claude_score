"""Behavioural badges.

Two flavours:

* **Trait badges** describe one person in absolute terms (thresholds on their
  own metrics). Used in interview mode — "this candidate tends to ...".
* **Cohort badges** are competitive: across a group, exactly one person wins
  each (argmax / argmin). Used in hackathon mode for the awards ceremony.

Thresholds are intentionally easy to tune in one place. They are heuristics
meant to be fun and directional, not a scientific personality test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .metrics import Metrics


@dataclass
class AwardedBadge:
    emoji: str
    name: str
    description: str
    citation: str  # a short, human-readable reason this was awarded


# --- trait badges -----------------------------------------------------------

@dataclass
class _TraitBadge:
    emoji: str
    name: str
    description: str
    predicate: Callable[[Metrics], bool]
    cite: Callable[[Metrics], str]


_TRAIT_BADGES: list[_TraitBadge] = [
    _TraitBadge(
        "🙏", "The Diplomat", "Consistently warm and polite with Claude.",
        lambda m: m.politeness_score > 0.25 and m.polite_hits >= 3,
        lambda m: f"{m.polite_hits} courteous phrases across {m.prompt_count} prompts.",
    ),
    _TraitBadge(
        "😤", "The Drill Sergeant", "Terse, commanding, no time for pleasantries.",
        lambda m: m.politeness_score < -0.15 or m.shouted_prompts >= 2,
        lambda m: f"{m.terse_hits} terse markers, {m.shouted_prompts} shouted prompt(s).",
    ),
    _TraitBadge(
        "🐋", "The Whale", "Moved a serious amount of new tokens.",
        lambda m: m.work_tokens >= 2_000_000,
        lambda m: f"{m.work_tokens:,} work tokens (~${m.estimated_cost_usd:.2f}).",
    ),
    _TraitBadge(
        "🪙", "The Miser", "Economical — got things done on few tokens per prompt.",
        lambda m: m.prompt_count >= 5 and m.tokens_per_prompt < 8_000,
        lambda m: f"only {m.tokens_per_prompt:,.0f} work tokens per prompt.",
    ),
    _TraitBadge(
        "🎯", "One-Shot", "Rarely had to correct course.",
        lambda m: m.prompt_count >= 5 and m.correction_rate < 0.1,
        lambda m: f"corrected on {m.correction_rate:.0%} of prompts.",
    ),
    _TraitBadge(
        "🌀", "The Micromanager", "Lots of small prompts, keeps a short leash.",
        lambda m: m.prompt_count >= 15 and m.tools_per_prompt < 1.5,
        lambda m: f"{m.prompt_count} prompts at {m.tools_per_prompt:.1f} tools each.",
    ),
    _TraitBadge(
        "🧘", "The Trusting", "Lets Claude run — many tools per instruction.",
        lambda m: m.tools_per_prompt >= 4,
        lambda m: f"{m.tools_per_prompt:.1f} tool calls per prompt.",
    ),
    _TraitBadge(
        "🦉", "The Reviewer", "Reads as much as it writes — checks the work.",
        lambda m: m.category_breakdown.get("read", 0) >= m.category_breakdown.get("write", 1),
        lambda m: f"{m.category_breakdown.get('read', 0)} reads vs "
                  f"{m.category_breakdown.get('write', 0)} writes.",
    ),
    _TraitBadge(
        "🗺️", "The Planner", "Leans on planning / todos / extended thinking.",
        lambda m: m.category_breakdown.get("plan", 0) >= 1 or m.thinking_turns >= 3,
        lambda m: f"{m.category_breakdown.get('plan', 0)} planning calls, "
                  f"{m.thinking_turns} thinking turns.",
    ),
    _TraitBadge(
        "📜", "The Novelist", "Writes long, detailed prompts.",
        lambda m: m.mean_prompt_words >= 60,
        lambda m: f"{m.mean_prompt_words:.0f} words per prompt on average.",
    ),
    _TraitBadge(
        "🤐", "Person of Few Words", "Keeps prompts short and punchy.",
        lambda m: m.prompt_count >= 5 and m.mean_prompt_words <= 12,
        lambda m: f"{m.mean_prompt_words:.0f} words per prompt on average.",
    ),
    _TraitBadge(
        "♻️", "The Cache Whisperer", "Structures context well — high cache reuse.",
        lambda m: m.cache_hit_ratio >= 0.7,
        lambda m: f"{m.cache_hit_ratio:.0%} of input served from cache.",
    ),
]


def evaluate_trait_badges(m: Metrics) -> list[AwardedBadge]:
    out: list[AwardedBadge] = []
    for b in _TRAIT_BADGES:
        try:
            if b.predicate(m):
                out.append(AwardedBadge(b.emoji, b.name, b.description, b.cite(m)))
        except (ZeroDivisionError, KeyError, ValueError):
            continue
    return out


# --- cohort (competitive) badges --------------------------------------------

@dataclass
class _CohortBadge:
    emoji: str
    name: str
    description: str
    key: Callable[[Metrics], float]
    want_max: bool
    cite: Callable[[Metrics], str]
    min_prompts: int = 1


_COHORT_BADGES: list[_CohortBadge] = [
    _CohortBadge("🙏", "Most Polite", "Warmest tone in the cohort.",
                 lambda m: m.politeness_score, True,
                 lambda m: f"politeness {m.politeness_score:+.2f}"),
    _CohortBadge("😤", "Most Demanding", "Tersest, most commanding tone.",
                 lambda m: m.politeness_score, False,
                 lambda m: f"politeness {m.politeness_score:+.2f}"),
    _CohortBadge("🐋", "Biggest Spender", "Highest estimated cost.",
                 lambda m: m.estimated_cost_usd, True,
                 lambda m: f"~${m.estimated_cost_usd:.2f}"),
    _CohortBadge("🪙", "Most Frugal", "Lowest cost per prompt.",
                 lambda m: m.cost_per_prompt, False,
                 lambda m: f"${m.cost_per_prompt:.3f}/prompt", min_prompts=5),
    _CohortBadge("⚡", "Fastest Hands", "Shortest gaps between prompts.",
                 lambda m: (sum(m.prompt_gaps_seconds) / len(m.prompt_gaps_seconds))
                 if m.prompt_gaps_seconds else 1e9, False,
                 lambda m: f"{(sum(m.prompt_gaps_seconds)/len(m.prompt_gaps_seconds)):.0f}s "
                           "between prompts" if m.prompt_gaps_seconds else "n/a"),
    _CohortBadge("🎯", "Cleanest Run", "Lowest correction rate.",
                 lambda m: m.correction_rate, False,
                 lambda m: f"{m.correction_rate:.0%} corrections", min_prompts=5),
    _CohortBadge("🧘", "Most Trusting", "Most tool calls per prompt.",
                 lambda m: m.tools_per_prompt, True,
                 lambda m: f"{m.tools_per_prompt:.1f} tools/prompt"),
    _CohortBadge("📜", "Most Verbose", "Longest prompts on average.",
                 lambda m: m.mean_prompt_words, True,
                 lambda m: f"{m.mean_prompt_words:.0f} words/prompt"),
    _CohortBadge("♻️", "Cache King", "Best prompt-cache reuse.",
                 lambda m: m.cache_hit_ratio, True,
                 lambda m: f"{m.cache_hit_ratio:.0%} cache reuse"),
]


@dataclass
class CohortAward:
    badge: AwardedBadge
    winner: str


def award_cohort(metrics_by_candidate: dict[str, Metrics]) -> list[CohortAward]:
    awards: list[CohortAward] = []
    if not metrics_by_candidate:
        return awards
    for b in _COHORT_BADGES:
        eligible = {
            name: m
            for name, m in metrics_by_candidate.items()
            if m.prompt_count >= b.min_prompts
        }
        if not eligible:
            continue
        winner = (max if b.want_max else min)(eligible, key=lambda n: b.key(eligible[n]))
        m = eligible[winner]
        awards.append(
            CohortAward(
                badge=AwardedBadge(b.emoji, b.name, b.description, b.cite(m)),
                winner=winner,
            )
        )
    return awards
