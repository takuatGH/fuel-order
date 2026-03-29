"""message handler - orchestrates intent parsing, fsm transitions, and responses.

this is the glue layer that:
1. loads conversation state from redis
2. parses incoming messages into intents
3. triggers fsm transitions
4. collects response messages
5. persists state back to redis
6. returns messages for the webhook to send

design principle: this layer knows about redis, fsm, and intents,
but the components themselves remain decoupled from each other.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as redis

from .states import OrderFlow, OrderState
from .intents import IntentParser, ParsedIntent


logger = logging.getLogger(__name__)


# session ttl in seconds (1 hour)
SESSION_TTL = 3600


@dataclass
class HandlerResult:
    """result of handling a message."""
    messages: list[str] = field(default_factory=list)  # messages to send back
    order_created: bool = False                         # true if order was placed
    order_draft: dict | None = None                     # draft data if order created


class MessageHandler:
    """
    orchestrates conversation flow for a single user.
    
    usage:
        handler = MessageHandler(redis_client)
        result = await handler.handle(
            phone_number="+27821234567",
            message={"type": "text", "text": {"body": "diesel"}}
        )
        # result.messages = ["Got it, Diesel. How many liters?"]
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.parser = IntentParser()
    
    async def handle(
        self,
        phone_number: str,
        message: dict,
    ) -> HandlerResult:
        """
        process an incoming whatsapp message.
        
        args:
            phone_number: user's phone number (e.g., "+27821234567")
            message: whatsapp message object with type and content
        
        returns:
            HandlerResult with messages to send and order status
        """
        result = HandlerResult()
        collected_messages: list[str] = []
        
        # load or create conversation flow
        flow = await self._load_flow(phone_number)
        
        # register message collector callback
        flow.message_callback = lambda msg: collected_messages.append(msg)
        
        # parse intent based on current state
        parsed = self.parser.parse(message, current_state=flow.state)
        
        logger.info(
            f"[{phone_number}] state={flow.state}, "
            f"intent={parsed.intent}, value={parsed.value}"
        )
        
        # handle the intent
        if parsed.intent == "help":
            collected_messages.append(self._help_message())
        
        elif parsed.intent == "unknown":
            collected_messages.append(self._unknown_message(flow.state))
        
        elif parsed.intent.startswith("invalid_"):
            collected_messages.append(self._error_message(parsed.intent, flow.state))
        
        else:
            # attempt fsm transition
            success = flow.process_input(parsed.value, parsed.intent)
            
            if not success:
                # transition failed (shouldn't happen if intent parser is correct)
                logger.warning(
                    f"[{phone_number}] transition failed: "
                    f"state={flow.state}, intent={parsed.intent}"
                )
                collected_messages.append(self._reprompt_message(flow.state))
        
        # check if order was placed
        if flow.state == OrderState.ORDER_PLACED.value:
            result.order_created = True
            result.order_draft = flow.draft.to_dict()
            # auto-reset for next order
            flow.reset()
        
        # persist state
        await self._save_flow(phone_number, flow)
        
        result.messages = collected_messages
        return result
    
    async def _load_flow(self, phone_number: str) -> OrderFlow:
        """load conversation flow from redis, or create new."""
        key = f"session:{phone_number}"
        data = await self.redis.hgetall(key)
        
        if data:
            # redis returns bytes, decode to strings
            decoded = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()
            }
            return OrderFlow.from_session_data(phone_number, decoded)
        
        return OrderFlow(phone_number=phone_number)
    
    async def _save_flow(self, phone_number: str, flow: OrderFlow):
        """persist conversation flow to redis with ttl."""
        key = f"session:{phone_number}"
        session_data = flow.to_session_data()
        
        await self.redis.hset(key, mapping=session_data)
        await self.redis.expire(key, SESSION_TTL)
    
    def _help_message(self) -> str:
        """return help/menu message."""
        return (
            "🛢️ *FuelFlow Help*\n\n"
            "I can help you order fuel for delivery.\n\n"
            "*Commands:*\n"
            "• Send *order* or *fuel* to start a new order\n"
            "• Send *cancel* anytime to cancel current order\n"
            "• Send *help* to see this message\n\n"
            "*Order Process:*\n"
            "1. Choose fuel type (Diesel/Petrol/Paraffin)\n"
            "2. Enter quantity (10-10,000 liters)\n"
            "3. Share delivery location\n"
            "4. Confirm order\n\n"
            "Ready? Send *order* to begin!"
        )
    
    def _unknown_message(self, current_state: str) -> str:
        """return appropriate message for unrecognized input."""
        if current_state == OrderState.IDLE.value:
            return (
                "👋 Hi! I'm FuelFlow, your fuel delivery assistant.\n\n"
                "Send *order* to place a fuel order, or *help* for more options."
            )
        
        # if in middle of flow, re-prompt current state
        return self._reprompt_message(current_state)
    
    def _error_message(self, error_intent: str, current_state: str) -> str:
        """return error-specific message."""
        if error_intent == "invalid_fuel_type":
            return (
                "Sorry, I didn't recognize that fuel type.\n\n"
                "Please reply with:\n"
                "• *Diesel*\n"
                "• *Petrol*\n"
                "• *Paraffin*"
            )
        
        if error_intent == "invalid_quantity":
            return (
                "I couldn't understand that quantity.\n\n"
                "Please enter a number, like:\n"
                "• *200* or *200 liters*\n"
                "• *500L*"
            )
        
        if error_intent == "invalid_quantity_range":
            return (
                "That quantity is outside our delivery range.\n\n"
                "We deliver between *10* and *10,000 liters*.\n"
                "Please enter a quantity in that range."
            )
        
        if error_intent == "invalid_location":
            return (
                "I couldn't understand that location.\n\n"
                "Please either:\n"
                "📍 Share your location using WhatsApp's location feature\n"
                "📝 Or type your full address"
            )
        
        if error_intent == "invalid_confirmation":
            return (
                "Please reply with *Yes* to confirm your order, "
                "or *Cancel* to start over."
            )
        
        # generic fallback
        return self._reprompt_message(current_state)
    
    def _reprompt_message(self, current_state: str) -> str:
        """re-ask current state's question."""
        prompts = {
            OrderState.AWAITING_FUEL_TYPE.value: (
                "What type of fuel do you need?\n\n"
                "Reply with *Diesel*, *Petrol*, or *Paraffin*."
            ),
            OrderState.AWAITING_QUANTITY.value: (
                "How many liters do you need?\n"
                "(Between 10 and 10,000 liters)"
            ),
            OrderState.AWAITING_LOCATION.value: (
                "Where should we deliver?\n\n"
                "📍 Share your location or type your address."
            ),
            OrderState.AWAITING_CONFIRMATION.value: (
                "Reply *Yes* to confirm or *Cancel* to start over."
            ),
        }
        
        return prompts.get(
            current_state,
            "Send *order* to place a fuel order, or *help* for options."
        )