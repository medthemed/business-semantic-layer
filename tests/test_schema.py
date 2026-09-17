"""Tests for schema validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from business_semantic_layer.dsl import parse_document
from business_semantic_layer.schema import SchemaError, validate_raw

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _load(name: str):
    return parse_document((EXAMPLES / name).read_text(encoding="utf-8"))


def test_valid_examples_pass():
    for name in ("checkout_v1.yaml", "checkout_v2.yaml"):
        errors = validate_raw(_load(name))
        assert errors.ok, str(errors)


def test_invalid_example_fails_with_paths():
    errors = validate_raw(_load("invalid_rules.yaml"))
    assert not errors.ok
    text = str(errors)
    assert "rules[0]" in text
    assert "statement" in text
    assert "version" in text
    assert "op" in text
    assert "duplicate rule id" in text


def test_missing_required_document_fields():
    errors = validate_raw({"name": "x"})
    assert not errors.ok
    joined = str(errors)
    assert "version" in joined
    assert "rules" in joined


def test_rule_missing_statement():
    data = {
        "name": "t",
        "version": "1",
        "rules": [{"id": "a.b", "version": 1}],
    }
    errors = validate_raw(data)
    assert any("statement" in p for p in errors.problems)


def test_bad_op_is_rejected():
    data = {
        "name": "t",
        "version": "1",
        "rules": [
            {
                "id": "a.b",
                "version": 1,
                "statement": "s",
                "when": [{"field": "x", "op": "sort_of_equals", "value": 1}],
                "then": [],
            }
        ],
    }
    errors = validate_raw(data)
    assert any("op" in p and "sort_of_equals" in p for p in errors.problems)


def test_exists_does_not_require_value():
    data = {
        "name": "t",
        "version": "1",
        "rules": [
            {
                "id": "a.b",
                "version": 1,
                "statement": "s",
                "when": [{"field": "x", "op": "exists"}],
                "then": [],
            }
        ],
    }
    errors = validate_raw(data)
    assert errors.ok, str(errors)


def test_version_must_be_positive_int():
    data = {
        "name": "t",
        "version": "1",
        "rules": [
            {
                "id": "a.b",
                "version": 0,
                "statement": "s",
                "when": [],
                "then": [],
            }
        ],
    }
    errors = validate_raw(data)
    assert any("version" in p and ">=" in p for p in errors.problems)


def test_id_must_be_slug():
    data = {
        "name": "t",
        "version": "1",
        "rules": [
            {
                "id": "Not A Slug!",
                "version": 1,
                "statement": "s",
                "when": [],
                "then": [],
            }
        ],
    }
    errors = validate_raw(data)
    assert any("id" in p and "slug" in p for p in errors.problems)


def test_document_must_be_mapping():
    errors = validate_raw([1, 2, 3])
    assert not errors.ok
