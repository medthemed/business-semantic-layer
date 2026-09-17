"""Tests for exporters."""

from __future__ import annotations

from pathlib import Path

from business_semantic_layer.dsl import load_ruleset_document
from business_semantic_layer.export import (
    export_markdown_report,
    export_python_constants,
    export_typescript_constants,
)
from business_semantic_layer.impact import analyze_impact

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _load(name: str):
    return load_ruleset_document((EXAMPLES / name).read_text(encoding="utf-8"))


def test_python_export_looks_importable(tmp_path):
    rs = _load("checkout_v1.yaml")
    code = export_python_constants(rs)
    assert "RULES = {" in code
    assert "'checkout.min-order'" in code
    assert "CHECKOUT_MIN_ORDER = RULES['checkout.min-order']" in code

    path = tmp_path / "rules_const.py"
    path.write_text(code, encoding="utf-8")

    # Actually import it to prove the stub is valid Python.
    import importlib.util

    spec = importlib.util.spec_from_file_location("rules_const", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.RULESET_NAME == "checkout-rules"
    assert module.RULES["checkout.min-order"]["version"] == 1
    assert module.CHECKOUT_FREE_SHIPPING["statement"]


def test_typescript_export_shape():
    rs = _load("checkout_v1.yaml")
    code = export_typescript_constants(rs)
    assert "export const RULES: Record<string, BusinessRule>" in code
    assert "export interface BusinessRule" in code
    assert 'id: "checkout.min-order"' in code
    assert "export const CheckoutMinOrder = RULES[\"checkout.min-order\"];" in code
    assert "affectedServices" in code


def test_markdown_report_contains_impact_sections():
    old = _load("checkout_v1.yaml")
    new = _load("checkout_v2.yaml")
    impact = analyze_impact(old, new)
    report = export_markdown_report(impact, old=old, new=new)
    assert "# Business rule impact report" in report
    assert "## Rules to review" in report
    assert "`checkout.free-shipping`" in report
    assert "## Services to refactor" in report
    assert "`checkout-api`" in report
    assert "## Checklist" in report


def test_markdown_report_no_impact():
    rs = _load("checkout_v1.yaml")
    impact = analyze_impact(rs, rs)
    report = export_markdown_report(impact, old=rs, new=rs)
    assert "No behavioral rule changes" in report
