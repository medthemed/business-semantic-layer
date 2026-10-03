"""End-to-end integration test: validate -> impact -> export on examples/.

Loads ``examples/checkout_v1.yaml`` and ``examples/checkout_v2.yaml``
through the *public* API only, so this exercises the same path a library
consumer would use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from business_semantic_layer import (
    RuleSet,
    analyze_impact,
    export_markdown_report,
    export_python_constants,
    export_typescript_constants,
    format_rule_set_diff,
    parse_document,
    validate_ruleset,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
V1 = EXAMPLES / "checkout_v1.yaml"
V2 = EXAMPLES / "checkout_v2.yaml"
INVALID = EXAMPLES / "invalid_rules.yaml"


def _load_valid(path: Path) -> RuleSet:
    data = parse_document(path.read_text(encoding="utf-8"))
    errors = validate_ruleset(RuleSet.from_dict(data))
    assert errors.ok, str(errors)
    return RuleSet.from_dict(data)


def test_examples_validate_cleanly():
    for path in (V1, V2):
        ruleset = _load_valid(path)
        assert ruleset.name == "checkout-rules"
        assert len(ruleset.rules) >= 3


def test_invalid_example_fails_validation():
    from business_semantic_layer import SchemaError
    from business_semantic_layer.schema import validate_raw

    data = parse_document(INVALID.read_text(encoding="utf-8"))
    errors = validate_raw(data)
    assert not errors.ok
    assert isinstance(errors, SchemaError)
    assert errors.problems


def test_full_pipeline_validate_impact_export():
    """The main workflow a consumer hits: load, validate, impact, export."""
    old = _load_valid(V1)
    new = _load_valid(V2)

    impact = analyze_impact(old, new)
    assert impact.has_impact()
    assert impact.added, "v2 adds a rule"
    assert impact.changed, "v2 changes an existing rule"
    services = impact.affected_services()
    assert services, "changed rules must list services"
    assert "promo-service" in services or "checkout-api" in services

    # Markdown report
    report = export_markdown_report(impact, old=old, new=new)
    assert "checkout-rules" in report
    assert "promo-service" in report or "checkout-api" in report

    # Language stubs
    py = export_python_constants(new)
    assert "CHECKOUT_MIN_ORDER" in py or "checkout" in py.lower()
    ts = export_typescript_constants(new)
    assert "export" in ts or "const" in ts

    # Human-readable diff
    diff = format_rule_set_diff(old, new, impact=impact)
    assert "checkout" in diff.lower()


def test_pipeline_json_roundtrip():
    """to_dict / from_dict must be lossless for the public model."""
    original = _load_valid(V1)
    rebuilt = RuleSet.from_dict(original.to_dict())
    assert rebuilt.name == original.name
    assert len(rebuilt.rules) == len(original.rules)
    assert rebuilt.by_id().keys() == original.by_id().keys()

    # A round-tripped set must produce the same impact as the original.
    other = _load_valid(V2)
    a = analyze_impact(original, other)
    b = analyze_impact(rebuilt, other)
    assert a.changed_ids == b.changed_ids
    assert a.affected_services() == b.affected_services()


def test_impact_identical_sets_is_quiet():
    spec = _load_valid(V1)
    impact = analyze_impact(spec, spec)
    assert not impact.has_impact()
    assert impact.affected_services() == []
    assert "no behavioral impact" in impact.format_summary()
