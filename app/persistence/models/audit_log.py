import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, UuidPrimaryKeyMixin
from app.persistence.models.enums import AuditActorType


class AuditLog(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    actor_type: Mapped[str] = mapped_column(
        String(50),
        default=AuditActorType.SYSTEM.value,
        index=True,
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    source: Mapped[str] = mapped_column(
        String(50),
        default="telegram_bot",
        index=True,
        nullable=False,
    )
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
    error_type: Mapped[str | None] = mapped_column(String(150))
    message: Mapped[str | None] = mapped_column(Text)
