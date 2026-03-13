"""Tests for Neo4j client wrapper."""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.infra.neo4j_client import Neo4jClient


class TestNeo4jClientInit:
    """Tests for Neo4j client initialization."""

    def test_initial_state(self) -> None:
        """Client should start with no driver."""
        client = Neo4jClient()
        assert client._driver is None

    def test_driver_property_raises_when_not_connected(self) -> None:
        """Accessing driver before connect should raise RuntimeError."""
        client = Neo4jClient()
        with pytest.raises(RuntimeError, match="Neo4j not connected"):
            _ = client.driver


class TestNeo4jClientConnect:
    """Tests for Neo4j connection."""

    @pytest.mark.asyncio
    @patch("app.infra.neo4j_client.get_settings")
    @patch("app.infra.neo4j_client.AsyncGraphDatabase")
    async def test_connect_initializes_driver(
        self,
        mock_graph_db: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """connect() should create and verify a driver."""
        mock_settings = MagicMock()
        mock_settings.neo4j_uri = "bolt://localhost:7687"
        mock_settings.neo4j_user = "neo4j"
        mock_settings.neo4j_password = "password"
        mock_settings.neo4j_database = "dingdong_rag"
        mock_get_settings.return_value = mock_settings

        mock_driver = AsyncMock()
        mock_graph_db.driver.return_value = mock_driver

        client = Neo4jClient()
        await client.connect()

        mock_graph_db.driver.assert_called_once_with(
            "bolt://localhost:7687",
            auth=("neo4j", "password"),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30,
        )
        mock_driver.verify_connectivity.assert_called_once()
        assert client._driver is mock_driver


class TestNeo4jClientClose:
    """Tests for Neo4j disconnection."""

    @pytest.mark.asyncio
    async def test_close_releases_driver(self) -> None:
        """close() should close driver and set to None."""
        client = Neo4jClient()
        client._driver = AsyncMock()

        await client.close()

        client._driver is None  # noqa: B015

    @pytest.mark.asyncio
    async def test_close_noop_when_not_connected(self) -> None:
        """close() should be safe when driver is None."""
        client = Neo4jClient()
        await client.close()  # Should not raise


class TestNeo4jClientHealthCheck:
    """Tests for health check."""

    @pytest.mark.asyncio
    @patch("app.infra.neo4j_client.get_settings")
    async def test_health_check_returns_healthy(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Should return healthy when RETURN 1 works."""
        mock_settings = MagicMock()
        mock_settings.neo4j_database = "dingdong_rag"
        mock_get_settings.return_value = mock_settings

        # Build the mock chain: driver.session() returns an async context manager
        # that yields a session with run() -> result -> single()
        mock_record = {"healthy": 1}
        mock_result = AsyncMock()
        mock_result.single.return_value = mock_record

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result

        # Make driver.session() return an async context manager
        mock_driver = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_ctx.__aexit__.return_value = False
        mock_driver.session.return_value = mock_ctx

        client = Neo4jClient()
        client._driver = mock_driver

        result = await client.health_check()

        assert result["status"] == "healthy"
        assert result["database"] == "dingdong_rag"

    @pytest.mark.asyncio
    @patch("app.infra.neo4j_client.get_settings")
    async def test_health_check_returns_unhealthy_on_error(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Should return unhealthy when driver raises."""
        mock_settings = MagicMock()
        mock_settings.neo4j_database = "dingdong_rag"
        mock_get_settings.return_value = mock_settings

        client = Neo4jClient()
        client._driver = MagicMock()
        client._driver.session.side_effect = Exception("Connection refused")

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "error" in result
