"""finite state machine for order conversation flow.

the fsm tracks where a user is in the ordering process and what
data they've provided so far. state is persisted to redis between
webhook requests since whatsapp is stateless.

key concepts:
- states: discrete steps in the order flow (idle, awaiting_fuel_type, etc)
- transitions: rules for moving between states based on user input
- draft: accumulated order data as user progresses through flow
- callbacks: actions triggered by state transitions (send messages, validate, etc)
"""
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable

from transitions import Machine


class OrderState(str, Enum):
    """all possible states in the order conversation flow."""
    IDLE = "idle"
    AWAITING_FUEL_TYPE = "awaiting_fuel_type"
    AWAITING_QUANTITY = "awaiting_quantity"
    AWAITING_LOCATION = "awaiting_location"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ORDER_PLACED = "order_placed"


@dataclass
class OrderDraft:
    """accumulates order data as user progresses through the flow."""
    fuel_type: str | None = None
    quantity_liters: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    
    def to_dict(self) -> dict:
        return {
            "fuel_type": self.fuel_type,
            "quantity_liters": self.quantity_liters,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "OrderDraft":
        return cls(
            fuel_type=data.get("fuel_type"),
            quantity_liters=data.get("quantity_liters"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
        )
    
    def is_complete(self) -> bool:
        """true if all required fields are populated."""
        return all([
            self.fuel_type is not None,
            self.quantity_liters is not None,
            self.latitude is not None,
            self.longitude is not None,
        ])


class OrderFlow:
    """
    finite state machine for managing order conversations.
    
    usage:
        flow = OrderFlow(phone_number="+27821234567")
        flow.start_order()        # transitions idle → awaiting_fuel_type
        flow.fuel_selected()      # transitions → awaiting_quantity (if valid)
        ...
    
    the machine auto-generates trigger methods (start_order, fuel_selected, etc)
    based on the transitions list.
    """
    
    # all possible states
    states = [s.value for s in OrderState]
    
    # transition definitions
    # format: trigger name, source state(s), destination state, optional conditions/callbacks
    transitions = [
        # starting an order
        {
            "trigger": "start_order",
            "source": OrderState.IDLE.value,
            "dest": OrderState.AWAITING_FUEL_TYPE.value,
            "after": "on_awaiting_fuel_type",
        },
        
        # fuel type provided
        {
            "trigger": "fuel_selected",
            "source": OrderState.AWAITING_FUEL_TYPE.value,
            "dest": OrderState.AWAITING_QUANTITY.value,
            "conditions": "is_valid_fuel_type",
            "before": "save_fuel_type",
            "after": "on_awaiting_quantity",
        },
        
        # quantity provided
        {
            "trigger": "quantity_provided",
            "source": OrderState.AWAITING_QUANTITY.value,
            "dest": OrderState.AWAITING_LOCATION.value,
            "conditions": "is_valid_quantity",
            "before": "save_quantity",
            "after": "on_awaiting_location",
        },
        
        # location provided
        {
            "trigger": "location_provided",
            "source": OrderState.AWAITING_LOCATION.value,
            "dest": OrderState.AWAITING_CONFIRMATION.value,
            "conditions": "is_valid_location",
            "before": "save_location",
            "after": "on_awaiting_confirmation",
        },
        
        # order confirmed
        {
            "trigger": "confirm_order",
            "source": OrderState.AWAITING_CONFIRMATION.value,
            "dest": OrderState.ORDER_PLACED.value,
            "after": "on_order_placed",
        },
        
        # cancel from any state (except idle and order_placed)
        {
            "trigger": "cancel",
            "source": [
                OrderState.AWAITING_FUEL_TYPE.value,
                OrderState.AWAITING_QUANTITY.value,
                OrderState.AWAITING_LOCATION.value,
                OrderState.AWAITING_CONFIRMATION.value,
            ],
            "dest": OrderState.IDLE.value,
            "before": "reset_draft",
            "after": "on_cancelled",
        },
        
        # reset after order placed (for new order)
        {
            "trigger": "reset",
            "source": OrderState.ORDER_PLACED.value,
            "dest": OrderState.IDLE.value,
            "before": "reset_draft",
        },
    ]
    
    def __init__(
        self,
        phone_number: str,
        initial_state: str = OrderState.IDLE.value,
        initial_draft: dict | None = None,
    ):
        self.phone_number = phone_number
        self.draft = OrderDraft.from_dict(initial_draft or {})
        
        # message_callback will be set by the handler layer
        # it's called whenever we need to send a whatsapp message
        self.message_callback: Callable[[str], None] | None = None
        
        # current input being processed (set before triggering transitions)
        self._current_input: Any = None
        
        # initialize the state machine
        self.machine = Machine(
            model=self,
            states=self.states,
            transitions=self.transitions,
            initial=initial_state,
            send_event=True,  # pass event data to callbacks
        )
    
    # --- validation conditions ---
    # these return True/False and gate whether a transition can proceed
    
    def is_valid_fuel_type(self, event) -> bool:
        """validate that input is a recognized fuel type."""
        valid_types = {"diesel", "petrol", "paraffin"}
        value = str(self._current_input).lower().strip()
        return value in valid_types
    
    def is_valid_quantity(self, event) -> bool:
        """validate quantity is a positive number within business limits."""
        try:
            qty = float(self._current_input)
            return 10.0 <= qty <= 10000.0  # min 10L, max 10,000L
        except (ValueError, TypeError):
            return False
    
    def is_valid_location(self, event) -> bool:
        """validate location data is present."""
        # for now, accept any non-empty input
        # in production, this would validate coordinates or address
        return bool(self._current_input)
    
    # --- before callbacks: save data to draft ---
    
    def save_fuel_type(self, event):
        """save validated fuel type to draft."""
        self.draft.fuel_type = str(self._current_input).lower().strip()
    
    def save_quantity(self, event):
        """save validated quantity to draft."""
        self.draft.quantity_liters = float(self._current_input)
    
    def save_location(self, event):
        """save location to draft."""
        # simplified: in production, parse lat/lng from whatsapp location message
        # for now, store as coordinates if dict, or parse text
        if isinstance(self._current_input, dict):
            self.draft.latitude = self._current_input.get("latitude")
            self.draft.longitude = self._current_input.get("longitude")
        else:
            # placeholder: would geocode address text
            self.draft.latitude = -26.2041
            self.draft.longitude = 28.0473
    
    def reset_draft(self, event):
        """clear the draft on cancel or reset."""
        self.draft = OrderDraft()
    
    # --- after callbacks: respond to user ---
    # these are stubs—the actual message sending is handled by the handler layer
    
    def on_awaiting_fuel_type(self, event):
        """called after transitioning to awaiting_fuel_type."""
        self._send_message(
            "What type of fuel do you need?\n\n"
            "Reply with:\n"
            "• *Diesel*\n"
            "• *Petrol*\n"
            "• *Paraffin*"
        )
    
    def on_awaiting_quantity(self, event):
        """called after transitioning to awaiting_quantity."""
        self._send_message(
            f"Got it, *{self.draft.fuel_type.title()}*.\n\n"
            "How many liters do you need?\n"
            "(Min: 10L, Max: 10,000L)"
        )
    
    def on_awaiting_location(self, event):
        """called after transitioning to awaiting_location."""
        self._send_message(
            f"*{self.draft.quantity_liters:.0f} liters* of {self.draft.fuel_type}.\n\n"
            "Where should we deliver?\n\n"
            "📍 Send your location using WhatsApp's location sharing, "
            "or type your address."
        )
    
    def on_awaiting_confirmation(self, event):
        """called after transitioning to awaiting_confirmation."""
        self._send_message(
            "📋 *Order Summary*\n\n"
            f"• Fuel: {self.draft.fuel_type.title()}\n"
            f"• Quantity: {self.draft.quantity_liters:.0f} liters\n"
            f"• Location: {self.draft.latitude:.4f}, {self.draft.longitude:.4f}\n\n"
            "Reply *Yes* to confirm or *Cancel* to start over."
        )
    
    def on_order_placed(self, event):
        """called after order is confirmed."""
        self._send_message(
            "✅ *Order Placed!*\n\n"
            "We're finding the nearest depot to fulfill your order. "
            "You'll receive updates on delivery status."
        )
    
    def on_cancelled(self, event):
        """called after order is cancelled."""
        self._send_message(
            "❌ Order cancelled.\n\n"
            "Send *order* anytime to start a new order."
        )
    
    def _send_message(self, text: str):
        """internal: dispatch message via callback if registered."""
        if self.message_callback:
            self.message_callback(text)
    
    # --- serialization for redis persistence ---
    
    def to_session_data(self) -> dict:
        """serialize current state and draft for redis storage."""
        return {
            "state": self.state,
            "draft": json.dumps(self.draft.to_dict()),
        }
    
    @classmethod
    def from_session_data(cls, phone_number: str, data: dict) -> "OrderFlow":
        """restore flow from redis session data."""
        return cls(
            phone_number=phone_number,
            initial_state=data.get("state", OrderState.IDLE.value),
            initial_draft=json.loads(data.get("draft", "{}")),
        )
    
    # --- helper for processing input ---
    
    def process_input(self, user_input: Any, intent: str) -> bool:
        """
        attempt to trigger a transition based on parsed intent.
        
        args:
            user_input: the raw or parsed value from user message
            intent: the intent name matching a trigger (e.g., "fuel_selected")
        
        returns:
            True if transition succeeded, False otherwise
        """
        self._current_input = user_input
        
        # get the trigger method dynamically
        trigger_fn = getattr(self, intent, None)
        if trigger_fn and callable(trigger_fn):
            try:
                return trigger_fn()
            except Exception:
                return False
        return False