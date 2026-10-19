"""business-semantic-layer: versioned business rules with change impact.

This package keeps product rules in a language-agnostic DSL (YAML/JSON),
validates them against a schema, and answers the question that actually
matters when a rule changes: *which services have to be refactored?*

Modules
-------
dsl      -- Rule / RuleSet dataclasses and a tiny YAML subset parser.
schema   -- Structural validation with path-qualified errors.
impact   -- Diff two rule sets; list changed rules and affected services.
rule_diff-- Human-readable field-level rule diffs for PR review.
export   -- Markdown impact report + Python/TypeScript constant stubs.
cli      -- `bsl validate | impact | diff | export`.

Public API
----------
Everything re-exported here (see ``__all__``) is covered by the 0.x
compatibility promise: names may be added, but existing names and their
call signatures stay stable within the 0.x series.
"""

from .errors import DslError, ImpactError
from .dsl import Rule, RuleSet, Condition, parse_document, dump_document
from .schema import SchemaError, validate_ruleset
from .impact import ChangeKind, ImpactResult, RuleChange, analyze_impact
from .rule_diff import FieldDelta, diff_rule, format_rule_set_diff
from .config import ProjectConfig, discover_config, load_config
from .init import write_starter
from .export import (
    export_markdown_report,
    export_python_constants,
    export_typescript_constants,
)

__all__ = [
    "Rule",
    "RuleSet",
    "Condition",
    "DslError",
    "ImpactError",
    "SchemaError",
    "ChangeKind",
    "ImpactResult",
    "RuleChange",
    "FieldDelta",
    "ProjectConfig",
    "parse_document",
    "dump_document",
    "validate_ruleset",
    "analyze_impact",
    "diff_rule",
    "format_rule_set_diff",
    "discover_config",
    "load_config",
    "write_starter",
    "export_markdown_report",
    "export_python_constants",
    "export_typescript_constants",
]

__version__ = "0.3.0"
