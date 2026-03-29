"""whatsapp webhook handlers.

handles incoming webhook events from meta's whatsapp cloud api:
- GET: webhook verification (one-time setup)
- POST: incoming messages, order creation, dispatch
"""
import hmac
import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, Request, HTTPException, Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from src.config import get_settings, Settings
from src.conversation import MessageHandler, HandlerResult
from src.database import get_session
from src.services import WhatsAppClient, IdentityService, OrderService, DispatchService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


async def get_redis() -> redis.Redis:
    """get redis client."""
    settings = get_settings()
    client = redis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.close()


async def get_whatsapp_client() -> WhatsAppClient:
    """get whatsapp api client."""
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
    """handle meta's webhook verification request."""
    settings = get_settings()
    
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("webhook verified successfully")
        return int(hub_challenge)
    
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
    """handle incoming whatsapp messages."""
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
    
    handler = MessageHandler(redis_client)
    result = await handler.handle(phone_number=phone_number, message=message)
    
    for msg_text in result.messages:
        await whatsapp.send_text_message(to=phone_number, text=msg_text)
    
    # persist order to database when conversation flow completes
    if result.order_created and result.order_draft:
        order_number = await _persist_order(
            session=session,
            phone_number=phone_number,
            draft=result.order_draft,
        )
        logger.info(f"order {order_number} persisted for {phone_number}")
        
        # send confirmation with order number
        await whatsapp.send_text_message(
            to=phone_number,
            text=f"📦 Your order number is *{order_number}*\nWe'll update you when a driver is assigned."
        )
    
    return {"status": "ok"}


async def _persist_order(
    session: AsyncSession,
    phone_number: str,
    draft: dict,
) -> str:
    """
    persist order from conversation flow to database.
    
    creates or finds shop profile, then creates order.
    returns the generated order number.
    """
    # get or create shop profile for this phone number
    identity_service = IdentityService(session)
    shop = await identity_service.get_or_create_shop(phone_number)
    
    # create the order
    order_service = OrderService(session)
    order = await order_service.create_order(
        shop_id=shop.id,
        fuel_type=draft["fuel_type"],
        quantity_liters=draft["quantity_liters"],
        latitude=draft.get("latitude", -26.2041),  # default to jhb
        longitude=draft.get("longitude", 28.0473),
    )
    
    # attempt dispatch (find depot, optionally assign driver)
    dispatch_service = DispatchService(session)
    depot, assignment = await dispatch_service.dispatch_order(
        order=order,
        latitude=draft.get("latitude", -26.2041),
        longitude=draft.get("longitude", 28.0473),
    )
    
    # commit all changes
    await session.commit()
    
    return order.order_number


def _verify_signature(body: bytes, signature_header: str | None, secret: str) -> bool:
    """verify meta's webhook signature."""
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
    """extract message data from webhook payload."""
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