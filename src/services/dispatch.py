import logging
import math
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import cast, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID
from geoalchemy2.types import Geography

from src.models import Depot, Driver, DriverStatus, Order, OrderStatus, DeliveryAssignment, AssignmentStatus


logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    depot: Depot | None
    assignment: DeliveryAssignment | None
    distance_km: float | None
    is_fallback: bool = False


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

    async def find_fallback_depots(
        self,
        primary_depot: Depot,
        fuel_type: str,
        max_distance_km: float = 50.0,
    ) -> list[Depot]:
        """Find other active depots with the fuel type, ordered by distance from primary depot."""
        primary_geo = cast(primary_depot.location, Geography(srid=4326))
        max_distance_m = max_distance_km * 1000

        stmt = (
            select(Depot)
            .where(
                Depot.is_active == True,
                Depot.id != primary_depot.id,
                Depot.fuel_types_available.contains([fuel_type.lower()]),
                ST_DWithin(cast(Depot.location, Geography(srid=4326)), primary_geo, max_distance_m),
            )
            .order_by(ST_Distance(cast(Depot.location, Geography(srid=4326)), primary_geo))
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _calculate_distance(
        self,
        depot: Depot,
        latitude: float,
        longitude: float,
    ) -> float | None:
        """Return distance in km between depot and delivery coordinates using PostGIS."""
        try:
            point = cast(
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
                Geography(srid=4326),
            )
            depot_geo = cast(depot.location, Geography(srid=4326))
            result = await self.session.execute(
                select(ST_Distance(depot_geo, point))
            )
            distance_m = result.scalar()
            return float(distance_m) / 1000.0 if distance_m is not None else None
        except Exception as e:
            logger.warning(f"distance calculation failed for depot {depot.id}: {e}")
            return None

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
    ) -> DispatchResult:
        primary_depot = await self.find_nearest_depot(
            latitude=latitude,
            longitude=longitude,
            fuel_type=order.fuel_type.value,
        )

        if not primary_depot:
            logger.warning(f"dispatch failed: no depot for order {order.order_number}")
            return DispatchResult(depot=None, assignment=None, distance_km=None)

        distance_km = await self._calculate_distance(primary_depot, latitude, longitude)

        driver = await self.find_available_driver(primary_depot.id)
        if driver:
            order.depot_id = primary_depot.id
            assignment = await self.assign_driver(order.id, driver.id)
            return DispatchResult(depot=primary_depot, assignment=assignment, distance_km=distance_km, is_fallback=False)

        fallback_depots = await self.find_fallback_depots(primary_depot, order.fuel_type.value)
        for fallback in fallback_depots:
            driver = await self.find_available_driver(fallback.id)
            if driver:
                fallback_distance = await self._calculate_distance(fallback, latitude, longitude)
                order.depot_id = fallback.id
                assignment = await self.assign_driver(order.id, driver.id)
                logger.info(f"order {order.order_number} assigned to fallback depot {fallback.name}")
                return DispatchResult(depot=fallback, assignment=assignment, distance_km=fallback_distance, is_fallback=True)

        # No drivers anywhere — keep primary depot on the order for manual follow-up
        order.depot_id = primary_depot.id
        logger.warning(f"no drivers available anywhere for order {order.order_number}")
        return DispatchResult(depot=primary_depot, assignment=None, distance_km=distance_km)
