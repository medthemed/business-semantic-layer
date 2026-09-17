"""Command-line interface for business-semantic-layer.

Subcommands
-----------
bsl init [DIR] [--force]
    Scaffold a starter ``rules.yaml`` and ``.bsl.yaml`` project config.

bsl validate RULES.yaml [RULES.yaml ...]
    Parse + schema-validate one or more rule documents. Directories expand
    to contained ``*.yaml`` / ``*.yml`` / ``*.json`` files. Multiple paths
    print an aggregate pass/fail table. Exit 0 on success, 1 on errors.

bsl impact OLD.yaml NEW.yaml [--format text|markdown] [-o OUT]
    Diff two rule sets; print changed rules and services to refactor.
    When OLD and NEW are directories, files pair by name and a multi-service
    impact rollup is printed. ``-o`` falls back to the project config
    ``output_path`` when omitted.

bsl diff OLD.yaml NEW.yaml [--show-unchanged] [-o OUT]
    Human-readable field-level rule diff for PR review.

bsl export RULES.yaml --lang python|typescript|markdown [-o OUT]
    Emit rule constants or (with impact) a markdown report stub.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .batch import impact_rollup, validate_many
from .config import discover_config
from .dsl import RuleSet, dump_document, load_ruleset_document, parse_document
from .errors import DslError, ImpactError
from .export import (
    export_markdown_report,
    export_python_constants,
    export_typescript_constants,
)
from .impact import analyze_impact
from .init import write_starter
from .rule_diff import format_rule_set_diff
from .schema import SchemaError, validate_raw


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _load_validated(path: str | Path) -> RuleSet:
    text = _read_text(path)
    data = parse_document(text)
    errors = validate_raw(data)
    if not errors.ok:
        raise errors
    return RuleSet.from_dict(data)


def _is_directory(path: str | Path) -> bool:
    return Path(path).is_dir()


def _resolve_output(args: argparse.Namespace) -> str | None:
    """CLI ``-o`` wins; otherwise fall back to the project config."""
    explicit = getattr(args, "output", None)
    if explicit:
        return explicit
    cfg = discover_config()
    return cfg.output_path


def _write_output(path_str: str, content: str, *, default_name: str) -> None:
    """Write ``content`` to ``path_str``.

    If ``path_str`` is an existing directory or has no file suffix, treat
    it as a directory and write ``default_name`` inside it.
    """
    path = Path(path_str)
    if path.is_dir() or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        path = path / default_name
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def cmd_validate(args: argparse.Namespace) -> int:
    paths: list[str] = list(args.rules)
    multi = len(paths) > 1 or any(_is_directory(p) for p in paths)

    if not multi:
        try:
            text = _read_text(paths[0])
        except OSError as exc:
            print(f"error: cannot read {paths[0]}: {exc}", file=sys.stderr)
            return 2
        try:
            data = parse_document(text)
        except DslError as exc:
            print(f"error: failed to parse {paths[0]}: {exc}", file=sys.stderr)
            return 1
        errors = validate_raw(data)
        if not errors.ok:
            print(str(errors), file=sys.stderr)
            return 1
        ruleset = RuleSet.from_dict(data)
        print(
            f"OK: {ruleset.name} v{ruleset.version} — "
            f"{len(ruleset.rules)} rule(s) valid"
        )
        return 0

    batch = validate_many(paths)
    if not batch.outcomes:
        print("error: no rule files found", file=sys.stderr)
        return 2
    print(batch.format_table(), end="")
    return 0 if batch.ok else 1


def cmd_impact(args: argparse.Namespace) -> int:
    batch_mode = _is_directory(args.old) or _is_directory(args.new)

    if batch_mode:
        rollup = impact_rollup([args.old], [args.new])
        if not rollup.pairs:
            print("error: no rule files found to compare", file=sys.stderr)
            return 2
        output = rollup.format_summary()
        target = _resolve_output(args)
        if target:
            _write_output(target, output, default_name="impact-rollup.txt")
        else:
            print(output, end="" if output.endswith("\n") else "\n")
        if rollup.errors and not rollup.with_impact and not any(
            p.impact is not None for p in rollup.pairs
        ):
            return 2
        if rollup.errors and not rollup.ok:
            # Some files failed to load; still emit the rollup for the rest.
            return 2 if not any(p.impact is not None for p in rollup.pairs) else 1
        return 1 if rollup.has_impact() and args.fail_on_impact else 0

    try:
        old = _load_validated(args.old)
        new = _load_validated(args.new)
    except SchemaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, DslError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        impact = analyze_impact(old, new)
    except ImpactError as exc:
        print(f"error: impact analysis failed: {exc}", file=sys.stderr)
        return 2

    if args.format == "markdown":
        output = export_markdown_report(impact, old=old, new=new)
    else:
        output = impact.format_summary() + "\n"

    target = _resolve_output(args)
    if target:
        _write_output(target, output, default_name="impact.md")
    else:
        print(output, end="" if output.endswith("\n") else "\n")

    # Exit 1 when there is real impact so CI can gate on rule drift.
    return 1 if impact.has_impact() and args.fail_on_impact else 0


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        old = _load_validated(args.old)
        new = _load_validated(args.new)
    except SchemaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, DslError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        impact = analyze_impact(old, new)
    except ImpactError as exc:
        print(f"error: impact analysis failed: {exc}", file=sys.stderr)
        return 2

    output = format_rule_set_diff(
        old,
        new,
        impact=impact,
        show_unchanged=args.show_unchanged,
    )

    target = _resolve_output(args)
    if target:
        _write_output(target, output, default_name="rule-diff.txt")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    try:
        ruleset = _load_validated(args.rules)
    except SchemaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, DslError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.lang == "python":
        output = export_python_constants(ruleset)
    elif args.lang in ("typescript", "ts"):
        output = export_typescript_constants(ruleset)
    elif args.lang == "markdown":
        # Without an old set, emit a "no prior version" summary of this set alone.
        from .impact import ImpactResult, RuleChange, ChangeKind

        solo = ImpactResult(old_name="(none)", new_name=ruleset.name)
        for rule in ruleset.rules:
            solo.changes.append(
                RuleChange(rule.id, ChangeKind.ADDED, old=None, new=rule)
            )
        output = export_markdown_report(solo, old=None, new=ruleset)
    elif args.lang == "json":
        import json

        output = json.dumps(ruleset.to_dict(), indent=2) + "\n"
    elif args.lang == "yaml":
        output = dump_document(ruleset.to_dict(), fmt="yaml")
    else:
        print(f"error: unknown --lang {args.lang!r}", file=sys.stderr)
        return 2

    target = _resolve_output(args)
    if target:
        ext = {
            "python": "py",
            "typescript": "ts",
            "ts": "ts",
            "markdown": "md",
            "json": "json",
            "yaml": "yaml",
        }.get(args.lang, "txt")
        _write_output(target, output, default_name=f"rules.{ext}")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    directory = args.directory or "."
    try:
        written = write_starter(directory, force=args.force)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write starter files: {exc}", file=sys.stderr)
        return 2
    for path in written:
        print(f"wrote {path}")
    print("Next: bsl validate rules.yaml")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bsl",
        description=(
            "Versioned business rules with validation, change impact, "
            "and codegen stubs."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init",
        help="scaffold a starter rules.yaml and .bsl.yaml project config",
    )
    p_init.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="target directory (default: current directory)",
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing starter files",
    )
    p_init.set_defaults(func=cmd_init)

    p_val = sub.add_parser(
        "validate",
        help="validate one or more rule documents",
    )
    p_val.add_argument(
        "rules",
        nargs="+",
        help="path(s) to rules YAML/JSON; directories expand to rule files",
    )
    p_val.set_defaults(func=cmd_validate)

    p_imp = sub.add_parser(
        "impact",
        help="diff two rule sets (files or directories paired by name)",
    )
    p_imp.add_argument("old", help="previous rules document or directory")
    p_imp.add_argument("new", help="current rules document or directory")
    p_imp.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="output format (default: text)",
    )
    p_imp.add_argument("-o", "--output", help="write report to this file")
    p_imp.add_argument(
        "--fail-on-impact",
        action="store_true",
        help="exit 1 when any rule was added, removed, or changed",
    )
    p_imp.set_defaults(func=cmd_impact)

    p_diff = sub.add_parser(
        "diff",
        help="human-readable field-level rule diff (for PR review)",
    )
    p_diff.add_argument("old", help="previous rules document")
    p_diff.add_argument("new", help="current rules document")
    p_diff.add_argument(
        "--show-unchanged",
        action="store_true",
        help="also list rules that did not change",
    )
    p_diff.add_argument("-o", "--output", help="write diff to this file")
    p_diff.set_defaults(func=cmd_diff)

    p_exp = sub.add_parser("export", help="export rule constants or a report")
    p_exp.add_argument("rules", help="path to rules YAML/JSON")
    p_exp.add_argument(
        "--lang",
        choices=("python", "typescript", "ts", "markdown", "json", "yaml"),
        default="python",
        help="output language/format (default: python)",
    )
    p_exp.add_argument("-o", "--output", help="write output to this file")
    p_exp.set_defaults(func=cmd_export)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
