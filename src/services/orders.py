import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_MakePoint, ST_SetSRID

from src.models import Order, OrderStatus, FuelType


logger = logging.getLogger(__name__)


class OrderService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_order(
        self,
        shop_id: UUID,
        fuel_type: str,
        quantity_liters: float,
        latitude: float,
        longitude: float,
        delivery_address: str | None = None,
    ) -> Order:
        order_number = await self._generate_order_number()

        order = Order(
            order_number=order_number,
            shop_id=shop_id,
            fuel_type=FuelType(fuel_type.lower()),
            quantity_liters=Decimal(str(quantity_liters)),
            delivery_location=ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
            delivery_address=delivery_address,
            status=OrderStatus.PENDING,
        )

        self.session.add(order)
        await self.session.flush()

        logger.info(f"created order {order_number} for shop {shop_id}")
        return order

    async def get_order(self, order_id: UUID) -> Order | None:
        stmt = select(Order).where(Order.id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_order_by_number(self, order_number: str) -> Order | None:
        stmt = select(Order).where(Order.order_number == order_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_orders_by_shop(self, shop_id: UUID, limit: int = 10) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.shop_id == shop_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, order_id: UUID, status: OrderStatus) -> Order | None:
        order = await self.get_order(order_id)
        if not order:
            return None
        order.status = status
        order.updated_at = datetime.utcnow()
        await self.session.flush()
        logger.info(f"order {order.order_number} status → {status.value}")
        return order

    async def assign_depot(self, order_id: UUID, depot_id: UUID) -> Order | None:
        order = await self.get_order(order_id)
        if not order:
            return None
        order.depot_id = depot_id
        order.status = OrderStatus.CONFIRMED
        order.updated_at = datetime.utcnow()
        await self.session.flush()
        logger.info(f"order {order.order_number} assigned to depot {depot_id}")
        return order

    async def _generate_order_number(self) -> str:
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"FO-{today}-"
        stmt = select(func.count()).where(Order.order_number.like(f"{prefix}%"))
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return f"{prefix}{count + 1:03d}"
