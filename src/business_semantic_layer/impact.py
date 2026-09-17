"""Change-impact analysis between two rule sets.

Given an *old* and a *new* :class:`~business_semantic_layer.dsl.RuleSet`,
produce:

- per-rule changes (added / removed / changed / unchanged)
- the set of services that must be refactored
- a small rule graph (entity -> rules, service -> rules)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .dsl import Rule, RuleSet
from .errors import ImpactError


class ChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class RuleChange:
    rule_id: str
    kind: ChangeKind
    old: Rule | None = None
    new: Rule | None = None
    fields_changed: tuple[str, ...] = ()

    @property
    def requires_refactor(self) -> bool:
        return self.kind in (ChangeKind.ADDED, ChangeKind.REMOVED, ChangeKind.CHANGED)

    def format_line(self) -> str:
        if self.kind == ChangeKind.ADDED:
            return f"+ {self.rule_id} v{self.new.version if self.new else '?'}"
        if self.kind == ChangeKind.REMOVED:
            return f"- {self.rule_id} v{self.old.version if self.old else '?'}"
        if self.kind == ChangeKind.CHANGED:
            fields = ", ".join(self.fields_changed) or "content"
            old_v = self.old.version if self.old else "?"
            new_v = self.new.version if self.new else "?"
            return f"~ {self.rule_id} v{old_v} -> v{new_v} ({fields})"
        return f"  {self.rule_id} (unchanged)"


def _diff_fields(old: Rule, new: Rule) -> list[str]:
    fields: list[str] = []
    if old.statement != new.statement:
        fields.append("statement")
    if [c.key() for c in old.when] != [c.key() for c in new.when]:
        fields.append("when")
    if [c.key() for c in old.then] != [c.key() for c in new.then]:
        fields.append("then")
    if old.entities != new.entities:
        fields.append("entities")
    if old.affected_services != new.affected_services:
        fields.append("affected_services")
    if old.enabled != new.enabled:
        fields.append("enabled")
    return fields


@dataclass
class ImpactResult:
    old_name: str
    new_name: str
    changes: list[RuleChange] = field(default_factory=list)

    @property
    def added(self) -> list[RuleChange]:
        return [c for c in self.changes if c.kind == ChangeKind.ADDED]

    @property
    def removed(self) -> list[RuleChange]:
        return [c for c in self.changes if c.kind == ChangeKind.REMOVED]

    @property
    def changed(self) -> list[RuleChange]:
        return [c for c in self.changes if c.kind == ChangeKind.CHANGED]

    @property
    def unchanged(self) -> list[RuleChange]:
        return [c for c in self.changes if c.kind == ChangeKind.UNCHANGED]

    @property
    def changed_ids(self) -> list[str]:
        return [c.rule_id for c in self.changes if c.requires_refactor]

    def affected_services(self) -> list[str]:
        """Union of services on every rule that was added, removed, or changed."""
        services: set[str] = set()
        for change in self.changes:
            if not change.requires_refactor:
                continue
            for rule in (change.old, change.new):
                if rule is not None:
                    services.update(rule.affected_services)
        return sorted(services)

    def affected_entities(self) -> list[str]:
        entities: set[str] = set()
        for change in self.changes:
            if not change.requires_refactor:
                continue
            for rule in (change.old, change.new):
                if rule is not None:
                    entities.update(rule.entities)
        return sorted(entities)

    def has_impact(self) -> bool:
        return any(c.requires_refactor for c in self.changes)

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable impact report (schema: ``impact-report``)."""
        return {
            "old_name": self.old_name,
            "new_name": self.new_name,
            "ok": True,
            "has_impact": self.has_impact(),
            "counts": {
                "added": len(self.added),
                "removed": len(self.removed),
                "changed": len(self.changed),
                "unchanged": len(self.unchanged),
            },
            "changes": [
                {
                    "rule_id": c.rule_id,
                    "kind": c.kind.value,
                    "requires_refactor": c.requires_refactor,
                    "fields_changed": list(c.fields_changed),
                    "old": c.old.to_dict() if c.old is not None else None,
                    "new": c.new.to_dict() if c.new is not None else None,
                }
                for c in self.changes
            ],
            "services": self.affected_services(),
            "entities": self.affected_entities(),
            "changed_ids": self.changed_ids,
        }

    def to_json(self, *, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, sort_keys=False) + "\n"

    def format_summary(self) -> str:
        lines = [
            f"Impact: {self.old_name} -> {self.new_name}",
            f"  added:     {len(self.added)}",
            f"  removed:   {len(self.removed)}",
            f"  changed:   {len(self.changed)}",
            f"  unchanged: {len(self.unchanged)}",
        ]
        if self.has_impact():
            lines.append("  rules to review:")
            for c in self.changes:
                if c.requires_refactor:
                    lines.append(f"    {c.format_line()}")
            services = self.affected_services()
            lines.append(f"  services to refactor ({len(services)}):")
            for s in services:
                lines.append(f"    - {s}")
        else:
            lines.append("  no behavioral impact")
        return "\n".join(lines)


def analyze_impact(old: RuleSet, new: RuleSet) -> ImpactResult:
    """Diff two rule sets and compute refactor impact.

    Raises :class:`~business_semantic_layer.errors.ImpactError` if either
    input is not a :class:`RuleSet` or contains duplicate rule ids.
    """
    for label, candidate in (("old", old), ("new", new)):
        if not isinstance(candidate, RuleSet):
            raise ImpactError(
                f"{label} must be a RuleSet, got {type(candidate).__name__}"
            )
        ids = [r.id for r in candidate.rules]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ImpactError(
                f"{label} rule set {candidate.name!r} has duplicate rule ids: {dupes}"
            )

    result = ImpactResult(old_name=old.name, new_name=new.name)
    old_map = old.by_id()
    new_map = new.by_id()

    for rule_id in sorted(set(old_map) | set(new_map)):
        o = old_map.get(rule_id)
        n = new_map.get(rule_id)
        if o is None and n is not None:
            result.changes.append(RuleChange(rule_id, ChangeKind.ADDED, old=None, new=n))
        elif o is not None and n is None:
            result.changes.append(RuleChange(rule_id, ChangeKind.REMOVED, old=o, new=None))
        else:
            assert o is not None and n is not None
            if o.content_key() == n.content_key() and o.version == n.version:
                result.changes.append(
                    RuleChange(rule_id, ChangeKind.UNCHANGED, old=o, new=n)
                )
            else:
                fields = _diff_fields(o, n)
                if o.version != n.version and "version" not in fields:
                    fields = ["version", *fields]
                result.changes.append(
                    RuleChange(
                        rule_id,
                        ChangeKind.CHANGED,
                        old=o,
                        new=n,
                        fields_changed=tuple(fields),
                    )
                )
    return result


@dataclass
class RuleGraph:
    """Bipartite-ish graph over entities, services, and rules."""

    entity_to_rules: dict[str, list[str]] = field(default_factory=dict)
    service_to_rules: dict[str, list[str]] = field(default_factory=dict)
    rule_to_entities: dict[str, list[str]] = field(default_factory=dict)
    rule_to_services: dict[str, list[str]] = field(default_factory=dict)

    def format(self) -> str:
        lines = ["Rule graph", "=========="]
        lines.append("entities:")
        for entity in sorted(self.entity_to_rules):
            rules = ", ".join(sorted(self.entity_to_rules[entity]))
            lines.append(f"  {entity}: {rules}")
        lines.append("services:")
        for service in sorted(self.service_to_rules):
            rules = ", ".join(sorted(self.service_to_rules[service]))
            lines.append(f"  {service}: {rules}")
        return "\n".join(lines)


def build_rule_graph(ruleset: RuleSet) -> RuleGraph:
    graph = RuleGraph()
    for rule in ruleset.rules:
        graph.rule_to_entities[rule.id] = list(rule.entities)
        graph.rule_to_services[rule.id] = list(rule.affected_services)
        for entity in rule.entities:
            graph.entity_to_rules.setdefault(entity, []).append(rule.id)
        for service in rule.affected_services:
            graph.service_to_rules.setdefault(service, []).append(rule.id)
    return graph


def services_impacted_by(ruleset: RuleSet, rule_ids: Iterable[str]) -> list[str]:
    """Services touched by a specific subset of rules (e.g. those that changed)."""
    wanted = set(rule_ids)
    services: set[str] = set()
    for rule in ruleset.rules:
        if rule.id in wanted:
            services.update(rule.affected_services)
    return sorted(services)
