from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PendingShieldItem(BaseModel):
    shield_id: UUID
    user_id: UUID
    name: str
    phone: str
    commitment_signed: bool
    applied_at: datetime


class PendingShieldsResponse(BaseModel):
    total: int
    shields: list[PendingShieldItem]


class VerifyShieldRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None


class VerifyShieldResponse(BaseModel):
    shield_id: UUID
    id_verified: bool
    status: str
    message: str


class AdminIncidentItem(BaseModel):
    incident_id: UUID
    triggered_by: UUID
    trigger_lat: float
    trigger_lng: float
    status: str
    triggered_at: datetime
    resolved_at: datetime | None


class AdminIncidentListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    incidents: list[AdminIncidentItem]


class AdminStatsResponse(BaseModel):
    total_users: int
    total_shields: int
    active_shields: int
    total_incidents: int
    resolved_incidents: int
    avg_response_time_seconds: float | None
