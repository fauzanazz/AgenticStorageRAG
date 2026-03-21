"""Tests for the connector registry."""

import pytest

from app.domain.ingestion.drive_connector import GoogleDriveConnector
from app.domain.ingestion.registry import (
    get_all_connectors,
    get_connector_class,
)


class TestRegistry:
    def test_google_drive_auto_registered(self):
        connectors = get_all_connectors()
        assert "google_drive" in connectors
        assert connectors["google_drive"] is GoogleDriveConnector

    def test_get_connector_class_returns_correct_class(self):
        cls = get_connector_class("google_drive")
        assert cls is GoogleDriveConnector

    def test_get_connector_class_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown source connector"):
            get_connector_class("nonexistent_source")

    def test_get_all_connectors_returns_copy(self):
        a = get_all_connectors()
        b = get_all_connectors()
        assert a is not b
        assert a == b


class TestGoogleDriveConnector:
    def test_source_name(self):
        c = GoogleDriveConnector()
        assert c.source_name == "google_drive"

    def test_label(self):
        c = GoogleDriveConnector()
        assert c.label == "Google Drive"

    def test_is_configured_returns_bool(self):
        result = GoogleDriveConnector.is_configured()
        assert isinstance(result, bool)
