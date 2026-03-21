import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IncidentStatus(enum.Enum):
    active = "active"
    resolved = "resolved"
    escalated = "escalated"


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    triggered_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    trigger_lat: Mapped[float] = mapped_column(Float, nullable=False)
    trigger_lng: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(IncidentStatus, name="incidentstatus"),
        nullable=False,
        default=IncidentStatus.active,
    )
    convergence_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    convergence_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    triggered_by_user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="incidents_triggered", foreign_keys=[triggered_by]
    )
    responses: Mapped[list["IncidentResponse"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "IncidentResponse", back_populates="incident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_triggered_by", "triggered_by"),
        Index("ix_incidents_triggered_at", "triggered_at"),
    )

    def __repr__(self) -> str:
        return f"<Incident id={self.id} status={self.status.value}>"
