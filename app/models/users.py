import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(enum.Enum):
    person = "person"
    shield = "shield"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole"), nullable=False, default=UserRole.person
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    shield_profile: Mapped["Shield"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Shield", back_populates="user", uselist=False
    )
    incidents_triggered: Mapped[list["Incident"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Incident", back_populates="triggered_by_user", foreign_keys="Incident.triggered_by"
    )

    __table_args__ = (
        Index("ix_users_phone", "phone"),
        Index("ix_users_role_active", "role", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone} role={self.role.value}>"
