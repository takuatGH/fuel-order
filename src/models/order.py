import uuid
from enum import Enum as PyEnum
from decimal import Decimal

from sqlalchemy import ForeignKey, Enum, String, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from .base import Base, uuid_pk, str_20, str_255, timestamp_now, timestamp_nullable


class FuelType(str, PyEnum):
    DIESEL = "diesel"
    PETROL = "petrol"
    PARAFFIN = "paraffin"


class OrderStatus(str, PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class AssignmentStatus(str, PyEnum):
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    FAILED = "failed"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid_pk]
    order_number: Mapped[str_20] = mapped_column(unique=True, index=True)
    shop_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_profiles.id"))
    depot_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("depots.id"), nullable=True)
    fuel_type: Mapped[FuelType] = mapped_column(
        Enum(FuelType, name="fuel_type", values_callable=lambda obj: [e.value for e in obj])
    )
    quantity_liters: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    delivery_location: Mapped[bytes] = mapped_column(Geometry("POINT", srid=4326))
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    quoted_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda obj: [e.value for e in obj]),
        default=OrderStatus.PENDING
    )
    created_at: Mapped[timestamp_now]
    updated_at: Mapped[timestamp_nullable]

    shop: Mapped["ShopProfile"] = relationship(back_populates="orders")
    depot: Mapped["Depot | None"] = relationship(back_populates="orders")
    assignment: Mapped["DeliveryAssignment | None"] = relationship(back_populates="order", uselist=False)


class DeliveryAssignment(Base):
    __tablename__ = "delivery_assignments"

    id: Mapped[uuid_pk]
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True)
    driver_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), index=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status", values_callable=lambda obj: [e.value for e in obj]),
        default=AssignmentStatus.ASSIGNED
    )
    assigned_at: Mapped[timestamp_now]
    started_at: Mapped[timestamp_nullable]
    completed_at: Mapped[timestamp_nullable]
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    proof_of_delivery_url: Mapped[str_255 | None] = mapped_column(nullable=True)

    order: Mapped["Order"] = relationship(back_populates="assignment")
    driver: Mapped["Driver"] = relationship(back_populates="assignments")
