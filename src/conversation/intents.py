"""deterministic intent parser for whatsapp messages.

translates raw user messages into structured intents based on
the current conversation state. uses rule-based pattern matching
for predictability and speed.

design philosophy:
- context-aware: same message means different things in different states
- fail-safe: unrecognized input returns "unknown" rather than guessing
- extensible: add new patterns without breaking existing logic
"""
import re
from dataclasses import dataclass
from typing import Any

from .states import OrderState


@dataclass
class ParsedIntent:
    """result of intent parsing."""
    intent: str               # maps to fsm trigger name (e.g., "fuel_selected")
    value: Any = None         # extracted data (e.g., "diesel", 200.0, {lat, lng})
    confidence: float = 1.0   # for future hybrid ml/rule approach


class IntentParser:
    """
    rule-based intent parser for order conversations.
    
    parses whatsapp messages into intents based on current fsm state.
    uses pattern matching rather than ml for determinism.
    
    usage:
        parser = IntentParser()
        result = parser.parse(message_data, current_state="awaiting_fuel_type")
        # → ParsedIntent(intent="fuel_selected", value="diesel")
    """
    
    # --- keyword sets for pattern matching ---
    
    FUEL_TYPES = {"diesel", "petrol", "paraffin"}
    
    ORDER_TRIGGERS = {
        "order", "fuel", "need fuel", "want fuel", "buy fuel",
        "fill up", "delivery", "i need", "get fuel"
    }
    
    CANCEL_TRIGGERS = {
        "cancel", "stop", "nevermind", "never mind", "abort",
        "quit", "exit", "no thanks", "forget it"
    }
    
    CONFIRM_TRIGGERS = {
        "yes", "yeah", "yep", "confirm", "confirmed", "ok", "okay",
        "correct", "proceed", "do it", "place order", "submit"
    }
    
    HELP_TRIGGERS = {
        "help", "?", "what", "how", "menu", "options", "commands"
    }

    DELIVERY_TRIGGERS = {
        "delivered", "done", "complete", "delivery done", "delivery complete"
    }
    
    # regex for quantity extraction (e.g., "200", "200L", "200 liters")
    QUANTITY_PATTERN = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:l|liters?|litres?)?",
        re.IGNORECASE
    )
    
    def parse(
        self,
        message: dict,
        current_state: str,
    ) -> ParsedIntent:
        """
        parse a whatsapp message into an intent.
        
        args:
            message: whatsapp message object with 'type' and content
            current_state: current fsm state (determines interpretation)
        
        returns:
            ParsedIntent with intent name and extracted value
        """
        msg_type = message.get("type", "text")
        
        # dispatch based on message type
        if msg_type == "text":
            text = message.get("text", {}).get("body", "").strip()
            return self._parse_text(text, current_state)
        
        elif msg_type == "location":
            location = message.get("location", {})
            return self._parse_location(location, current_state)
        
        elif msg_type == "interactive":
            interactive = message.get("interactive", {})
            return self._parse_interactive(interactive, current_state)
        
        # unsupported message type
        return ParsedIntent(intent="unknown")
    
    def _parse_text(self, text: str, current_state: str) -> ParsedIntent:
        """parse plain text message based on current state."""
        text_lower = text.lower().strip()
        
        # --- global intents (work in any state) ---
        
        # cancel always works (except in idle or order_placed)
        if self._matches_any(text_lower, self.CANCEL_TRIGGERS):
            if current_state not in (OrderState.IDLE.value, OrderState.ORDER_PLACED.value):
                return ParsedIntent(intent="cancel")
        
        # help always works
        if self._matches_any(text_lower, self.HELP_TRIGGERS):
            return ParsedIntent(intent="help")
        
        # --- state-specific parsing ---
        
        if current_state == OrderState.IDLE.value:
            return self._parse_idle(text_lower)
        
        elif current_state == OrderState.AWAITING_FUEL_TYPE.value:
            return self._parse_fuel_type(text_lower)
        
        elif current_state == OrderState.AWAITING_QUANTITY.value:
            return self._parse_quantity(text_lower)
        
        elif current_state == OrderState.AWAITING_LOCATION.value:
            return self._parse_location_text(text_lower)
        
        elif current_state == OrderState.AWAITING_CONFIRMATION.value:
            return self._parse_confirmation(text_lower)
        
        elif current_state == OrderState.ORDER_PLACED.value:
            return self._parse_idle(text_lower)

        elif current_state == "on_delivery":
            return self._parse_delivery_confirmation(text_lower)

        return ParsedIntent(intent="unknown")
    
    def _parse_idle(self, text: str) -> ParsedIntent:
        return ParsedIntent(intent="start_order")
    
    def _parse_fuel_type(self, text: str) -> ParsedIntent:
        """parse fuel type selection."""
        for fuel in self.FUEL_TYPES:
            if fuel in text:
                return ParsedIntent(intent="fuel_selected", value=fuel)
        
        # didn't recognize fuel type
        return ParsedIntent(intent="invalid_fuel_type")
    
    def _parse_quantity(self, text: str) -> ParsedIntent:
        """parse quantity input."""
        match = self.QUANTITY_PATTERN.search(text)
        if match:
            try:
                quantity = float(match.group(1))
                # validate business rules
                if 10.0 <= quantity <= 10000.0:
                    return ParsedIntent(intent="quantity_provided", value=quantity)
                else:
                    return ParsedIntent(intent="invalid_quantity_range")
            except ValueError:
                pass
        
        return ParsedIntent(intent="invalid_quantity")
    
    def _parse_delivery_confirmation(self, text: str) -> ParsedIntent:
        if self._matches_any(text, self.DELIVERY_TRIGGERS):
            return ParsedIntent(intent="delivery_confirmed")
        return ParsedIntent(intent="unknown")

    def _parse_location_text(self, text: str) -> ParsedIntent:
        """parse text-based location (address)."""
        # for mvp, accept any non-empty text as location
        # production would validate/geocode
        if len(text) >= 5:  # minimum reasonable address length
            return ParsedIntent(intent="location_provided", value=text)
        
        return ParsedIntent(intent="invalid_location")
    
    def _parse_confirmation(self, text: str) -> ParsedIntent:
        """parse confirmation response."""
        if self._matches_any(text, self.CONFIRM_TRIGGERS):
            return ParsedIntent(intent="confirm_order")
        
        if self._matches_any(text, self.CANCEL_TRIGGERS):
            return ParsedIntent(intent="cancel")
        
        return ParsedIntent(intent="invalid_confirmation")
    
    def _parse_location(self, location: dict, current_state: str) -> ParsedIntent:
        """parse whatsapp location message."""
        lat = location.get("latitude")
        lng = location.get("longitude")
        
        if lat is not None and lng is not None:
            if current_state == OrderState.AWAITING_LOCATION.value:
                return ParsedIntent(
                    intent="location_provided",
                    value={"latitude": lat, "longitude": lng}
                )
            elif current_state == "on_delivery":
                return ParsedIntent(
                    intent="location_provided",
                    value={"latitude": lat, "longitude": lng}
                )
            elif current_state in (OrderState.IDLE.value, OrderState.ORDER_PLACED.value):
                return ParsedIntent(intent="start_order")
        
        return ParsedIntent(intent="unknown")
    
    def _parse_interactive(self, interactive: dict, current_state: str) -> ParsedIntent:
        """parse interactive message (button/list replies)."""
        # button reply
        if "button_reply" in interactive:
            button_id = interactive["button_reply"].get("id", "")
            return self._parse_button_id(button_id, current_state)
        
        # list reply
        if "list_reply" in interactive:
            list_id = interactive["list_reply"].get("id", "")
            return self._parse_button_id(list_id, current_state)
        
        return ParsedIntent(intent="unknown")
    
    def _parse_button_id(self, button_id: str, current_state: str) -> ParsedIntent:
        """parse button/list selection by id."""
        button_id = button_id.lower()
        
        # fuel selection buttons
        if button_id in ("fuel_diesel", "diesel"):
            return ParsedIntent(intent="fuel_selected", value="diesel")
        if button_id in ("fuel_petrol", "petrol"):
            return ParsedIntent(intent="fuel_selected", value="petrol")
        if button_id in ("fuel_paraffin", "paraffin"):
            return ParsedIntent(intent="fuel_selected", value="paraffin")
        
        # confirmation buttons
        if button_id in ("confirm_yes", "yes", "confirm"):
            return ParsedIntent(intent="confirm_order")
        if button_id in ("confirm_no", "no", "cancel"):
            return ParsedIntent(intent="cancel")
        
        # order start
        if button_id in ("start_order", "order", "new_order"):
            return ParsedIntent(intent="start_order")

        if button_id == "job_accept":
            return ParsedIntent(intent="accept_job")
        if button_id == "job_decline":
            return ParsedIntent(intent="decline_job")

        if button_id == "delivery_override_yes":
            return ParsedIntent(intent="delivery_confirmed")
        if button_id == "delivery_override_no":
            return ParsedIntent(intent="delivery_override_cancel")

        return ParsedIntent(intent="unknown")
    
    def _matches_any(self, text: str, keywords: set) -> bool:
        """check if text matches any keyword (exact or contains)."""
        # exact match
        if text in keywords:
            return True
        
        # check if any keyword is contained in text
        for keyword in keywords:
            if keyword in text:
                return True
        
        return False