"""Filter requested fields and enforce aggregate group-size thresholds."""

from __future__ import annotations

from collections.abc import Iterable

from app.policy.policy import AccessPolicy


def filter_fields(
    policy: AccessPolicy,
    role: str,
    dataset: str,
    fields: Iterable[str],
) -> list[str]:
    """Keep only requested fields explicitly allowed for this role."""
    return list(
        dict.fromkeys(
            field
            for field in fields
            if policy.can_access_field(role, dataset, field)
        )
    )


def group_size_allowed(
    policy: AccessPolicy,
    role: str,
    dataset: str,
    group_size: int,
) -> bool:
    """Check that an accessible aggregate group meets its configured minimum."""
    if (
        isinstance(group_size, bool)
        or not isinstance(group_size, int)
        or group_size < 0
    ):
        raise ValueError("group_size must be a non-negative integer.")
    minimum = policy.minimum_group_size(role, dataset)
    return minimum is not None and group_size >= minimum
