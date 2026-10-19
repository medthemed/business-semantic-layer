"""Tests for project config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from business_semantic_layer import (
    DslError,
    ProjectConfig,
    discover_config,
    load_config,
)


def test_defaults_when_no_config(tmp_path: Path):
    cfg = discover_config(tmp_path)
    assert cfg.default_services == ()
    assert cfg.output_path is None
    assert cfg.source is None


def test_load_yaml_config(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text(
        "default_services:\n  - checkout-api\n  - storefront-web\n"
        "output_path: reports\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.default_services == ("checkout-api", "storefront-web")
    assert cfg.output_path == "reports"
    assert cfg.source == str(path)


def test_load_json_config(tmp_path: Path):
    path = tmp_path / ".bsl.json"
    path.write_text(
        '{"default_services": ["api"], "output_path": "out"}',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.default_services == ("api",)
    assert cfg.output_path == "out"


def test_discover_prefers_yaml_over_json(tmp_path: Path):
    (tmp_path / ".bsl.yaml").write_text(
        "default_services:\n  - from-yaml\n", encoding="utf-8"
    )
    (tmp_path / ".bsl.json").write_text(
        '{"default_services": ["from-json"]}', encoding="utf-8"
    )
    cfg = discover_config(tmp_path)
    assert cfg.default_services == ("from-yaml",)


def test_partial_config(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text("output_path: reports\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.default_services == ()
    assert cfg.output_path == "reports"


def test_non_mapping_raises_dsl_error(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(DslError, match="must be a mapping"):
        load_config(path)


def test_bad_services_type_raises_dsl_error(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text("default_services: not-a-list\n", encoding="utf-8")
    with pytest.raises(DslError, match="must be a list"):
        load_config(path)


def test_empty_service_string_raises_dsl_error(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text("default_services:\n  - ok\n  - ''\n", encoding="utf-8")
    with pytest.raises(DslError, match="non-empty string"):
        load_config(path)


def test_bad_output_path_raises_dsl_error(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text("output_path: ''\n", encoding="utf-8")
    with pytest.raises(DslError, match="non-empty string"):
        load_config(path)


def test_extra_keys_are_ignored(tmp_path: Path):
    path = tmp_path / ".bsl.yaml"
    path.write_text(
        "output_path: reports\nfuture_key: true\n", encoding="utf-8"
    )
    cfg = load_config(path)
    assert cfg.output_path == "reports"


def test_project_config_to_dict():
    cfg = ProjectConfig(
        default_services=("a",), output_path="out", source="/x/.bsl.yaml"
    )
    d = cfg.to_dict()
    assert d["default_services"] == ["a"]
    assert d["output_path"] == "out"
    assert d["source"] == "/x/.bsl.yaml"
