"""Tests for human-readable rule diffs."""

from __future__ import annotations

from pathlib import Path

from business_semantic_layer.dsl import Condition, Rule, RuleSet
from business_semantic_layer.rule_diff import (
    diff_rule,
    format_rule_diff,
    format_rule_set_diff,
)
from business_semantic_layer.impact import analyze_impact

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _rule(**kwargs) -> Rule:
    defaults = dict(
        id="checkout.sample",
        version=1,
        statement="Sample rule.",
        when=(Condition("cart.subtotal", "ge", 10),),
        then=(Condition("cart.ok", "is_true", None),),
        entities=("cart",),
        affected_services=("checkout-api",),
    )
    defaults.update(kwargs)
    return Rule(**defaults)


def test_diff_rule_statement_and_when():
    old = _rule()
    new = _rule(
        version=2,
        statement="Sample rule tightened.",
        when=(Condition("cart.subtotal", "ge", 25),),
    )
    deltas = {d.field: d for d in diff_rule(old, new)}
    assert "statement" in deltas
    assert deltas["statement"].old_lines == ("Sample rule.",)
    assert deltas["statement"].new_lines == ("Sample rule tightened.",)
    assert "when" in deltas
    assert "ge 10" in deltas["when"].old_lines[0]
    assert "ge 25" in deltas["when"].new_lines[0]
    assert "version" in deltas


def test_diff_rule_unchanged_content_no_deltas():
    old = _rule()
    new = _rule()
    assert diff_rule(old, new) == []


def test_diff_rule_service_addition():
    old = _rule()
    new = _rule(affected_services=("checkout-api", "storefront-web"))
    deltas = {d.field: d for d in diff_rule(old, new)}
    assert deltas["affected_services"].new_lines == ("storefront-web",)
    assert deltas["affected_services"].old_lines == ()
    rendered = deltas["affected_services"].format()
    assert "+ storefront-web" in rendered


def test_format_rule_set_diff_examples():
    from business_semantic_layer.dsl import load_ruleset_document

    old_text = (EXAMPLES / "checkout_v1.yaml").read_text(encoding="utf-8")
    new_text = (EXAMPLES / "checkout_v2.yaml").read_text(encoding="utf-8")
    old = load_ruleset_document(old_text)
    new = load_ruleset_document(new_text)

    text = format_rule_set_diff(old, new)
    assert "RuleSet checkout-rules: 1.0.0 -> 1.1.0" in text
    assert "+ checkout.coupon-stack v1" in text
    assert "~ checkout.free-shipping v1 -> v2" in text
    assert "Orders of $50 or more ship free." in text
    assert "- Free shipping is not offered." in text
    assert "+ Orders of $50 or more ship free." in text
    assert "Services to refactor" in text
    assert "promo-service" in text
    # unchanged rule only appears when requested
    assert "inventory.hold-stock (unchanged)" not in text

    with_unchanged = format_rule_set_diff(old, new, show_unchanged=True)
    assert "inventory.hold-stock (unchanged)" in with_unchanged


def test_format_rule_set_diff_identical():
    from business_semantic_layer.dsl import load_ruleset_document

    text = (EXAMPLES / "checkout_v1.yaml").read_text(encoding="utf-8")
    ruleset = load_ruleset_document(text)
    out = format_rule_set_diff(ruleset, ruleset)
    assert "No rule changes." in out


def test_format_added_and_removed_blocks():
    old = RuleSet(
        name="demo",
        version="1",
        rules=(_rule(id="demo.old", statement="Go away."),),
    )
    new = RuleSet(
        name="demo",
        version="2",
        rules=(_rule(id="demo.new", statement="Hello."),),
    )
    impact = analyze_impact(old, new)
    added = next(c for c in impact.changes if c.rule_id == "demo.new")
    removed = next(c for c in impact.changes if c.rule_id == "demo.old")
    assert format_rule_diff(added).startswith("+ demo.new v1")
    assert "Hello." in format_rule_diff(added)
    assert format_rule_diff(removed).startswith("- demo.old v1")
    assert "Go away." in format_rule_diff(removed)
