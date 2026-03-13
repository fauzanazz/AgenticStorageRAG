"""Tests for database infrastructure."""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.database import (
    Base,
    create_engine,
    create_session_factory,
    init_db,
    close_db,
    get_db_session,
)


class TestBase:
    """Tests for the SQLAlchemy declarative base."""

    def test_base_is_declarative_base(self) -> None:
        """Base should be a DeclarativeBase subclass with metadata."""
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")


class TestCreateEngine:
    """Tests for engine creation."""

    @patch("app.infra.database.get_settings")
    @patch("app.infra.database.create_async_engine")
    def test_create_engine_uses_settings(
        self,
        mock_create_async_engine: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """Engine should be created with settings from config."""
        mock_settings = MagicMock()
        mock_settings.database_url = "postgresql+asyncpg://test:test@localhost/test"
        mock_settings.debug = False
        mock_get_settings.return_value = mock_settings

        create_engine()

        mock_create_async_engine.assert_called_once_with(
            "postgresql+asyncpg://test:test@localhost/test",
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
        )


class TestCreateSessionFactory:
    """Tests for session factory creation."""

    def test_creates_async_session_maker(self) -> None:
        """Should return an async_sessionmaker bound to the engine."""
        mock_engine = MagicMock()
        factory = create_session_factory(mock_engine)

        assert isinstance(factory, async_sessionmaker)


class TestInitDb:
    """Tests for database initialization."""

    @patch("app.infra.database.create_engine")
    @patch("app.infra.database.create_session_factory")
    def test_init_returns_engine_and_factory(
        self,
        mock_create_factory: MagicMock,
        mock_create_engine: MagicMock,
    ) -> None:
        """init_db should return (engine, session_factory) tuple."""
        mock_engine = MagicMock()
        mock_factory = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_create_factory.return_value = mock_factory

        engine, factory = init_db()

        assert engine is mock_engine
        assert factory is mock_factory


class TestCloseDb:
    """Tests for database shutdown."""

    @pytest.mark.asyncio
    async def test_close_db_disposes_engine(self) -> None:
        """close_db should dispose the engine."""
        import app.infra.database as db_mod

        mock_engine = AsyncMock()
        db_mod._engine = mock_engine

        await close_db()

        mock_engine.dispose.assert_called_once()
        assert db_mod._engine is None

    @pytest.mark.asyncio
    async def test_close_db_noop_when_not_initialized(self) -> None:
        """close_db should be safe to call when engine is None."""
        import app.infra.database as db_mod

        db_mod._engine = None
        await close_db()  # Should not raise


class TestGetDbSession:
    """Tests for session dependency injection."""

    @pytest.mark.asyncio
    async def test_raises_when_not_initialized(self) -> None:
        """Should raise RuntimeError if init_db wasn't called."""
        import app.infra.database as db_mod

        db_mod._session_factory = None

        with pytest.raises(RuntimeError, match="Database not initialized"):
            async for _ in get_db_session():
                pass
