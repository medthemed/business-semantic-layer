"""Structural schema validation for rule documents.

Validation is path-qualified: every error names the JSON-pointer-ish path
(``rules[2].when[0].op``) so PMs and engineers can fix the file quickly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .dsl import Condition, Rule, RuleSet

ALLOWED_OPS = frozenset(
    {
        "eq",
        "ne",
        "lt",
        "le",
        "gt",
        "ge",
        "in",
        "not_in",
        "contains",
        "exists",
        "not_exists",
        "is_true",
        "is_false",
    }
)

REQUIRED_RULE_FIELDS = ("id", "version", "statement")
REQUIRED_DOC_FIELDS = ("name", "version", "rules")


@dataclass
class SchemaError(Exception):
    """One or more schema violations, each with a path and message."""

    problems: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        if not self.problems:
            return "schema error"
        return "schema validation failed:\n" + "\n".join(f"  - {p}" for p in self.problems)

    def add(self, path: str, message: str) -> None:
        self.problems.append(f"{path}: {message}")

    @property
    def ok(self) -> bool:
        return not self.problems


def _is_slug(value: str) -> bool:
    if not value:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
    return all(ch in allowed for ch in value.lower()) and value == value.strip()


def _validate_condition(cond: Any, path: str, errors: SchemaError) -> None:
    if not isinstance(cond, Mapping):
        errors.add(path, f"expected a mapping, got {type(cond).__name__}")
        return
    field_name = cond.get("field")
    op = cond.get("op")
    if not isinstance(field_name, str) or not field_name.strip():
        errors.add(f"{path}.field", "must be a non-empty string")
    if op not in ALLOWED_OPS:
        errors.add(
            f"{path}.op",
            f"must be one of {sorted(ALLOWED_OPS)}, got {op!r}",
        )
    if op not in ("exists", "not_exists", "is_true", "is_false") and "value" not in cond:
        errors.add(f"{path}.value", f"is required for op {op!r}")


def _validate_str_list(value: Any, path: str, errors: SchemaError, *, slug: bool = False) -> None:
    if value is None:
        return
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        errors.add(path, f"must be a list of strings, got {type(value).__name__}")
        return
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.add(f"{path}[{i}]", "must be a non-empty string")
        elif slug and not _is_slug(item):
            errors.add(f"{path}[{i}]", f"{item!r} is not a valid slug (a-z0-9-_.)")


def _validate_rule(rule: Any, path: str, errors: SchemaError) -> None:
    if not isinstance(rule, Mapping):
        errors.add(path, f"expected a mapping, got {type(rule).__name__}")
        return

    for req in REQUIRED_RULE_FIELDS:
        if req not in rule:
            errors.add(f"{path}.{req}", "is required")

    rule_id = rule.get("id")
    if rule_id is not None and (not isinstance(rule_id, str) or not _is_slug(rule_id)):
        errors.add(f"{path}.id", f"must be a slug string, got {rule_id!r}")

    version = rule.get("version")
    if version is not None:
        if isinstance(version, bool) or not isinstance(version, int):
            errors.add(f"{path}.version", f"must be an integer, got {version!r}")
        elif version < 1:
            errors.add(f"{path}.version", "must be >= 1")

    statement = rule.get("statement")
    if statement is not None and (not isinstance(statement, str) or not statement.strip()):
        errors.add(f"{path}.statement", "must be a non-empty string")

    for key in ("when", "then"):
        clauses = rule.get(key)
        if clauses is None:
            continue
        if not isinstance(clauses, Sequence) or isinstance(clauses, (str, bytes)):
            errors.add(f"{path}.{key}", "must be a list of conditions")
            continue
        for i, cond in enumerate(clauses):
            _validate_condition(cond, f"{path}.{key}[{i}]", errors)

    _validate_str_list(rule.get("entities"), f"{path}.entities", errors, slug=True)
    _validate_str_list(
        rule.get("affected_services"), f"{path}.affected_services", errors, slug=True
    )

    enabled = rule.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        errors.add(f"{path}.enabled", f"must be a boolean, got {enabled!r}")


def validate_raw(data: Any) -> SchemaError:
    """Validate a raw parsed document. Returns a :class:`SchemaError` (possibly empty)."""
    errors = SchemaError()
    if not isinstance(data, Mapping):
        errors.add("$", f"document must be a mapping, got {type(data).__name__}")
        return errors

    for req in REQUIRED_DOC_FIELDS:
        if req not in data:
            errors.add(req, "is required")

    for key in ("name", "version"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            errors.add(key, f"must be a string, got {type(value).__name__}")

    rules = data.get("rules")
    if rules is None:
        errors.add("rules", "is required")
        return errors
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        errors.add("rules", f"must be a list, got {type(rules).__name__}")
        return errors

    seen_ids: dict[str, int] = {}
    for i, rule in enumerate(rules):
        _validate_rule(rule, f"rules[{i}]", errors)
        if isinstance(rule, Mapping):
            rid = rule.get("id")
            if isinstance(rid, str):
                if rid in seen_ids:
                    errors.add(
                        f"rules[{i}].id",
                        f"duplicate rule id {rid!r} (first seen at rules[{seen_ids[rid]}])",
                    )
                else:
                    seen_ids[rid] = i
    return errors


def validate_ruleset(ruleset: RuleSet) -> SchemaError:
    """Validate an already-constructed RuleSet (re-checks model invariants)."""
    return validate_raw(ruleset.to_dict())


def validate_document(data: Any) -> None:
    """Raise :class:`SchemaError` if ``data`` is not a valid rule document."""
    errors = validate_raw(data)
    if not errors.ok:
        raise errors
