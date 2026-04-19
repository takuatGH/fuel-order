from __future__ import annotations

import json
from enum import Enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .responses import OutboundMessage


class OrderState(str, Enum):
    IDLE = "idle"
    AWAITING_FUEL_TYPE = "awaiting_fuel_type"
    AWAITING_QUANTITY = "awaiting_quantity"
    AWAITING_LOCATION = "awaiting_location"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_EDIT_FIELD = "awaiting_edit_field"
    ORDER_PLACED = "order_placed"


@dataclass
class OrderDraft:
    fuel_type: str | None = None
    quantity_liters: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    delivery_address: str | None = None
    is_editing: bool = False

    def to_dict(self) -> dict:
        return {
            "fuel_type": self.fuel_type,
            "quantity_liters": self.quantity_liters,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "delivery_address": self.delivery_address,
            "is_editing": self.is_editing,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderDraft":
        return cls(
            fuel_type=data.get("fuel_type"),
            quantity_liters=data.get("quantity_liters"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            delivery_address=data.get("delivery_address"),
            is_editing=bool(data.get("is_editing", False)),
        )

    def is_complete(self) -> bool:
        return all([
            self.fuel_type is not None,
            self.quantity_liters is not None,
            self.latitude is not None,
            self.longitude is not None,
        ])


class OrderFlow:
    """declarative FSM for order conversations. public API: process_input(user_input, intent) -> bool."""

    _TRANSITIONS = [
        {
            "trigger":   "start_order",
            "source":    "idle",
            "dest":      "awaiting_fuel_type",
            "condition": None,
            "before":    None,
            "after":     "on_awaiting_fuel_type",
        },
        {
            "trigger":   "fuel_selected",
            "source":    "awaiting_fuel_type",
            "dest":      "awaiting_quantity",
            "condition": "is_valid_fuel_type",
            "before":    "save_fuel_type",
            "after":     "on_awaiting_quantity",
        },
        {
            "trigger":   "quantity_provided",
            "source":    "awaiting_quantity",
            "dest":      "awaiting_location",
            "condition": "is_valid_quantity",
            "before":    "save_quantity",
            "after":     "on_awaiting_location",
        },
        {
            "trigger":   "location_provided",
            "source":    "awaiting_location",
            "dest":      "awaiting_confirmation",
            "condition": "is_valid_location",
            "before":    "save_location",
            "after":     "on_awaiting_confirmation",
        },
        {
            "trigger":   "confirm_order",
            "source":    "awaiting_confirmation",
            "dest":      "order_placed",
            "condition": None,
            "before":    None,
            "after":     "on_order_placed",
        },
        {
            "trigger":   "edit_order",
            "source":    "awaiting_confirmation",
            "dest":      "awaiting_edit_field",
            "condition": None,
            "before":    None,
            "after":     "on_awaiting_edit_field",
        },
        {
            "trigger":   "edit_fuel_type",
            "source":    "awaiting_edit_field",
            "dest":      "awaiting_fuel_type",
            "condition": None,
            "before":    "set_editing",
            "after":     "on_awaiting_fuel_type_edit",
        },
        {
            "trigger":   "edit_quantity",
            "source":    "awaiting_edit_field",
            "dest":      "awaiting_quantity",
            "condition": None,
            "before":    "set_editing",
            "after":     "on_awaiting_quantity",
        },
        {
            "trigger":   "edit_location",
            "source":    "awaiting_edit_field",
            "dest":      "awaiting_location",
            "condition": None,
            "before":    "set_editing",
            "after":     "on_awaiting_location",
        },
        {
            "trigger":   "fuel_selected_edit",
            "source":    "awaiting_fuel_type",
            "dest":      "awaiting_confirmation",
            "condition": "is_valid_fuel_type",
            "before":    "save_fuel_type_clear_edit",
            "after":     "on_awaiting_confirmation",
        },
        {
            "trigger":   "quantity_provided_edit",
            "source":    "awaiting_quantity",
            "dest":      "awaiting_confirmation",
            "condition": "is_valid_quantity",
            "before":    "save_quantity_clear_edit",
            "after":     "on_awaiting_confirmation",
        },
        {
            "trigger":   "location_provided_edit",
            "source":    "awaiting_location",
            "dest":      "awaiting_confirmation",
            "condition": "is_valid_location",
            "before":    "save_location_clear_edit",
            "after":     "on_awaiting_confirmation",
        },
        {
            "trigger":   "cancel",
            "source":    [
                "awaiting_fuel_type",
                "awaiting_quantity",
                "awaiting_location",
                "awaiting_confirmation",
                "awaiting_edit_field",
            ],
            "dest":      "idle",
            "condition": None,
            "before":    "reset_draft",
            "after":     "on_cancelled",
        },
        {
            "trigger":   "reset",
            "source":    "order_placed",
            "dest":      "idle",
            "condition": None,
            "before":    "reset_draft",
            "after":     None,
        },
    ]

    def __init__(
        self,
        phone_number: str,
        initial_state: str = OrderState.IDLE.value,
        initial_draft: dict | None = None,
    ):
        self.phone_number = phone_number
        self.state = initial_state
        self.draft = OrderDraft.from_dict(initial_draft or {})
        self.message_callback: Callable[[OutboundMessage], None] | None = None
        self._current_input: Any = None
        self.pending_events: list[dict] = []  # drained by handler layer; used by Phase 4 SAGA

    def process_input(self, user_input: Any, intent: str) -> bool:
        self._current_input = user_input
        for t in self._TRANSITIONS:
            src = t["source"]
            if t["trigger"] == intent and (
                src == self.state or (isinstance(src, list) and self.state in src)
            ):
                return self._execute(t)
        return False

    def reset(self):
        """reset to idle after order placed — called by handler layer."""
        self._execute(next(t for t in self._TRANSITIONS if t["trigger"] == "reset"))

    def _execute(self, t: dict) -> bool:
        if t["condition"] and not getattr(self, t["condition"])():
            return False
        if t["before"]:
            getattr(self, t["before"])()
        self.state = t["dest"]
        if t["after"]:
            getattr(self, t["after"])()
        return True

    def is_valid_fuel_type(self) -> bool:
        return str(self._current_input).lower().strip() in {"diesel", "petrol", "paraffin"}

    def is_valid_quantity(self) -> bool:
        try:
            qty = float(self._current_input)
            return 10.0 <= qty <= 10000.0
        except (ValueError, TypeError):
            return False

    def is_valid_location(self) -> bool:
        return (
            isinstance(self._current_input, dict)
            and self._current_input.get("latitude") is not None
            and self._current_input.get("longitude") is not None
        )

    def save_fuel_type(self):
        self.draft.fuel_type = str(self._current_input).lower().strip()

    def save_quantity(self):
        self.draft.quantity_liters = float(self._current_input)

    def save_location(self):
        self.draft.latitude = self._current_input.get("latitude")
        self.draft.longitude = self._current_input.get("longitude")

    def set_editing(self):
        self.draft.is_editing = True

    def save_fuel_type_clear_edit(self):
        self.save_fuel_type()
        self.draft.is_editing = False

    def save_quantity_clear_edit(self):
        self.save_quantity()
        self.draft.is_editing = False

    def save_location_clear_edit(self):
        self.save_location()
        self.draft.is_editing = False

    def reset_draft(self):
        self.draft = OrderDraft()

    def on_awaiting_fuel_type(self):
        from . import responses
        self._send_message(responses.welcome_message())
        self._send_message(responses.fuel_type_prompt())

    def on_awaiting_quantity(self):
        from . import responses
        self._send_message(responses.quantity_prompt(self.draft.fuel_type))

    def on_awaiting_location(self):
        from . import responses
        self._send_message(responses.location_prompt(self.draft.quantity_liters, self.draft.fuel_type))

    def on_awaiting_edit_field(self):
        from . import responses
        self._send_message(responses.edit_field_prompt())

    def on_awaiting_fuel_type_edit(self):
        from . import responses
        self._send_message(responses.fuel_type_prompt())

    def on_awaiting_confirmation(self):
        from . import responses
        from src.config import get_settings
        address = (
            self.draft.delivery_address
            or (f"GPS: {self.draft.latitude:.4f}, {self.draft.longitude:.4f}"
                if self.draft.latitude else "Unknown")
        )
        settings = get_settings()
        quoted_price = None
        if self.draft.quantity_liters and settings.default_price_per_liter:
            quoted_price = self.draft.quantity_liters * settings.default_price_per_liter
        self._send_message(responses.confirmation_prompt(
            self.draft.fuel_type, self.draft.quantity_liters, address, quoted_price
        ))

    def on_order_placed(self):
        self.pending_events.append({"type": "order_created", "draft": self.draft.to_dict()})

    def on_cancelled(self):
        from . import responses
        self._send_message(responses.cancelled_message())

    def _send_message(self, msg: Any):
        if self.message_callback:
            self.message_callback(msg)

    def to_session_data(self) -> dict:
        return {
            "state": self.state,
            "draft": json.dumps(self.draft.to_dict()),
        }

    @classmethod
    def from_session_data(cls, phone_number: str, data: dict) -> "OrderFlow":
        return cls(
            phone_number=phone_number,
            initial_state=data.get("state", OrderState.IDLE.value),
            initial_draft=json.loads(data.get("draft", "{}")),
        )
