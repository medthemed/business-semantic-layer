# Public API and error handling

This page documents the 0.x compatibility promise and the typed exceptions
you should catch.

## Compatibility promise

Everything re-exported from `business_semantic_layer` (see `__all__`) is
public API. Within the 0.x series:

- Existing names and their call signatures stay stable.
- New names may be added.
- Anything not in `__all__` is internal and may change without notice.

The freeze is enforced by `tests/test_public_api.py`.

### Frozen pipeline entry points

| Symbol | Notes |
| --- | --- |
| `parse_document(text, fmt=None)` | Parse JSON or the YAML subset. |
| `validate_ruleset(ruleset)` | Returns a `SchemaError` (possibly empty). |
| `validate_many(paths, *, expand=True)` | Returns `BatchValidateResult` over many files. |
| `discover_rule_files(directory)` | Sorted `*.yaml` / `*.yml` / `*.json` children. |
| `expand_rule_paths(paths)` | Directories → rule files. |
| `analyze_impact(old, new)` | Returns `ImpactResult`. |
| `impact_rollup(old_paths, new_paths)` | Returns `ImpactRollup` with multi-service rollup. |
| `diff_rule` / `format_rule_set_diff` | Human-readable field-level diffs. |
| `export_markdown_report` | Markdown impact report. |
| `export_python_constants` / `export_typescript_constants` | Codegen stubs. |

## Typed exceptions

Three exception types in the public surface:

### `DslError` (subclasses `ValueError`)

The rule document could not be parsed into the DSL model. Raised by:

- The YAML-subset parser (`YamlError` is a `DslError` alias)
- `parse_document` / `load_ruleset_document` for non-mapping documents

### `SchemaError`

Structural validation failures, path-qualified. Returned by
`validate_ruleset` / `validate_raw`; raised by `validate_document`.

### `ImpactError` (subclasses `RuntimeError`)

Change-impact analysis cannot proceed. Raised by `analyze_impact` when:

- An input is not a `RuleSet`
- A rule set contains duplicate rule ids

### Example

```python
from business_semantic_layer import (
    DslError, ImpactError, SchemaError,
    RuleSet, parse_document, validate_ruleset, analyze_impact,
)

try:
    data = parse_document(text)
except DslError as exc:
    print(f"cannot parse: {exc}")

errors = validate_ruleset(RuleSet.from_dict(data))
if not errors.ok:
    print(errors)

try:
    impact = analyze_impact(old, new)
except ImpactError as exc:
    print(f"cannot diff: {exc}")
```

The CLI maps `DslError` / `SchemaError` to exit code 1 (bad input) and
`OSError` / unexpected failures to exit code 2.
