"""Pydantic schemas for the public tracking endpoint."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ShieldTrackingInfo(BaseModel):
    shield_index: int
    lat: float | None = None
    lng: float | None = None
    eta_seconds: int | None = None
    status: str


class TrackingResponse(BaseModel):
    incident_id: UUID
    status: str
    person_lat: float | None = None
    person_lng: float | None = None
    responding_shields: list[ShieldTrackingInfo]
    convergence_lat: float | None = None
    convergence_lng: float | None = None
    triggered_at: datetime
    resolved_at: datetime | None = None
