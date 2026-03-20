"""Connector registry.

Maps source keys to SourceConnector subclasses so the ingestion layer
can resolve connectors dynamically instead of hard-coding imports.
"""

from __future__ import annotations

from app.domain.ingestion.interfaces import SourceConnector

_registry: dict[str, type[SourceConnector]] = {}


def register_connector(name: str, cls: type[SourceConnector]) -> None:
    _registry[name] = cls


def get_connector_class(name: str) -> type[SourceConnector]:
    try:
        return _registry[name]
    except KeyError:
        raise ValueError(f"Unknown source connector: {name!r}") from None


def get_all_connectors() -> dict[str, type[SourceConnector]]:
    return dict(_registry)


# Auto-register built-in connectors
from app.domain.ingestion.drive_connector import GoogleDriveConnector  # noqa: E402

register_connector("google_drive", GoogleDriveConnector)
