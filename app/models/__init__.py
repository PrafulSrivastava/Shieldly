# Import every model so Alembic autogenerate can discover all tables via Base.metadata.
from app.models.users import User, UserRole
from app.models.shields import Shield, ShieldStatus
from app.models.incidents import Incident, IncidentStatus
from app.models.incident_responses import IncidentResponse, ResponseStatus
from app.models.hotspot_data import HotspotData

__all__ = [
    "User",
    "UserRole",
    "Shield",
    "ShieldStatus",
    "Incident",
    "IncidentStatus",
    "IncidentResponse",
    "ResponseStatus",
    "HotspotData",
]
