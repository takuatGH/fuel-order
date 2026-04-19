"""Tests for DriverMessageHandler and module-level helpers."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.conversation.driver_handlers import (
    DriverMessageHandler,
    DRIVER_OFFER_TTL,
    _haversine_m,
    _is_timed_out,
)
from src.conversation.responses import (
    InteractiveButtonsMessage,
    TextMessage,
)
from src.models import Driver, DriverStatus


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_driver(**kwargs) -> Driver:
    d = Driver()
    d.id = kwargs.get("id", uuid4())
    d.phone_number = kwargs.get("phone_number", "27711000001")
    d.name = kwargs.get("name", "Test Driver")
    d.vehicle_plate = kwargs.get("vehicle_plate", "GP 99 ZZ")
    d.status = kwargs.get("status", DriverStatus.AVAILABLE)
    d.depot_id = kwargs.get("depot_id", uuid4())
    return d


def make_handler(redis_data: dict | None = None):
    """Return (handler, redis_mock, session_mock, whatsapp_mock)."""
    redis_mock = AsyncMock()
    session_mock = AsyncMock()
    session_mock.add = MagicMock()   # session.add is synchronous
    whatsapp_mock = AsyncMock()

    async def fake_hgetall(key):
        if redis_data and key in redis_data:
            raw = redis_data[key]
            return {k.encode(): v.encode() for k, v in raw.items()}
        return {}

    redis_mock.hgetall = fake_hgetall

    handler = DriverMessageHandler(redis_mock, session_mock, whatsapp_mock)
    return handler, redis_mock, session_mock, whatsapp_mock


def fresh_offer(**overrides) -> dict:
    order_id = str(uuid4())
    depot_id = str(uuid4())
    base = {
        "order_id": order_id,
        "order_number": "FO-20260401-001",
        "shop_phone": "27821234567",
        "fuel_type": "diesel",
        "quantity_liters": "200.0",
        "delivery_address": "123 Main St, Johannesburg",
        "delivery_lat": "-26.2041",
        "delivery_lng": "28.0473",
        "depot_id": depot_id,
        "attempt": "1",
        "offer_sent_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def expired_offer(**overrides) -> dict:
    sent = datetime.now(timezone.utc) - timedelta(seconds=DRIVER_OFFER_TTL + 60)
    return fresh_offer(offer_sent_at=sent.isoformat(), **overrides)


def delivery_record(**overrides) -> dict:
    assignment_id = str(uuid4())
    order_id = str(uuid4())
    base = {
        "order_id": order_id,
        "order_number": "FO-20260401-002",
        "shop_phone": "27821234567",
        "delivery_lat": "-26.2041",
        "delivery_lng": "28.0473",
        "fuel_type": "diesel",
        "quantity_liters": "200.0",
        "delivery_address": "456 Test Ave",
        "assignment_id": assignment_id,
    }
    base.update(overrides)
    return base


def btn_msg(button_id: str) -> dict:
    return {"type": "interactive", "interactive": {"button_reply": {"id": button_id}}}


def txt_msg(body: str) -> dict:
    return {"type": "text", "text": {"body": body}}


def loc_msg(lat: float, lng: float) -> dict:
    return {"type": "location", "location": {"latitude": lat, "longitude": lng}}


# ---------------------------------------------------------------------------
# no active offer or delivery
# ---------------------------------------------------------------------------

async def test_no_offer_no_delivery_returns_no_active_offer():
    handler, *_ = make_handler()
    driver = make_driver()
    result = await handler.handle(driver, txt_msg("hello"))
    assert len(result.messages) == 1
    assert isinstance(result.messages[0], TextMessage)


# ---------------------------------------------------------------------------
# offer: expired
# ---------------------------------------------------------------------------

async def test_expired_offer_returns_expired_message_and_releases_driver():
    offer = expired_offer()
    handler, redis_mock, session_mock, _ = make_handler({
        f"driver_offer:{make_driver().phone_number}": offer,
    })
    driver = make_driver()
    result = await handler.handle(driver, txt_msg("hi"))
    assert isinstance(result.messages[0], TextMessage)
    redis_mock.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# offer: unknown message re-presents offer
# ---------------------------------------------------------------------------

async def test_unknown_message_with_active_offer_reprompts():
    driver = make_driver()
    offer = fresh_offer()
    handler, *_ = make_handler({f"driver_offer:{driver.phone_number}": offer})
    result = await handler.handle(driver, txt_msg("gotta go"))
    assert isinstance(result.messages[0], InteractiveButtonsMessage)
    ids = {b["id"] for b in result.messages[0].buttons}
    assert "job_accept" in ids


# ---------------------------------------------------------------------------
# offer: accept
# ---------------------------------------------------------------------------

async def test_accept_job_creates_assignment_and_notifies_shop():
    driver = make_driver()
    offer = fresh_offer()
    handler, redis_mock, session_mock, whatsapp_mock = make_handler(
        {f"driver_offer:{driver.phone_number}": offer}
    )
    result = await handler.handle(driver, btn_msg("job_accept"))

    assert isinstance(result.messages[0], TextMessage)
    assert "confirmed" in result.messages[0].body.lower()

    whatsapp_mock.send_text_message.assert_awaited_once()
    call_kwargs = whatsapp_mock.send_text_message.call_args.kwargs
    assert call_kwargs["to"] == offer["shop_phone"]
    assert driver.name in call_kwargs["text"]

    redis_mock.delete.assert_awaited()
    redis_mock.hset.assert_awaited()
    redis_mock.expire.assert_awaited()
    session_mock.commit.assert_awaited_once()


async def test_accept_sets_delivery_key_in_redis():
    driver = make_driver()
    offer = fresh_offer()
    handler, redis_mock, *_ = make_handler(
        {f"driver_offer:{driver.phone_number}": offer}
    )
    await handler.handle(driver, btn_msg("job_accept"))

    delivery_key = f"driver_delivery:{driver.phone_number}"
    hset_calls = [str(c) for c in redis_mock.hset.call_args_list]
    assert any(delivery_key in c for c in hset_calls)


# ---------------------------------------------------------------------------
# offer: decline
# ---------------------------------------------------------------------------

async def test_decline_job_releases_driver_and_deletes_offer():
    driver = make_driver()
    offer = fresh_offer()
    handler, redis_mock, session_mock, whatsapp_mock = make_handler(
        {f"driver_offer:{driver.phone_number}": offer}
    )
    # patch _find_next_drivers to return empty list (no more drivers)
    with patch("src.conversation.driver_handlers._find_next_drivers", new=AsyncMock(return_value=[])):
        result = await handler.handle(driver, btn_msg("job_decline"))

    assert isinstance(result.messages[0], TextMessage)
    redis_mock.delete.assert_awaited()
    session_mock.commit.assert_awaited_once()


async def test_decline_notifies_shop_when_no_next_driver():
    driver = make_driver()
    offer = fresh_offer(attempt="3")  # at max attempts
    handler, _, _, whatsapp_mock = make_handler(
        {f"driver_offer:{driver.phone_number}": offer}
    )
    with patch("src.conversation.driver_handlers._find_next_drivers", new=AsyncMock(return_value=[])):
        await handler.handle(driver, btn_msg("job_decline"))

    whatsapp_mock.send_text_message.assert_awaited_once()
    call_kwargs = whatsapp_mock.send_text_message.call_args.kwargs
    assert call_kwargs["to"] == offer["shop_phone"]


async def test_decline_sends_offer_to_next_driver_when_available():
    driver = make_driver(phone_number="27711000001")
    next_driver = make_driver(phone_number="27711000002", name="Next Driver")
    offer = fresh_offer()
    handler, redis_mock, session_mock, whatsapp_mock = make_handler(
        {f"driver_offer:{driver.phone_number}": offer}
    )
    with patch("src.conversation.driver_handlers._find_next_drivers", new=AsyncMock(return_value=[next_driver])), \
         patch("src.conversation.driver_handlers._send_offer", new=AsyncMock()) as mock_send:
        await handler.handle(driver, btn_msg("job_decline"))

    mock_send.assert_awaited_once()
    # _send_offer is called positionally: (redis, whatsapp, session, driver, offer_data, attempt)
    call_args = mock_send.call_args
    positional = call_args.args
    assert positional[3] == next_driver
    assert int(positional[5]) == 2


# ---------------------------------------------------------------------------
# delivery: text confirmation
# ---------------------------------------------------------------------------

async def test_delivered_text_completes_delivery():
    driver = make_driver()
    d = delivery_record()
    handler, redis_mock, session_mock, whatsapp_mock = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    result = await handler.handle(driver, txt_msg("delivered"))

    assert isinstance(result.messages[0], TextMessage)
    assert d["order_number"] in result.messages[0].body

    # shop notified
    whatsapp_mock.send_text_message.assert_awaited()
    shop_call = whatsapp_mock.send_text_message.call_args_list[0].kwargs
    assert shop_call["to"] == d["shop_phone"]

    redis_mock.delete.assert_awaited()
    session_mock.commit.assert_awaited_once()


@pytest.mark.parametrize("word", ["done", "complete", "delivery done"])
async def test_delivery_trigger_words_all_confirm(word):
    driver = make_driver()
    d = delivery_record()
    handler, *_ = make_handler({f"driver_delivery:{driver.phone_number}": d})
    result = await handler.handle(driver, txt_msg(word))
    assert d["order_number"] in result.messages[0].body


# ---------------------------------------------------------------------------
# delivery: location within proximity
# ---------------------------------------------------------------------------

async def test_location_within_500m_completes_delivery():
    driver = make_driver()
    d = delivery_record(delivery_lat="-26.2041", delivery_lng="28.0473")
    handler, redis_mock, _, whatsapp_mock = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    # same coordinates → 0 m distance
    result = await handler.handle(driver, loc_msg(-26.2041, 28.0473))
    assert d["order_number"] in result.messages[0].body
    redis_mock.delete.assert_awaited()


# ---------------------------------------------------------------------------
# delivery: location outside proximity
# ---------------------------------------------------------------------------

async def test_location_beyond_500m_shows_warning():
    driver = make_driver()
    d = delivery_record(delivery_lat="-26.2041", delivery_lng="28.0473")
    handler, redis_mock, _, _ = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    # ~11 km away
    result = await handler.handle(driver, loc_msg(-26.3, 28.0473))
    assert isinstance(result.messages[0], InteractiveButtonsMessage)
    ids = {b["id"] for b in result.messages[0].buttons}
    assert "delivery_override_yes" in ids
    redis_mock.delete.assert_not_awaited()


async def test_delivery_override_yes_after_warning_completes():
    driver = make_driver()
    d = delivery_record()
    handler, redis_mock, _, _ = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    result = await handler.handle(driver, btn_msg("delivery_override_yes"))
    assert d["order_number"] in result.messages[0].body
    redis_mock.delete.assert_awaited()


async def test_delivery_override_no_reprompts():
    driver = make_driver()
    d = delivery_record()
    handler, redis_mock, _, _ = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    result = await handler.handle(driver, btn_msg("delivery_override_no"))
    assert isinstance(result.messages[0], TextMessage)
    redis_mock.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# delivery: unrecognised message reprompts
# ---------------------------------------------------------------------------

async def test_unknown_message_while_on_delivery_reprompts():
    driver = make_driver()
    d = delivery_record()
    handler, redis_mock, _, _ = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    result = await handler.handle(driver, txt_msg("what is my next job"))
    assert isinstance(result.messages[0], TextMessage)
    redis_mock.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# admin digest
# ---------------------------------------------------------------------------

async def test_admin_digest_sent_when_configured():
    driver = make_driver()
    d = delivery_record()
    handler, _, _, whatsapp_mock = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    with patch("src.conversation.driver_handlers.get_settings") as mock_settings:
        mock_settings.return_value.admin_whatsapp_number = "27800000000"
        mock_settings.return_value.delivery_proximity_threshold_m = 500
        mock_settings.return_value.max_driver_reassignment_attempts = 3
        await handler.handle(driver, txt_msg("delivered"))

    # shop notification + admin digest = 2 calls
    assert whatsapp_mock.send_text_message.await_count == 2
    admin_call = whatsapp_mock.send_text_message.call_args_list[1].kwargs
    assert admin_call["to"] == "27800000000"
    assert d["order_number"] in admin_call["text"]


async def test_admin_digest_not_sent_when_unconfigured():
    driver = make_driver()
    d = delivery_record()
    handler, _, _, whatsapp_mock = make_handler(
        {f"driver_delivery:{driver.phone_number}": d}
    )
    with patch("src.conversation.driver_handlers.get_settings") as mock_settings:
        mock_settings.return_value.admin_whatsapp_number = None
        mock_settings.return_value.delivery_proximity_threshold_m = 500
        mock_settings.return_value.max_driver_reassignment_attempts = 3
        await handler.handle(driver, txt_msg("delivered"))

    assert whatsapp_mock.send_text_message.await_count == 1  # shop only


# ---------------------------------------------------------------------------
# _haversine_m
# ---------------------------------------------------------------------------

def test_haversine_same_point_is_zero():
    assert _haversine_m(-26.2041, 28.0473, -26.2041, 28.0473) == pytest.approx(0.0)


def test_haversine_known_distance():
    # Sandton (-26.1076, 28.0567) → Soweto (-26.2678, 27.8585) ≈ 26.5 km
    dist = _haversine_m(-26.1076, 28.0567, -26.2678, 27.8585)
    assert 24_000 < dist < 29_000


def test_haversine_500m_threshold():
    # ~450 m north along same longitude
    dist = _haversine_m(-26.2041, 28.0473, -26.1997, 28.0473)
    assert dist < 500


def test_haversine_exceeds_500m():
    # ~1.1 km
    dist = _haversine_m(-26.2041, 28.0473, -26.1940, 28.0473)
    assert dist > 500


# ---------------------------------------------------------------------------
# _is_timed_out
# ---------------------------------------------------------------------------

def test_fresh_offer_not_timed_out():
    offer = {"offer_sent_at": datetime.now(timezone.utc).isoformat()}
    assert not _is_timed_out(offer)


def test_old_offer_is_timed_out():
    sent = datetime.now(timezone.utc) - timedelta(seconds=DRIVER_OFFER_TTL + 1)
    offer = {"offer_sent_at": sent.isoformat()}
    assert _is_timed_out(offer)


def test_missing_offer_sent_at_not_timed_out():
    assert not _is_timed_out({})


# ---------------------------------------------------------------------------
# availability: status transitions
# ---------------------------------------------------------------------------

async def test_mark_available_when_offline_sets_status_and_returns_now_available():
    driver = make_driver(status=DriverStatus.OFFLINE)
    handler, redis_mock, session_mock, _ = make_handler()
    with patch("src.services.DispatchService") as MockDS:
        MockDS.return_value.find_pending_order_for_depot = AsyncMock(return_value=None)
        result = await handler.handle(driver, txt_msg("available"))

    assert len(result.messages) == 1
    assert "available" in result.messages[0].body.lower()
    session_mock.execute.assert_awaited()


async def test_mark_available_when_already_available_returns_already_available():
    driver = make_driver(status=DriverStatus.AVAILABLE)
    handler, *_ = make_handler()
    with patch("src.services.DispatchService") as MockDS:
        MockDS.return_value.find_pending_order_for_depot = AsyncMock(return_value=None)
        result = await handler.handle(driver, txt_msg("available"))

    assert len(result.messages) == 1
    assert "already" in result.messages[0].body.lower()


async def test_mark_offline_when_available_sets_status_and_returns_now_offline():
    driver = make_driver(status=DriverStatus.AVAILABLE)
    handler, _, session_mock, _ = make_handler()
    result = await handler.handle(driver, txt_msg("offline"))

    assert len(result.messages) == 1
    assert "offline" in result.messages[0].body.lower()
    session_mock.execute.assert_awaited()


async def test_mark_offline_when_already_offline_returns_already_offline():
    driver = make_driver(status=DriverStatus.OFFLINE)
    handler, *_ = make_handler()
    result = await handler.handle(driver, txt_msg("offline"))

    assert len(result.messages) == 1
    assert "already" in result.messages[0].body.lower()


async def test_mark_available_rejected_when_on_delivery():
    driver = make_driver(status=DriverStatus.ON_DELIVERY)
    d = delivery_record()
    handler, *_ = make_handler({f"driver_delivery:{driver.phone_number}": d})
    result = await handler.handle(driver, txt_msg("available"))

    assert len(result.messages) == 1
    assert "delivery" in result.messages[0].body.lower()


async def test_mark_offline_rejected_when_on_delivery():
    driver = make_driver(status=DriverStatus.ON_DELIVERY)
    d = delivery_record()
    handler, *_ = make_handler({f"driver_delivery:{driver.phone_number}": d})
    result = await handler.handle(driver, txt_msg("offline"))

    assert len(result.messages) == 1
    assert "delivery" in result.messages[0].body.lower()


async def test_mark_available_rejected_when_pending_acceptance():
    driver = make_driver(status=DriverStatus.PENDING_ACCEPTANCE)
    offer = fresh_offer()
    handler, *_ = make_handler({f"driver_offer:{driver.phone_number}": offer})
    result = await handler.handle(driver, txt_msg("available"))

    assert len(result.messages) == 1
    # message should explain they have a pending offer
    assert len(result.messages[0].body) > 0


async def test_availability_dispatches_pending_order_if_waiting():
    driver = make_driver(status=DriverStatus.OFFLINE)
    handler, redis_mock, session_mock, whatsapp_mock = make_handler()

    from src.models import Order, OrderStatus
    pending_order = MagicMock(spec=Order)
    pending_order.id = uuid4()
    pending_order.order_number = "FO-20260416-001"
    pending_order.shop_id = uuid4()
    pending_order.depot_id = driver.depot_id
    pending_order.fuel_type = MagicMock()
    pending_order.fuel_type.value = "diesel"
    pending_order.quantity_liters = 50
    pending_order.delivery_address = "1 Main St"
    pending_order.status = OrderStatus.CONFIRMED

    shop_mock = MagicMock()
    shop_mock.phone_number = "27821234567"

    coords_result = MagicMock()
    coords_result.fetchone = MagicMock(return_value=(-26.2041, 28.0473))

    async def fake_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=shop_mock)
        return result

    session_mock.execute = AsyncMock(side_effect=fake_execute)

    with patch("src.services.DispatchService") as MockDS, \
         patch("src.conversation.driver_handlers._send_offer", new=AsyncMock(return_value=True)):
        MockDS.return_value.find_pending_order_for_depot = AsyncMock(return_value=pending_order)
        result = await handler.handle(driver, txt_msg("available"))

    assert len(result.messages) == 1
    assert "available" in result.messages[0].body.lower()


# ---------------------------------------------------------------------------
# messaging window tracking
# ---------------------------------------------------------------------------

async def test_messaging_window_set_on_every_message():
    driver = make_driver()
    handler, redis_mock, *_ = make_handler()
    await handler.handle(driver, txt_msg("hello"))

    redis_mock.set.assert_awaited_once()
    call = redis_mock.set.call_args
    assert f"driver_window:{driver.phone_number}" in call.args or \
           call.args[0] == f"driver_window:{driver.phone_number}"


async def test_messaging_window_redis_failure_does_not_raise():
    driver = make_driver()
    handler, redis_mock, *_ = make_handler()
    redis_mock.set = AsyncMock(side_effect=Exception("redis down"))

    result = await handler.handle(driver, txt_msg("hello"))
    assert isinstance(result.messages[0], TextMessage)
