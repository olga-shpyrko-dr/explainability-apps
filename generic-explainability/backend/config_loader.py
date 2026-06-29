"""
Loads and validates the three JSON configuration files:
  feature_group_mapping.json — feature → group assignments
  profile_config.json        — sidebar filter and cohort profile attributes
  narrative_config.json      — LLM domain vocabulary and prompt settings
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent

_REQUIRED_NARRATIVE_FIELDS = [
    "domain_description",
    "entity_label",
    "entity_label_plural",
    "target_audience",
    "high_score_label",
    "low_score_label",
    "factor_positive_label",
    "factor_negative_label",
]

_VALID_FILTER_TYPES = {"range", "multiselect", "toggle"}


def load_group_map() -> dict[str, str]:
    """Return {feature_name: group_label} from feature_group_mapping.json."""
    path = _HERE / "feature_group_mapping.json"
    with open(path) as f:
        raw = json.load(f)
    mapping: dict[str, str] = {}
    for group, features in raw["groups"].items():
        for feat in features:
            if feat not in mapping:  # first-match wins on duplicate
                mapping[feat] = group
    return mapping


def load_profile_config() -> dict[str, Any]:
    """
    Load and validate profile_config.json.

    Returns the parsed config dict. Raises ValueError on invalid content.
    Downgrades toggle attributes with >2 distinct values to multiselect at
    runtime (handled separately when column metadata is available).
    """
    path = _HERE / "profile_config.json"
    with open(path) as f:
        cfg = json.load(f)

    for attr in cfg.get("profile_attributes", []):
        if "column" not in attr or "display_name" not in attr:
            raise ValueError(
                f"profile_config.json: each attribute needs 'column' and 'display_name'. Got: {attr}"
            )
        ft = attr.get("filter_type", "range")
        if ft not in _VALID_FILTER_TYPES:
            raise ValueError(
                f"profile_config.json: invalid filter_type '{ft}' for column '{attr['column']}'. "
                f"Must be one of {_VALID_FILTER_TYPES}."
            )
        attr.setdefault("show_in_profile", True)

    cfg.setdefault("score_filter", {"show": True, "display_name": "Prediction Score"})
    cfg.setdefault(
        "top_explanation_filter",
        {"show": True, "display_name": "Top Explanation Feature", "explanation_slot": 1},
    )
    return cfg


def load_narrative_config() -> dict[str, Any]:
    """
    Load and validate narrative_config.json.

    Returns the parsed config dict. Raises ValueError if required fields are missing.
    """
    path = _HERE / "narrative_config.json"
    with open(path) as f:
        cfg = json.load(f)

    missing = [f for f in _REQUIRED_NARRATIVE_FIELDS if not cfg.get(f)]
    if missing:
        raise ValueError(
            f"narrative_config.json: missing or empty required fields: {missing}"
        )
    return cfg


def validate_columns_against_profile(
    df_columns: list[str],
    profile_cfg: dict[str, Any],
) -> None:
    """
    Warn if any profile_attributes column is absent from the dataset.
    Does not raise — missing columns are simply skipped at filter render time.
    """
    dataset_cols = set(df_columns)
    for attr in profile_cfg.get("profile_attributes", []):
        col = attr["column"]
        if col not in dataset_cols:
            logger.warning(
                "profile_config.json: column '%s' (display_name='%s') not found in dataset — "
                "it will be hidden in the sidebar.",
                col,
                attr.get("display_name", col),
            )
