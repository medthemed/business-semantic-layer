# Architecture

## Goals

Keep business rules as **versioned, language-agnostic data** so that:

1. PMs and engineers share one source of truth (`statement` + `when`/`then`).
2. Schema validation catches structurally broken rules in CI.
3. Diffing two rule sets answers *which services must be refactored*.
4. Codegen stubs give application code a typed surface without hand-copying.

Non-goals for v0.1:

- Executing rules (this is not a rules engine).
- Rewriting service code automatically.
- Full YAML 1.2 (see `dsl.py` for the supported subset).

## Pipeline

```
YAML / JSON text
      │
      ▼
dsl.parse_document  ──►  raw dict
      │
      ▼
schema.validate_raw ──►  SchemaError | ok
      │
      ▼
RuleSet.from_dict   ──►  RuleSet
      │
      ├──► impact.analyze_impact(old, new) ──► ImpactResult
      │         │
      │         └──► export.export_markdown_report
      │
      └──► export.export_python_constants / export_typescript_constants
```

## Modules

| Module | Responsibility |
| --- | --- |
| `dsl.py` | `Condition`, `Rule`, `RuleSet` dataclasses. Tiny YAML-subset parser and JSON loader. YAML/JSON dumpers. |
| `schema.py` | Path-qualified structural validation (`rules[2].when[0].op: …`). Duplicate-id detection. |
| `impact.py` | Diff two rule sets (`ChangeKind`), compute affected services/entities, build a rule graph. |
| `rule_diff.py` | Human-readable field-level diffs for PR review (`bsl diff`). |
| `export.py` | Markdown impact report; Python and TypeScript constant modules. |
| `cli.py` | `bsl validate` / `bsl impact` / `bsl diff` / `bsl export`. Exit codes suitable for CI. |

## Rule model

A rule is identified by `id`. Its *meaning* is the `content_key()`:

```
(statement, when[], then[], entities[], affected_services[], enabled)
```

`version` is metadata humans bump; the impact analyzer reports a change when
either the content key **or** the version differs, so a silent bump without a
content change still shows up as `changed (version)`.

Unknown keys on a rule are preserved under `metadata` so PMs can attach
`owner:`, `jira:`, etc. without a schema change.

## Impact algorithm

```
old_map = {r.id: r for r in old.rules}
new_map = {r.id: r for r in new.rules}

for id in sorted(old_map ∪ new_map):
    if id only in new   → ADDED
    if id only in old   → REMOVED
    else if content_key and version equal → UNCHANGED
    else                → CHANGED (with fields_changed)

affected_services = ⋃ affected_services of (old ∪ new) for every
                    added / removed / changed rule
```

Services that only appear on unchanged rules are **not** flagged — that is
the whole point of the tool: keep the refactor list small and correct.

## YAML subset

Implemented in `dsl.py` with no third-party dependency. Supported:

- `key: scalar` (str / int / float / bool / null)
- nested maps by indentation
- block lists (`- item`) including list-of-maps
- inline lists `[a, b]` and maps `{k: v}`
- `# comments`

Not supported (use JSON or extend the parser):

- anchors / aliases
- multi-line folded/literal scalars (`|`, `>`) beyond a pass-through stub
- multiple documents in one stream

## CLI exit codes

| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `validate` | valid | invalid | unreadable |
| `impact` | ok (or impact, unless `--fail-on-impact`) | impact when `--fail-on-impact` | load error |
| `export` | ok | invalid input | load/unknown-lang error |

## Testing strategy

- Parser: scalars, nested structures, round-trip through JSON/YAML dump.
- Schema: valid examples pass; the intentionally broken example must produce
  path-qualified errors (missing statement, bad op, duplicate id, version 0).
- Impact: v1 → v2 checkout examples must detect changed min-order /
  free-shipping, added coupon-stack, unchanged hold-stock, and flag
  `storefront-web` + `promo-service` while leaving `inventory-service` out.
- Export: Python stub is *actually imported* in the test; TS stub is checked
  for shape; markdown report contains the impact sections.
- CLI: exit codes and file output.

## Extension points (post-MVP)

- Full YAML via optional `pyyaml` extra.
- Rule dependency edges derived from shared entities (beyond the bipartite graph).
- JSON Schema export of the rule document for editor autocomplete.
- OpenAPI / protobuf constant emitters.
- A `bsl watch` mode that re-runs impact on file save.
