"""Tests for the dispatch_order ARQ task."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.models import Order, OrderStatus, Driver, DriverStatus
from src.tasks.dispatch import dispatch_order


def make_order(status=OrderStatus.CONFIRMED, depot_id=None):
    o = Order()
    o.id = uuid4()
    o.order_number = "FO-20260416-001"
    o.shop_id = uuid4()
    o.depot_id = depot_id or uuid4()
    o.fuel_type = MagicMock()
    o.fuel_type.value = "diesel"
    o.quantity_liters = 50
    o.delivery_address = "1 Main St"
    o.status = status
    return o


def make_driver(phone="27791885824"):
    d = Driver()
    d.id = uuid4()
    d.phone_number = phone
    d.name = "Test Driver"
    d.vehicle_plate = "TEST 001"
    d.status = DriverStatus.AVAILABLE
    d.depot_id = uuid4()
    return d


def make_depot():
    from src.models import Depot
    dep = Depot()
    dep.id = uuid4()
    dep.name = "Sandton Depot"
    return dep


def make_ctx(order=None, depot=None, drivers=None, send_offer_return=True):
    session = AsyncMock()
    session.get = AsyncMock(return_value=order)

    whatsapp = AsyncMock()
    redis = AsyncMock()

    dispatch_svc = AsyncMock()
    dispatch_svc.find_nearest_depot = AsyncMock(return_value=depot)
    dispatch_svc.find_available_drivers = AsyncMock(return_value=drivers or [])

    return {
        "session": session,
        "whatsapp": whatsapp,
        "redis": redis,
        "_dispatch_svc": dispatch_svc,
        "_send_offer_return": send_offer_return,
    }


DRAFT = {
    "fuel_type": "diesel",
    "quantity_liters": 50,
    "latitude": -26.2041,
    "longitude": 28.0473,
    "delivery_address": "1 Main St",
}


async def test_dispatch_happy_path_sends_offer():
    order = make_order()
    depot = make_depot()
    driver = make_driver()
    order.depot_id = depot.id
    driver.depot_id = depot.id

    ctx = make_ctx(order=order, depot=depot, drivers=[driver])

    with patch("src.tasks.dispatch.DispatchService", return_value=ctx["_dispatch_svc"]), \
         patch("src.tasks.dispatch._send_offer", new=AsyncMock(return_value=True)) as mock_offer:
        await dispatch_order(ctx, order_id=str(order.id), shop_phone="27799626597", draft=DRAFT)

    mock_offer.assert_awaited_once()
    ctx["session"].commit.assert_awaited()


async def test_dispatch_skips_already_dispatched_order():
    """If order is no longer CONFIRMED when task runs, do nothing."""
    order = make_order(status=OrderStatus.DISPATCHED)
    ctx = make_ctx(order=order)

    with patch("src.tasks.dispatch.DispatchService", return_value=ctx["_dispatch_svc"]), \
         patch("src.tasks.dispatch._send_offer", new=AsyncMock()) as mock_offer:
        await dispatch_order(ctx, order_id=str(order.id), shop_phone="27799626597", draft=DRAFT)

    mock_offer.assert_not_awaited()


async def test_dispatch_no_depot_notifies_shop():
    order = make_order()
    ctx = make_ctx(order=order, depot=None)

    with patch("src.tasks.dispatch.DispatchService", return_value=ctx["_dispatch_svc"]):
        await dispatch_order(ctx, order_id=str(order.id), shop_phone="27799626597", draft=DRAFT)

    ctx["whatsapp"].send_text_message.assert_awaited_once()
    call_kwargs = ctx["whatsapp"].send_text_message.call_args.kwargs
    assert call_kwargs["to"] == "27799626597"
    assert "no depot" in call_kwargs["text"].lower()


async def test_dispatch_no_driver_with_window_leaves_order_confirmed():
    """No drivers have open messaging windows — order stays CONFIRMED for later pickup."""
    depot = make_depot()
    order = make_order(depot_id=depot.id)   # depot_id matches → assign_depot not called
    driver = make_driver()

    ctx = make_ctx(order=order, depot=depot, drivers=[driver])

    with patch("src.tasks.dispatch.DispatchService", return_value=ctx["_dispatch_svc"]), \
         patch("src.tasks.dispatch._send_offer", new=AsyncMock(return_value=False)):
        await dispatch_order(ctx, order_id=str(order.id), shop_phone="27799626597", draft=DRAFT)

    # Order stays CONFIRMED — no status mutation, no shop notification beyond order placed
    ctx["whatsapp"].send_text_message.assert_not_awaited()
    ctx["session"].commit.assert_awaited()


async def test_dispatch_order_not_found_exits_cleanly():
    ctx = make_ctx(order=None)
    with patch("src.tasks.dispatch.DispatchService", return_value=ctx["_dispatch_svc"]), \
         patch("src.tasks.dispatch._send_offer", new=AsyncMock()) as mock_offer:
        await dispatch_order(ctx, order_id=str(uuid4()), shop_phone="27799626597", draft=DRAFT)

    mock_offer.assert_not_awaited()


async def test_dispatch_tries_multiple_drivers_until_one_accepts():
    """First driver has no window, second does — offer goes to second."""
    depot = make_depot()
    order = make_order(depot_id=depot.id)   # depot_id matches → assign_depot not called
    driver_a = make_driver("27700000001")
    driver_b = make_driver("27700000002")

    ctx = make_ctx(order=order, depot=depot, drivers=[driver_a, driver_b])

    send_results = [False, True]  # driver_a fails, driver_b succeeds

    async def fake_send_offer(redis_client, whatsapp, session, driver, offer_data, attempt=1):
        return send_results.pop(0)

    with patch("src.tasks.dispatch.DispatchService", return_value=ctx["_dispatch_svc"]), \
         patch("src.tasks.dispatch._send_offer", side_effect=fake_send_offer):
        await dispatch_order(ctx, order_id=str(order.id), shop_phone="27799626597", draft=DRAFT)

    # Both drivers were tried, second one got the offer
    assert send_results == []  # both calls consumed
