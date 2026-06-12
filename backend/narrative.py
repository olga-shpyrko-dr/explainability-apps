"""
Builds the LLM prompt and calls the configured LLM provider to generate a
plain-English cohort narrative.  Policy_Number values are NEVER in the prompt.
"""

from __future__ import annotations

from typing import Any, Optional

from llm_client import call_llm


SYSTEM_PROMPT = (
    "You are an insurance data analyst summarising model outputs for a retention team. "
    "Your summaries are concise, factual, and use plain language a financial adviser would understand. "
    "Never use the terms 'SHAP' or 'feature importance'. "
    "Instead say 'factor increasing surrender risk' or 'factor reducing surrender risk'. "
    "End your response with a one-sentence recommended action."
)

USER_TEMPLATE = """\
COHORT: {n_rows} policies ({pct_of_total:.1f}% of total scored population).
Filter criteria: {filter_description}

SCORE DISTRIBUTION:
  Cohort — mean={mean_score:.3f}, median={median_score:.3f}
  Full population — mean={mean_score_full:.3f}, median={median_score_full:.3f}

TOP EXPLANATION GROUPS (average contribution to lapse propensity, cohort):
{group_table}

KEY FEATURE VALUES (cohort vs full population):
{feature_table}

{outcome_note}

Write two short paragraphs:
1. Profile: describe who these policyholders are based on the feature values above.
2. Drivers: explain what is driving their lapse propensity scores.

Then add one recommended action sentence starting with "Recommended action:".

{custom_instruction}"""


def _format_group_table(groups: list[dict[str, Any]]) -> str:
    lines = ["Group | Avg contribution | Direction | Coverage"]
    lines.append("-" * 60)
    for g in groups[:6]:
        direction = "increases risk" if g["avg_shap"] > 0 else "reduces risk"
        lines.append(
            f"{g['feature_group']:<30} | {g['avg_shap']:+.4f} | {direction} | {g['coverage_pct']:.0f}%"
        )
    return "\n".join(lines)


def _format_feature_table(groups: list[dict[str, Any]], n_per_group: int = 2) -> str:
    lines = []
    for g in groups[:4]:
        for feat in g.get("top_features", [])[:n_per_group]:
            lines.append(
                f"  {feat['feature_name']}: avg SHAP {feat['avg_shap']:+.4f} "
                f"(present in {feat['n_rows']} rows)"
            )
    return "\n".join(lines) if lines else "  (no feature detail available)"


def build_prompt(
    profile: dict[str, Any],
    groups: list[dict[str, Any]],
    filters: dict[str, Any],
    outcome_rate: Optional[float] = None,
    custom_instruction: str = "",
) -> str:
    score = profile.get("score_stats", {})
    score_full = profile.get("score_stats_full", {})

    filter_desc = _describe_filters(filters) or "none (full scored population)"
    outcome_note = (
        f"OBSERVED LAPSE RATE (training labels): {outcome_rate:.1%}"
        if outcome_rate is not None
        else ""
    )

    return USER_TEMPLATE.format(
        n_rows=profile["n_rows"],
        pct_of_total=profile.get("pct_of_total", 0),
        filter_description=filter_desc,
        mean_score=score.get("mean") or 0,
        median_score=score.get("median") or 0,
        mean_score_full=score_full.get("mean") or 0,
        median_score_full=score_full.get("median") or 0,
        group_table=_format_group_table(groups),
        feature_table=_format_feature_table(groups),
        outcome_note=outcome_note,
        custom_instruction=f"Additional instruction: {custom_instruction}" if custom_instruction else "",
    )


def generate_narrative(
    profile: dict[str, Any],
    groups: list[dict[str, Any]],
    filters: dict[str, Any],
    settings: Any,
    outcome_rate: Optional[float] = None,
    custom_instruction: str = "",
    provider: Optional[str] = None,
) -> str:
    if profile["n_rows"] < 30:
        size_warning = (
            f"[Warning: cohort has only {profile['n_rows']} rows — "
            "group-level averages may not be stable.]\n\n"
        )
    else:
        size_warning = ""

    user_msg = build_prompt(profile, groups, filters, outcome_rate, custom_instruction)

    text = call_llm(
        messages=[{"role": "user", "content": user_msg}],
        system=SYSTEM_PROMPT,
        settings=settings,
        provider=provider,
        max_tokens=700,
    )
    return size_warning + text


def _describe_filters(filters: dict[str, Any]) -> str:
    parts = []
    for col, spec in filters.items():
        if isinstance(spec, dict):
            lo = spec.get("min")
            hi = spec.get("max")
            if lo is not None and hi is not None:
                parts.append(f"{col} between {lo} and {hi}")
            elif lo is not None:
                parts.append(f"{col} >= {lo}")
            elif hi is not None:
                parts.append(f"{col} <= {hi}")
        elif isinstance(spec, list):
            parts.append(f"{col} in {spec}")
        else:
            parts.append(f"{col} = {spec}")
    return "; ".join(parts)
