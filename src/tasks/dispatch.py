"""
Async dispatch task — runs in the ARQ worker process.

Moves the heavy work (depot lookup, driver selection, WhatsApp offer) off the
webhook request path so the webhook can return 200 immediately.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models import Order, OrderStatus, ShopProfile
from src.services import DispatchService, WhatsAppClient
from src.services.whatsapp import WhatsAppError
from src.conversation import responses
from src.conversation.driver_handlers import _send_offer

logger = logging.getLogger(__name__)


async def dispatch_order(ctx: dict, *, order_id: str, shop_phone: str, draft: dict) -> None:
    """
    ARQ task: find the nearest depot, pick an available driver with an open
    messaging window, and send a job offer.  If no driver is reachable right
    now the order stays in CONFIRMED state — _handle_availability will pick
    it up when a driver next signals availability.

    ctx is injected by ARQ and contains:
        ctx["redis"]    — arq's own redis connection
        ctx["session"]  — AsyncSession created in WorkerSettings.on_startup
        ctx["whatsapp"] — WhatsAppClient created in WorkerSettings.on_startup
    """
    session: AsyncSession = ctx["session"]
    whatsapp: WhatsAppClient = ctx["whatsapp"]
    redis_client = ctx["redis"]

    # Re-fetch order to make sure it hasn't already been dispatched by a
    # concurrent task (e.g. duplicate webhook delivery)
    order = await session.get(Order, UUID(order_id))
    if order is None:
        logger.error(f"dispatch_order: order {order_id} not found")
        return
    if order.status != OrderStatus.CONFIRMED:
        logger.info(f"dispatch_order: order {order_id} is {order.status}, skipping")
        return

    lat = draft.get("latitude", -26.2041)
    lng = draft.get("longitude", 28.0473)
    fuel_type = draft["fuel_type"]

    dispatch_service = DispatchService(session)
    depot = await dispatch_service.find_nearest_depot(
        latitude=lat,
        longitude=lng,
        fuel_type=fuel_type,
    )

    if not depot:
        logger.warning(f"dispatch_order: no depot for order {order_id}")
        try:
            await whatsapp.send_text_message(
                to=shop_phone,
                text="Sorry, no depot is available in your area for this fuel type.",
            )
        except WhatsAppError as e:
            logger.error(f"failed to notify shop of no depot: {e}")
        return

    # Assign depot on the order if not already set
    if order.depot_id != depot.id:
        from src.services import OrderService
        order_service = OrderService(session)
        await order_service.assign_depot(order.id, depot.id)

    offer_data = {
        "order_id": order_id,
        "order_number": order.order_number,
        "shop_phone": shop_phone,
        "fuel_type": fuel_type,
        "quantity_liters": str(draft["quantity_liters"]),
        "delivery_address": draft.get("delivery_address", ""),
        "delivery_lat": str(lat),
        "delivery_lng": str(lng),
        "depot_id": str(depot.id),
    }

    drivers = await dispatch_service.find_available_drivers(depot.id)
    sent = False
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

    if not sent:
        logger.info(
            f"dispatch_order: no driver with open window for order {order_id}, "
            "order stays confirmed — will dispatch when a driver comes online"
        )

    await session.commit()
