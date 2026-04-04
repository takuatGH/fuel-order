import logging
from dataclasses import dataclass, field

import redis.asyncio as redis

from .states import OrderFlow, OrderState
from .intents import IntentParser
from .responses import OutboundMessage
from . import responses
from src.services.geocoding import GeocodingService


logger = logging.getLogger(__name__)

SESSION_TTL = 3600


@dataclass
class HandlerResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    order_created: bool = False
    order_draft: dict | None = None
    events: list[dict] = field(default_factory=list)


class MessageHandler:

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
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
        if parsed.intent == "location_provided":
            if isinstance(parsed.value, dict):
                coords = parsed.value
                flow.draft.delivery_address = await self.geocoding.reverse_geocode(
                    coords["latitude"], coords["longitude"]
                )
            elif isinstance(parsed.value, str):
                flow.draft.delivery_address = parsed.value

        if parsed.intent == "help":
            collected_messages.append(responses.help_message())

        elif parsed.intent == "unknown":
            if flow.state == OrderState.IDLE.value:
                flow.process_input(None, "start_order")
            else:
                collected_messages.append(responses.reprompt(flow.state))

        elif parsed.intent.startswith("invalid_"):
            if parsed.intent == "invalid_fuel_type":
                collected_messages.append(responses.invalid_fuel_type_error())
            elif parsed.intent in ("invalid_quantity", "invalid_quantity_range"):
                collected_messages.append(responses.invalid_quantity_error())
            elif parsed.intent == "invalid_confirmation":
                collected_messages.append(responses.invalid_confirmation_error())
            else:
                collected_messages.append(responses.reprompt(flow.state))

        else:
            success = flow.process_input(parsed.value, parsed.intent)
            if not success:
                logger.warning(f"[{phone_number}] transition failed: state={flow.state}, intent={parsed.intent}")
                collected_messages.append(responses.reprompt(flow.state))

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
