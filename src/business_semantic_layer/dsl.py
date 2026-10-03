"""Rule model and a tiny YAML-subset / JSON loader.

YAML support is intentionally a *subset* implemented on the stdlib so the
package has zero runtime dependencies. Supported constructs:

- key: value scalars (str, int, float, bool, null)
- nested mappings via indentation
- block lists with ``- item``
- inline lists ``[a, b, c]`` and inline maps ``{k: v}``
- ``# comments`` and blank lines

If you need full YAML (anchors, multi-line strings, …), convert to JSON
first or extend this parser.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .errors import DslError


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """A single when/then clause.

    ``field`` is a dotted path into a domain entity, ``op`` is a comparison
    operator, ``value`` is the compared literal.
    """

    field: str
    op: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Condition":
        return Condition(field=data["field"], op=data["op"], value=data.get("value"))

    def key(self) -> tuple:
        """Stable identity used when diffing rules."""
        return (self.field, self.op, json.dumps(self.value, sort_keys=True, default=str))


@dataclass(frozen=True)
class Rule:
    """A versioned business rule.

    Attributes
    ----------
    id:               Stable slug, e.g. ``checkout.min-order``.
    version:          Monotonic integer. Bump when the rule *meaning* changes.
    statement:        Human-readable English the PM signed off on.
    when:             Conditions that must all hold for the rule to apply.
    then:             Conditions (effects / assertions) enforced when it applies.
    entities:         Domain entities this rule reads or writes.
    affected_services: Services whose implementation must track this rule.
    enabled:          Soft kill-switch; disabled rules are still diffed.
    metadata:         Free-form extra keys (owner, jira, …).
    """

    id: str
    version: int
    statement: str
    when: tuple[Condition, ...] = ()
    then: tuple[Condition, ...] = ()
    entities: tuple[str, ...] = ()
    affected_services: tuple[str, ...] = ()
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "version": self.version,
            "statement": self.statement,
            "when": [c.to_dict() for c in self.when],
            "then": [c.to_dict() for c in self.then],
            "entities": list(self.entities),
            "affected_services": list(self.affected_services),
            "enabled": self.enabled,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Rule":
        known = {
            "id",
            "version",
            "statement",
            "when",
            "then",
            "entities",
            "affected_services",
            "enabled",
            "metadata",
        }
        metadata = dict(data.get("metadata") or {})
        for key, value in data.items():
            if key not in known:
                metadata[key] = value
        return Rule(
            id=data["id"],
            version=int(data["version"]),
            statement=data.get("statement", ""),
            when=tuple(Condition.from_dict(c) for c in data.get("when") or ()),
            then=tuple(Condition.from_dict(c) for c in data.get("then") or ()),
            entities=tuple(data.get("entities") or ()),
            affected_services=tuple(data.get("affected_services") or ()),
            enabled=bool(data.get("enabled", True)),
            metadata=metadata,
        )

    def content_key(self) -> tuple:
        """Identity of the *meaning* of the rule (excludes version/metadata)."""
        return (
            self.statement,
            tuple(c.key() for c in self.when),
            tuple(c.key() for c in self.then),
            tuple(self.entities),
            tuple(self.affected_services),
            self.enabled,
        )


@dataclass(frozen=True)
class RuleSet:
    """A named, versioned collection of rules."""

    name: str
    version: str
    rules: tuple[Rule, ...]
    description: str = ""

    def by_id(self) -> dict[str, Rule]:
        return {r.id: r for r in self.rules}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "rules": [r.to_dict() for r in self.rules],
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "RuleSet":
        return RuleSet(
            name=data["name"],
            version=str(data.get("version", "0")),
            description=data.get("description", ""),
            rules=tuple(Rule.from_dict(r) for r in data.get("rules") or ()),
        )


# ---------------------------------------------------------------------------
# Tiny YAML subset parser
# ---------------------------------------------------------------------------


class YamlError(DslError):
    """Raised when the YAML subset parser hits something it cannot handle.

    Kept as a distinct name for backward compatibility; it is a
    :class:`~business_semantic_layer.errors.DslError`.
    """


def _strip_comment(line: str) -> str:
    """Remove a trailing ``# comment`` that is not inside quotes."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1] in " \t":
                return line[:i].rstrip()
    return line.rstrip()


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "" or text == "~" or text.lower() in ("null", "none"):
        return None
    if text.lower() in ("true", "yes", "on"):
        return True
    if text.lower() in ("false", "no", "off"):
        return False
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        return _parse_inline_list(text)
    if text.startswith("{") and text.endswith("}"):
        return _parse_inline_map(text)
    # numbers
    try:
        if any(c in text for c in ".eE") and not text.startswith("0x"):
            return float(text)
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` ignoring separators inside quotes/brackets."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0 and not in_single and not in_double:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in (part.strip() for part in parts) if p != ""]


def _parse_inline_list(text: str) -> list[Any]:
    inner = text.strip()[1:-1].strip()
    if not inner:
        return []
    return [_parse_scalar(p) for p in _split_top_level(inner)]


def _parse_inline_map(text: str) -> dict[str, Any]:
    inner = text.strip()[1:-1].strip()
    result: dict[str, Any] = {}
    if not inner:
        return result
    for part in _split_top_level(inner):
        if ":" not in part:
            raise YamlError(f"Inline map entry missing ':': {part!r}")
        key, _, value = part.partition(":")
        result[key.strip().strip("'\"")] = _parse_scalar(value)
    return result


def _split_key_value(line: str) -> tuple[str, str] | None:
    """Return (key, rest) for ``key: value`` or ``key:``; None if not a mapping line."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            # end of key must be at i, and either EOL or a space follows
            if i + 1 >= len(line) or line[i + 1] in " \t":
                key = line[:i].strip()
                if not key:
                    return None
                return key.strip("'\""), line[i + 1 :].strip()
    return None


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    """Parse a block starting at ``lines[index]`` with the given indent.

    Returns (value, next_index).
    """
    # Detect list vs mapping by the first meaningful line.
    while index < len(lines):
        stripped = _strip_comment(lines[index])
        if stripped.strip() == "":
            index += 1
            continue
        break
    if index >= len(lines):
        return None, index

    current = _strip_comment(lines[index])
    cur_indent = len(current) - len(current.lstrip(" "))
    if cur_indent < indent:
        return None, index

    is_list = current.lstrip(" ").startswith("- ")
    if is_list or current.lstrip(" ") == "-":
        items: list[Any] = []
        while index < len(lines):
            raw = _strip_comment(lines[index])
            if raw.strip() == "":
                index += 1
                continue
            this_indent = len(raw) - len(raw.lstrip(" "))
            if this_indent < cur_indent:
                break
            body = raw.lstrip(" ")
            if not body.startswith("-"):
                # still part of previous item? treat as continuation only if deeper
                if this_indent > cur_indent:
                    # merge into last item if it's a dict
                    if items and isinstance(items[-1], dict):
                        sub, index = _parse_block(lines, index, this_indent)
                        if isinstance(sub, dict):
                            items[-1].update(sub)
                        else:
                            items.append(sub)
                        continue
                break
            rest = body[1:].strip()
            if rest == "":
                sub, index = _parse_block(lines, index + 1, this_indent + 1)
                items.append(sub)
                continue
            kv = _split_key_value(rest)
            if kv is not None:
                key, value_text = kv
                item: dict[str, Any] = {}
                if value_text == "":
                    sub, index = _parse_block(lines, index + 1, this_indent + 2)
                    item[key] = sub
                else:
                    item[key] = _parse_scalar(value_text)
                    index += 1
                # consume following more-indented keys belonging to this list item
                while index < len(lines):
                    peek = _strip_comment(lines[index])
                    if peek.strip() == "":
                        index += 1
                        continue
                    peek_indent = len(peek) - len(peek.lstrip(" "))
                    if peek_indent <= this_indent:
                        break
                    if peek.lstrip(" ").startswith("- "):
                        break
                    kv2 = _split_key_value(peek.lstrip(" "))
                    if kv2 is None:
                        break
                    k2, v2 = kv2
                    if v2 == "":
                        sub, index = _parse_block(lines, index + 1, peek_indent + 1)
                        item[k2] = sub
                    else:
                        item[k2] = _parse_scalar(v2)
                        index += 1
                items.append(item)
            else:
                items.append(_parse_scalar(rest))
                index += 1
        return items, index

    # Mapping
    mapping: dict[str, Any] = {}
    while index < len(lines):
        raw = _strip_comment(lines[index])
        if raw.strip() == "":
            index += 1
            continue
        this_indent = len(raw) - len(raw.lstrip(" "))
        if this_indent < cur_indent:
            break
        if this_indent > cur_indent:
            # orphaned indented block — parse and attach if we have a pending key
            raise YamlError(f"Unexpected indent at line {index + 1}: {raw!r}")
        body = raw.lstrip(" ")
        if body.startswith("- "):
            break
        kv = _split_key_value(body)
        if kv is None:
            raise YamlError(f"Expected 'key: value' at line {index + 1}: {raw!r}")
        key, value_text = kv
        if value_text == "" or value_text == "|":
            sub, index = _parse_block(lines, index + 1, this_indent + 1)
            mapping[key] = sub
        else:
            mapping[key] = _parse_scalar(value_text)
            index += 1
    return mapping, index


def parse_yaml_subset(text: str) -> Any:
    """Parse a YAML-subset document into Python objects."""
    lines = text.splitlines()
    value, index = _parse_block(lines, 0, 0)
    # trailing content check
    while index < len(lines):
        if _strip_comment(lines[index]).strip() != "":
            raise YamlError(f"Unexpected trailing content at line {index + 1}")
        index += 1
    return value


def parse_document(text: str, *, fmt: str | None = None) -> Any:
    """Parse JSON or YAML-subset text into Python objects.

    ``fmt`` may be ``"json"``, ``"yaml"``, or ``None`` (auto-detect by
    leading ``{`` / ``[``).
    """
    stripped = text.lstrip("\ufeff \t\r\n")
    if fmt is None:
        fmt = "json" if stripped.startswith(("{", "[")) else "yaml"
    if fmt == "json":
        return json.loads(text)
    if fmt == "yaml":
        return parse_yaml_subset(text)
    raise ValueError(f"Unknown format: {fmt!r}")


def dump_document(data: Any, *, fmt: str = "json", indent: int = 2) -> str:
    """Serialize ``data`` as JSON or a simple YAML-subset document."""
    if fmt == "json":
        return json.dumps(data, indent=indent, sort_keys=False) + "\n"
    if fmt == "yaml":
        return _dump_yaml(data, indent=0) + "\n"
    raise ValueError(f"Unknown format: {fmt!r}")


def _dump_yaml(data: Any, indent: int) -> str:
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return pad + "{}"
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{key}:")
                lines.append(_dump_yaml(value, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_dump_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return pad + "[]"
        lines = []
        for item in data:
            if isinstance(item, dict) and item:
                first = True
                sub = _dump_yaml(item, indent + 1)
                sub_lines = sub.splitlines()
                for i, line in enumerate(sub_lines):
                    if first and i == 0:
                        lines.append(f"{pad}- {line.strip()}")
                        first = False
                    else:
                        lines.append(line)
            else:
                lines.append(f"{pad}- {_dump_scalar(item)}")
        return "\n".join(lines)
    return pad + _dump_scalar(data)


def _dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value == "" or value != value.strip() or any(c in value for c in ":#{}[]"):
            return json.dumps(value)
        return value
    return json.dumps(value)


def load_ruleset_document(text: str, *, fmt: str | None = None) -> RuleSet:
    """Parse text into a :class:`RuleSet` (no schema validation)."""
    data = parse_document(text, fmt=fmt)
    if not isinstance(data, Mapping):
        raise DslError(
            f"Rule document must be a mapping, got {type(data).__name__}"
        )
    return RuleSet.from_dict(data)
