"""Tests for Supabase Storage client wrapper."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.infra.storage import StorageClient, DOCUMENTS_BUCKET


class TestStorageClientInit:
    """Tests for storage client initialization."""

    def test_initial_state(self) -> None:
        """Client should start with no connection."""
        client = StorageClient()
        assert client._client is None

    def test_client_property_raises_when_not_connected(self) -> None:
        """Accessing client before connect should raise RuntimeError."""
        client = StorageClient()
        with pytest.raises(RuntimeError, match="Supabase Storage not connected"):
            _ = client.client


class TestStorageClientConnect:
    """Tests for storage connection."""

    @patch("app.infra.storage.get_settings")
    @patch("app.infra.storage.create_client")
    def test_connect_initializes_supabase(
        self,
        mock_create_client: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """connect() should create Supabase client with credentials."""
        mock_settings = MagicMock()
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.supabase_service_role_key = "test-key"
        mock_get_settings.return_value = mock_settings

        mock_supabase = MagicMock()
        mock_create_client.return_value = mock_supabase

        client = StorageClient()
        client.connect()

        mock_create_client.assert_called_once_with(
            "https://test.supabase.co",
            "test-key",
        )
        assert client._client is mock_supabase

    @patch("app.infra.storage.get_settings")
    def test_connect_warns_when_no_credentials(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """connect() should warn and skip when credentials are missing."""
        mock_settings = MagicMock()
        mock_settings.supabase_url = ""
        mock_settings.supabase_service_role_key = ""
        mock_get_settings.return_value = mock_settings

        client = StorageClient()
        client.connect()

        assert client._client is None


class TestStorageClientUpload:
    """Tests for file upload."""

    @pytest.mark.asyncio
    async def test_upload_file(self) -> None:
        """upload_file() should call Supabase storage upload."""
        client = StorageClient()
        mock_supabase = MagicMock()
        mock_bucket = MagicMock()
        mock_supabase.storage.from_.return_value = mock_bucket
        mock_bucket.upload.return_value = {"Key": "test.pdf"}
        client._client = mock_supabase

        result = await client.upload_file(
            file_path="user_1/doc.pdf",
            file_content=b"test bytes",
            content_type="application/pdf",
        )

        mock_supabase.storage.from_.assert_called_once_with(DOCUMENTS_BUCKET)
        mock_bucket.upload.assert_called_once_with(
            path="user_1/doc.pdf",
            file=b"test bytes",
            file_options={"content-type": "application/pdf"},
        )
        assert result["path"] == "user_1/doc.pdf"
        assert result["bucket"] == DOCUMENTS_BUCKET


class TestStorageClientDownload:
    """Tests for file download."""

    @pytest.mark.asyncio
    async def test_download_file(self) -> None:
        """download_file() should return raw bytes."""
        client = StorageClient()
        mock_supabase = MagicMock()
        mock_bucket = MagicMock()
        mock_supabase.storage.from_.return_value = mock_bucket
        mock_bucket.download.return_value = b"file content"
        client._client = mock_supabase

        result = await client.download_file("user_1/doc.pdf")

        assert result == b"file content"


class TestStorageClientDelete:
    """Tests for file deletion."""

    @pytest.mark.asyncio
    async def test_delete_file(self) -> None:
        """delete_file() should call remove on bucket."""
        client = StorageClient()
        mock_supabase = MagicMock()
        mock_bucket = MagicMock()
        mock_supabase.storage.from_.return_value = mock_bucket
        client._client = mock_supabase

        await client.delete_file("user_1/doc.pdf")

        mock_bucket.remove.assert_called_once_with(["user_1/doc.pdf"])

    @pytest.mark.asyncio
    async def test_delete_files_skips_empty_list(self) -> None:
        """delete_files() should no-op on empty list."""
        client = StorageClient()
        mock_supabase = MagicMock()
        client._client = mock_supabase

        await client.delete_files([])

        mock_supabase.storage.from_.assert_not_called()


class TestStorageClientSignedUrl:
    """Tests for signed URL generation."""

    @pytest.mark.asyncio
    async def test_get_signed_url(self) -> None:
        """get_signed_url() should return a signed URL string."""
        client = StorageClient()
        mock_supabase = MagicMock()
        mock_bucket = MagicMock()
        mock_supabase.storage.from_.return_value = mock_bucket
        mock_bucket.create_signed_url.return_value = {
            "signedURL": "https://supabase.co/signed/test.pdf"
        }
        client._client = mock_supabase

        url = await client.get_signed_url("user_1/doc.pdf", expires_in=7200)

        assert url == "https://supabase.co/signed/test.pdf"
        mock_bucket.create_signed_url.assert_called_once_with("user_1/doc.pdf", 7200)


class TestStorageClientTTL:
    """Tests for TTL calculation."""

    @patch("app.infra.storage.get_settings")
    def test_calculate_expiry_uses_default(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """calculate_expiry() should use config default when no arg given."""
        mock_settings = MagicMock()
        mock_settings.upload_ttl_days = 7
        mock_get_settings.return_value = mock_settings

        expiry = StorageClient.calculate_expiry()

        assert isinstance(expiry, datetime)
        assert expiry.tzinfo == timezone.utc
        # Should be approximately 7 days from now
        delta = expiry - datetime.now(timezone.utc)
        assert 6.9 < delta.days + delta.seconds / 86400 < 7.1

    def test_calculate_expiry_with_custom_ttl(self) -> None:
        """calculate_expiry() should respect custom TTL."""
        expiry = StorageClient.calculate_expiry(ttl_days=30)

        delta = expiry - datetime.now(timezone.utc)
        assert 29.9 < delta.days + delta.seconds / 86400 < 30.1
