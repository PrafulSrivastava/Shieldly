"""Pydantic request/response schemas for SafeCall voice agent safety updates."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Nested extraction sub-models ─────────────────────────────────────────────

class ExtractedLocation(BaseModel):
    described: str | None = None
    gps: str | None = None


class ExtractedThreat(BaseModel):
    description: str | None = None
    name: str | None = None
    vehicle: str | None = None
    weapon: str | None = None
    behavior: str | None = None


class ExtractedSituation(BaseModel):
    summary: str | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    distress_level: Literal["calm", "worried", "urgent", "critical"] | None = None


class ExtractedSafetyInfo(BaseModel):
    location: ExtractedLocation | None = None
    threat: ExtractedThreat | None = None
    situation: ExtractedSituation | None = None
    raw_transcript_snippet: str | None = None


# ── POST /safecall/{incident_id}/update ──────────────────────────────────────

class SafetyUpdateRequest(BaseModel):
    timestamp: datetime
    extracted: ExtractedSafetyInfo
    transcript_length: int = Field(..., ge=0)


class SafetyUpdateResponse(BaseModel):
    status: str = "received"
    update_number: int
    incident_id: UUID


# ── GET /safecall/{incident_id}/latest ───────────────────────────────────────

class SafetyUpdateRecord(BaseModel):
    update_number: int
    timestamp: datetime
    extracted: ExtractedSafetyInfo
    transcript_length: int


class LatestSafetyUpdateResponse(BaseModel):
    incident_id: UUID
    update: SafetyUpdateRecord | None = None


# ── GET /safecall/{incident_id}/history ──────────────────────────────────────

class SafetyUpdateHistoryResponse(BaseModel):
    incident_id: UUID
    total: int
    updates: list[SafetyUpdateRecord]
