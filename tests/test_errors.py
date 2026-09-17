"""Tests for typed DslError / ImpactError exceptions."""

from __future__ import annotations

import pytest

from business_semantic_layer import (
    DslError,
    ImpactError,
    Rule,
    RuleSet,
    analyze_impact,
    parse_document,
)
from business_semantic_layer.dsl import YamlError, load_ruleset_document


def test_dsl_error_is_value_error():
    assert issubclass(DslError, ValueError)
    assert issubclass(YamlError, DslError)


def test_yaml_error_still_catchable_as_dsl_error():
    with pytest.raises(DslError):
        parse_document("trailing junk\nmore")


def test_yaml_error_still_catchable_by_name():
    with pytest.raises(YamlError):
        parse_document("key:\n  orphan\nnext: 1")


def test_non_mapping_document_raises_dsl_error():
    with pytest.raises(DslError, match="must be a mapping"):
        load_ruleset_document("[1, 2, 3]")


def test_impact_error_on_non_ruleset():
    with pytest.raises(ImpactError, match="must be a RuleSet"):
        analyze_impact({"not": "a ruleset"}, RuleSet(name="x", version="1", rules=()))  # type: ignore[arg-type]


def _make_rule(rid: str) -> Rule:
    return Rule(id=rid, version=1, statement=f"rule {rid}")


def test_impact_error_on_duplicate_ids():
    old = RuleSet(name="a", version="1", rules=(_make_rule("r1"), _make_rule("r1")))
    new = RuleSet(name="b", version="1", rules=(_make_rule("r1"),))
    with pytest.raises(ImpactError, match="duplicate rule ids"):
        analyze_impact(old, new)


def test_analyze_impact_accepts_valid_rulesets():
    old = RuleSet(name="a", version="1", rules=(_make_rule("r1"),))
    new = RuleSet(name="b", version="1", rules=(_make_rule("r1"), _make_rule("r2")))
    result = analyze_impact(old, new)
    assert result.has_impact()
    assert len(result.added) == 1
