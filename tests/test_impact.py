"""Tests for change-impact analysis."""

from __future__ import annotations

from pathlib import Path

from business_semantic_layer.dsl import load_ruleset_document
from business_semantic_layer.impact import (
    ChangeKind,
    analyze_impact,
    build_rule_graph,
    services_impacted_by,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _load(name: str):
    return load_ruleset_document((EXAMPLES / name).read_text(encoding="utf-8"))


def test_example_v1_to_v2_detects_changes():
    old = _load("checkout_v1.yaml")
    new = _load("checkout_v2.yaml")
    impact = analyze_impact(old, new)

    kinds = {c.rule_id: c.kind for c in impact.changes}
    assert kinds["checkout.min-order"] == ChangeKind.CHANGED
    assert kinds["checkout.free-shipping"] == ChangeKind.CHANGED
    assert kinds["inventory.hold-stock"] == ChangeKind.UNCHANGED
    assert kinds["checkout.coupon-stack"] == ChangeKind.ADDED

    assert impact.changed_ids == [
        "checkout.coupon-stack",
        "checkout.free-shipping",
        "checkout.min-order",
    ]


def test_impact_lists_affected_services():
    old = _load("checkout_v1.yaml")
    new = _load("checkout_v2.yaml")
    impact = analyze_impact(old, new)
    services = impact.affected_services()
    # storefront-web joins free-shipping in v2; promo-service is on the new rule
    assert "checkout-api" in services
    assert "shipping-service" in services
    assert "storefront-web" in services
    assert "promo-service" in services
    # inventory-service only appears on an unchanged rule
    assert "inventory-service" not in services


def test_removed_rule_flags_services():
    old = _load("checkout_v1.yaml")
    # drop the min-order rule entirely
    from business_semantic_layer.dsl import RuleSet

    new = RuleSet(
        name=old.name,
        version="0.9.0",
        description="",
        rules=tuple(r for r in old.rules if r.id != "checkout.min-order"),
    )
    impact = analyze_impact(old, new)
    assert len(impact.removed) == 1
    assert impact.removed[0].rule_id == "checkout.min-order"
    assert "storefront-web" in impact.affected_services()


def test_identical_sets_have_no_impact():
    old = _load("checkout_v1.yaml")
    impact = analyze_impact(old, old)
    assert not impact.has_impact()
    assert impact.affected_services() == []
    assert len(impact.unchanged) == len(old.rules)


def test_version_bump_alone_counts_as_changed():
    from business_semantic_layer.dsl import Rule, RuleSet, Condition

    rule = Rule(
        id="a.b",
        version=1,
        statement="same",
        when=(),
        then=(),
        entities=("x",),
        affected_services=("svc",),
    )
    bumped = Rule(
        id="a.b",
        version=2,
        statement="same",
        when=(),
        then=(),
        entities=("x",),
        affected_services=("svc",),
    )
    old = RuleSet(name="s", version="1", rules=(rule,))
    new = RuleSet(name="s", version="2", rules=(bumped,))
    impact = analyze_impact(old, new)
    assert len(impact.changed) == 1
    assert "version" in impact.changed[0].fields_changed


def test_rule_graph_builds():
    rs = _load("checkout_v1.yaml")
    graph = build_rule_graph(rs)
    assert "checkout.min-order" in graph.entity_to_rules["cart"]
    assert "checkout-api" in graph.service_to_rules
    assert set(graph.rule_to_services["checkout.free-shipping"]) == {
        "checkout-api",
        "shipping-service",
    }
    text = graph.format()
    assert "entities:" in text
    assert "services:" in text


def test_services_impacted_by_subset():
    rs = _load("checkout_v2.yaml")
    services = services_impacted_by(rs, ["checkout.coupon-stack"])
    assert services == ["checkout-api", "promo-service"]


def test_format_summary_mentions_services():
    impact = analyze_impact(_load("checkout_v1.yaml"), _load("checkout_v2.yaml"))
    text = impact.format_summary()
    assert "added:" in text
    assert "services to refactor" in text
    assert "checkout-api" in text
