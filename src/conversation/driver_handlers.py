import logging
import math
from datetime import datetime, timezone, timedelta
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models import Driver, DriverStatus, Order, OrderStatus, DeliveryAssignment, AssignmentStatus
from src.services import WhatsAppClient
from .intents import IntentParser
from .handlers import HandlerResult
from . import responses


logger = logging.getLogger(__name__)

DRIVER_OFFER_TTL = 300
DRIVER_DELIVERY_TTL = 28800
DRIVER_WINDOW_TTL = 86400  # 24 hours in seconds
DELIVERY_PROXIMITY_THRESHOLD_M = 500


class DriverMessageHandler:

    def __init__(self, redis_client: redis.Redis, session: AsyncSession, whatsapp: WhatsAppClient):
        self.redis = redis_client
        self.session = session
        self.whatsapp = whatsapp
        self.parser = IntentParser()

    async def handle(self, driver: Driver, message: dict) -> HandlerResult:
        # Track messaging window at the start
        await self._track_messaging_window(driver.phone_number)

        # Determine current state for intent parsing
        offer = await self._load_key(f"driver_offer:{driver.phone_number}")
        delivery = await self._load_key(f"driver_delivery:{driver.phone_number}")

        if offer:
            current_state = "pending_acceptance"
        elif delivery:
            current_state = "on_delivery"
        else:
            current_state = "idle"

        # Parse message to get intent
        parsed = self.parser.parse(message, current_state=current_state)

        # Route availability intents (can be handled in any state)
        if parsed.intent in ("mark_available", "mark_offline"):
            return await self._handle_availability(driver, parsed.intent)

        # Route help intent
        if parsed.intent == "help":
            return HandlerResult(messages=[responses.driver_help_message()])

        # Existing flow for job offers
        if offer:
            if _is_timed_out(offer):
                await _set_driver_status(self.session, driver.id, DriverStatus.AVAILABLE)
                await self.redis.delete(f"driver_offer:{driver.phone_number}")
                return HandlerResult(messages=[responses.driver_offer_expired()])

            if parsed.intent == "accept_job":
                return await self._accept(driver, offer)
            elif parsed.intent == "decline_job":
                return await self._decline(driver, offer)
            else:
                return HandlerResult(messages=[responses.driver_job_offer(
                    offer["order_number"],
                    offer["fuel_type"],
                    float(offer["quantity_liters"]),
                    offer.get("delivery_address") or offer["order_number"],
                )])

        # Existing flow for deliveries
        if delivery:
            return await self._handle_delivery(driver, message, delivery)

        return HandlerResult(messages=[responses.driver_no_active_offer()])

    async def _accept(self, driver: Driver, offer: dict) -> HandlerResult:
        order_id = UUID(offer["order_id"])
        assignment = await _create_assignment(self.session, order_id, driver.id)
        await self.redis.delete(f"driver_offer:{driver.phone_number}")

        delivery_payload = {
            "order_id": offer["order_id"],
            "order_number": offer["order_number"],
            "shop_phone": offer["shop_phone"],
            "delivery_lat": offer.get("delivery_lat", ""),
            "delivery_lng": offer.get("delivery_lng", ""),
            "fuel_type": offer.get("fuel_type", ""),
            "quantity_liters": offer.get("quantity_liters", "0"),
            "delivery_address": offer.get("delivery_address", ""),
            "assignment_id": str(assignment.id),
        }
        await self.redis.hset(f"driver_delivery:{driver.phone_number}", mapping=delivery_payload)
        await self.redis.expire(f"driver_delivery:{driver.phone_number}", DRIVER_DELIVERY_TTL)

        await self.whatsapp.send_text_message(
            to=offer["shop_phone"],
            text=responses.shop_driver_assigned(driver.name, driver.vehicle_plate).body,
        )
        await self.session.commit()

        address = offer.get("delivery_address") or offer["order_number"]
        return HandlerResult(messages=[responses.driver_job_confirmed(address)])

    async def _decline(self, driver: Driver, offer: dict) -> HandlerResult:
        await _set_driver_status(self.session, driver.id, DriverStatus.AVAILABLE)
        await self.redis.delete(f"driver_offer:{driver.phone_number}")

        attempt = int(offer.get("attempt", 1))
        depot_id = UUID(offer["depot_id"])
        shop_phone = offer["shop_phone"]
        settings = get_settings()

        if attempt < settings.max_driver_reassignment_attempts:
            next_drivers = await _find_next_drivers(self.session, depot_id, driver.id)
            for next_driver in next_drivers:
                sent = await _send_offer(self.redis, self.whatsapp, self.session, next_driver, offer, attempt + 1)
                if sent:
                    await self.session.commit()
                    return HandlerResult(messages=[responses.driver_job_declined()])

        await self.whatsapp.send_text_message(
            to=shop_phone,
            text=responses.shop_no_drivers_available(offer["order_number"]).body,
        )
        await self.session.commit()
        return HandlerResult(messages=[responses.driver_job_declined()])

    async def _handle_delivery(self, driver: Driver, message: dict, delivery: dict) -> HandlerResult:
        parsed = self.parser.parse(message, current_state="on_delivery")

        if parsed.intent == "delivery_confirmed":
            return await self._complete_delivery(driver, delivery)

        if parsed.intent == "location_provided" and isinstance(parsed.value, dict):
            try:
                dist_m = _haversine_m(
                    float(delivery["delivery_lat"]), float(delivery["delivery_lng"]),
                    parsed.value["latitude"], parsed.value["longitude"],
                )
                if dist_m <= DELIVERY_PROXIMITY_THRESHOLD_M:
                    return await self._complete_delivery(driver, delivery)
                return HandlerResult(messages=[responses.driver_delivery_location_warning(
                    dist_m, delivery["order_number"]
                )])
            except (ValueError, KeyError):
                return await self._complete_delivery(driver, delivery)

        if parsed.intent == "delivery_override_cancel":
            return HandlerResult(messages=[responses.driver_delivery_prompt()])

        return HandlerResult(messages=[responses.driver_delivery_prompt()])

    async def _complete_delivery(self, driver: Driver, delivery: dict) -> HandlerResult:
        assignment_id = UUID(delivery["assignment_id"])
        order_id = UUID(delivery["order_id"])
        shop_phone = delivery["shop_phone"]
        order_number = delivery["order_number"]

        await _complete_assignment(self.session, assignment_id, order_id, driver.id)
        await self.redis.delete(f"driver_delivery:{driver.phone_number}")

        await self.whatsapp.send_text_message(
            to=shop_phone,
            text=responses.shop_order_delivered(order_number).body,
        )

        settings = get_settings()
        if settings.admin_whatsapp_number:
            await self.whatsapp.send_text_message(
                to=settings.admin_whatsapp_number,
                text=responses.admin_order_completed(
                    order_number=order_number,
                    fuel_type=delivery.get("fuel_type", ""),
                    quantity=float(delivery.get("quantity_liters", 0)),
                    shop_phone=shop_phone,
                    driver_name=driver.name,
                    vehicle_plate=driver.vehicle_plate,
                    address=delivery.get("delivery_address", ""),
                ).body,
            )

        await self.session.commit()
        return HandlerResult(messages=[responses.driver_delivery_confirmed(order_number)])

    async def _handle_availability(self, driver: Driver, intent: str) -> HandlerResult:
        from src.services import DispatchService
        from src.models import ShopProfile
        from sqlalchemy import func, text

        if driver.status == DriverStatus.ON_DELIVERY:
            return HandlerResult(messages=[responses.driver_cannot_change_status_on_delivery()])

        if driver.status == DriverStatus.PENDING_ACCEPTANCE:
            return HandlerResult(messages=[responses.driver_cannot_change_status_pending()])

        if intent == "mark_offline":
            if driver.status == DriverStatus.OFFLINE:
                return HandlerResult(messages=[responses.driver_already_offline()])
            await _set_driver_status(self.session, driver.id, DriverStatus.OFFLINE)
            return HandlerResult(messages=[responses.driver_now_offline()])

        # mark_available
        was_offline = driver.status != DriverStatus.AVAILABLE
        if was_offline:
            await _set_driver_status(self.session, driver.id, DriverStatus.AVAILABLE)

        # Check for waiting orders at this driver's depot
        dispatch = DispatchService(self.session)
        pending_order = await dispatch.find_pending_order_for_depot(driver.depot_id)
        if pending_order:
            shop_result = await self.session.execute(
                select(ShopProfile).where(ShopProfile.id == pending_order.shop_id)
            )
            shop = shop_result.scalar_one_or_none()
            shop_phone = shop.phone_number if shop else ""

            # Extract lat/lng from PostGIS geometry
            coords_result = await self.session.execute(
                text("SELECT ST_Y(delivery_location::geometry), ST_X(delivery_location::geometry) FROM orders WHERE id = :oid"),
                {"oid": pending_order.id},
            )
            row = coords_result.fetchone()
            lat, lng = (row[0], row[1]) if row else (0.0, 0.0)

            offer_data = {
                "order_id": str(pending_order.id),
                "order_number": pending_order.order_number,
                "shop_phone": shop_phone,
                "fuel_type": pending_order.fuel_type.value,
                "quantity_liters": str(pending_order.quantity_liters),
                "delivery_address": pending_order.delivery_address or "",
                "delivery_lat": str(lat),
                "delivery_lng": str(lng),
                "depot_id": str(pending_order.depot_id),
            }
            sent = await _send_offer(self.redis, self.whatsapp, self.session, driver, offer_data)
            if sent:
                # Offer IS the notification — just confirm status change if needed
                return HandlerResult(messages=[responses.driver_now_available()] if was_offline else [])

        if not was_offline:
            return HandlerResult(messages=[responses.driver_already_available()])
        return HandlerResult(messages=[responses.driver_now_available()])

    async def _load_key(self, key: str) -> dict | None:
        data = await self.redis.hgetall(key)
        if not data:
            return None
        return {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }

    async def _track_messaging_window(self, phone_number: str) -> None:
        """
        Track the 24-hour WhatsApp messaging window.
        Sets a Redis key that expires after 24 hours.
        Best-effort: logs warning on failure but doesn't raise.
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            await self.redis.set(
                f"driver_window:{phone_number}",
                timestamp,
                ex=DRIVER_WINDOW_TTL
            )
        except Exception as e:
            logger.warning(f"Failed to track messaging window for {phone_number}: {e}")


async def _send_offer(
    redis_client: redis.Redis,
    whatsapp: WhatsAppClient,
    session: AsyncSession,
    driver: Driver,
    offer_data: dict,
    attempt: int = 1,
) -> bool:
    """Send a job offer to a driver. Returns False if the 24h messaging window is closed."""
    window = await redis_client.get(f"driver_window:{driver.phone_number}")
    if not window:
        logger.warning(f"driver {driver.phone_number} has no open messaging window, skipping offer")
        return False

    await _set_driver_status(session, driver.id, DriverStatus.PENDING_ACCEPTANCE)

    payload = {
        **offer_data,
        "attempt": str(attempt),
        "offer_sent_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.hset(f"driver_offer:{driver.phone_number}", mapping=payload)
    await redis_client.expire(f"driver_offer:{driver.phone_number}", DRIVER_OFFER_TTL)

    msg = responses.driver_job_offer(
        offer_data["order_number"],
        offer_data["fuel_type"],
        float(offer_data["quantity_liters"]),
        offer_data.get("delivery_address") or offer_data["order_number"],
    )
    await whatsapp.send_interactive_buttons(
        to=driver.phone_number,
        body_text=msg.body,
        buttons=msg.buttons,
        header_text=msg.header,
        footer_text=msg.footer,
    )
    return True


async def _create_assignment(session: AsyncSession, order_id: UUID, driver_id: UUID) -> DeliveryAssignment:
    await _set_driver_status(session, driver_id, DriverStatus.ON_DELIVERY)
    await session.execute(
        update(Order).where(Order.id == order_id).values(status=OrderStatus.DISPATCHED)
    )
    assignment = DeliveryAssignment(
        order_id=order_id,
        driver_id=driver_id,
        status=AssignmentStatus.ASSIGNED,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def _complete_assignment(
    session: AsyncSession,
    assignment_id: UUID,
    order_id: UUID,
    driver_id: UUID,
):
    await session.execute(
        update(DeliveryAssignment)
        .where(DeliveryAssignment.id == assignment_id)
        .values(status=AssignmentStatus.COMPLETED, completed_at=datetime.utcnow())
    )
    await session.execute(
        update(Order).where(Order.id == order_id).values(status=OrderStatus.DELIVERED)
    )
    await _set_driver_status(session, driver_id, DriverStatus.AVAILABLE)


async def _set_driver_status(session: AsyncSession, driver_id: UUID, status: DriverStatus):
    await session.execute(
        update(Driver).where(Driver.id == driver_id).values(status=status)
    )


async def _find_next_drivers(session: AsyncSession, depot_id: UUID, exclude_driver_id: UUID) -> list[Driver]:
    stmt = (
        select(Driver)
        .where(
            Driver.depot_id == depot_id,
            Driver.status == DriverStatus.AVAILABLE,
            Driver.id != exclude_driver_id,
        )
        .order_by(Driver.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _is_timed_out(offer: dict) -> bool:
    try:
        sent_at = datetime.fromisoformat(offer["offer_sent_at"])
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - sent_at > timedelta(seconds=DRIVER_OFFER_TTL)
    except (KeyError, ValueError):
        return False


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lng2 - lng1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))
