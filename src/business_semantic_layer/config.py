"""Project-level configuration for business-semantic-layer.

A small file sitting next to your rules can set defaults so CI and local
runs agree without repeating flags:

    # .bsl.yaml
    default_services:
      - checkout-api
      - storefront-web
    output_path: reports

Lookup order (first hit wins):

1. Explicit CLI flag
2. ``.bsl.yaml`` in the current directory
3. ``.bsl.json`` in the current directory
4. Built-in defaults (no default services, output to stdout)

Only the keys ``default_services`` and ``output_path`` are recognised
today; extra keys are ignored so the file can grow without breaking
older CLIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .dsl import parse_document
from .errors import DslError

#: Filenames probed in the current directory, in order.
CONFIG_FILENAMES = (".bsl.yaml", ".bsl.json")


@dataclass(frozen=True)
class ProjectConfig:
    """Resolved project defaults for ``bsl`` commands."""

    default_services: tuple[str, ...] = ()
    output_path: str | None = None
    source: str | None = None  # path of the config file, if any

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.default_services:
            payload["default_services"] = list(self.default_services)
        if self.output_path:
            payload["output_path"] = self.output_path
        if self.source:
            payload["source"] = self.source
        return payload


def _coerce_services(value: Any, source: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DslError(
            f"{source}: 'default_services' must be a list of strings, "
            f"got {type(value).__name__}"
        )
    services: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise DslError(
                f"{source}: default_services[{i}] must be a non-empty string, "
                f"got {item!r}"
            )
        services.append(item.strip())
    return tuple(services)


def _coerce_output_path(value: Any, source: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DslError(
            f"{source}: 'output_path' must be a non-empty string, got {value!r}"
        )
    return value.strip()


def load_config(path: str | Path) -> ProjectConfig:
    """Load a single config file. Raises :class:`DslError` on bad content."""
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise DslError(f"cannot read config {p}: {exc}") from exc
    try:
        data = parse_document(raw)
    except Exception as exc:  # noqa: BLE001 - normalise parse failures
        raise DslError(f"{p}: not valid config: {exc}") from exc
    if not isinstance(data, Mapping):
        raise DslError(
            f"{p}: config must be a mapping, got {type(data).__name__}"
        )

    return ProjectConfig(
        default_services=_coerce_services(data.get("default_services"), str(p)),
        output_path=_coerce_output_path(data.get("output_path"), str(p)),
        source=str(p),
    )


def discover_config(directory: str | Path | None = None) -> ProjectConfig:
    """Probe ``directory`` (default: cwd) for a known config filename."""
    base = Path(directory) if directory is not None else Path.cwd()
    for name in CONFIG_FILENAMES:
        candidate = base / name
        if candidate.is_file():
            return load_config(candidate)
    return ProjectConfig()


__all__ = [
    "CONFIG_FILENAMES",
    "ProjectConfig",
    "load_config",
    "discover_config",
]
