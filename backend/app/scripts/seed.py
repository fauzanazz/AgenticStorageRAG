"""Seed script for development data.

Creates a default admin account and a regular user account.
Run: python -m app.scripts.seed
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.auth.models import User
from app.domain.auth.password import PasswordHasher
from app.infra.database import close_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default dev accounts
SEED_ACCOUNTS = [
    {
        "email": "admin@dingdong.dev",
        "password": "admin123",
        "full_name": "Admin User",
        "is_admin": True,
    },
    {
        "email": "user@dingdong.dev",
        "password": "user123",
        "full_name": "Regular User",
        "is_admin": False,
    },
]


async def seed_users(session: AsyncSession) -> None:
    """Create seed accounts if they don't already exist."""
    hasher = PasswordHasher()

    for account in SEED_ACCOUNTS:
        # Check if already exists
        result = await session.execute(select(User).where(User.email == account["email"]))
        existing = result.scalar_one_or_none()

        if existing:
            logger.info("  [skip] %s already exists", account["email"])
            continue

        user = User(
            email=account["email"],
            hashed_password=hasher.hash(account["password"]),
            full_name=account["full_name"],
            is_admin=account["is_admin"],
            is_active=True,
        )
        session.add(user)
        role = "admin" if account["is_admin"] else "user"
        logger.info("  [created] %s (%s)", account["email"], role)

    await session.commit()


async def main() -> None:
    """Run all seed operations."""
    settings = get_settings()
    logger.info("Seeding database: %s", settings.environment)
    logger.info("")

    _engine, session_factory = init_db()

    async with session_factory() as session:
        logger.info("--- Users ---")
        await seed_users(session)

    await close_db()

    logger.info("")
    logger.info("Seed complete. Dev accounts:")
    logger.info("  Admin: admin@dingdong.dev / admin123")
    logger.info("  User:  user@dingdong.dev  / user123")


if __name__ == "__main__":
    asyncio.run(main())
