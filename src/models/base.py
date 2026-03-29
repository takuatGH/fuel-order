"""declarative base and reusable column types for all models."""
import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import func, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs


uuid_pk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
]

str_20 = Annotated[str, mapped_column(String(20))]
str_255 = Annotated[str, mapped_column(String(255))]

timestamp_now = Annotated[datetime, mapped_column(default=func.now())]
timestamp_nullable = Annotated[datetime | None, mapped_column(default=None)]


class Base(AsyncAttrs, DeclarativeBase):
    """base class inherited by all orm models."""
    pass