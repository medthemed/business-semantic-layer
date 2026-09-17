"""Tests for the DSL model and YAML/JSON parser."""

from __future__ import annotations

import json

import pytest

from business_semantic_layer.dsl import (
    Condition,
    Rule,
    RuleSet,
    YamlError,
    dump_document,
    load_ruleset_document,
    parse_document,
    parse_yaml_subset,
)


SAMPLE_YAML = """
name: demo
version: "1.0.0"
description: a demo
rules:
  - id: demo.rule
    version: 1
    statement: hello world
    when:
      - field: cart.total
        op: ge
        value: 10
    then:
      - field: cart.ok
        op: is_true
    entities:
      - cart
    affected_services:
      - api
    enabled: true
"""


def test_parse_yaml_subset_scalars():
    data = parse_yaml_subset(
        """
        a: 1
        b: true
        c: null
        d: hello
        e: 3.5
        f: "quoted: colon"
        """
    )
    assert data == {
        "a": 1,
        "b": True,
        "c": None,
        "d": "hello",
        "e": 3.5,
        "f": "quoted: colon",
    }


def test_parse_yaml_inline_collections():
    data = parse_yaml_subset(
        """
        nums: [1, 2, 3]
        empty: []
        flags: {a: true, b: false}
        """
    )
    assert data["nums"] == [1, 2, 3]
    assert data["empty"] == []
    assert data["flags"] == {"a": True, "b": False}


def test_parse_yaml_nested_maps_and_lists():
    data = parse_yaml_subset(SAMPLE_YAML)
    assert data["name"] == "demo"
    assert data["rules"][0]["id"] == "demo.rule"
    assert data["rules"][0]["when"][0] == {"field": "cart.total", "op": "ge", "value": 10}
    assert data["rules"][0]["entities"] == ["cart"]


def test_parse_document_json_auto():
    data = parse_document('{"name": "x", "version": "1", "rules": []}')
    assert data["name"] == "x"


def test_rule_from_dict_and_to_dict_roundtrip():
    rule = Rule.from_dict(
        {
            "id": "a.b",
            "version": 2,
            "statement": "s",
            "when": [{"field": "x", "op": "eq", "value": 1}],
            "then": [{"field": "y", "op": "is_true"}],
            "entities": ["x"],
            "affected_services": ["svc"],
            "owner": "pm-team",
        }
    )
    assert rule.metadata["owner"] == "pm-team"
    data = rule.to_dict()
    again = Rule.from_dict(data)
    assert again.id == rule.id
    assert again.when == rule.when
    assert again.content_key() == rule.content_key()


def test_ruleset_json_roundtrip():
    rs = load_ruleset_document(SAMPLE_YAML)
    text = dump_document(rs.to_dict(), fmt="json")
    data = json.loads(text)
    rs2 = RuleSet.from_dict(data)
    assert rs2.by_id().keys() == rs.by_id().keys()


def test_ruleset_yaml_roundtrip_basics():
    rs = load_ruleset_document(SAMPLE_YAML)
    text = dump_document(rs.to_dict(), fmt="yaml")
    rs2 = load_ruleset_document(text)
    assert rs2.name == rs.name
    assert rs2.rules[0].id == rs.rules[0].id
    assert rs2.rules[0].when[0].value == 10


def test_yaml_error_on_bad_line():
    with pytest.raises(YamlError):
        parse_yaml_subset("just a bare sentence\n")


def test_condition_key_is_stable():
    c1 = Condition("a.b", "eq", 1)
    c2 = Condition("a.b", "eq", 1)
    c3 = Condition("a.b", "eq", 2)
    assert c1.key() == c2.key()
    assert c1.key() != c3.key()
