"""Batch validation and multi-file impact rollup.

Lets teams point ``bsl validate`` / ``bsl impact`` at a directory of rule
documents and get an aggregate table plus a cross-file service blast
radius, instead of one process per file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .dsl import RuleSet, dump_document, parse_document
from .errors import DslError, ImpactError
from .impact import ImpactResult, analyze_impact
from .schema import SchemaError, validate_raw

RULE_SUFFIXES = frozenset({".yaml", ".yml", ".json"})


def discover_rule_files(directory: str | Path) -> list[Path]:
    """Return rule documents directly under ``directory``, sorted by name.

    Only ``*.yaml`` / ``*.yml`` / ``*.json`` files are considered. Nested
    directories are ignored so a reports/ folder does not get swept in.
    """
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")
    return sorted(
        p for p in root.iterdir() if p.is_file() and p.suffix.lower() in RULE_SUFFIXES
    )


def expand_rule_paths(paths: Sequence[str | Path]) -> list[Path]:
    """Expand directories to contained rule files; keep explicit files as-is."""
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            expanded.extend(discover_rule_files(path))
        else:
            expanded.append(path)
    return expanded


def _load_validated(path: str | Path) -> RuleSet:
    text = Path(path).read_text(encoding="utf-8")
    data = parse_document(text)
    errors = validate_raw(data)
    if not errors.ok:
        raise errors
    return RuleSet.from_dict(data)


@dataclass
class FileOutcome:
    """Outcome of validating one rule document."""

    path: str
    ok: bool = False
    error: str | None = None
    name: str | None = None
    version: str | None = None
    rule_count: int = 0

    @property
    def label(self) -> str:
        return Path(self.path).name or self.path

    @property
    def status(self) -> str:
        return "ok" if self.ok else "error"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "status": self.status,
            "ok": self.ok,
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.name is not None:
            payload["name"] = self.name
        if self.version is not None:
            payload["version"] = self.version
        payload["rule_count"] = self.rule_count
        return payload


@dataclass
class BatchValidateResult:
    """Aggregate of validating many rule documents."""

    outcomes: list[FileOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.outcomes) and all(o.ok for o in self.outcomes)

    @property
    def passed(self) -> list[FileOutcome]:
        return [o for o in self.outcomes if o.ok]

    @property
    def failed(self) -> list[FileOutcome]:
        return [o for o in self.outcomes if not o.ok]

    def format_table(self) -> str:
        header = ("FILE", "STATUS", "NAME", "RULES", "DETAIL")
        rows: list[tuple[str, str, str, str, str]] = [header]
        for outcome in self.outcomes:
            rows.append(
                (
                    outcome.label,
                    outcome.status.upper(),
                    outcome.name or "-",
                    str(outcome.rule_count) if outcome.ok else "-",
                    (outcome.error or "").splitlines()[0] if outcome.error else "",
                )
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
        # Cap DETAIL so the table stays readable.
        widths[-1] = min(widths[-1], 48)
        lines: list[str] = []
        for index, row in enumerate(rows):
            cells = []
            for i, cell in enumerate(row):
                text = cell if len(cell) <= widths[i] else cell[: widths[i] - 1] + "…"
                cells.append(text.ljust(widths[i]))
            lines.append("  ".join(cells).rstrip())
            if index == 0:
                lines.append("  ".join("-" * widths[i] for i in range(len(header))))
        lines.append("")
        lines.append(
            f"{len(self.outcomes)} files, "
            f"{len(self.passed)} ok, "
            f"{len(self.failed)} failed"
        )
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "count": len(self.outcomes),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "results": [o.to_dict() for o in self.outcomes],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False) + "\n"


def validate_many(
    paths: Sequence[str | Path],
    *,
    expand: bool = True,
) -> BatchValidateResult:
    """Validate every path; failures become outcomes rather than exceptions."""
    resolved = expand_rule_paths(paths) if expand else [Path(p) for p in paths]
    outcomes: list[FileOutcome] = []
    for path in resolved:
        label = str(path)
        try:
            ruleset = _load_validated(path)
        except SchemaError as exc:
            outcomes.append(FileOutcome(path=label, error=str(exc)))
            continue
        except (OSError, DslError, KeyError, TypeError, ValueError) as exc:
            outcomes.append(FileOutcome(path=label, error=str(exc)))
            continue
        outcomes.append(
            FileOutcome(
                path=label,
                ok=True,
                name=ruleset.name,
                version=ruleset.version,
                rule_count=len(ruleset.rules),
            )
        )
    return BatchValidateResult(outcomes=outcomes)


@dataclass
class FileImpact:
    """Impact of one old/new rule-file pair."""

    old_path: str
    new_path: str
    impact: ImpactResult | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.impact is not None

    @property
    def label(self) -> str:
        return Path(self.new_path).name or self.new_path

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "old_path": self.old_path,
            "new_path": self.new_path,
            "ok": self.ok,
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.impact is not None:
            payload["impact"] = {
                "old_name": self.impact.old_name,
                "new_name": self.impact.new_name,
                "added": [c.rule_id for c in self.impact.added],
                "removed": [c.rule_id for c in self.impact.removed],
                "changed": [c.rule_id for c in self.impact.changed],
                "unchanged": [c.rule_id for c in self.impact.unchanged],
                "services": self.impact.affected_services(),
                "entities": self.impact.affected_entities(),
                "has_impact": self.impact.has_impact(),
            }
        return payload


@dataclass
class ImpactRollup:
    """Cross-file impact plus a multi-service blast-radius rollup."""

    pairs: list[FileImpact] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.pairs) and all(p.ok for p in self.pairs)

    @property
    def errors(self) -> list[FileImpact]:
        return [p for p in self.pairs if not p.ok]

    @property
    def with_impact(self) -> list[FileImpact]:
        return [
            p for p in self.pairs if p.ok and p.impact is not None and p.impact.has_impact()
        ]

    def has_impact(self) -> bool:
        return any(
            p.impact is not None and p.impact.has_impact() for p in self.pairs
        )

    def affected_services(self) -> list[str]:
        """Union of services across every successful pair."""
        services: set[str] = set()
        for pair in self.pairs:
            if pair.impact is not None:
                services.update(pair.impact.affected_services())
        return sorted(services)

    def service_rollup(self) -> dict[str, list[str]]:
        """Map each affected service -> rule-file labels that touch it."""
        rollup: dict[str, set[str]] = {}
        for pair in self.pairs:
            if pair.impact is None or not pair.impact.has_impact():
                continue
            for service in pair.impact.affected_services():
                rollup.setdefault(service, set()).add(pair.label)
        return {svc: sorted(files) for svc, files in sorted(rollup.items())}

    def format_summary(self) -> str:
        lines = [
            f"Impact rollup: {len(self.pairs)} file pair(s)",
            f"  pairs with impact: {len(self.with_impact)}",
        ]
        if self.errors:
            lines.append(f"  errors: {len(self.errors)}")
            for pair in self.errors:
                lines.append(f"    ! {pair.label}: {pair.error}")
        lines.append("  per-file:")
        for pair in self.pairs:
            if pair.impact is None:
                lines.append(f"    {pair.label}: ERROR")
                continue
            impact = pair.impact
            if impact.has_impact():
                lines.append(
                    f"    {pair.label}: "
                    f"+{len(impact.added)} -{len(impact.removed)} ~{len(impact.changed)}"
                )
            else:
                lines.append(f"    {pair.label}: no impact")
        services = self.service_rollup()
        lines.append(f"  services to refactor ({len(services)}):")
        if not services:
            lines.append("    (none)")
        for service, files in services.items():
            lines.append(f"    - {service}  [{', '.join(files)}]")
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "has_impact": self.has_impact(),
            "pair_count": len(self.pairs),
            "pairs_with_impact": len(self.with_impact),
            "services": self.affected_services(),
            "service_rollup": self.service_rollup(),
            "results": [p.to_dict() for p in self.pairs],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False) + "\n"


def _pair_paths(
    old_paths: Sequence[Path],
    new_paths: Sequence[Path],
) -> list[tuple[Path | None, Path | None]]:
    """Pair old/new files by filename. Unmatched files still get a slot."""
    old_map = {p.name: p for p in old_paths}
    new_map = {p.name: p for p in new_paths}
    names = sorted(set(old_map) | set(new_map))
    return [(old_map.get(n), new_map.get(n)) for n in names]


def impact_rollup(
    old_paths: Sequence[str | Path],
    new_paths: Sequence[str | Path],
    *,
    expand: bool = True,
) -> ImpactRollup:
    """Compare old/new rule trees and aggregate multi-service impact.

    Directories pair by filename. A file present on only one side becomes a
    fully added or fully removed impact (all rules added / removed).
    """
    old_resolved = expand_rule_paths(old_paths) if expand else [Path(p) for p in old_paths]
    new_resolved = expand_rule_paths(new_paths) if expand else [Path(p) for p in new_paths]

    # If both sides are single files, pair them directly regardless of name.
    if len(old_resolved) == 1 and len(new_resolved) == 1 and not any(
        Path(p).is_dir() for p in list(old_paths) + list(new_paths)
    ):
        pairs_src = [(old_resolved[0], new_resolved[0])]
    else:
        pairs_src = _pair_paths(old_resolved, new_resolved)

    pairs: list[FileImpact] = []
    for old_path, new_path in pairs_src:
        old_label = str(old_path) if old_path is not None else ""
        new_label = str(new_path) if new_path is not None else ""
        try:
            if old_path is not None and new_path is not None:
                old = _load_validated(old_path)
                new = _load_validated(new_path)
                impact = analyze_impact(old, new)
            elif new_path is not None:
                new = _load_validated(new_path)
                impact = _all_added(new, old_name=f"(missing: {Path(new_path).name})")
            elif old_path is not None:
                old = _load_validated(old_path)
                impact = _all_removed(old, new_name=f"(missing: {Path(old_path).name})")
            else:  # pragma: no cover - defensive
                raise ImpactError("empty pair")
        except (SchemaError, OSError, DslError, ImpactError, KeyError, TypeError, ValueError) as exc:
            pairs.append(
                FileImpact(old_path=old_label, new_path=new_label, error=str(exc))
            )
            continue
        pairs.append(
            FileImpact(old_path=old_label, new_path=new_label, impact=impact)
        )
    return ImpactRollup(pairs=pairs)


def _all_added(ruleset: RuleSet, *, old_name: str) -> ImpactResult:
    from .impact import ChangeKind, RuleChange

    result = ImpactResult(old_name=old_name, new_name=ruleset.name)
    for rule in ruleset.rules:
        result.changes.append(
            RuleChange(rule.id, ChangeKind.ADDED, old=None, new=rule)
        )
    return result


def _all_removed(ruleset: RuleSet, *, new_name: str) -> ImpactResult:
    from .impact import ChangeKind, RuleChange

    result = ImpactResult(old_name=ruleset.name, new_name=new_name)
    for rule in ruleset.rules:
        result.changes.append(
            RuleChange(rule.id, ChangeKind.REMOVED, old=rule, new=None)
        )
    return result
