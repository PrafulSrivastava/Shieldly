import enum
from datetime import datetime, time
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ShieldStatus(enum.Enum):
    active = "active"
    inactive = "inactive"
    pending = "pending"
    rejected = "rejected"


class Shield(Base):
    __tablename__ = "shields"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    status: Mapped[ShieldStatus] = mapped_column(
        SAEnum(ShieldStatus, name="shieldstatus"), nullable=False, default=ShieldStatus.pending
    )
    id_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    commitment_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    active_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    active_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="shield_profile"
    )
    incident_responses: Mapped[list["IncidentResponse"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "IncidentResponse", back_populates="shield"
    )

    __table_args__ = (
        Index("ix_shields_status_verified", "status", "id_verified"),
        Index("ix_shields_location", "current_lat", "current_lng"),
    )

    def __repr__(self) -> str:
        return f"<Shield id={self.id} user_id={self.user_id} status={self.status.value}>"
