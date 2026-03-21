from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HotspotData(Base):
    __tablename__ = "hotspot_data"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    geohash: Mapped[str] = mapped_column(String(12), nullable=False)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_incident: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {hour_of_day (0-23): incident_count}
    time_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_hotspot_data_geohash", "geohash"),
        Index("ix_hotspot_data_incident_count", "incident_count"),
    )

    def __repr__(self) -> str:
        return f"<HotspotData geohash={self.geohash} count={self.incident_count}>"
