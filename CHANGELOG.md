# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-04

### Added
- Typed exceptions: `DslError` for DSL parse / model problems, `ImpactError` for
  impact-analysis failures. `YamlError` now subclasses `DslError`.
- Public API freeze: `__all__` is the compatibility contract; `test_public_api.py`
  pins `parse_document`, `analyze_impact`, `validate_ruleset`, and export signatures.
- Integration tests that run the full `validate -> impact -> export` pipeline on
  `examples/checkout_v1.yaml` and `examples/checkout_v2.yaml` through the public API.

### Changed
- `analyze_impact` validates its inputs and raises `ImpactError` on non-`RuleSet`
  arguments or duplicate rule ids.
- CLI catches `DslError` / `ImpactError` explicitly instead of bare `Exception`.

### Docs
- `docs/PUBLIC_API.md`: frozen entry points, exception taxonomy, CLI exit codes.

## [0.1.1] - 2026-09-17

### Added
- `bsl diff OLD.yaml NEW.yaml` human-readable field-level rule diff for PR review.
- `rule_diff` module (`diff_rule`, `format_rule_set_diff`) with `--show-unchanged`.

### Docs
- End-to-end PM-to-refactor walkthrough (`docs/PM_TO_REFACTOR.md`).

## [0.1.0] - 2026-03-16

### Added
- YAML/JSON DSL for versioned business rules (id, version, statement, when/then, entities, services).
- Schema validation with clear error paths.
- Change-impact analysis between two rule sets (added / removed / changed rules, affected services).
- Markdown impact report generator.
- Codegen stubs for Python and TypeScript rule constants.
- CLI: `bsl validate`, `bsl impact`, `bsl export`.
- Pytest suite and two worked example rule files.
