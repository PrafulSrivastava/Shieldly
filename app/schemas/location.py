from pydantic import BaseModel, Field


class UpdateLocationRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")


class PersonLocationResponse(BaseModel):
    lat: float
    lng: float
    updated_at: str | None = None


class ShieldLocationResponse(BaseModel):
    shield_id: str
    lat: float
    lng: float
    updated_at: str | None = None


class IncidentLocationsResponse(BaseModel):
    """All live positions for an active incident."""

    incident_id: str
    person: PersonLocationResponse | None
    shields: list[ShieldLocationResponse]


class NearbyShieldResponse(BaseModel):
    """A single shield returned by the proximity search."""

    shield_id: str
    user_id: str
    name: str
    lat: float
    lng: float
    distance_km: float
