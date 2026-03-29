from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from .base import Base, uuid_pk, str_255, timestamp_now


class VerificationStatus(str, PyEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class ShopProfile(Base):
    __tablename__ = "shop_profiles"

    id: Mapped[uuid_pk]
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    business_name: Mapped[str_255]
    contact_name: Mapped[str_255 | None]
    default_location: Mapped[bytes | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status", values_callable=lambda obj: [e.value for e in obj]),
        default=VerificationStatus.PENDING
    )
    created_at: Mapped[timestamp_now]

    orders: Mapped[list["Order"]] = relationship(back_populates="shop")
