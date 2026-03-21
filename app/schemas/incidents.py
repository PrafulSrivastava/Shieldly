"""Pydantic request/response schemas for the incidents domain."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Shared sub-models ─────────────────────────────────────────────────────────

class ConvergencePoint(BaseModel):
    lat: float
    lng: float


# ── POST /incidents/trigger ───────────────────────────────────────────────────

class TriggerSOSRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude of SOS trigger point")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude of SOS trigger point")


class TriggerSOSResponse(BaseModel):
    incident_id: UUID
    shields_notified: int
    convergence_point: ConvergencePoint | None = None


# ── POST /incidents/{incident_id}/respond ─────────────────────────────────────

class RespondToIncidentRequest(BaseModel):
    action: Literal["responding", "declined"]


class RespondingShieldInfo(BaseModel):
    shield_id: UUID
    name: str
    lat: float | None = None
    lng: float | None = None


class RespondToIncidentResponse(BaseModel):
    convergence_point: ConvergencePoint | None
    other_responding_shields: list[RespondingShieldInfo]


# ── POST /incidents/{incident_id}/all-clear ───────────────────────────────────

class AllClearResponse(BaseModel):
    status: str = "resolved"


# ── GET /incidents/{incident_id} ──────────────────────────────────────────────

class ShieldStatusInfo(BaseModel):
    shield_id: UUID
    name: str
    status: str
    lat: float | None = None
    lng: float | None = None
    # Walking ETA from the shield's current position to the convergence point
    eta_seconds: int | None = None


class IncidentDetailResponse(BaseModel):
    incident_id: UUID
    status: str
    trigger_lat: float
    trigger_lng: float
    convergence_point: ConvergencePoint | None
    triggered_at: datetime
    resolved_at: datetime | None
    shields_notified: int
    shields: list[ShieldStatusInfo]
    # Encoded polyline for the person's walking route to the convergence point
    person_polyline: str | None = None
