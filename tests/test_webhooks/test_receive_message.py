"""Tests for the webhook receive_message endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from src.main import app


def make_whatsapp_payload(from_number: str, text: str, message_id: str = None) -> dict:
    message_id = message_id or f"wamid.{uuid4().hex}"
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": from_number,
                        "id": message_id,
                        "type": "text",
                        "text": {"body": text},
                    }]
                }
            }]
        }]
    }


def make_button_payload(from_number: str, button_id: str, message_id: str = None) -> dict:
    message_id = message_id or f"wamid.{uuid4().hex}"
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": from_number,
                        "id": message_id,
                        "type": "interactive",
                        "interactive": {
                            "type": "button_reply",
                            "button_reply": {"id": button_id, "title": button_id},
                        },
                    }]
                }
            }]
        }]
    }


@pytest.fixture
def mock_deps():
    """Patch all external dependencies so no real I/O happens."""
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)   # idempotency: new message
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.hgetall = AsyncMock(return_value={})

    session_mock = AsyncMock()
    session_mock.add = MagicMock()

    whatsapp_mock = AsyncMock()

    with patch("src.api.webhooks.get_redis", return_value=_async_gen(redis_mock)), \
         patch("src.api.webhooks.get_whatsapp_client", return_value=_async_gen(whatsapp_mock)), \
         patch("src.api.webhooks.get_session", return_value=_async_gen(session_mock)), \
         patch("src.services.IdentityService.get_driver_by_phone", new=AsyncMock(return_value=None)):
        yield {"redis": redis_mock, "session": session_mock, "whatsapp": whatsapp_mock}


async def _async_gen(value):
    yield value


async def test_duplicate_message_id_is_dropped():
    """Same message_id sent twice — second one is dropped before any processing."""
    msg_id = f"wamid.{uuid4().hex}"
    payload = make_whatsapp_payload("27799626597", "order", message_id=msg_id)

    seen: set[str] = set()

    async def fake_is_seen(redis_client, message_id: str) -> bool:
        if message_id in seen:
            return True
        seen.add(message_id)
        return False

    from src.conversation.handlers import HandlerResult
    handler_mock = AsyncMock(return_value=HandlerResult(messages=[]))

    async def fake_redis():
        yield AsyncMock()

    async def fake_whatsapp():
        yield AsyncMock()

    async def fake_session():
        yield AsyncMock()

    with patch("src.api.webhooks.is_already_seen", new=fake_is_seen), \
         patch("src.api.webhooks.get_redis", new=fake_redis), \
         patch("src.api.webhooks.get_whatsapp_client", new=fake_whatsapp), \
         patch("src.api.webhooks.get_session", new=fake_session), \
         patch("src.services.IdentityService.get_driver_by_phone", new=AsyncMock(return_value=None)), \
         patch("src.conversation.MessageHandler.handle", new=handler_mock):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post("/webhook", json=payload)
            r2 = await client.post("/webhook", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    # Handler only called once — second message dropped at idempotency check
    handler_mock.assert_awaited_once()


async def test_order_created_enqueues_job_not_direct_dispatch():
    """When state machine signals order_created, webhook enqueues an ARQ job."""
    from src.conversation.handlers import HandlerResult

    order_draft = {
        "fuel_type": "diesel",
        "quantity_liters": 50,
        "latitude": -26.2041,
        "longitude": 28.0473,
    }
    handler_result = HandlerResult(messages=[], order_created=True, order_draft=order_draft)

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.hgetall = AsyncMock(return_value={})

    session_mock = AsyncMock()
    session_mock.add = MagicMock()

    whatsapp_mock = AsyncMock()

    arq_mock = AsyncMock()
    enqueue_mock = AsyncMock()
    arq_mock.enqueue_job = enqueue_mock

    fake_order = MagicMock()
    fake_order.id = uuid4()
    fake_order.order_number = "FO-20260416-001"

    with patch("src.api.webhooks.get_redis", return_value=_async_gen(redis_mock)), \
         patch("src.api.webhooks.get_whatsapp_client", return_value=_async_gen(whatsapp_mock)), \
         patch("src.api.webhooks.get_session", return_value=_async_gen(session_mock)), \
         patch("src.services.IdentityService.get_driver_by_phone", new=AsyncMock(return_value=None)), \
         patch("src.conversation.MessageHandler.handle", new=AsyncMock(return_value=handler_result)), \
         patch("src.services.IdentityService.get_or_create_shop", new=AsyncMock(return_value=MagicMock(id=uuid4()))), \
         patch("src.services.OrderService.create_order", new=AsyncMock(return_value=fake_order)), \
         patch("src.api.webhooks.get_arq", new=AsyncMock(return_value=arq_mock)):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/webhook", json=make_whatsapp_payload("27799626597", "order"))

    assert r.status_code == 200
    enqueue_mock.assert_awaited_once()
    call_kwargs = enqueue_mock.call_args
    assert call_kwargs.args[0] == "dispatch_order"
    assert call_kwargs.kwargs["order_id"] == str(fake_order.id)


async def test_enqueue_failure_does_not_crash_webhook():
    """If ARQ is unavailable, webhook still returns 200 — order stays confirmed for later."""
    from src.conversation.handlers import HandlerResult

    order_draft = {"fuel_type": "diesel", "quantity_liters": 50,
                   "latitude": -26.2041, "longitude": 28.0473}
    handler_result = HandlerResult(messages=[], order_created=True, order_draft=order_draft)

    fake_order = MagicMock()
    fake_order.id = uuid4()
    fake_order.order_number = "FO-20260416-002"

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.hgetall = AsyncMock(return_value={})

    with patch("src.api.webhooks.get_redis", return_value=_async_gen(redis_mock)), \
         patch("src.api.webhooks.get_whatsapp_client", return_value=_async_gen(AsyncMock())), \
         patch("src.api.webhooks.get_session", return_value=_async_gen(AsyncMock())), \
         patch("src.services.IdentityService.get_driver_by_phone", new=AsyncMock(return_value=None)), \
         patch("src.conversation.MessageHandler.handle", new=AsyncMock(return_value=handler_result)), \
         patch("src.services.IdentityService.get_or_create_shop", new=AsyncMock(return_value=MagicMock(id=uuid4()))), \
         patch("src.services.OrderService.create_order", new=AsyncMock(return_value=fake_order)), \
         patch("src.api.webhooks.get_arq", new=AsyncMock(side_effect=Exception("redis down"))):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/webhook", json=make_whatsapp_payload("27799626597", "order"))

    assert r.status_code == 200


async def test_non_order_message_does_not_enqueue():
    """A regular conversational message (e.g. mid-flow) never enqueues a dispatch job."""
    from src.conversation.handlers import HandlerResult
    from src.conversation.responses import TextMessage

    handler_result = HandlerResult(
        messages=[TextMessage(body="How many litres do you need?")],
        order_created=False,
    )

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.hgetall = AsyncMock(return_value={})

    enqueue_mock = AsyncMock()

    with patch("src.api.webhooks.get_redis", return_value=_async_gen(redis_mock)), \
         patch("src.api.webhooks.get_whatsapp_client", return_value=_async_gen(AsyncMock())), \
         patch("src.api.webhooks.get_session", return_value=_async_gen(AsyncMock())), \
         patch("src.services.IdentityService.get_driver_by_phone", new=AsyncMock(return_value=None)), \
         patch("src.conversation.MessageHandler.handle", new=AsyncMock(return_value=handler_result)), \
         patch("src.api.webhooks.get_arq", new=AsyncMock()) as arq_mock:

        arq_mock.return_value.enqueue_job = enqueue_mock

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/webhook", json=make_whatsapp_payload("27799626597", "50"))

    assert r.status_code == 200
    enqueue_mock.assert_not_awaited()
