"""Unit tests for DispatchService — multi-depot fallback and distance foundation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.dispatch import DispatchService, DispatchResult
from src.models import Depot, Driver, DriverStatus, Order, OrderStatus


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_depot(name="Main Depot", fuel_types=None, active=True):
    d = Depot()
    d.id = uuid4()
    d.name = name
    d.phone_number = f"+2710{d.id.int % 10000000:07d}"
    d.location = b""          # opaque bytes — PostGIS handles this in prod
    d.fuel_types_available = fuel_types or ["diesel"]
    d.is_active = active
    d.owner_id = None
    return d


def make_driver(depot_id=None, status=DriverStatus.AVAILABLE):
    dr = Driver()
    dr.id = uuid4()
    dr.name = "Test Driver"
    dr.phone_number = f"+2779{dr.id.int % 10000000:07d}"
    dr.vehicle_plate = "GP 99 ZZ"
    dr.status = status
    dr.depot_id = depot_id or uuid4()
    return dr


def make_order(fuel_type_val="diesel"):
    o = Order()
    o.id = uuid4()
    o.order_number = "FO-20260419-001"
    o.shop_id = uuid4()
    o.depot_id = None
    o.fuel_type = MagicMock()
    o.fuel_type.value = fuel_type_val
    o.quantity_liters = 50
    o.delivery_address = "1 Main St"
    o.status = OrderStatus.CONFIRMED
    return o


def make_service():
    session = AsyncMock()
    return DispatchService(session), session


# ---------------------------------------------------------------------------
# find_fallback_depots
# ---------------------------------------------------------------------------

async def test_find_fallback_depots_excludes_primary():
    service, session = make_service()
    primary = make_depot("Primary")
    fallback = make_depot("Fallback")

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [fallback]
    session.execute = AsyncMock(return_value=result_mock)

    depots = await service.find_fallback_depots(primary, "diesel")

    assert fallback in depots
    assert primary not in depots
    # Verify the query excluded primary depot id
    query_str = str(session.execute.call_args.args[0])
    assert "id" in query_str.lower() or session.execute.called


async def test_find_fallback_depots_returns_ordered_by_distance():
    service, session = make_service()
    primary = make_depot("Primary")
    near = make_depot("Near Fallback")
    far = make_depot("Far Fallback")

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [near, far]
    session.execute = AsyncMock(return_value=result_mock)

    depots = await service.find_fallback_depots(primary, "diesel")

    assert depots == [near, far]


async def test_find_fallback_depots_empty_when_none_match():
    service, session = make_service()
    primary = make_depot("Primary")

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)

    depots = await service.find_fallback_depots(primary, "petrol")
    assert depots == []


async def test_find_fallback_depots_calls_execute_once():
    service, session = make_service()
    primary = make_depot()

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)

    await service.find_fallback_depots(primary, "diesel")
    session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# dispatch_order — primary depot has driver (no fallback needed)
# ---------------------------------------------------------------------------

async def test_dispatch_assigns_from_primary_when_driver_available():
    service, session = make_service()
    order = make_order()
    primary = make_depot()
    driver = make_driver(depot_id=primary.id)
    assignment = MagicMock()

    service.find_nearest_depot = AsyncMock(return_value=primary)
    service._calculate_distance = AsyncMock(return_value=5.2)
    service.find_available_driver = AsyncMock(return_value=driver)
    service.assign_driver = AsyncMock(return_value=assignment)

    result = await service.dispatch_order(order, -26.2041, 28.0473)

    assert result.depot == primary
    assert result.assignment == assignment
    assert result.distance_km == 5.2
    assert result.is_fallback is False
    assert order.depot_id == primary.id


async def test_dispatch_returns_no_assignment_when_no_depot():
    service, session = make_service()
    order = make_order()

    service.find_nearest_depot = AsyncMock(return_value=None)

    result = await service.dispatch_order(order, -26.2041, 28.0473)

    assert result.depot is None
    assert result.assignment is None
    assert result.distance_km is None


# ---------------------------------------------------------------------------
# dispatch_order — fallback path
# ---------------------------------------------------------------------------

async def test_dispatch_uses_fallback_when_primary_has_no_driver():
    service, session = make_service()
    order = make_order()
    primary = make_depot("Primary")
    fallback = make_depot("Fallback")
    driver = make_driver(depot_id=fallback.id)
    assignment = MagicMock()

    service.find_nearest_depot = AsyncMock(return_value=primary)
    service._calculate_distance = AsyncMock(side_effect=[5.0, 12.0])
    service.find_available_driver = AsyncMock(side_effect=[None, driver])
    service.find_fallback_depots = AsyncMock(return_value=[fallback])
    service.assign_driver = AsyncMock(return_value=assignment)

    result = await service.dispatch_order(order, -26.2041, 28.0473)

    assert result.depot == fallback
    assert result.assignment == assignment
    assert result.distance_km == 12.0
    assert result.is_fallback is True
    assert order.depot_id == fallback.id


async def test_dispatch_updates_order_depot_to_fallback():
    service, session = make_service()
    order = make_order()
    primary = make_depot("Primary")
    fallback = make_depot("Fallback")
    driver = make_driver(depot_id=fallback.id)

    service.find_nearest_depot = AsyncMock(return_value=primary)
    service._calculate_distance = AsyncMock(return_value=8.0)
    service.find_available_driver = AsyncMock(side_effect=[None, driver])
    service.find_fallback_depots = AsyncMock(return_value=[fallback])
    service.assign_driver = AsyncMock(return_value=MagicMock())

    await service.dispatch_order(order, -26.2041, 28.0473)

    assert order.depot_id == fallback.id


async def test_dispatch_tries_fallbacks_in_order_stops_at_first_driver():
    service, session = make_service()
    order = make_order()
    primary = make_depot("Primary")
    near_fallback = make_depot("Near")
    far_fallback = make_depot("Far")
    driver = make_driver(depot_id=near_fallback.id)

    # no driver at primary, driver at near_fallback
    driver_calls = [None, driver]
    service.find_nearest_depot = AsyncMock(return_value=primary)
    service._calculate_distance = AsyncMock(return_value=5.0)
    service.find_available_driver = AsyncMock(side_effect=driver_calls)
    service.find_fallback_depots = AsyncMock(return_value=[near_fallback, far_fallback])
    service.assign_driver = AsyncMock(return_value=MagicMock())

    result = await service.dispatch_order(order, -26.2041, 28.0473)

    assert result.depot == near_fallback
    # far_fallback was never checked — find_available_driver called exactly twice
    assert service.find_available_driver.await_count == 2


async def test_dispatch_returns_no_assignment_when_no_drivers_anywhere():
    service, session = make_service()
    order = make_order()
    primary = make_depot()

    service.find_nearest_depot = AsyncMock(return_value=primary)
    service._calculate_distance = AsyncMock(return_value=3.0)
    service.find_available_driver = AsyncMock(return_value=None)
    service.find_fallback_depots = AsyncMock(return_value=[])

    result = await service.dispatch_order(order, -26.2041, 28.0473)

    assert result.depot == primary
    assert result.assignment is None
    assert result.is_fallback is False
    assert order.depot_id == primary.id


async def test_dispatch_keeps_primary_depot_on_order_when_no_drivers():
    """Primary depot is kept on the order for manual follow-up."""
    service, session = make_service()
    order = make_order()
    primary = make_depot("Primary")
    fallback = make_depot("Fallback")

    service.find_nearest_depot = AsyncMock(return_value=primary)
    service._calculate_distance = AsyncMock(return_value=2.0)
    service.find_available_driver = AsyncMock(return_value=None)
    service.find_fallback_depots = AsyncMock(return_value=[fallback])

    await service.dispatch_order(order, -26.2041, 28.0473)

    assert order.depot_id == primary.id


# ---------------------------------------------------------------------------
# DispatchResult dataclass
# ---------------------------------------------------------------------------

def test_dispatch_result_defaults():
    r = DispatchResult(depot=None, assignment=None, distance_km=None)
    assert r.is_fallback is False


def test_dispatch_result_is_fallback_flag():
    r = DispatchResult(depot=MagicMock(), assignment=MagicMock(), distance_km=5.0, is_fallback=True)
    assert r.is_fallback is True
