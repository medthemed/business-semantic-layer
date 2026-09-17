# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
