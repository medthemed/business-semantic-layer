# JSON Schema interop

Published machine-readable contracts for `business-semantic-layer`. All
schemas are Draft 2020-12 and ship inside the package:

```
business_semantic_layer/schemas/*.schema.json
```

## Loading a schema

```python
from business_semantic_layer import load_schema, schema_path, IMPACT_REPORT

schema = load_schema(IMPACT_REPORT)   # dict
path = schema_path(IMPACT_REPORT)     # Path to the .schema.json file
```

## Catalog

| Name | CLI / API | `$id` |
| --- | --- | --- |
| `rules-document` | input for `bsl validate` / `impact` / `export` | `.../rules-document.schema.json` |
| `impact-report` | `bsl impact OLD NEW --format json` | `.../impact-report.schema.json` |
| `impact-rollup` | `bsl impact OLD_DIR NEW_DIR --format json` | `.../impact-rollup.schema.json` |

## `--format json` contract

`bsl impact --format json` (files) prints a single impact report:

```json
{
  "old_name": "checkout-rules",
  "new_name": "checkout-rules",
  "ok": true,
  "has_impact": true,
  "counts": {"added": 1, "removed": 0, "changed": 1, "unchanged": 3},
  "changes": [
    {
      "rule_id": "checkout.coupon-stack",
      "kind": "added",
      "requires_refactor": true,
      "fields_changed": [],
      "old": null,
      "new": {"id": "checkout.coupon-stack", "version": 1, "statement": "..."}
    }
  ],
  "services": ["promo-service"],
  "entities": ["cart"],
  "changed_ids": ["checkout.coupon-stack", "checkout.free-shipping"]
}
```

Directory mode (`OLD_DIR NEW_DIR`) prints an impact rollup with
`service_rollup` mapping each service to the files that touch it.

## Stability

Within the 0.x series:

- Required properties of `impact-report` will not be removed.
- New optional properties may be added.
- `kind` enum values may gain members; treat unknown members as opaque.
- `services` remains the sorted union used by CI gates.

## Exit codes (unchanged)

| Code | Meaning |
| --- | --- |
| 0 | success (unless `--fail-on-impact` and drift exists) |
| 1 | schema errors, or gated impact |
| 2 | I/O / unexpected model errors |

## Example

```bash
bsl impact examples/checkout_v1.yaml examples/checkout_v2.yaml --format json > impact.json
# validate impact.json against schemas/impact-report.schema.json
```
