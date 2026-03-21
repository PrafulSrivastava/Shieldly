import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResponseStatus(enum.Enum):
    notified = "notified"
    responding = "responding"
    arrived = "arrived"
    declined = "declined"


class IncidentResponse(Base):
    __tablename__ = "incident_responses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    shield_id: Mapped[UUID] = mapped_column(
        ForeignKey("shields.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ResponseStatus] = mapped_column(
        SAEnum(ResponseStatus, name="responsestatus"),
        nullable=False,
        default=ResponseStatus.notified,
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    incident: Mapped["Incident"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Incident", back_populates="responses"
    )
    shield: Mapped["Shield"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Shield", back_populates="incident_responses"
    )

    __table_args__ = (
        # A shield can only have one response record per incident
        UniqueConstraint("incident_id", "shield_id", name="uq_incident_responses_incident_shield"),
        Index("ix_incident_responses_incident_id", "incident_id"),
        Index("ix_incident_responses_shield_id", "shield_id"),
        Index("ix_incident_responses_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<IncidentResponse incident={self.incident_id} "
            f"shield={self.shield_id} status={self.status.value}>"
        )
