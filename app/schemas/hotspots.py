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
