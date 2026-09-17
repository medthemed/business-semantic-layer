"""Freeze the public API surface for the 0.x compatibility promise.

Every name in ``business_semantic_layer.__all__`` must be importable, and
the signatures of the pipeline entry points must not change without a
minor version bump.
"""

from __future__ import annotations

import inspect

import business_semantic_layer as bsl


EXPECTED_ALL = {
    "Rule",
    "RuleSet",
    "Condition",
    "DslError",
    "ImpactError",
    "SchemaError",
    "ChangeKind",
    "ImpactResult",
    "RuleChange",
    "FieldDelta",
    "parse_document",
    "dump_document",
    "validate_ruleset",
    "analyze_impact",
    "diff_rule",
    "format_rule_set_diff",
    "export_markdown_report",
    "export_python_constants",
    "export_typescript_constants",
}


def test_all_matches_expected_surface():
    assert set(bsl.__all__) == EXPECTED_ALL


def test_all_names_are_importable():
    for name in bsl.__all__:
        assert hasattr(bsl, name), f"__all__ lists {name!r} but it is not importable"
        assert getattr(bsl, name) is not None


def test_no_stray_dunder_or_private_in_all():
    for name in bsl.__all__:
        assert not name.startswith("_"), f"{name!r} should not be in the public API"


def test_parse_document_signature_frozen():
    sig = inspect.signature(bsl.parse_document)
    params = list(sig.parameters)
    assert params == ["text", "fmt"], f"parse_document signature changed: {params}"
    assert sig.parameters["fmt"].default is None


def test_analyze_impact_signature_frozen():
    sig = inspect.signature(bsl.analyze_impact)
    assert list(sig.parameters) == ["old", "new"]


def test_validate_ruleset_signature_frozen():
    sig = inspect.signature(bsl.validate_ruleset)
    assert list(sig.parameters) == ["ruleset"]


def test_export_helpers_present():
    for name in (
        "export_markdown_report",
        "export_python_constants",
        "export_typescript_constants",
    ):
        assert callable(getattr(bsl, name)), name


def test_rule_diff_helpers_present():
    for name in ("diff_rule", "format_rule_set_diff"):
        assert callable(getattr(bsl, name)), name


def test_rule_model_fields_frozen():
    required = {
        "id",
        "version",
        "statement",
        "when",
        "then",
        "entities",
        "affected_services",
        "enabled",
        "metadata",
    }
    assert required <= set(bsl.Rule.__dataclass_fields__)


def test_ruleset_model_fields_frozen():
    required = {"name", "version", "rules", "description"}
    assert required <= set(bsl.RuleSet.__dataclass_fields__)


def test_version_string_is_semver():
    parts = bsl.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
