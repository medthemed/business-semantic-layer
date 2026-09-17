"""Tests for bsl init scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest

from business_semantic_layer import RuleSet, parse_document, validate_ruleset, write_starter
from business_semantic_layer.cli import main
from business_semantic_layer.init import STARTER_RULES_YAML


def test_write_starter_creates_rules_and_config(tmp_path: Path):
    written = write_starter(tmp_path)
    names = {p.name for p in written}
    assert names == {"rules.yaml", ".bsl.yaml"}
    for path in written:
        assert path.is_file()
        assert path.read_text(encoding="utf-8")


def test_starter_rules_validate_cleanly(tmp_path: Path):
    write_starter(tmp_path, config_name=None)
    text = (tmp_path / "rules.yaml").read_text(encoding="utf-8")
    data = parse_document(text)
    errors = validate_ruleset(RuleSet.from_dict(data))
    assert errors.ok, str(errors)
    ruleset = RuleSet.from_dict(data)
    assert ruleset.name == "starter-rules"
    assert len(ruleset.rules) == 2
    for rule in ruleset.rules:
        assert rule.affected_services, f"{rule.id} must list services"


def test_write_starter_refuses_overwrite(tmp_path: Path):
    write_starter(tmp_path)
    with pytest.raises(FileExistsError):
        write_starter(tmp_path)


def test_write_starter_force_overwrites(tmp_path: Path):
    write_starter(tmp_path)
    written = write_starter(tmp_path, force=True)
    assert len(written) == 2


def test_write_starter_rules_only(tmp_path: Path):
    written = write_starter(tmp_path, config_name=None)
    assert [p.name for p in written] == ["rules.yaml"]
    assert not (tmp_path / ".bsl.yaml").exists()


def test_cli_init(tmp_path: Path, capsys):
    code = main(["init", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "wrote" in out
    assert (tmp_path / "rules.yaml").exists()
    assert (tmp_path / ".bsl.yaml").exists()


def test_cli_init_refuses_existing(tmp_path: Path, capsys):
    main(["init", str(tmp_path)])
    code = main(["init", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 1
    assert "already exists" in err


def test_cli_init_force(tmp_path: Path):
    main(["init", str(tmp_path)])
    code = main(["init", str(tmp_path), "--force"])
    assert code == 0


def test_cli_init_then_validate(tmp_path: Path, capsys):
    """The happy path a new user hits: init, then validate."""
    assert main(["init", str(tmp_path)]) == 0
    capsys.readouterr()
    code = main(["validate", str(tmp_path / "rules.yaml")])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK:" in out
    assert "starter-rules" in out


def test_cli_export_uses_config_output_path(tmp_path: Path, capsys, monkeypatch):
    """A .bsl.yaml output_path is used when -o is omitted."""
    write_starter(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["export", "rules.yaml", "--lang", "python"])
    out = capsys.readouterr().out
    assert code == 0
    # output_path: reports -> reports/rules.py
    written = tmp_path / "reports" / "rules.py"
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert "CHECKOUT" in content or "checkout" in content.lower()


def test_cli_export_flag_overrides_config_output(tmp_path: Path, capsys, monkeypatch):
    write_starter(tmp_path)
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "custom.py"
    code = main(["export", "rules.yaml", "--lang", "python", "-o", str(target)])
    assert code == 0
    assert target.exists()
    assert not (tmp_path / "reports").exists()


def test_starter_yaml_structure():
    """Sanity-check the embedded starter so we notice accidental edits."""
    assert "starter-rules" in STARTER_RULES_YAML
    assert "checkout.min-order" in STARTER_RULES_YAML
    assert "affected_services" in STARTER_RULES_YAML
