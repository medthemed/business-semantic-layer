"""Human-readable field-level diffs between two rule sets.

``impact.analyze_impact`` answers *which rules changed* and *which services
to refactor*. This module answers the reviewer question that comes next:
*what exactly moved inside each rule?*

Output is a plain-text diff suitable for a terminal or a PR comment.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dsl import Condition, Rule, RuleSet
from .impact import ChangeKind, ImpactResult, RuleChange, analyze_impact


def _format_condition(cond: Condition) -> str:
    if cond.value is None and cond.op in ("exists", "not_exists", "is_true", "is_false"):
        return f"{cond.field} {cond.op}"
    return f"{cond.field} {cond.op} {cond.value!r}"


def _condition_lines(conditions: tuple[Condition, ...], prefix: str) -> list[str]:
    if not conditions:
        return [f"{prefix}(none)"]
    return [f"{prefix}{_format_condition(c)}" for c in conditions]


def _list_line(values: tuple[str, ...] | list[str]) -> str:
    if not values:
        return "(none)"
    return ", ".join(values)


@dataclass
class FieldDelta:
    """One field that differs between old and new rule content."""

    field: str
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]

    def format(self, indent: str = "  ") -> str:
        lines = [f"{indent}{self.field}"]
        for old in self.old_lines:
            lines.append(f"{indent}  - {old}")
        for new in self.new_lines:
            lines.append(f"{indent}  + {new}")
        return "\n".join(lines)


def diff_rule(old: Rule | None, new: Rule | None) -> list[FieldDelta]:
    """Field-level deltas for one rule (either side may be None)."""
    if old is None and new is None:
        return []
    if old is None and new is not None:
        return [
            FieldDelta("statement", (), (new.statement or "(empty)",)),
            FieldDelta("when", (), tuple(_format_condition(c) for c in new.when)),
            FieldDelta("then", (), tuple(_format_condition(c) for c in new.then)),
            FieldDelta("entities", (), (list(new.entities),)),
            FieldDelta("affected_services", (), (list(new.affected_services),)),
        ]
    if old is not None and new is None:
        return [
            FieldDelta("statement", (old.statement or "(empty)",), ()),
            FieldDelta("when", tuple(_format_condition(c) for c in old.when), ()),
            FieldDelta("then", tuple(_format_condition(c) for c in old.then), ()),
            FieldDelta("entities", (list(old.entities),), ()),
            FieldDelta("affected_services", (list(old.affected_services),), ()),
        ]

    assert old is not None and new is not None
    deltas: list[FieldDelta] = []

    if old.statement != new.statement:
        deltas.append(
            FieldDelta(
                "statement",
                (old.statement or "(empty)",),
                (new.statement or "(empty)",),
            )
        )

    old_when = [_format_condition(c) for c in old.when]
    new_when = [_format_condition(c) for c in new.when]
    if old_when != new_when:
        deltas.append(FieldDelta("when", tuple(old_when), tuple(new_when)))

    old_then = [_format_condition(c) for c in old.then]
    new_then = [_format_condition(c) for c in new.then]
    if old_then != new_then:
        deltas.append(FieldDelta("then", tuple(old_then), tuple(new_then)))

    if old.entities != new.entities:
        deltas.append(
            FieldDelta(
                "entities",
                (_list_line(old.entities),),
                (_list_line(new.entities),),
            )
        )

    if old.affected_services != new.affected_services:
        old_set = set(old.affected_services)
        new_set = set(new.affected_services)
        removed = tuple(s for s in old.affected_services if s not in new_set)
        added = tuple(s for s in new.affected_services if s not in old_set)
        if removed and added:
            old_lines = (_list_line(old.affected_services),)
            new_lines = (_list_line(new.affected_services),)
        elif removed:
            old_lines, new_lines = removed, ()
        else:
            old_lines, new_lines = (), added
        deltas.append(FieldDelta("affected_services", old_lines, new_lines))

    if old.enabled != new.enabled:
        deltas.append(
            FieldDelta("enabled", (str(old.enabled).lower(),), (str(new.enabled).lower(),))
        )

    if old.version != new.version:
        deltas.append(FieldDelta("version", (str(old.version),), (str(new.version),)))

    return deltas


def format_rule_diff(change: RuleChange) -> str:
    """Render one :class:`RuleChange` as a human-readable block."""
    if change.kind == ChangeKind.UNCHANGED:
        return f"  {change.rule_id} (unchanged)"

    if change.kind == ChangeKind.ADDED:
        assert change.new is not None
        lines = [f"+ {change.rule_id} v{change.new.version}"]
        lines.append(f"  statement: {change.new.statement}")
        if change.new.when:
            lines.extend(_condition_lines(change.new.when, "  when: "))
        if change.new.then:
            lines.extend(_condition_lines(change.new.then, "  then: "))
        lines.append(f"  entities: {_list_line(change.new.entities)}")
        lines.append(f"  services: {_list_line(change.new.affected_services)}")
        return "\n".join(lines)

    if change.kind == ChangeKind.REMOVED:
        assert change.old is not None
        lines = [f"- {change.rule_id} v{change.old.version}"]
        lines.append(f"  statement: {change.old.statement}")
        lines.append(f"  entities: {_list_line(change.old.entities)}")
        lines.append(f"  services: {_list_line(change.old.affected_services)}")
        return "\n".join(lines)

    # CHANGED
    old_v = change.old.version if change.old else "?"
    new_v = change.new.version if change.new else "?"
    fields = ", ".join(change.fields_changed) or "content"
    lines = [f"~ {change.rule_id} v{old_v} -> v{new_v} ({fields})"]
    for delta in diff_rule(change.old, change.new):
        lines.append(delta.format())
    return "\n".join(lines)


def format_rule_set_diff(
    old: RuleSet,
    new: RuleSet,
    *,
    impact: ImpactResult | None = None,
    show_unchanged: bool = False,
) -> str:
    """Render a full human-readable diff of two rule sets."""
    result = impact if impact is not None else analyze_impact(old, new)
    lines: list[str] = []
    if old.name == new.name:
        header = f"RuleSet {old.name}: {old.version} -> {new.version}"
    else:
        header = f"RuleSet {old.name} v{old.version} -> {new.name} v{new.version}"
    lines.append(header)
    lines.append("")

    actionable = [c for c in result.changes if c.requires_refactor]
    unchanged = [c for c in result.changes if not c.requires_refactor]

    if not actionable:
        lines.append("No rule changes.")
        if show_unchanged:
            for change in unchanged:
                lines.append(format_rule_diff(change))
        return "\n".join(lines) + "\n"

    for change in actionable:
        lines.append(format_rule_diff(change))
        lines.append("")

    if show_unchanged and unchanged:
        lines.append(f"Unchanged ({len(unchanged)}):")
        for change in unchanged:
            lines.append(format_rule_diff(change))
        lines.append("")

    services = result.affected_services()
    lines.append(f"Services to refactor ({len(services)}):")
    for service in services:
        lines.append(f"  - {service}")
    lines.append("")
    return "\n".join(lines)
