"""Access to the published JSON Schemas for machine-readable contracts.

Schemas live next to the package
(``business_semantic_layer/schemas/*.schema.json``) so consumers can vendor
them or point a validator at a stable path. Loading is stdlib-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

#: Canonical schema names shipped with the package.
RULES_DOCUMENT = "rules-document"
IMPACT_REPORT = "impact-report"
IMPACT_ROLLUP = "impact-rollup"

KNOWN_SCHEMAS: tuple[str, ...] = (RULES_DOCUMENT, IMPACT_REPORT, IMPACT_ROLLUP)


def schema_path(name: str) -> Path:
    """Return the filesystem path of a published schema file.

    ``name`` may be ``"impact-report"`` or ``"impact-report.schema.json"``.
    Raises :class:`KeyError` for unknown names.
    """
    stem = name.removesuffix(".schema.json")
    if stem not in KNOWN_SCHEMAS:
        raise KeyError(
            f"unknown schema {name!r}; expected one of {list(KNOWN_SCHEMAS)}"
        )
    return SCHEMA_DIR / f"{stem}.schema.json"


def load_schema(name: str) -> dict[str, Any]:
    """Load a published schema as a Python dict."""
    path = schema_path(name)
    return json.loads(path.read_text(encoding="utf-8"))


def schema_ids() -> dict[str, str]:
    """Map schema name -> ``$id`` URI (stable interop identifier)."""
    return {name: str(load_schema(name).get("$id", "")) for name in KNOWN_SCHEMAS}
