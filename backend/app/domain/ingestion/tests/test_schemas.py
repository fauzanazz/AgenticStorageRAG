"""Tests for ingestion schemas."""

from app.domain.ingestion.schemas import ProviderInfo, TriggerIngestionRequest


class TestTriggerIngestionRequest:
    def test_default_source(self):
        req = TriggerIngestionRequest()
        assert req.source == "google_drive"
        assert req.folder_id is None
        assert req.force is False

    def test_custom_source(self):
        req = TriggerIngestionRequest(source="notion", force=True)
        assert req.source == "notion"
        assert req.force is True

    def test_backward_compat_no_source(self):
        req = TriggerIngestionRequest(folder_id="abc123")
        assert req.source == "google_drive"
        assert req.folder_id == "abc123"


class TestProviderInfo:
    def test_creation(self):
        p = ProviderInfo(key="google_drive", label="Google Drive", configured=True)
        assert p.key == "google_drive"
        assert p.label == "Google Drive"
        assert p.configured is True
