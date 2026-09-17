"""Tests for batch validation and multi-file impact rollup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_semantic_layer.batch import (
    BatchValidateResult,
    ImpactRollup,
    discover_rule_files,
    expand_rule_paths,
    impact_rollup,
    validate_many,
)
from business_semantic_layer.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
V1 = EXAMPLES / "checkout_v1.yaml"
V2 = EXAMPLES / "checkout_v2.yaml"
INVALID = EXAMPLES / "invalid_rules.yaml"


def test_discover_rule_files(tmp_path):
    (tmp_path / "a.yaml").write_text("name: a\nversion: '1'\nrules: []\n", encoding="utf-8")
    (tmp_path / "b.json").write_text(
        json.dumps({"name": "b", "version": "1", "rules": []}), encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("skip", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.yaml").write_text("name: c\n", encoding="utf-8")
    found = discover_rule_files(tmp_path)
    assert [p.name for p in found] == ["a.yaml", "b.json"]


def test_discover_rule_files_not_a_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        discover_rule_files(tmp_path / "missing")


def test_expand_rule_paths_mixed(tmp_path):
    (tmp_path / "x.yaml").write_text("name: x\nversion: '1'\nrules: []\n", encoding="utf-8")
    expanded = expand_rule_paths([V1, tmp_path])
    assert V1 in expanded
    assert any(p.name == "x.yaml" for p in expanded)


def test_validate_many_ok_and_invalid():
    batch = validate_many([V1, INVALID])
    assert isinstance(batch, BatchValidateResult)
    assert not batch.ok
    assert len(batch.passed) == 1
    assert len(batch.failed) == 1
    assert "schema validation failed" in (batch.failed[0].error or "")


def test_validate_many_directory(tmp_path):
    (tmp_path / "good.yaml").write_text(V1.read_text(encoding="utf-8"), encoding="utf-8")
    batch = validate_many([tmp_path])
    assert batch.ok
    assert batch.outcomes[0].name == "checkout-rules"
    assert batch.outcomes[0].rule_count > 0


def test_batch_validate_table(capsys):
    batch = validate_many([V1, V2])
    table = batch.format_table()
    assert "FILE" in table
    assert "checkout_v1.yaml" in table
    assert "2 files" in table
    assert "2 ok" in table


def test_batch_validate_to_dict():
    batch = validate_many([V1])
    payload = batch.to_dict()
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["name"] == "checkout-rules"


def test_impact_rollup_single_files():
    rollup = impact_rollup([V1], [V2])
    assert isinstance(rollup, ImpactRollup)
    assert rollup.ok
    assert rollup.has_impact()
    assert len(rollup.pairs) == 1
    assert "promo-service" in rollup.affected_services()


def test_impact_rollup_directories(tmp_path):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "checkout.yaml").write_text(V1.read_text(encoding="utf-8"), encoding="utf-8")
    (new_dir / "checkout.yaml").write_text(V2.read_text(encoding="utf-8"), encoding="utf-8")
    (new_dir / "shipping.yaml").write_text(
        (
            "name: shipping-rules\n"
            "version: '1.0.0'\n"
            "rules:\n"
            "  - id: shipping.express\n"
            "    version: 1\n"
            "    statement: Express ships in 1 day.\n"
            "    affected_services: [shipping-service]\n"
        ),
        encoding="utf-8",
    )

    rollup = impact_rollup([old_dir], [new_dir])
    assert rollup.ok
    assert len(rollup.pairs) == 2
    assert rollup.has_impact()
    services = rollup.affected_services()
    assert "promo-service" in services
    assert "shipping-service" in services
    roll = rollup.service_rollup()
    assert "checkout.yaml" in roll["promo-service"]
    assert "shipping.yaml" in roll["shipping-service"]
    # shipping only exists on the new side -> fully added
    shipping = next(p for p in rollup.pairs if p.label == "shipping.yaml")
    assert shipping.impact is not None
    assert shipping.impact.added
    assert not shipping.impact.removed


def test_impact_rollup_format_summary():
    rollup = impact_rollup([V1], [V2])
    text = rollup.format_summary()
    assert "Impact rollup" in text
    assert "services to refactor" in text
    assert "promo-service" in text


def test_impact_rollup_to_dict():
    rollup = impact_rollup([V1], [V2])
    payload = rollup.to_dict()
    assert payload["has_impact"] is True
    assert payload["pair_count"] == 1
    assert "promo-service" in payload["services"]


def test_cli_validate_directory(tmp_path, capsys):
    (tmp_path / "a.yaml").write_text(V1.read_text(encoding="utf-8"), encoding="utf-8")
    code = main(["validate", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "FILE" in out
    assert "1 ok" in out


def test_cli_validate_multiple_with_failure(capsys):
    code = main(["validate", str(V1), str(INVALID)])
    out = capsys.readouterr().out
    assert code == 1
    assert "1 failed" in out


def test_cli_validate_single_unchanged(capsys):
    code = main(["validate", str(V1)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("OK:")


def test_cli_impact_directories(tmp_path, capsys):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "checkout.yaml").write_text(V1.read_text(encoding="utf-8"), encoding="utf-8")
    (new_dir / "checkout.yaml").write_text(V2.read_text(encoding="utf-8"), encoding="utf-8")
    code = main(["impact", str(old_dir), str(new_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Impact rollup" in out
    assert "promo-service" in out


def test_cli_impact_directories_fail_on_impact(tmp_path):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "checkout.yaml").write_text(V1.read_text(encoding="utf-8"), encoding="utf-8")
    (new_dir / "checkout.yaml").write_text(V2.read_text(encoding="utf-8"), encoding="utf-8")
    code = main(["impact", str(old_dir), str(new_dir), "--fail-on-impact"])
    assert code == 1
