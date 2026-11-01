from app.feature_config import load_feature_config


def get_purpose(purpose: str) -> dict[str, object]:
    """Return validated configuration for one draft purpose."""
    purposes = load_feature_config("draft_purposes.json")
    settings = purposes.get(purpose)
    if not isinstance(settings, dict):
        raise ValueError("Unknown draft purpose.")
    return settings


def purpose_allowed(purpose: str, role: str, result_type: str | None = None) -> bool:
    """Return whether a role and optional result type can use a purpose."""
    settings = get_purpose(purpose)
    if role not in settings["allowed_roles"]:
        return False
    return result_type is None or result_type in settings["allowed_result_types"]
