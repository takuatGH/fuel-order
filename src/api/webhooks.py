import hmac
import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, Request, HTTPException, Depends, Query, Header
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from src.config import get_settings
from src.conversation import MessageHandler, HandlerResult, DriverMessageHandler
from src.conversation.responses import OutboundMessage
from src.conversation import responses
from src.database import get_session
from src.services import WhatsAppClient, IdentityService, OrderService, DispatchService
from src.services.whatsapp import WhatsAppError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


async def get_redis() -> redis.Redis:
    settings = get_settings()
    client = redis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.close()


async def get_whatsapp_client() -> WhatsAppClient:
    settings = get_settings()
    return WhatsAppClient(
        phone_number_id=settings.whatsapp_phone_number_id,
        access_token=settings.whatsapp_access_token,
    )


@router.get("")
async def verify_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
):
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("webhook verified successfully")
        return PlainTextResponse(content=hub_challenge)
    logger.warning(f"webhook verification failed: mode={hub_mode}")
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("")
async def receive_message(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    redis_client: redis.Redis = Depends(get_redis),
    whatsapp: WhatsAppClient = Depends(get_whatsapp_client),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    body = await request.body()

    if settings.enable_signature_verification:
        if not _verify_signature(body, x_hub_signature_256, settings.whatsapp_webhook_secret):
            logger.warning("invalid webhook signature")
            raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="invalid json")

    message_data = _extract_message(payload)
    if not message_data:
        logger.debug("webhook event without message, ignoring")
        return {"status": "ok"}

    phone_number = message_data["from"]
    message = message_data["message"]
    logger.info(f"received message from {phone_number}: {message.get('type')}")

    identity_service = IdentityService(session)
    driver = await identity_service.get_driver_by_phone(phone_number)
    logger.info(f"driver lookup for {phone_number}: {'found' if driver else 'not found'}")

    if driver:
        handler = DriverMessageHandler(redis_client, session, whatsapp)
        result = await handler.handle(driver=driver, message=message)
        await session.commit()
    else:
        handler = MessageHandler(redis_client)
        result = await handler.handle(phone_number=phone_number, message=message)
    logger.info(f"handler result: {len(result.messages)} messages, intents processed")

    for msg in result.messages:
        await _send_outbound(whatsapp, phone_number, msg)

    if result.order_created and result.order_draft:
        order_number, driver_dispatched = await _persist_order(
            session=session,
            phone_number=phone_number,
            draft=result.order_draft,
            redis_client=redis_client,
            whatsapp=whatsapp,
        )
        logger.info(f"order {order_number} persisted for {phone_number}, driver dispatched: {driver_dispatched}")
        try:
            await whatsapp.send_text_message(
                to=phone_number,
                text=responses.order_placed_message(order_number).body,
            )
        except WhatsAppError as e:
            logger.error(f"failed to send order number to {phone_number}: {e.status_code} {e.error_data}")

    return {"status": "ok"}


async def _send_outbound(whatsapp: WhatsAppClient, to: str, msg: OutboundMessage):
    try:
        if msg.kind == "text":
            await whatsapp.send_text_message(to=to, text=msg.body)
        elif msg.kind == "buttons":
            await whatsapp.send_interactive_buttons(
                to=to,
                body_text=msg.body,
                buttons=msg.buttons,
                header_text=msg.header,
                footer_text=msg.footer,
            )
        elif msg.kind == "location_request":
            await whatsapp.send_location_request(to=to, body_text=msg.body)
    except WhatsAppError as e:
        logger.error(f"failed to send outbound message to {to}: {e.status_code} {e.error_data}")


async def _persist_order(
    session: AsyncSession,
    phone_number: str,
    draft: dict,
    redis_client: redis.Redis,
    whatsapp: WhatsAppClient,
) -> tuple[str, bool]:
    from src.conversation.driver_handlers import _send_offer

    lat = draft.get("latitude", -26.2041)
    lng = draft.get("longitude", 28.0473)

    identity_service = IdentityService(session)
    shop = await identity_service.get_or_create_shop(phone_number)

    order_service = OrderService(session)
    order = await order_service.create_order(
        shop_id=shop.id,
        fuel_type=draft["fuel_type"],
        quantity_liters=draft["quantity_liters"],
        latitude=lat,
        longitude=lng,
        delivery_address=draft.get("delivery_address"),
    )

    dispatch_service = DispatchService(session)
    depot = await dispatch_service.find_nearest_depot(
        latitude=lat,
        longitude=lng,
        fuel_type=draft["fuel_type"],
    )

    if not depot:
        await whatsapp.send_text_message(
            to=phone_number,
            text="Sorry, no depot is available in your area for this fuel type.",
        )
        await session.commit()
        return order.order_number, False

    await order_service.assign_depot(order.id, depot.id)

    offer_data = {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "shop_phone": phone_number,
        "fuel_type": draft["fuel_type"],
        "quantity_liters": str(draft["quantity_liters"]),
        "delivery_address": draft.get("delivery_address", ""),
        "delivery_lat": str(lat),
        "delivery_lng": str(lng),
        "depot_id": str(depot.id),
    }

    sent = False
    drivers = await dispatch_service.find_available_drivers(depot.id)
    for driver in drivers:
        sent = await _send_offer(
            redis_client=redis_client,
            whatsapp=whatsapp,
            session=session,
            driver=driver,
            offer_data=offer_data,
        )
        if sent:
            break

    await session.commit()
    return order.order_number, sent


def _verify_signature(body: bytes, signature_header: str | None, secret: str) -> bool:
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected_signature = signature_header[7:]
    computed = hmac.new(
        key=secret.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, expected_signature)


def _extract_message(payload: dict) -> dict | None:
    try:
        entry = payload.get("entry", [])
        if not entry:
            return None
        changes = entry[0].get("changes", [])
        if not changes:
            return None
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        return {
            "from": msg.get("from"),
            "message_id": msg.get("id"),
            "message": {
                "type": msg.get("type"),
                **{k: v for k, v in msg.items() if k not in ("from", "id", "timestamp", "type")}
            }
        }
    except (IndexError, KeyError, TypeError) as e:
        logger.error(f"failed to extract message from payload: {e}")
        return None
