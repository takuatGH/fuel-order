import logging
from dataclasses import dataclass, field

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from .states import OrderFlow, OrderState
from .intents import IntentParser
from .responses import OutboundMessage
from . import responses
from src.services.geocoding import GeocodingService
from src.models import OrderStatus


logger = logging.getLogger(__name__)

SESSION_TTL = 3600


@dataclass
class HandlerResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    order_created: bool = False
    order_draft: dict | None = None
    events: list[dict] = field(default_factory=list)


class MessageHandler:

    def __init__(self, redis_client: redis.Redis, session: AsyncSession | None = None):
        self.redis = redis_client
        self.session = session
        self.parser = IntentParser()
        self.geocoding = GeocodingService(redis_client)

    async def handle(self, phone_number: str, message: dict) -> HandlerResult:
        result = HandlerResult()
        collected_messages: list[OutboundMessage] = []

        flow = await self._load_flow(phone_number)
        flow.message_callback = lambda msg: collected_messages.append(msg)

        parsed = self.parser.parse(message, current_state=flow.state)

        logger.info(f"[{phone_number}] state={flow.state}, intent={parsed.intent}, value={parsed.value}")

        # geocode before process_input so delivery_address is set when on_awaiting_confirmation fires
        if parsed.intent == "location_provided" and isinstance(parsed.value, dict):
            coords = parsed.value
            address = await self.geocoding.reverse_geocode(coords["latitude"], coords["longitude"])
            flow.draft.delivery_address = address or f"GPS: {coords['latitude']:.4f}, {coords['longitude']:.4f}"

        if parsed.intent == "help":
            collected_messages.append(responses.help_message())

        elif parsed.intent == "check_status":
            collected_messages.append(await self._handle_check_status(phone_number))

        elif parsed.intent == "cancel_last_order":
            collected_messages.append(await self._handle_cancel_last_order(phone_number))

        elif parsed.intent == "unknown":
            if flow.state == OrderState.IDLE.value:
                flow.process_input(None, "start_order")
            else:
                collected_messages.append(responses.reprompt(flow.state, draft=flow.draft))

        elif parsed.intent.startswith("invalid_"):
            if parsed.intent == "invalid_fuel_type":
                collected_messages.append(responses.invalid_fuel_type_error())
            elif parsed.intent in ("invalid_quantity", "invalid_quantity_range"):
                collected_messages.append(responses.invalid_quantity_error(flow.draft.fuel_type))
            elif parsed.intent == "invalid_confirmation":
                collected_messages.append(responses.invalid_confirmation_error())
            else:
                collected_messages.append(responses.reprompt(flow.state, draft=flow.draft))

        else:
            # Route to edit-mode trigger when user is editing a single field
            _EDIT_TRIGGER = {
                "fuel_selected": "fuel_selected_edit",
                "quantity_provided": "quantity_provided_edit",
                "location_provided": "location_provided_edit",
            }
            trigger = _EDIT_TRIGGER.get(parsed.intent, parsed.intent) if flow.draft.is_editing else parsed.intent

            success = flow.process_input(parsed.value, trigger)
            if not success:
                logger.warning(f"[{phone_number}] transition failed: state={flow.state}, intent={parsed.intent}")
                collected_messages.append(responses.reprompt(flow.state, draft=flow.draft))

        result.events = flow.pending_events
        flow.pending_events = []

        if flow.state == OrderState.ORDER_PLACED.value:
            result.order_created = True
            result.order_draft = flow.draft.to_dict()
            flow.reset()

        await self._save_flow(phone_number, flow)

        result.messages = collected_messages
        return result

    async def _load_flow(self, phone_number: str) -> OrderFlow:
        key = f"session:{phone_number}"
        data = await self.redis.hgetall(key)
        if data:
            decoded = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()
            }
            return OrderFlow.from_session_data(phone_number, decoded)
        return OrderFlow(phone_number=phone_number)

    async def _save_flow(self, phone_number: str, flow: OrderFlow):
        key = f"session:{phone_number}"
        await self.redis.hset(key, mapping=flow.to_session_data())
        await self.redis.expire(key, SESSION_TTL)

    async def _handle_check_status(self, phone_number: str) -> OutboundMessage:
        if not self.session:
            return responses.no_recent_orders()
        from src.services.identity import IdentityService
        from src.services.orders import OrderService
        shop = await IdentityService(self.session).get_or_create_shop(phone_number)
        order = await OrderService(self.session).get_latest_order_by_shop(shop.id)
        if not order:
            return responses.no_recent_orders()
        driver_name = plate = None
        if order.assignment and order.assignment.driver:
            driver_name = order.assignment.driver.name
            plate = order.assignment.driver.vehicle_plate
        return responses.order_status_message(
            order.order_number,
            order.status.value,
            order.fuel_type.value,
            float(order.quantity_liters),
            driver_name,
            plate,
        )

    async def _handle_cancel_last_order(self, phone_number: str) -> OutboundMessage:
        if not self.session:
            return responses.no_recent_orders()
        from src.services.identity import IdentityService
        from src.services.orders import OrderService
        shop = await IdentityService(self.session).get_or_create_shop(phone_number)
        order_service = OrderService(self.session)
        order = await order_service.get_latest_order_by_shop(shop.id)
        if not order:
            return responses.no_recent_orders()
        if order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
            return responses.order_cancel_denied_final(order.order_number, order.status.value)
        if order.status == OrderStatus.DISPATCHED:
            return responses.order_cancel_denied_dispatched(order.order_number)
        await order_service.cancel_order(order.id)
        await self.session.commit()
        return responses.order_cancel_confirmed(order.order_number)
