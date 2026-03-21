from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HotspotContextResponse(BaseModel):
    risk_level: Literal["low", "medium", "high"] = Field(
        description="Aggregated risk level for the area based on recent incident history"
    )
    total_incidents: int = Field(
        description="Total incident count across the centre cell and its 8 neighbours"
    )
    gemini_summary: str = Field(
        description="AI-generated or pre-canned safety awareness message for the area"
    )
    shield_count_nearby: int = Field(
        description="Number of active, verified Shields within 1 km"
    )


class HotspotSummaryResponse(BaseModel):
    summary: str | None = Field(
        default=None,
        description="Gemini-generated one-sentence safety context, or null if insufficient data",
    )
    incident_count: int | None = Field(
        default=None,
        description="Number of incidents recorded in this geohash cell",
    )
    last_incident: datetime | None = Field(
        default=None,
        description="Timestamp of the most recent incident in this cell",
    )
