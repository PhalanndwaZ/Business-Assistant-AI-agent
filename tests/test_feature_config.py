"""Tests for Step 1 feature configuration loading."""

from app.feature_config import validate_feature_configs


def test_feature_configs_load_and_validate() -> None:
    """All four feature configs satisfy the planned shared validation."""
    configs = validate_feature_configs()

    assert set(configs) == {
        "segments.json",
        "portfolio.json",
        "draft_purposes.json",
        "uploads.json",
    }
