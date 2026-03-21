from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class VerifyTokenRequest(BaseModel):
    firebase_id_token: str
    name: str = Field(min_length=1, max_length=120)
    role: Literal["person", "shield"]
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: str | None = Field(default=None, max_length=20)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    phone: str
    role: str
