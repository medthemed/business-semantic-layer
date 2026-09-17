"""Interop tests: published JSON Schemas and `bsl impact --format json`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from business_semantic_layer.cli import main
from business_semantic_layer.dsl import parse_document, RuleSet
from business_semantic_layer.impact import analyze_impact
from business_semantic_layer.schemas import (
    IMPACT_REPORT,
    IMPACT_ROLLUP,
    KNOWN_SCHEMAS,
    RULES_DOCUMENT,
    load_schema,
    schema_path,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
V1 = EXAMPLES / "checkout_v1.yaml"
V2 = EXAMPLES / "checkout_v2.yaml"


def _resolve(
    schema: dict[str, Any], root: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if "$ref" not in schema:
        return schema, root
    ref = schema["$ref"]
    if ref.startswith("#/"):
        node: Any = root
        for part in ref[2:].split("/"):
            node = node[part]
        return node, root
    name = ref.removesuffix(".schema.json")
    loaded = load_schema(name)
    return loaded, loaded


def _type_ok(value: Any, expected: str | list[str]) -> bool:
    names = [expected] if isinstance(expected, str) else expected
    for name in names:
        if name == "string" and isinstance(value, str):
            return True
        if name == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if name == "boolean" and isinstance(value, bool):
            return True
        if name == "array" and isinstance(value, list):
            return True
        if name == "object" and isinstance(value, dict):
            return True
        if name == "null" and value is None:
            return True
    return False


def validate(instance: Any, schema: dict[str, Any], *, root: dict[str, Any] | None = None) -> None:
    root = schema if root is None else root
    schema, root = _resolve(schema, root)

    if "enum" in schema:
        assert instance in schema["enum"], f"{instance!r} not in {schema['enum']}"

    if "oneOf" in schema:
        errors: list[Exception] = []
        for option in schema["oneOf"]:
            try:
                validate(instance, option, root=root)
                return
            except AssertionError as exc:
                errors.append(exc)
        raise AssertionError(f"oneOf failed for {instance!r}: {errors}")

    expected = schema.get("type")
    if expected is not None:
        assert _type_ok(instance, expected), f"{instance!r} is not type {expected}"

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            assert key in instance, f"missing required key {key!r} in {instance!r}"
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(props)
            extra -= {"$schema", "$id", "title", "description", "$defs"}
            assert not extra, f"unexpected keys {sorted(extra)}"
        for key, value in instance.items():
            if key in props:
                validate(value, props[key], root=root)
            elif schema.get("additionalProperties") not in (None, True, False):
                validate(value, schema["additionalProperties"], root=root)

    if isinstance(instance, list) and "items" in schema:
        for item in instance:
            validate(item, schema["items"], root=root)

    if isinstance(instance, str) and "minLength" in schema:
        assert len(instance) >= schema["minLength"]
    if isinstance(instance, int) and not isinstance(instance, bool) and "minimum" in schema:
        assert instance >= schema["minimum"]


def test_known_schemas_present():
    assert set(KNOWN_SCHEMAS) == {RULES_DOCUMENT, IMPACT_REPORT, IMPACT_ROLLUP}
    for name in KNOWN_SCHEMAS:
        path = schema_path(name)
        assert path.is_file(), path
        data = load_schema(name)
        assert data["$schema"].startswith("https://json-schema.org/draft/2020-12/")
        assert data["$id"]


def test_schema_path_rejects_unknown():
    with pytest.raises(KeyError):
        schema_path("nope")


def test_rules_document_schema_matches_example():
    text = V1.read_text(encoding="utf-8")
    data = parse_document(text)
    validate(data, load_schema(RULES_DOCUMENT))


def test_impact_report_matches_library_output():
    old = RuleSet.from_dict(parse_document(V1.read_text(encoding="utf-8")))
    new = RuleSet.from_dict(parse_document(V2.read_text(encoding="utf-8")))
    impact = analyze_impact(old, new)
    validate(impact.to_dict(), load_schema(IMPACT_REPORT))
    payload = json.loads(impact.to_json())
    assert payload["has_impact"] is True
    assert "promo-service" in payload["services"]


def test_impact_report_matches_cli_json(capsys):
    code = main(["impact", str(V1), str(V2), "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    validate(payload, load_schema(IMPACT_REPORT))
    assert payload["old_name"] == "checkout-rules"
    assert payload["counts"]["added"] >= 1


def test_impact_rollup_matches_cli_json(tmp_path, capsys):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "checkout.yaml").write_text(V1.read_text(encoding="utf-8"), encoding="utf-8")
    (new_dir / "checkout.yaml").write_text(V2.read_text(encoding="utf-8"), encoding="utf-8")
    code = main(["impact", str(old_dir), str(new_dir), "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    validate(payload, load_schema(IMPACT_ROLLUP))
    assert payload["has_impact"] is True
    assert "promo-service" in payload["services"]


def test_impact_json_to_file(tmp_path):
    out = tmp_path / "impact.json"
    code = main(["impact", str(V1), str(V2), "--format", "json", "-o", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    validate(payload, load_schema(IMPACT_REPORT))
