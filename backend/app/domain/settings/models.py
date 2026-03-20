import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class UserModelSettings(Base):
    __tablename__ = "user_model_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Model selections (stored as LiteLLM provider/model strings)
    chat_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="dashscope/qwen3-max",
    )
    ingestion_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="dashscope/qwen3-max",
    )
    embedding_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="openai/text-embedding-3-small",
    )

    # API keys (Fernet encrypted; None = not configured)
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    openai_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    dashscope_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    openrouter_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
