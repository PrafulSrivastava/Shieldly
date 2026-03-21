import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ApplyShieldRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    commitment_accepted: bool


class ApplyShieldResponse(BaseModel):
    shield_id: UUID
    status: str
    message: str


class UpdateShieldStatusRequest(BaseModel):
    status: Literal["active", "inactive"]


class UpdateShieldStatusResponse(BaseModel):
    shield_id: UUID
    status: str


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class UpdateActiveHoursRequest(BaseModel):
    active_hours_start: str
    active_hours_end: str

    @field_validator("active_hours_start", "active_hours_end")
    @classmethod
    def validate_hhmm(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("Time must be in HH:MM format (00:00–23:59)")
        return v


class UpdateActiveHoursResponse(BaseModel):
    shield_id: UUID
    active_hours_start: str
    active_hours_end: str


class ShieldProfileResponse(BaseModel):
    shield_id: UUID
    user_id: UUID
    name: str
    phone: str
    status: str
    id_verified: bool
    commitment_signed: bool
    active_hours_start: str | None
    active_hours_end: str | None


class DeviceRegistrationRequest(BaseModel):
    expo_push_token: str

    @field_validator("expo_push_token")
    @classmethod
    def validate_expo_token(cls, v: str) -> str:
        if not v.startswith("ExponentPushToken["):
            raise ValueError("Must be a valid Expo push token")
        return v


class DeviceRegistrationResponse(BaseModel):
    registered: bool
    token_preview: str  # last 8 chars only — never return the full token
