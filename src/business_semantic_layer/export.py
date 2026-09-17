"""Exporters: markdown impact report and language constant stubs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .dsl import Condition, Rule, RuleSet
from .impact import ChangeKind, ImpactResult


def _slug_to_pascal(slug: str) -> str:
    parts = [p for p in slug.replace("-", "_").replace(".", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _slug_to_screaming(slug: str) -> str:
    parts = [p for p in slug.replace("-", "_").replace(".", "_").split("_") if p]
    return "_".join(p.upper() for p in parts)


def _python_literal(value) -> str:
    return repr(value)


def _ts_literal(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_ts_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{k}: {_ts_literal(v)}" for k, v in value.items())
        return "{" + pairs + "}"
    return f'"{value}"'


def _condition_dict_list(conditions: Iterable[Condition]) -> list[dict]:
    return [c.to_dict() for c in conditions]


def export_markdown_report(
    impact: ImpactResult,
    *,
    old: RuleSet | None = None,
    new: RuleSet | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Render a human-readable Markdown impact report."""
    ts = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Business rule impact report",
        "",
        f"- **From:** {impact.old_name}"
        + (f" v{old.version}" if old else ""),
        f"- **To:** {impact.new_name}"
        + (f" v{new.version}" if new else ""),
        f"- **Generated:** {ts}",
        "",
        "## Summary",
        "",
        "| Kind | Count |",
        "| --- | ---: |",
        f"| Added | {len(impact.added)} |",
        f"| Removed | {len(impact.removed)} |",
        f"| Changed | {len(impact.changed)} |",
        f"| Unchanged | {len(impact.unchanged)} |",
        "",
    ]

    if not impact.has_impact():
        lines.extend(["## Result", "", "No behavioral rule changes. Nothing to refactor.", ""])
        return "\n".join(lines)

    lines.extend(["## Rules to review", ""])
    for change in impact.changes:
        if not change.requires_refactor:
            continue
        lines.append(f"### `{change.rule_id}` — {change.kind.value}")
        lines.append("")
        if change.kind == ChangeKind.CHANGED:
            lines.append(f"- Version: {change.old.version if change.old else '?'} → "
                         f"{change.new.version if change.new else '?'}")
            if change.fields_changed:
                lines.append(f"- Fields changed: {', '.join(change.fields_changed)}")
            if change.new and change.new.statement:
                lines.append(f"- Statement: {change.new.statement}")
            if change.old and change.new and change.old.statement != change.new.statement:
                lines.append(f"- Old statement: {change.old.statement}")
        elif change.kind == ChangeKind.ADDED and change.new:
            lines.append(f"- Version: {change.new.version}")
            lines.append(f"- Statement: {change.new.statement}")
            lines.append(f"- Services: {', '.join(change.new.affected_services) or '(none)'}")
        elif change.kind == ChangeKind.REMOVED and change.old:
            lines.append(f"- Was version: {change.old.version}")
            lines.append(f"- Statement: {change.old.statement}")
            lines.append(f"- Services: {', '.join(change.old.affected_services) or '(none)'}")
        lines.append("")

    services = impact.affected_services()
    lines.extend(
        [
            "## Services to refactor",
            "",
            "| Service | Reason |",
            "| --- | --- |",
        ]
    )
    # Build a reason per service from the changes that mention it.
    for service in services:
        reasons = []
        for change in impact.changes:
            if not change.requires_refactor:
                continue
            for rule in (change.old, change.new):
                if rule and service in rule.affected_services:
                    reasons.append(f"{change.rule_id} ({change.kind.value})")
                    break
        # de-dupe preserving order
        seen: set[str] = set()
        uniq = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                uniq.append(r)
        lines.append(f"| `{service}` | {', '.join(uniq)} |")
    lines.append("")

    entities = impact.affected_entities()
    if entities:
        lines.extend(["## Domain entities touched", ""])
        for e in entities:
            lines.append(f"- `{e}`")
        lines.append("")

    lines.extend(
        [
            "## Checklist",
            "",
            "- [ ] Open PRs / tickets for every service listed above",
            "- [ ] Update unit and integration tests for changed rules",
            "- [ ] Confirm feature-flag / kill-switch behavior if `enabled` flipped",
            "- [ ] Re-run `bsl impact` against the merged rule set in CI",
            "",
        ]
    )
    return "\n".join(lines)


def export_python_constants(ruleset: RuleSet) -> str:
    """Emit a Python module of rule constants (importable stub)."""
    lines = [
        '"""Auto-generated rule constants. Do not edit by hand."""',
        "",
        f"RULESET_NAME = {ruleset.name!r}",
        f"RULESET_VERSION = {ruleset.version!r}",
        "",
        "RULES = {",
    ]
    for rule in ruleset.rules:
        lines.append(f"    {rule.id!r}: {{")
        lines.append(f"        'id': {rule.id!r},")
        lines.append(f"        'version': {rule.version},")
        lines.append(f"        'statement': {rule.statement!r},")
        lines.append(f"        'when': {_python_literal(_condition_dict_list(rule.when))},")
        lines.append(f"        'then': {_python_literal(_condition_dict_list(rule.then))},")
        lines.append(f"        'entities': {list(rule.entities)!r},")
        lines.append(
            f"        'affected_services': {list(rule.affected_services)!r},"
        )
        lines.append(f"        'enabled': {rule.enabled!r},")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    # Named aliases for nicer imports
    for rule in ruleset.rules:
        alias = _slug_to_screaming(rule.id)
        lines.append(f"{alias} = RULES[{rule.id!r}]")
    lines.append("")
    return "\n".join(lines)


def export_typescript_constants(ruleset: RuleSet) -> str:
    """Emit a TypeScript module of rule constants (importable stub)."""
    lines = [
        "/** Auto-generated rule constants. Do not edit by hand. */",
        "",
        f"export const RULESET_NAME = {_ts_literal(ruleset.name)};",
        f"export const RULESET_VERSION = {_ts_literal(ruleset.version)};",
        "",
        "export interface RuleCondition {",
        "  field: string;",
        "  op: string;",
        "  value?: unknown;",
        "}",
        "",
        "export interface BusinessRule {",
        "  id: string;",
        "  version: number;",
        "  statement: string;",
        "  when: RuleCondition[];",
        "  then: RuleCondition[];",
        "  entities: string[];",
        "  affectedServices: string[];",
        "  enabled: boolean;",
        "}",
        "",
        "export const RULES: Record<string, BusinessRule> = {",
    ]
    for rule in ruleset.rules:
        lines.append(f"  {_ts_literal(rule.id)}: {{")
        lines.append(f"    id: {_ts_literal(rule.id)},")
        lines.append(f"    version: {rule.version},")
        lines.append(f"    statement: {_ts_literal(rule.statement)},")
        lines.append(f"    when: {_ts_literal(_condition_dict_list(rule.when))},")
        lines.append(f"    then: {_ts_literal(_condition_dict_list(rule.then))},")
        lines.append(f"    entities: {_ts_literal(list(rule.entities))},")
        lines.append(
            f"    affectedServices: {_ts_literal(list(rule.affected_services))},"
        )
        lines.append(f"    enabled: {'true' if rule.enabled else 'false'},")
        lines.append("  },")
    lines.append("};")
    lines.append("")
    for rule in ruleset.rules:
        alias = _slug_to_pascal(rule.id)
        lines.append(f"export const {alias} = RULES[{_ts_literal(rule.id)}];")
    lines.append("")
    return "\n".join(lines)
