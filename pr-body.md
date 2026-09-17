Closes #12

## Summary
- `bsl validate` accepts multiple paths and directories of rule files
- Aggregate pass/fail table via `validate_many` / `BatchValidateResult`
- `bsl impact` accepts directories, pairs files by name, and prints a multi-service impact rollup
- New public API: `discover_rule_files`, `expand_rule_paths`, `validate_many`, `impact_rollup`, `ImpactRollup`, `FileOutcome`, `FileImpact`

## Verification
- `pytest -q` — 114 passed
- Directory impact rollup covered in `tests/test_batch.py`
- Single-file CLI behavior unchanged
