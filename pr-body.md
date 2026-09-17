Closes #14

## Summary
- Draft 2020-12 schemas: `rules-document`, `impact-report`, `impact-rollup`
- Package exports: `load_schema`, `schema_path`, `KNOWN_SCHEMAS`
- `ImpactResult.to_dict()` / `to_json()`
- `bsl impact --format json` for files and directories
- `docs/JSON_SCHEMA.md` documents the interop contract

## Verification
- `pytest -q` — 121 passed
- CLI JSON payloads validated against the published schemas in `tests/test_json_schema.py`
