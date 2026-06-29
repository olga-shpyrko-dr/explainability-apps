"""
Builds the LLM prompt and calls the configured LLM provider.

All domain-specific vocabulary comes from narrative_config.json so this module
contains no hardcoded domain language. Entity identifiers are never passed to
the LLM — only aggregated cohort statistics.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import logging

from llm_client import call_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt(nc: dict[str, Any]) -> str:
    """
    Assemble the LLM system prompt from narrative_config fields.
    Uses custom_system_prompt verbatim if provided.
    """
    if nc.get("custom_system_prompt"):
        return nc["custom_system_prompt"]

    return (
        f"You are a data analyst summarising {nc['domain_description']} model outputs "
        f"for a {nc['target_audience']}. "
        f"Never use the terms 'SHAP' or 'feature importance'. "
        f"Instead say '{nc['factor_positive_label']}' or '{nc['factor_negative_label']}'. "
        f"You MUST respond with a valid JSON object only — no prose, no markdown fences, no extra text."
    )


# ---------------------------------------------------------------------------
# User prompt
# ---------------------------------------------------------------------------

_USER_TEMPLATE = """\
Return a JSON object with these exact keys. No other text.

{{
  "summary": "<one sentence: cohort size and overall risk level, average score>",
  "drivers": [
    {{"group": "<factor group name>", "explanation": "<what it contributes to the score>"}},
    ...one object per group in the table below, plus one extra for any notable pattern...
  ],
  "recommendation": "<one sentence action starting with: Recommended action:>"
}}

DATA:

COHORT: {n_rows} {entity_label_plural} ({pct_of_total:.1f}% of total scored population).
Filter criteria: {filter_description}

SCORE DISTRIBUTION (probability of {high_score_label}):
  Cohort    — mean={mean_score:.3f}, median={median_score:.3f}
  Full pop. — mean={mean_score_full:.3f}, median={median_score_full:.3f}

TOP EXPLANATION GROUPS (average contribution, cohort):
{group_table}

KEY FEATURE VALUES (cohort):
{feature_table}

{outcome_note}
{custom_instruction}"""


def _json_to_markdown(raw: str) -> str:
    """Parse a JSON narrative response into formatted markdown. Falls back to raw text."""
    # Strip markdown code fences if the model added them anyway
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    try:
        data = json.loads(text)
        lines: list[str] = []
        if summary := data.get("summary"):
            lines.append(summary)
        drivers = data.get("drivers", [])
        if drivers:
            lines.append("")
            for d in drivers:
                group = d.get("group", "")
                explanation = d.get("explanation", "")
                lines.append(f"- **{group}**: {explanation}" if group else f"- {explanation}")
        if rec := data.get("recommendation"):
            lines.append("")
            lines.append(rec)
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("JSON parse failed for group narrative (%s). Raw: %.500s", exc, raw)
        return raw


def _format_group_table(
    groups: list[dict[str, Any]],
    nc: dict[str, Any],
    n_groups: int,
) -> str:
    lines = ["Group | Avg contribution | Direction | Coverage"]
    lines.append("-" * 60)
    for g in groups[:n_groups]:
        direction = (
            nc["factor_positive_label"] if g["avg_shap"] > 0 else nc["factor_negative_label"]
        )
        lines.append(
            f"{g['feature_group']:<30} | {g['avg_shap']:+.4f} | {direction} | {g['coverage_pct']:.0f}%"
        )
    return "\n".join(lines)


def _format_feature_table(
    groups: list[dict[str, Any]],
    n_groups: int,
    n_per_group: int,
) -> str:
    lines = []
    for g in groups[:n_groups]:
        for feat in g.get("top_features", [])[:n_per_group]:
            sign = "+" if feat["avg_shap"] >= 0 else ""
            lines.append(
                f"  {feat['feature_name']}: avg SHAP {sign}{feat['avg_shap']:.4f} "
                f"(present in {feat['n_rows']} rows)"
            )
    return "\n".join(lines) if lines else "  (no feature detail available)"


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


def build_prompt(
    profile: dict[str, Any],
    groups: list[dict[str, Any]],
    filters: dict[str, Any],
    nc: dict[str, Any],
    outcome_rate: Optional[float] = None,
    custom_instruction: str = "",
    narrative_groups_in_prompt: int = 6,
    narrative_features_per_group: int = 2,
) -> str:
    score = profile.get("score_stats", {})
    score_full = profile.get("score_stats_full", {})
    filter_desc = _describe_filters(filters) or "none (full scored population)"
    outcome_label = nc.get("outcome_label", "observed outcome rate")
    outcome_note = (
        f"{outcome_label.upper()}: {outcome_rate:.1%}" if outcome_rate is not None else ""
    )

    # Future: replace with DataRobot Prompt Management API for versioned templates.
    template = nc.get("custom_user_template") or _USER_TEMPLATE
    return template.format(
        n_rows=profile["n_rows"],
        pct_of_total=profile.get("pct_of_total", 0),
        entity_label_plural=nc["entity_label_plural"],
        high_score_label=nc["high_score_label"],
        filter_description=filter_desc,
        mean_score=score.get("mean") or 0,
        median_score=score.get("median") or 0,
        mean_score_full=score_full.get("mean") or 0,
        median_score_full=score_full.get("median") or 0,
        group_table=_format_group_table(groups, nc, narrative_groups_in_prompt),
        feature_table=_format_feature_table(groups, narrative_groups_in_prompt, narrative_features_per_group),
        outcome_note=outcome_note,
        custom_instruction=f"Additional instruction: {custom_instruction}" if custom_instruction else "",
    )


# ---------------------------------------------------------------------------
# Row-level narrative (individual claim / entity)
# ---------------------------------------------------------------------------

def build_row_system_prompt(nc: dict[str, Any]) -> str:
    return (
        f"You are a senior {nc['entity_label']} reviewer. "
        f"Explain concisely why a specific {nc['entity_label']} received its risk score "
        f"so a junior analyst understands what to look for and what action to take. "
        f"Never use the terms 'SHAP' or 'feature importance'. "
        f"Refer to factors as directly observed characteristics of the {nc['entity_label']}. "
        f"You MUST respond with a valid JSON object only — no prose, no markdown fences, no extra text."
    )


def build_row_prompt(
    row_id: str,
    prediction: float,
    waterfall: list[dict[str, Any]],
    nc: dict[str, Any],
    custom_instruction: str = "",
) -> str:
    score_pct = f"{prediction * 100:.1f}%"

    groups_seen: list[str] = []
    for entry in waterfall:
        g = entry.get("feature_group") or entry["feature_name"]
        if g not in groups_seen:
            groups_seen.append(g)

    driver_schema = ", ".join(
        f'{{"group": "{g}", "explanation": "<...>"}}'
        for g in groups_seen
    )

    lines = [
        "Return a JSON object with these exact keys. No other text.",
        "",
        '{',
        f'  "summary": "<one sentence: risk level and {score_pct} score, main driver>",',
        f'  "drivers": [{driver_schema}],',
        '  "recommendations": "<one or two concrete actions for the reviewer>"',
        '}',
        "",
        "DATA:",
        "",
        f"{nc['entity_label'].title()} ID: {row_id}",
        f"Risk score (probability of {nc['high_score_label']}): {score_pct}",
        "",
        "Top factors (ordered by impact):",
    ]
    for entry in waterfall:
        direction = (
            nc["factor_positive_label"] if (entry.get("shap_strength") or 0) > 0
            else nc["factor_negative_label"]
        )
        val = entry.get("actual_value") or "?"
        strength = entry.get("shap_strength") or 0
        lines.append(
            f"  - {entry['feature_name']} = {val}  →  {direction} (impact {strength:+.4f})"
        )

    if custom_instruction:
        lines += ["", f"Additional instruction: {custom_instruction}"]
    return "\n".join(lines)


def _json_to_markdown_row(raw: str) -> str:
    """Parse a JSON row narrative response into formatted markdown. Falls back to raw text."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    try:
        data = json.loads(text)
        lines: list[str] = []
        if summary := data.get("summary"):
            lines.append(summary)
        drivers = data.get("drivers", [])
        if drivers:
            lines.append("")
            for d in drivers:
                group = d.get("group", "")
                explanation = d.get("explanation", "")
                lines.append(f"- **{group}**: {explanation}" if group else f"- {explanation}")
        if rec := data.get("recommendations") or data.get("recommendation"):
            lines.append("")
            lines.append(rec)
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("JSON parse failed for row narrative (%s). Raw: %.500s", exc, raw)
        return raw


def generate_row_narrative(
    row_data: dict[str, Any],
    nc: dict[str, Any],
    settings: Any,
    provider: Optional[str] = None,
    custom_instruction: str = "",
    narrative_max_tokens: int = 500,
) -> str:
    system = build_row_system_prompt(nc)
    user_msg = build_row_prompt(
        row_data["row_id"],
        row_data["prediction"] or 0.0,
        row_data.get("waterfall", []),
        nc,
        custom_instruction=custom_instruction,
    )
    raw = call_llm(
        messages=[{"role": "user", "content": user_msg}],
        system=system,
        settings=settings,
        provider=provider,
        max_tokens=narrative_max_tokens,
    )
    return _json_to_markdown_row(raw)


# ---------------------------------------------------------------------------
# Generation entry point (cohort / group level)
# ---------------------------------------------------------------------------

def generate_narrative(
    profile: dict[str, Any],
    groups: list[dict[str, Any]],
    filters: dict[str, Any],
    nc: dict[str, Any],
    settings: Any,
    outcome_rate: Optional[float] = None,
    custom_instruction: str = "",
    provider: Optional[str] = None,
    cohort_warning_min_rows: int = 30,
    narrative_max_tokens: int = 700,
    narrative_groups_in_prompt: int = 6,
    narrative_features_per_group: int = 2,
) -> str:
    warning = ""
    if profile["n_rows"] < cohort_warning_min_rows:
        warning = (
            f"[Note: cohort has only {profile['n_rows']} rows — "
            "group-level averages may not be stable.]\n\n"
        )

    system = build_system_prompt(nc)
    user_msg = build_prompt(
        profile, groups, filters, nc,
        outcome_rate=outcome_rate,
        custom_instruction=custom_instruction,
        narrative_groups_in_prompt=narrative_groups_in_prompt,
        narrative_features_per_group=narrative_features_per_group,
    )

    raw = call_llm(
        messages=[{"role": "user", "content": user_msg}],
        system=system,
        settings=settings,
        provider=provider,
        max_tokens=narrative_max_tokens,
    )
    return warning + _json_to_markdown(raw)
