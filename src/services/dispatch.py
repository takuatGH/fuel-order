import logging
from uuid import UUID

from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID
from geoalchemy2.types import Geography

from src.models import Depot, Driver, DriverStatus, Order, OrderStatus, DeliveryAssignment, AssignmentStatus


logger = logging.getLogger(__name__)


class DispatchService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_nearest_depot(
        self,
        latitude: float,
        longitude: float,
        fuel_type: str,
        max_distance_km: float = 50.0,
    ) -> Depot | None:
        point = cast(
            ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
            Geography(srid=4326),
        )
        depot_geo = cast(Depot.location, Geography(srid=4326))
        max_distance_m = max_distance_km * 1000

        stmt = (
            select(Depot)
            .where(
                Depot.is_active == True,
                Depot.fuel_types_available.contains([fuel_type.lower()]),
                ST_DWithin(depot_geo, point, max_distance_m),
            )
            .order_by(ST_Distance(depot_geo, point))
            .limit(1)
        )

        result = await self.session.execute(stmt)
        depot = result.scalar_one_or_none()

        if depot:
            logger.info(f"found nearest depot: {depot.name}")
        else:
            logger.warning(f"no depot found for {fuel_type} within {max_distance_km}km")

        return depot

    async def find_available_driver(self, depot_id: UUID) -> Driver | None:
        stmt = (
            select(Driver)
            .where(Driver.depot_id == depot_id, Driver.status == DriverStatus.AVAILABLE)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_pending_order_for_depot(self, depot_id: UUID) -> Order | None:
        """Return the oldest unassigned confirmed order at this depot."""
        stmt = (
            select(Order)
            .where(Order.depot_id == depot_id, Order.status == OrderStatus.CONFIRMED)
            .order_by(Order.created_at)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_available_drivers(self, depot_id: UUID) -> list[Driver]:
        """Return all available drivers at a depot, ordered by id for determinism."""
        stmt = (
            select(Driver)
            .where(Driver.depot_id == depot_id, Driver.status == DriverStatus.AVAILABLE)
            .order_by(Driver.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def assign_driver(self, order_id: UUID, driver_id: UUID) -> DeliveryAssignment:
        stmt = select(Driver).where(Driver.id == driver_id)
        result = await self.session.execute(stmt)
        driver = result.scalar_one()
        driver.status = DriverStatus.ON_DELIVERY

        assignment = DeliveryAssignment(
            order_id=order_id,
            driver_id=driver_id,
            status=AssignmentStatus.ASSIGNED,
        )
        self.session.add(assignment)
        await self.session.flush()

        logger.info(f"assigned driver {driver.name} to order {order_id}")
        return assignment

    async def dispatch_order(
        self,
        order: Order,
        latitude: float,
        longitude: float,
    ) -> tuple[Depot | None, DeliveryAssignment | None]:
        depot = await self.find_nearest_depot(
            latitude=latitude,
            longitude=longitude,
            fuel_type=order.fuel_type.value,
        )

        if not depot:
            logger.warning(f"dispatch failed: no depot for order {order.order_number}")
            return None, None

        order.depot_id = depot.id

        driver = await self.find_available_driver(depot.id)
        if not driver:
            logger.warning(f"no driver available at depot for {order.order_number}")
            return depot, None

        assignment = await self.assign_driver(order.id, driver.id)
        return depot, assignment
