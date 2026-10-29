"""Load role permissions and answer access-policy questions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

DEFAULT_POLICY_PATH = PROJECT_ROOT / "data" / "policy" / "access_policy.json"


class PolicyError(ValueError):
    """Raised when the access policy cannot be loaded or validated."""


class AccessPolicy:
    """Read the policy once and expose fail-closed permission checks."""

    def __init__(self, path: Path = DEFAULT_POLICY_PATH) -> None:
        """Load and validate policy rules from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PolicyError(f"Could not load access policy from {path}: {exc}") from exc
        self._validate(data)
        self._data: dict[str, Any] = data
        self._roles: dict[str, Any] = data["roles"]
        self._levels: dict[str, int] = data["classification_levels"]

    @staticmethod
    def _validate(data: Any) -> None:
        """Reject malformed policies instead of silently granting access."""
        if not isinstance(data, dict):
            raise PolicyError("Access policy must be a JSON object.")
        levels = data.get("classification_levels")
        roles = data.get("roles")
        field_classifications = data.get("field_classifications")
        if (
            not isinstance(levels, dict)
            or set(levels) != {"public", "internal", "confidential", "restricted"}
            or not isinstance(roles, dict)
            or not roles
            or not isinstance(field_classifications, dict)
        ):
            raise PolicyError("Access policy is missing required sections.")
        if any(
            isinstance(level, bool) or not isinstance(level, int)
            for level in levels.values()
        ) or len(set(levels.values())) != len(levels):
            raise PolicyError("Classification levels must have unique integer ranks.")

        for dataset_name, fields in field_classifications.items():
            if not isinstance(dataset_name, str) or not isinstance(fields, dict):
                raise PolicyError("Field classifications must map datasets to fields.")
            if any(
                not isinstance(field, str)
                or not isinstance(classification, str)
                or classification not in levels
                for field, classification in fields.items()
            ):
                raise PolicyError("A field has an invalid classification.")

        for role_name, role in roles.items():
            if not isinstance(role_name, str) or not isinstance(role, dict):
                raise PolicyError("Each role must be a named object.")
            permissions = role.get("permissions")
            maxima = role.get("max_classification")
            datasets = role.get("datasets")
            analyses = role.get("analyses")
            documents = role.get("documents")
            if (
                not isinstance(permissions, list)
                or not all(isinstance(item, str) for item in permissions)
                or len(permissions) != len(set(permissions))
                or not isinstance(maxima, dict)
                or any(
                    not isinstance(level, str) or level not in levels
                    for level in maxima.values()
                )
                or not isinstance(datasets, dict)
                or not isinstance(analyses, list)
                or not all(isinstance(item, str) for item in analyses)
                or not isinstance(documents, dict)
            ):
                raise PolicyError(f"Role {role_name!r} has invalid policy fields.")
            document_departments = documents.get("departments")
            if (
                not isinstance(document_departments, list)
                or not all(isinstance(item, str) for item in document_departments)
                or not isinstance(documents.get("max_classification"), str)
                or documents.get("max_classification") not in levels
            ):
                raise PolicyError(f"Role {role_name!r} has invalid document rules.")
            for dataset_name, rule in datasets.items():
                fields = rule.get("fields") if isinstance(rule, dict) else None
                mode = rule.get("mode") if isinstance(rule, dict) else None
                if (
                    not isinstance(dataset_name, str)
                    or not isinstance(rule, dict)
                    or fields != "*"
                    and (
                        not isinstance(fields, list)
                        or not all(isinstance(field, str) for field in fields)
                    )
                    or mode not in {"read", "aggregate_only"}
                    or not isinstance(rule.get("department"), str)
                    or not isinstance(rule.get("classification"), str)
                    or rule.get("classification") not in levels
                ):
                    raise PolicyError(
                        f"Role {role_name!r} has invalid dataset rule "
                        f"{dataset_name!r}."
                    )
                if mode == "aggregate_only":
                    minimum = rule.get("min_group_size")
                    if (
                        isinstance(minimum, bool)
                        or not isinstance(minimum, int)
                        or minimum < 2
                    ):
                        raise PolicyError(
                            f"Aggregate dataset {dataset_name!r} needs a "
                            "minimum group size of at least two."
                        )

    def roles(self) -> tuple[str, ...]:
        """Return the configured role names."""
        return tuple(self._roles)

    def allows(self, role: str, permission: str) -> bool:
        """Check whether a configured role has one exact permission."""
        role_config = self._roles.get(role)
        return (
            isinstance(role_config, dict)
            and permission in role_config.get("permissions", [])
        )

    def can_use_tool(self, role: str, tool: str) -> bool:
        """Check whether a role may invoke the named tool."""
        return self.allows(role, f"tool:{tool}:use")

    def can_generate_report(self, role: str) -> bool:
        """Check report tool permission and at least one approved report type."""
        return self.can_use_tool(role, "generate_report") and any(
            self.allows(role, f"report:{report_type}:generate")
            for report_type in ("sales", "risk")
        )

    def can_access_dataset(self, role: str, dataset: str) -> bool:
        """Check role permission and dataset classification before access."""
        role_config = self._roles.get(role)
        if not isinstance(role_config, dict):
            return False
        rule = role_config.get("datasets", {}).get(dataset)
        if not isinstance(rule, dict):
            return False
        department = rule["department"]
        maximum = role_config.get("max_classification", {}).get(department)
        classification = rule["classification"]
        return (
            self.allows(role, f"dataset:{dataset}:read")
            and maximum in self._levels
            and self._levels[classification] <= self._levels[maximum]
        )

    def can_access_field(self, role: str, dataset: str, field: str) -> bool:
        """Allow only listed, explicitly classified fields within role limits."""
        if not self.can_access_dataset(role, dataset):
            return False
        role_config = self._roles[role]
        dataset_rule = role_config["datasets"][dataset]
        allowed_fields = dataset_rule["fields"]
        if allowed_fields != "*" and field not in allowed_fields:
            return False
        classification = self._data["field_classifications"].get(
            dataset, {}
        ).get(field)
        if not isinstance(classification, str) or classification not in self._levels:
            return False
        maximum = role_config["max_classification"].get(
            dataset_rule["department"]
        )
        return (
            maximum in self._levels
            and self._levels[classification] <= self._levels[maximum]
        )

    def can_run_analysis(self, role: str, analysis: str) -> bool:
        """Check both the analysis allow-list and its explicit permission."""
        role_config = self._roles.get(role)
        return (
            isinstance(role_config, dict)
            and analysis in role_config.get("analyses", [])
            and self.allows(role, f"analysis:{analysis}:run")
        )

    def can_access_document(
        self,
        role: str,
        department: str,
        classification: str,
    ) -> bool:
        """Check document department and classification before retrieval."""
        role_config = self._roles.get(role)
        if not isinstance(role_config, dict):
            return False
        document_rules = role_config["documents"]
        maximum = document_rules["max_classification"]
        if not isinstance(department, str) or not isinstance(classification, str):
            return False
        role_maximum = role_config["max_classification"].get(department)
        return (
            department in document_rules["departments"]
            and self.allows(role, f"documents:{department}:read")
            and classification in self._levels
            and self._levels[classification] <= self._levels[maximum]
            and role_maximum in self._levels
            and self._levels[classification] <= self._levels[role_maximum]
        )

    def dataset_mode(self, role: str, dataset: str) -> str | None:
        """Return the permitted access mode for a dataset, if accessible."""
        if not self.can_access_dataset(role, dataset):
            return None
        return self._roles[role]["datasets"][dataset]["mode"]

    def minimum_group_size(self, role: str, dataset: str) -> int | None:
        """Return the aggregate group's minimum size, or None if inaccessible."""
        mode = self.dataset_mode(role, dataset)
        if mode is None:
            return None
        rule = self._roles[role]["datasets"][dataset]
        return rule.get("min_group_size", 1)
