"""Typed exceptions for business-semantic-layer.

Two families:

- :class:`DslError`     -- the rule document itself is malformed (YAML
  subset parse failure, missing keys, wrong types, non-mapping documents).
- :class:`ImpactError`  -- change-impact analysis cannot proceed.

:class:`~business_semantic_layer.schema.SchemaError` remains a separate
type for *schema* violations (path-qualified structural problems). It is
what ``validate_ruleset`` / ``validate_raw`` return.

``DslError`` subclasses :class:`ValueError` so existing ``except ValueError``
handlers keep working through the 0.x line. ``ImpactError`` subclasses
:class:`RuntimeError` because it signals an analysis failure, not a bad
argument.
"""

from __future__ import annotations


class DslError(ValueError):
    """A rule document could not be parsed into the DSL model.

    Raised by the YAML-subset parser, ``parse_document``, and model
    constructors when the caller supplies something that cannot form a
    legal rule set.
    """


class ImpactError(RuntimeError):
    """Change-impact analysis cannot proceed.

    Raised when inputs are structurally valid but the impact computation
    itself cannot be completed (e.g. mismatched rule-set identities that
    the caller promised were comparable).
    """


__all__ = ["DslError", "ImpactError"]
