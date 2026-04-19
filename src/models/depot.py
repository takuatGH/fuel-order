import uuid

from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from .base import Base, uuid_pk, str_255, timestamp_now


class Depot(Base):
    __tablename__ = "depots"

    id: Mapped[uuid_pk]
    name: Mapped[str_255]
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    location: Mapped[bytes] = mapped_column(Geometry("POINT", srid=4326))
    fuel_types_available: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, default=None)
    created_at: Mapped[timestamp_now]

    orders: Mapped[list["Order"]] = relationship(back_populates="depot")
    drivers: Mapped[list["Driver"]] = relationship(back_populates="depot")
