"""business-semantic-layer: versioned business rules with change impact.

This package keeps product rules in a language-agnostic DSL (YAML/JSON),
validates them against a schema, and answers the question that actually
matters when a rule changes: *which services have to be refactored?*

Modules
-------
dsl      -- Rule / RuleSet dataclasses and a tiny YAML subset parser.
schema   -- Structural validation with path-qualified errors.
impact   -- Diff two rule sets; list changed rules and affected services.
export   -- Markdown impact report + Python/TypeScript constant stubs.
cli      -- `bsl validate | impact | export`.
"""

from .dsl import Rule, RuleSet, Condition, parse_document, dump_document
from .schema import SchemaError, validate_ruleset
from .impact import ChangeKind, ImpactResult, RuleChange, analyze_impact
from .export import (
    export_markdown_report,
    export_python_constants,
    export_typescript_constants,
)

__all__ = [
    "Rule",
    "RuleSet",
    "Condition",
    "SchemaError",
    "ChangeKind",
    "ImpactResult",
    "RuleChange",
    "parse_document",
    "dump_document",
    "validate_ruleset",
    "analyze_impact",
    "export_markdown_report",
    "export_python_constants",
    "export_typescript_constants",
]

__version__ = "0.1.0"
