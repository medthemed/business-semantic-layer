"""Tests for the bsl CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from business_semantic_layer.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
V1 = str(EXAMPLES / "checkout_v1.yaml")
V2 = str(EXAMPLES / "checkout_v2.yaml")
INVALID = str(EXAMPLES / "invalid_rules.yaml")


def test_validate_ok(capsys):
    code = main(["validate", V1])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK:" in out
    assert "checkout-rules" in out


def test_validate_invalid(capsys):
    code = main(["validate", INVALID])
    err = capsys.readouterr().err
    assert code == 1
    assert "schema validation failed" in err


def test_validate_missing_file(capsys):
    code = main(["validate", "nope.yaml"])
    assert code == 2


def test_impact_text(capsys):
    code = main(["impact", V1, V2])
    out = capsys.readouterr().out
    assert code == 0
    assert "added:" in out
    assert "changed:" in out
    assert "services to refactor" in out
    assert "promo-service" in out


def test_impact_fail_on_impact_flag():
    code = main(["impact", V1, V2, "--fail-on-impact"])
    assert code == 1


def test_impact_identical_exit_zero():
    code = main(["impact", V1, V1])
    assert code == 0


def test_impact_markdown_to_file(tmp_path, capsys):
    out_file = tmp_path / "report.md"
    code = main(["impact", V1, V2, "--format", "markdown", "-o", str(out_file)])
    assert code == 0
    text = out_file.read_text(encoding="utf-8")
    assert "# Business rule impact report" in text
    assert "Services to refactor" in text


def test_export_python(capsys):
    code = main(["export", V1, "--lang", "python"])
    out = capsys.readouterr().out
    assert code == 0
    assert "RULES = {" in out
    assert "CHECKOUT_MIN_ORDER" in out


def test_export_typescript(tmp_path):
    out_file = tmp_path / "rules.ts"
    code = main(["export", V2, "--lang", "typescript", "-o", str(out_file)])
    assert code == 0
    text = out_file.read_text(encoding="utf-8")
    assert "export const RULES" in text
    assert "checkout.coupon-stack" in text


def test_export_rejects_invalid():
    code = main(["export", INVALID, "--lang", "python"])
    assert code == 1
