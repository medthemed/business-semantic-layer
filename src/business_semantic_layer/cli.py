"""Command-line interface for business-semantic-layer.

Subcommands
-----------
bsl validate RULES.yaml
    Parse + schema-validate a rule document. Exit 0 on success, 1 on errors.

bsl impact OLD.yaml NEW.yaml [--format text|markdown] [-o OUT]
    Diff two rule sets; print changed rules and services to refactor.

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

from .dsl import RuleSet, dump_document, load_ruleset_document, parse_document
from .export import (
    export_markdown_report,
    export_python_constants,
    export_typescript_constants,
)
from .impact import analyze_impact
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


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        text = _read_text(args.rules)
    except OSError as exc:
        print(f"error: cannot read {args.rules}: {exc}", file=sys.stderr)
        return 2
    try:
        data = parse_document(text)
    except Exception as exc:  # noqa: BLE001 - surface parse errors cleanly
        print(f"error: failed to parse {args.rules}: {exc}", file=sys.stderr)
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


def cmd_impact(args: argparse.Namespace) -> int:
    try:
        old = _load_validated(args.old)
        new = _load_validated(args.new)
    except SchemaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to load rule sets: {exc}", file=sys.stderr)
        return 2

    impact = analyze_impact(old, new)
    if args.format == "markdown":
        output = export_markdown_report(impact, old=old, new=new)
    else:
        output = impact.format_summary() + "\n"

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"wrote {args.output}")
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
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to load rule sets: {exc}", file=sys.stderr)
        return 2

    impact = analyze_impact(old, new)
    output = format_rule_set_diff(
        old,
        new,
        impact=impact,
        show_unchanged=args.show_unchanged,
    )

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    try:
        ruleset = _load_validated(args.rules)
    except SchemaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to load rule set: {exc}", file=sys.stderr)
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

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
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

    p_val = sub.add_parser("validate", help="validate a rule document")
    p_val.add_argument("rules", help="path to rules YAML/JSON")
    p_val.set_defaults(func=cmd_validate)

    p_imp = sub.add_parser("impact", help="diff two rule sets")
    p_imp.add_argument("old", help="previous rules document")
    p_imp.add_argument("new", help="current rules document")
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
