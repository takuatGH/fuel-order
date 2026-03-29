from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, uuid_pk, str_255, timestamp_now


class DriverStatus(str, PyEnum):
    AVAILABLE = "available"
    ON_DELIVERY = "on_delivery"
    OFFLINE = "offline"


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[uuid_pk]
    depot_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("depots.id"), index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str_255]
    vehicle_plate: Mapped[str] = mapped_column(String(20))
    status: Mapped[DriverStatus] = mapped_column(
        Enum(DriverStatus, name="driver_status", values_callable=lambda obj: [e.value for e in obj]),
        default=DriverStatus.OFFLINE
    )
    created_at: Mapped[timestamp_now]

    depot: Mapped["Depot"] = relationship(back_populates="drivers")
    assignments: Mapped[list["DeliveryAssignment"]] = relationship(back_populates="driver")
